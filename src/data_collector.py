import requests
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
import json
from config import Config
from database import BalloonDatabase

# Using only ADSB Exchange APIs

class DataCollector:
    _instance = None
    _initialized = False
    
    def __new__(cls, database: BalloonDatabase = None):
        if cls._instance is None:
            cls._instance = super(DataCollector, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, database: BalloonDatabase = None):
        if self._initialized:
            return
        self._initialized = True
        
        if database is None:
            raise ValueError("Database must be provided for first DataCollector initialization")
        self.db = database
        # ADSB Exchange only
        self.fallback_client = None
        self.real_adsb_client = None
        self.running = False
        self.collection_thread = None
        self.tracked_icao_list = []
        
        # Initialize ADSB Exchange client for balloon tracking
        try:
            from real_adsb_client import BalloonSpecificADSBClient
            self.real_adsb_client = BalloonSpecificADSBClient()
            print("ADSB Exchange client initialized for balloon tracking")
        except ImportError:
            print("ADSB Exchange client not available")
        
        # Initialize fallback client
        try:
            from alternative_data_source import FallbackDataCollector
            self.fallback_client = FallbackDataCollector()
            print("Fallback data sources initialized")
        except ImportError:
            print("Fallback data sources not available")
    
    @classmethod
    def get_instance(cls):
        """Get the singleton instance"""
        if cls._instance is None:
            raise RuntimeError("DataCollector not initialized. Call DataCollector(database) first.")
        return cls._instance
        
    def add_tracked_aircraft(self, icao24: str, callsign: str = None, description: str = None):
        """Add aircraft to tracking list and start session"""
        icao24 = icao24.lower()  # Normalize to lowercase
        self.db.add_tracked_aircraft(icao24, callsign, description)
        self.db.start_tracking_session(icao24)  # Start new session
        if icao24 not in self.tracked_icao_list:
            self.tracked_icao_list.append(icao24)
        print(f"Added {icao24} to tracking list")
    
    def remove_tracked_aircraft(self, icao24: str):
        """Remove aircraft from tracking list"""
        icao24 = icao24.lower()
        if icao24 in self.tracked_icao_list:
            self.tracked_icao_list.remove(icao24)
        print(f"Removed {icao24} from tracking list")
    
    def start_collection(self):
        """Start data collection in background thread"""
        if self.running:
            print("Data collection already running")
            return
            
        self.running = True
        self.collection_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.collection_thread.start()
        print("Started data collection")
    
    def stop_collection(self):
        """Stop data collection"""
        self.running = False
        if self.collection_thread:
            self.collection_thread.join(timeout=5)
        print("Stopped data collection")
    
    def cleanup(self):
        """Clean up resources and prevent memory leaks"""
        self.stop_collection()
        self.tracked_icao_list.clear()
        
        # Close any open client connections
        if hasattr(self.real_adsb_client, 'cleanup'):
            self.real_adsb_client.cleanup()
        if hasattr(self.fallback_client, 'cleanup'):
            self.fallback_client.cleanup()
            
        print("DataCollector cleaned up")
    
    def _cleanup_memory(self):
        """Periodic memory cleanup to prevent leaks"""
        import gc
        
        # Force garbage collection
        collected = gc.collect()
        if collected > 0:
            print(f"Memory cleanup: collected {collected} objects")
        
        # Clear any inactive tracking entries
        inactive_icaos = []
        for icao in self.tracked_icao_list:
            latest_data = self.db.get_latest_data(icao)
            if latest_data:
                # Check if data is older than 30 minutes
                last_seen = latest_data.get('timestamp', 0)
                if time.time() - last_seen > 1800:  # 30 minutes
                    inactive_icaos.append(icao)
        
        for icao in inactive_icaos:
            print(f"Removing inactive aircraft {icao.upper()} from tracking list")
            self.tracked_icao_list.remove(icao)
    
    def _collection_loop(self):
        """Main data collection loop"""
        while self.running:
            try:
                # Load tracked aircraft from database
                tracked_aircraft = self.db.get_tracked_aircraft()
                current_icao_list = [aircraft['icao24'] for aircraft in tracked_aircraft]
                
                # Update local tracking list
                self.tracked_icao_list = current_icao_list
                
                if not self.tracked_icao_list:
                    print("No aircraft being tracked, sleeping...")
                    time.sleep(Config.UPDATE_INTERVAL)
                    continue
                
                # Collect data for each tracked aircraft
                for icao24 in self.tracked_icao_list:
                    if not self.running:
                        break
                        
                    aircraft_data = None
                    
                    # For real balloons, try ADSB Exchange client first
                    if icao24.lower() in Config.TRACKED_BALLOONS and self.real_adsb_client:
                        try:
                            print(f"Trying ADSB Exchange for balloon {icao24.upper()}...")
                            aircraft_data = self.real_adsb_client.get_aircraft_by_icao(icao24)
                            if aircraft_data:
                                print(f"Retrieved data for balloon {icao24.upper()}")
                            else:
                                print(f"No data found for balloon {icao24.upper()} from ADSB Exchange")
                        except Exception as e:
                            print(f"ADSB Exchange client error for {icao24}: {e}")
                    
                    # Only try fallback for real APIs (no mock data in production)
                    if not aircraft_data and self.fallback_client:
                        try:
                            # Only use fallback if it has real API sources configured
                            aircraft_data = self.fallback_client.get_aircraft_by_icao(icao24)
                            if aircraft_data:
                                print(f"Using fallback data source for {icao24}: {aircraft_data.get('data_source', 'unknown')}")
                        except Exception as e:
                            print(f"Fallback data source error for {icao24}: {e}")
                    
                    if not aircraft_data:
                        print(f"No real ADSB data found for {icao24.upper()} from any source!")
                    
                    if aircraft_data:
                        # Store in database
                        success = self.db.add_aircraft_data(aircraft_data)
                        if success:
                            self.db.update_aircraft_last_seen(icao24)
                            alt = aircraft_data.get('baro_altitude', 'Unknown')
                            source = aircraft_data.get('data_source', 'Unknown')
                            print(f"Updated data for {icao24}: Alt={alt}m (Source: {source})")
                        else:
                            print(f"Failed to store data for {icao24}")
                    else:
                        print(f"No data available for {icao24} from any source")
                
                # Clean up old data and memory periodically
                if time.time() % (Config.CLEANUP_INTERVAL_MINUTES * 60) < Config.UPDATE_INTERVAL:
                    self.db.cleanup_old_data()
                    self._cleanup_memory()
                
                time.sleep(Config.UPDATE_INTERVAL)
                
            except Exception as e:
                print(f"Error in collection loop: {e}")
                time.sleep(Config.UPDATE_INTERVAL)
    
