"""
Real ADSB API client using only ADSB Exchange
"""
import requests
import time
import json
from datetime import datetime
from typing import Dict, List, Optional
import random


class ADSBExchangeOnlyClient:
    """ADSB client that uses only ADSB Exchange APIs"""
    
    def __init__(self):
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Half second between requests
    
    def _rate_limit(self):
        """Rate limiting to be respectful to APIs"""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Get aircraft data using only ADSB Exchange paid API"""
        from paid_adsb_client import ADSBExchangeRapidAPIClient
        
        try:
            self._rate_limit()
            client = ADSBExchangeRapidAPIClient()
            return client.get_aircraft_by_icao(icao24)
        except Exception as e:
            print(f"ADSB Exchange API error for {icao24}: {e}")
            return None
    
    def get_aircraft_in_region(self, lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> List[Dict]:
        """Get all aircraft in a region using ADSB Exchange"""
        from paid_adsb_client import ADSBExchangeRapidAPIClient
        
        try:
            self._rate_limit()
            client = ADSBExchangeRapidAPIClient()
            return client.get_aircraft_in_region(lat_min, lat_max, lon_min, lon_max)
        except Exception as e:
            print(f"ADSB Exchange regional search error: {e}")
            return []


class BalloonSpecificADSBClient:
    """Specialized client for balloon tracking using only ADSB Exchange"""
    
    def __init__(self):
        self.adsb_client = ADSBExchangeOnlyClient()
        self.paid_client = None
        
        # Initialize ADSB Exchange paid API
        try:
            from paid_adsb_client import PaidADSBClient
            self.paid_client = PaidADSBClient()
            if self.paid_client.clients:
                print("✅ Paid ADSB APIs available for balloon tracking")
            else:
                print("💡 No paid APIs configured - ADSB Exchange API key required")
        except ImportError:
            print("❌ Paid ADSB client not available")
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Get balloon data using ADSB Exchange only"""
        
        # Try direct ICAO search with ADSB Exchange
        if self.paid_client and self.paid_client.clients:
            print(f"🔄 Trying ADSB Exchange for balloon {icao24.upper()}...")
            
            # Try direct ICAO search
            result = self.paid_client.get_aircraft_by_icao(icao24)
            if result:
                print(f"✅ Found balloon {icao24.upper()} via ADSB Exchange")
                return result
            
            # Try regional search for balloons
            result = self.paid_client.find_balloon_in_region(icao24)
            if result:
                print(f"✅ Found balloon {icao24.upper()} via regional search")
                return result
        
        # Fallback to basic ADSB Exchange client
        result = self.adsb_client.get_aircraft_by_icao(icao24)
        if result:
            return result
        
        print(f"No data found for balloon {icao24.upper()} - balloon may not be transmitting")
        return None
    
    def find_balloons_in_region(self, lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> List[Dict]:
        """Find all balloons in a region using ADSB Exchange"""
        if not self.paid_client or not self.paid_client.clients:
            print("❌ Regional balloon search requires ADSB Exchange API access")
            return []
        
        try:
            # Get all aircraft in the region
            all_aircraft = self.adsb_client.get_aircraft_in_region(lat_min, lat_max, lon_min, lon_max)
            
            # Filter for balloon-like aircraft
            balloons = []
            for aircraft in all_aircraft:
                if self._is_likely_balloon(aircraft):
                    balloons.append(aircraft)
            
            print(f"Found {len(balloons)} potential balloons in region")
            return balloons
            
        except Exception as e:
            print(f"❌ Regional balloon search failed: {e}")
            return []
    
    def _is_likely_balloon(self, aircraft: Dict) -> bool:
        """Determine if aircraft is likely a balloon based on characteristics"""
        try:
            # Check altitude (balloons typically fly high)
            altitude = aircraft.get('altitude', 0) or 0
            if altitude < 15000:  # Below 15,000m typically not high-altitude balloons
                return False
            
            # Check speed (balloons are slow)
            velocity = aircraft.get('velocity', 0) or 0
            if velocity > 100:  # Above 100 m/s unlikely for balloons
                return False
            
            # Check aircraft category if available
            category = aircraft.get('category', '')
            if category == 'B2':  # B2 is balloon category in ADSB
                return True
            
            # Check registration for balloon patterns (if available)
            registration = aircraft.get('registration', '')
            if registration and ('HBAL' in registration.upper() or 'BAL' in registration.upper()):
                return True
            
            # Check callsign for balloon patterns
            callsign = aircraft.get('callsign', '')
            if callsign and ('HBAL' in callsign.upper() or 'BAL' in callsign.upper()):
                return True
            
            # High altitude + slow speed = likely balloon
            if altitude > 20000 and velocity < 50:
                return True
            
            return False
            
        except Exception:
            return False