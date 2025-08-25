import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json
from config import Config

class BalloonDatabase:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.ensure_directory()
        self.init_database()
    
    def ensure_directory(self):
        """Ensure the database directory exists"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    def init_database(self):
        """Initialize database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Aircraft tracking data table  
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS aircraft_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    icao24 TEXT NOT NULL,
                    callsign TEXT,
                    timestamp REAL NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    altitude REAL,
                    velocity REAL,
                    heading REAL,
                    vertical_rate REAL,
                    on_ground BOOLEAN,
                    last_contact REAL,
                    geo_altitude REAL,
                    squawk TEXT,
                    position_source INTEGER,
                    data_source TEXT,
                    registration TEXT,
                    category TEXT,
                    emergency TEXT,
                    geom_rate REAL,
                    nic INTEGER,
                    nac_p INTEGER,
                    nac_v INTEGER,
                    sil INTEGER,
                    gva INTEGER,
                    sda INTEGER,
                    messages INTEGER,
                    rssi REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Wind data calculated from aircraft movement
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS wind_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    icao24 TEXT NOT NULL,
                    altitude_bin INTEGER NOT NULL,
                    wind_speed REAL,
                    wind_direction REAL,
                    sample_count INTEGER,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tracked aircraft configuration
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tracked_aircraft (
                    icao24 TEXT PRIMARY KEY,
                    callsign TEXT,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen DATETIME,
                    session_start_time REAL
                )
            ''')
            
            # Session tracking for filtering data
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tracking_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    icao24 TEXT,
                    session_start_time REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_aircraft_data_icao24_timestamp ON aircraft_data(icao24, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_wind_data_icao24_altitude ON wind_data(icao24, altitude_bin)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_aircraft_data_timestamp ON aircraft_data(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_aircraft_data_icao24_desc ON aircraft_data(icao24 DESC, timestamp DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracked_aircraft_active ON tracked_aircraft(is_active, last_seen)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_aircraft_data_lat_lon ON aircraft_data(latitude, longitude)')
            
            # Optimize SQLite settings for performance
            cursor.execute('PRAGMA journal_mode = WAL')  # Write-Ahead Logging
            cursor.execute('PRAGMA synchronous = NORMAL')  # Balance safety vs performance
            cursor.execute('PRAGMA cache_size = 10000')  # 10MB cache
            cursor.execute('PRAGMA temp_store = memory')  # Use memory for temp tables
            cursor.execute('PRAGMA mmap_size = 268435456')  # 256MB memory mapping
            
            conn.commit()
    
    def add_aircraft_data(self, aircraft_data: Dict) -> bool:
        """Add aircraft tracking data to database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO aircraft_data 
                    (icao24, callsign, timestamp, latitude, longitude, altitude, 
                     velocity, heading, vertical_rate, on_ground, last_contact,
                     geo_altitude, squawk, position_source, data_source,
                     registration, category, emergency, geom_rate, nic, nac_p, nac_v,
                     sil, gva, sda, messages, rssi)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    aircraft_data.get('icao24'),
                    aircraft_data.get('callsign'),
                    aircraft_data.get('time_position'),
                    aircraft_data.get('latitude'),
                    aircraft_data.get('longitude'),
                    aircraft_data.get('altitude'),  # Use database-consistent 'altitude' field
                    aircraft_data.get('velocity'),
                    aircraft_data.get('track'),
                    aircraft_data.get('vertical_rate'),
                    aircraft_data.get('on_ground'),
                    aircraft_data.get('last_contact'),
                    aircraft_data.get('geo_altitude'),
                    aircraft_data.get('squawk'),
                    aircraft_data.get('position_source'),
                    aircraft_data.get('data_source'),
                    aircraft_data.get('registration'),
                    aircraft_data.get('category'),
                    aircraft_data.get('emergency'),
                    aircraft_data.get('geom_rate'),
                    aircraft_data.get('nic'),
                    aircraft_data.get('nac_p'),
                    aircraft_data.get('nac_v'),
                    aircraft_data.get('sil'),
                    aircraft_data.get('gva'),
                    aircraft_data.get('sda'),
                    aircraft_data.get('messages'),
                    aircraft_data.get('rssi')
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error adding aircraft data: {e}")
            return False
    
    def get_aircraft_data(self, icao24: str, hours_back: int = 24) -> List[Dict]:
        """Get aircraft data for specified time period"""
        cutoff_time = datetime.now().timestamp() - (hours_back * 3600)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM aircraft_data 
                WHERE icao24 = ? AND timestamp > ?
                ORDER BY timestamp
            ''', (icao24, cutoff_time))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_aircraft_data_since_session(self, icao24: str) -> List[Dict]:
        """Get aircraft data only since the current tracking session started"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get session start time for this aircraft
            cursor.execute('''
                SELECT session_start_time FROM tracked_aircraft 
                WHERE icao24 = ?
            ''', (icao24,))
            
            result = cursor.fetchone()
            if not result or not result[0]:
                # No session start time recorded, return empty
                return []
            
            session_start = result[0]
            
            cursor.execute('''
                SELECT * FROM aircraft_data 
                WHERE icao24 = ? AND timestamp >= ?
                ORDER BY timestamp
            ''', (icao24, session_start))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def start_tracking_session(self, icao24: str):
        """Mark the start of a new tracking session"""
        session_start = datetime.now().timestamp()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Update tracked aircraft with session start time
            cursor.execute('''
                UPDATE tracked_aircraft 
                SET session_start_time = ?
                WHERE icao24 = ?
            ''', (session_start, icao24))
            
            # Also record in sessions table
            cursor.execute('''
                INSERT INTO tracking_sessions (icao24, session_start_time)
                VALUES (?, ?)
            ''', (icao24, session_start))
            
            conn.commit()
            print(f"Started tracking session for {icao24.upper()} at {datetime.fromtimestamp(session_start)}")
    
    def add_wind_data(self, icao24: str, altitude_bin: int, wind_speed: float, 
                     wind_direction: float, sample_count: int) -> bool:
        """Add calculated wind data"""
        try:
            timestamp = datetime.now().timestamp()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO wind_data 
                    (icao24, altitude_bin, wind_speed, wind_direction, sample_count, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (icao24, altitude_bin, wind_speed, wind_direction, sample_count, timestamp))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error adding wind data: {e}")
            return False
    
    def get_wind_data(self, icao24: str, hours_back: int = 24) -> List[Dict]:
        """Get wind data for specified aircraft"""
        cutoff_time = datetime.now().timestamp() - (hours_back * 3600)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM wind_data 
                WHERE icao24 = ? AND timestamp > ?
                ORDER BY altitude_bin
            ''', (icao24, cutoff_time))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def add_tracked_aircraft(self, icao24: str, callsign: str = None, description: str = None) -> bool:
        """Add aircraft to tracking list"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO tracked_aircraft 
                    (icao24, callsign, description, is_active, last_seen)
                    VALUES (?, ?, ?, TRUE, CURRENT_TIMESTAMP)
                ''', (icao24, callsign, description))
                conn.commit()
                return True
        except Exception as e:
            print(f"Error adding tracked aircraft: {e}")
            return False
    
    def get_tracked_aircraft(self) -> List[Dict]:
        """Get list of tracked aircraft"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM tracked_aircraft 
                WHERE is_active = TRUE
                ORDER BY last_seen DESC
            ''')
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def update_aircraft_last_seen(self, icao24: str):
        """Update last seen timestamp for tracked aircraft"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tracked_aircraft 
                SET last_seen = CURRENT_TIMESTAMP 
                WHERE icao24 = ?
            ''', (icao24,))
            conn.commit()
    
    def cleanup_old_data(self):
        """Remove old data based on retention policy"""
        cutoff_time = datetime.now() - timedelta(hours=Config.MAX_DATA_AGE_HOURS)
        cutoff_timestamp = cutoff_time.timestamp()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Clean up old aircraft data
            cursor.execute('DELETE FROM aircraft_data WHERE timestamp < ?', (cutoff_timestamp,))
            aircraft_deleted = cursor.rowcount
            
            # Clean up old wind data
            cursor.execute('DELETE FROM wind_data WHERE timestamp < ?', (cutoff_timestamp,))
            wind_deleted = cursor.rowcount
            
            # Clean up old tracking sessions
            cursor.execute('DELETE FROM tracking_sessions WHERE session_start_time < ?', (cutoff_timestamp,))
            sessions_deleted = cursor.rowcount
            
            # Optimize database after cleanup
            cursor.execute('VACUUM')
            cursor.execute('ANALYZE')
            
            conn.commit()
            
            if aircraft_deleted > 0 or wind_deleted > 0 or sessions_deleted > 0:
                print(f"Cleaned up {aircraft_deleted} aircraft records, {wind_deleted} wind records, {sessions_deleted} sessions")
    
    def get_latest_data(self, icao24: str) -> Optional[Dict]:
        """Get most recent data point for an aircraft"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM aircraft_data 
                WHERE icao24 = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''', (icao24,))
            
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
    
    def add_aircraft_data_batch(self, aircraft_data_list: List[Dict]) -> int:
        """Add multiple aircraft data records in a batch for better performance"""
        if not aircraft_data_list:
            return 0
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Prepare batch data
                batch_data = []
                for aircraft_data in aircraft_data_list:
                    batch_data.append((
                        aircraft_data.get('icao24'),
                        aircraft_data.get('callsign'),
                        aircraft_data.get('time_position'),
                        aircraft_data.get('latitude'),
                        aircraft_data.get('longitude'),
                        aircraft_data.get('altitude'),
                        aircraft_data.get('velocity'),
                        aircraft_data.get('track'),
                        aircraft_data.get('vertical_rate'),
                        aircraft_data.get('on_ground'),
                        aircraft_data.get('last_contact'),
                        aircraft_data.get('geo_altitude'),
                        aircraft_data.get('squawk'),
                        aircraft_data.get('position_source'),
                        aircraft_data.get('data_source'),
                        aircraft_data.get('registration'),
                        aircraft_data.get('category'),
                        aircraft_data.get('emergency'),
                        aircraft_data.get('geom_rate'),
                        aircraft_data.get('nic'),
                        aircraft_data.get('nac_p'),
                        aircraft_data.get('nac_v'),
                        aircraft_data.get('sil'),
                        aircraft_data.get('gva'),
                        aircraft_data.get('sda'),
                        aircraft_data.get('messages'),
                        aircraft_data.get('rssi')
                    ))
                
                cursor.executemany('''
                    INSERT INTO aircraft_data 
                    (icao24, callsign, timestamp, latitude, longitude, altitude, 
                     velocity, heading, vertical_rate, on_ground, last_contact,
                     geo_altitude, squawk, position_source, data_source,
                     registration, category, emergency, geom_rate, nic, nac_p, nac_v,
                     sil, gva, sda, messages, rssi)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', batch_data)
                
                conn.commit()
                return len(batch_data)
        except Exception as e:
            print(f"Error adding batch aircraft data: {e}")
            return 0