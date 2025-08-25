import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from geopy.distance import geodesic
import math
from config import Config
from database import BalloonDatabase

class WindCalculator:
    def __init__(self, database: BalloonDatabase):
        self.db = database
        self.altitude_bin_size = Config.ALTITUDE_BIN_SIZE
        self.min_samples = Config.MIN_SAMPLES_PER_BIN
        self.smoothing_window = Config.SMOOTHING_WINDOW
    
    def calculate_wind_from_trajectory(self, icao24: str, hours_back: int = 1) -> Dict[int, Dict]:
        """
        Calculate wind speed and direction from balloon GPS trajectory
        
        Returns:
            Dict with altitude bins as keys and wind data as values
            {altitude_bin: {'wind_speed': float, 'wind_direction': float, 'sample_count': int}}
        """
        # Get recent aircraft data
        aircraft_data = self.db.get_aircraft_data(icao24, hours_back)
        
        if len(aircraft_data) < 2:
            print(f"Insufficient data points for wind calculation: {len(aircraft_data)}")
            return {}
        
        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(aircraft_data)
        
        # Filter out invalid positions
        df = df.dropna(subset=['latitude', 'longitude', 'altitude', 'timestamp'])
        df = df[df['latitude'] != 0]
        df = df[df['longitude'] != 0]
        df = df[df['altitude'] > 0]
        
        if len(df) < 2:
            print("Insufficient valid data points after filtering")
            return {}
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Calculate movement vectors between consecutive points
        wind_vectors = []
        
        for i in range(1, len(df)):
            prev_point = df.iloc[i-1]
            curr_point = df.iloc[i]
            
            # Calculate time difference
            dt = curr_point['timestamp'] - prev_point['timestamp']
            
            if dt <= 0 or dt > 300:  # Skip if time difference is invalid or too large (5 min)
                continue
            
            # Calculate horizontal movement
            prev_pos = (prev_point['latitude'], prev_point['longitude'])
            curr_pos = (curr_point['latitude'], curr_point['longitude'])
            
            # Distance in meters
            distance = geodesic(prev_pos, curr_pos).meters
            
            # Calculate bearing (wind direction)
            bearing = self._calculate_bearing(prev_pos, curr_pos)
            
            # Calculate horizontal speed (wind speed)
            horizontal_speed = distance / dt  # m/s
            
            # Average altitude for this segment
            avg_altitude = (prev_point['altitude'] + curr_point['altitude']) / 2
            
            if avg_altitude > 0:  # Valid altitude
                wind_vectors.append({
                    'altitude': avg_altitude,
                    'wind_speed': horizontal_speed,
                    'wind_direction': bearing,
                    'dt': dt,
                    'distance': distance
                })
        
        if not wind_vectors:
            print("No valid wind vectors calculated")
            return {}
        
        # Group by altitude bins and calculate average wind
        wind_by_altitude = self._bin_wind_data(wind_vectors)
        
        # Store calculated wind data in database
        for altitude_bin, wind_data in wind_by_altitude.items():
            self.db.add_wind_data(
                icao24,
                altitude_bin,
                wind_data['wind_speed'],
                wind_data['wind_direction'],
                wind_data['sample_count']
            )
        
        return wind_by_altitude
    
    def _calculate_bearing(self, point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """
        Calculate bearing from point1 to point2 in degrees (0-360)
        """
        lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
        lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])
        
        dlon = lon2 - lon1
        
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        
        bearing = math.atan2(y, x)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360
        
        return bearing
    
    def _bin_wind_data(self, wind_vectors: List[Dict]) -> Dict[int, Dict]:
        """
        Group wind vectors by altitude bins and calculate statistics
        """
        # Create DataFrame from wind vectors
        df = pd.DataFrame(wind_vectors)
        
        # Create altitude bins
        df['altitude_bin'] = (df['altitude'] // self.altitude_bin_size) * self.altitude_bin_size
        
        wind_by_altitude = {}
        
        for altitude_bin in df['altitude_bin'].unique():
            bin_data = df[df['altitude_bin'] == altitude_bin]
            
            if len(bin_data) < self.min_samples:
                continue
            
            # Calculate vector average for wind direction
            # Convert wind directions to vectors, average them, then convert back
            wind_speeds = bin_data['wind_speed'].values
            wind_directions = bin_data['wind_direction'].values
            
            # Convert to vector components
            u_components = wind_speeds * np.sin(np.radians(wind_directions))
            v_components = wind_speeds * np.cos(np.radians(wind_directions))
            
            # Average the components
            avg_u = np.mean(u_components)
            avg_v = np.mean(v_components)
            
            # Convert back to speed and direction
            avg_wind_speed = np.sqrt(avg_u**2 + avg_v**2)
            avg_wind_direction = np.degrees(np.arctan2(avg_u, avg_v))
            avg_wind_direction = (avg_wind_direction + 360) % 360
            
            wind_by_altitude[int(altitude_bin)] = {
                'wind_speed': float(avg_wind_speed),
                'wind_direction': float(avg_wind_direction),
                'sample_count': len(bin_data),
                'wind_speed_std': float(np.std(wind_speeds)),
                'wind_direction_std': float(np.std(wind_directions))
            }
        
        return wind_by_altitude
    
    def get_wind_profile(self, icao24: str, hours_back: int = 6) -> Dict:
        """
        Get wind profile (wind vs altitude) for an aircraft
        """
        wind_data = self.db.get_wind_data(icao24, hours_back)
        
        if not wind_data:
            return {}
        
        # Convert to more usable format
        profile = {}
        for record in wind_data:
            altitude_bin = record['altitude_bin']
            profile[altitude_bin] = {
                'wind_speed': record['wind_speed'],
                'wind_direction': record['wind_direction'],
                'sample_count': record['sample_count'],
                'timestamp': record['timestamp']
            }
        
        return profile
    
    def calculate_wind_profile(self, icao24: str, altitude_source: str = 'altitude', 
                             time_filter_seconds: Optional[int] = None, 
                             distance_filter_km: Optional[float] = None,
                             reference_icao: Optional[str] = None,
                             include_historical_hours: Optional[int] = None) -> List[Dict]:
        """
        Calculate wind profile with optional time and distance filtering
        If reference_icao is provided, distance filtering uses that balloon's current position
        """
        from datetime import datetime
        
        # Get aircraft data - either session data or historical data based on parameter
        if include_historical_hours is not None:
            # Load historical data when explicitly requested
            aircraft_data = self.db.get_aircraft_data(icao24, hours_back=include_historical_hours)
        else:
            # Default: only show data since current tracking session started
            aircraft_data = self.db.get_aircraft_data_since_session(icao24)
        
        if len(aircraft_data) < 2:
            return []
        
        # Apply time filter if specified
        if time_filter_seconds is not None and time_filter_seconds > 0:
            cutoff_time = datetime.now().timestamp() - time_filter_seconds
            aircraft_data = [d for d in aircraft_data if d['timestamp'] >= cutoff_time]
        
        # Get reference position for distance filtering
        reference_position = None
        if distance_filter_km is not None and distance_filter_km > 0 and reference_icao:
            # Only apply distance filtering if we have both a distance value AND a reference balloon
            ref_data = self.db.get_aircraft_data_since_session(reference_icao)
            if ref_data:
                latest_ref = max(ref_data, key=lambda x: x['timestamp'])
                if latest_ref['latitude'] and latest_ref['longitude']:
                    reference_position = (latest_ref['latitude'], latest_ref['longitude'])
        
        # Apply distance filter ONLY if we have both reference position AND distance filter
        if reference_position and distance_filter_km and distance_filter_km > 0:
            filtered_data = []
            for point in aircraft_data:
                if point['latitude'] and point['longitude']:
                    distance = geodesic(reference_position, (point['latitude'], point['longitude'])).kilometers
                    if distance <= distance_filter_km:
                        filtered_data.append(point)
            aircraft_data = filtered_data
        
        if len(aircraft_data) < 2:
            return []
        
        # Calculate wind vectors from GPS trajectory
        wind_vectors = []
        df = pd.DataFrame(aircraft_data)
        
        # Use the selected altitude source, fallback to barometric if geo not available
        if altitude_source == 'geo_altitude' and 'geo_altitude' in df.columns:
            altitude_col = 'geo_altitude'
        else:
            altitude_col = 'altitude'
        
        # Remove invalid data
        df = df.dropna(subset=['latitude', 'longitude', altitude_col, 'timestamp'])
        df = df[df['latitude'] != 0]
        df = df[df['longitude'] != 0] 
        df = df[df[altitude_col] > 0]
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        if len(df) < 2:
            return []
        
        # Calculate wind vectors between consecutive points
        for i in range(1, len(df)):
            prev_point = df.iloc[i-1]
            curr_point = df.iloc[i]
            
            time_diff = curr_point['timestamp'] - prev_point['timestamp']
            if time_diff <= 0:
                continue
            
            # Calculate distance and bearing
            distance = geodesic(
                (prev_point['latitude'], prev_point['longitude']),
                (curr_point['latitude'], curr_point['longitude'])
            ).kilometers
            
            bearing = self._calculate_bearing(
                (prev_point['latitude'], prev_point['longitude']),
                (curr_point['latitude'], curr_point['longitude'])
            )
            
            # Calculate ground speed
            ground_speed = distance / (time_diff / 3600)  # km/h
            
            # Convert to wind direction (opposite of ground track)
            wind_direction = (bearing + 180) % 360
            
            wind_vectors.append({
                'altitude': curr_point[altitude_col],
                'wind_speed': ground_speed,
                'wind_direction': wind_direction,
                'timestamp': curr_point['timestamp']
            })
        
        # Return individual wind vectors instead of binned/averaged data
        # This ensures ALL wind calculations are plotted, not just averaged bins
        if not wind_vectors:
            return []
        
        result = []
        for vector in wind_vectors:
            result.append({
                'altitude_bin': float(vector['altitude']),  # Use actual altitude, not binned
                'wind_speed': float(vector['wind_speed']),
                'wind_direction': float(vector['wind_direction']),
                'sample_count': 1,  # Each point is individual
                'timestamp': vector['timestamp']
            })
        
        return result
    
    def calculate_vertical_velocity(self, icao24: str, window_minutes: int = 5) -> List[Dict]:
        """
        Calculate vertical velocity from altitude changes
        """
        # Get recent data
        aircraft_data = self.db.get_aircraft_data(icao24, hours_back=1)
        
        if len(aircraft_data) < 2:
            return []
        
        df = pd.DataFrame(aircraft_data)
        df = df.dropna(subset=['altitude', 'timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        vertical_velocities = []
        
        # Apply smoothing window
        window_size = max(3, len(df) // 10)  # Adaptive window size
        
        for i in range(window_size, len(df)):
            window_data = df.iloc[i-window_size:i+1]
            
            # Calculate vertical velocity using linear regression over window
            times = window_data['timestamp'].values
            altitudes = window_data['altitude'].values
            
            if len(times) >= 2:
                # Linear fit: altitude = a * time + b
                # Vertical velocity = da/dt = a
                coeffs = np.polyfit(times, altitudes, 1)
                vertical_velocity = coeffs[0]  # m/s
                
                vertical_velocities.append({
                    'timestamp': df.iloc[i]['timestamp'],
                    'altitude': df.iloc[i]['altitude'],
                    'vertical_velocity': vertical_velocity,
                    'window_size': len(window_data)
                })
        
        return vertical_velocities
    
    def get_wind_rose_data(self, icao24: str, altitude_min: float = None, 
                          altitude_max: float = None) -> Dict:
        """
        Generate wind rose data for specific altitude range
        """
        aircraft_data = self.db.get_aircraft_data(icao24, hours_back=6)
        
        if not aircraft_data:
            return {}
        
        # Filter by altitude if specified
        if altitude_min is not None or altitude_max is not None:
            filtered_data = []
            for point in aircraft_data:
                alt = point.get('altitude')
                if alt is not None:
                    if altitude_min is not None and alt < altitude_min:
                        continue
                    if altitude_max is not None and alt > altitude_max:
                        continue
                    filtered_data.append(point)
            aircraft_data = filtered_data
        
        # Recalculate wind for this altitude range
        wind_vectors = []
        
        # Simple implementation - calculate wind from consecutive points
        for i in range(1, len(aircraft_data)):
            prev_point = aircraft_data[i-1]
            curr_point = aircraft_data[i]
            
            if not all(k in prev_point and k in curr_point for k in ['latitude', 'longitude', 'timestamp']):
                continue
            
            dt = curr_point['timestamp'] - prev_point['timestamp']
            if dt <= 0 or dt > 300:
                continue
            
            prev_pos = (prev_point['latitude'], prev_point['longitude'])
            curr_pos = (curr_point['latitude'], curr_point['longitude'])
            
            distance = geodesic(prev_pos, curr_pos).meters
            bearing = self._calculate_bearing(prev_pos, curr_pos)
            speed = distance / dt
            
            wind_vectors.append({
                'wind_speed': speed,
                'wind_direction': bearing
            })
        
        if not wind_vectors:
            return {}
        
        # Create wind rose bins
        direction_bins = np.arange(0, 361, 22.5)  # 16 compass directions
        speed_bins = [0, 5, 10, 15, 20, 25, 30, 50, 100]  # m/s bins
        
        rose_data = {}
        
        for i, (dir_start, dir_end) in enumerate(zip(direction_bins[:-1], direction_bins[1:])):
            direction_label = f"{dir_start:.0f}-{dir_end:.0f}°"
            rose_data[direction_label] = {}
            
            # Find winds in this direction bin
            direction_winds = []
            for vector in wind_vectors:
                wind_dir = vector['wind_direction']
                if dir_start <= wind_dir < dir_end:
                    direction_winds.append(vector['wind_speed'])
            
            # Bin by speed
            for j, (speed_start, speed_end) in enumerate(zip(speed_bins[:-1], speed_bins[1:])):
                speed_label = f"{speed_start}-{speed_end} m/s"
                count = sum(1 for speed in direction_winds if speed_start <= speed < speed_end)
                rose_data[direction_label][speed_label] = count
        
        return rose_data