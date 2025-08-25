import unittest
import sys
import os
import tempfile
import shutil
from datetime import datetime, timedelta
import numpy as np

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import BalloonDatabase
from wind_calculator import WindCalculator

class TestWindCalculations(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        # Create temporary database
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test_balloons.db')
        self.db = BalloonDatabase(self.db_path)
        self.wind_calc = WindCalculator(self.db)
        
        # Test ICAO
        self.test_icao = 'test123'
    
    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.temp_dir)
    
    def test_database_initialization(self):
        """Test that database initializes correctly"""
        # Check that tables exist
        with self.db.init_database():
            pass  # Should not raise any errors
    
    def test_add_aircraft_data(self):
        """Test adding aircraft data to database"""
        test_data = {
            'icao24': self.test_icao,
            'callsign': 'TEST001',
            'time_position': datetime.now().timestamp(),
            'latitude': 42.3601,
            'longitude': -71.0589,
            'baro_altitude': 10000,
            'velocity': 50,
            'true_track': 90,
            'vertical_rate': 5,
            'on_ground': False,
            'last_contact': datetime.now().timestamp()
        }
        
        success = self.db.add_aircraft_data(test_data)
        self.assertTrue(success)
        
        # Verify data was stored
        retrieved_data = self.db.get_aircraft_data(self.test_icao, hours_back=1)
        self.assertEqual(len(retrieved_data), 1)
        self.assertEqual(retrieved_data[0]['icao24'], self.test_icao)
    
    def test_wind_calculation_with_straight_flight(self):
        """Test wind calculation with straight eastward flight"""
        base_time = datetime.now().timestamp() - 3600
        base_lat = 42.3601
        base_lon = -71.0589
        altitude = 15000
        
        # Create straight eastward flight path (simulating eastward wind)
        for i in range(10):
            timestamp = base_time + (i * 60)  # 1 minute intervals
            lon_offset = i * 0.001  # Moving east
            
            aircraft_data = {
                'icao24': self.test_icao,
                'callsign': 'TEST001',
                'time_position': timestamp,
                'latitude': base_lat,
                'longitude': base_lon + lon_offset,
                'baro_altitude': altitude,
                'velocity': 50,
                'true_track': 90,  # East
                'vertical_rate': 0,
                'on_ground': False,
                'last_contact': timestamp
            }
            
            self.db.add_aircraft_data(aircraft_data)
        
        # Calculate wind
        wind_data = self.wind_calc.calculate_wind_from_trajectory(self.test_icao, hours_back=2)
        
        # Should have wind data for the altitude bin
        altitude_bin = (altitude // 500) * 500
        self.assertIn(altitude_bin, wind_data)
        
        # Wind should be generally eastward (around 90 degrees)
        wind_direction = wind_data[altitude_bin]['wind_direction']
        self.assertGreater(wind_direction, 45)
        self.assertLess(wind_direction, 135)
        
        # Wind speed should be positive
        wind_speed = wind_data[altitude_bin]['wind_speed']
        self.assertGreater(wind_speed, 0)
    
    def test_wind_calculation_with_circular_pattern(self):
        """Test wind calculation with circular flight pattern (should show low wind)"""
        base_time = datetime.now().timestamp() - 1800  # 30 minutes ago
        base_lat = 42.3601
        base_lon = -71.0589
        altitude = 20000
        radius = 0.01  # degrees
        
        # Create circular pattern
        for i in range(12):  # 12 points in circle
            timestamp = base_time + (i * 150)  # 2.5 minute intervals
            angle = (i / 12) * 2 * np.pi
            
            lat_offset = radius * np.sin(angle)
            lon_offset = radius * np.cos(angle)
            
            aircraft_data = {
                'icao24': self.test_icao,
                'callsign': 'TEST001', 
                'time_position': timestamp,
                'latitude': base_lat + lat_offset,
                'longitude': base_lon + lon_offset,
                'baro_altitude': altitude,
                'velocity': 30,
                'true_track': (angle * 180 / np.pi) % 360,
                'vertical_rate': 0,
                'on_ground': False,
                'last_contact': timestamp
            }
            
            self.db.add_aircraft_data(aircraft_data)
        
        # Calculate wind
        wind_data = self.wind_calc.calculate_wind_from_trajectory(self.test_icao, hours_back=1)
        
        # Should have wind data for the altitude bin
        altitude_bin = (altitude // 500) * 500
        self.assertIn(altitude_bin, wind_data)
        
        # Wind speed should be relatively low (circular pattern cancels out)
        wind_speed = wind_data[altitude_bin]['wind_speed']
        self.assertLess(wind_speed, 20)  # Less than 20 m/s
    
    def test_vertical_velocity_calculation(self):
        """Test vertical velocity calculation"""
        base_time = datetime.now().timestamp() - 1800
        base_lat = 42.3601
        base_lon = -71.0589
        
        # Create ascending balloon trajectory
        for i in range(10):
            timestamp = base_time + (i * 180)  # 3 minute intervals
            altitude = 5000 + (i * 1000)  # Ascending 1000m every 3 minutes
            
            aircraft_data = {
                'icao24': self.test_icao,
                'callsign': 'TEST001',
                'time_position': timestamp,
                'latitude': base_lat,
                'longitude': base_lon,
                'baro_altitude': altitude,
                'velocity': 40,
                'true_track': 45,
                'vertical_rate': 5.5,  # Should be around 1000m/180s ≈ 5.5 m/s
                'on_ground': False,
                'last_contact': timestamp
            }
            
            self.db.add_aircraft_data(aircraft_data)
        
        # Calculate vertical velocity
        vel_data = self.wind_calc.calculate_vertical_velocity(self.test_icao, window_minutes=5)
        
        self.assertGreater(len(vel_data), 0)
        
        # Check that calculated vertical velocities are positive (ascending)
        for vel_point in vel_data:
            self.assertGreater(vel_point['vertical_velocity'], 0)
    
    def test_bearing_calculation(self):
        """Test bearing calculation between two points"""
        # Test known bearings
        point1 = (42.3601, -71.0589)  # Boston
        point2 = (42.3601, -70.0589)  # 1 degree east
        
        bearing = self.wind_calc._calculate_bearing(point1, point2)
        
        # Should be approximately 90 degrees (due east)
        self.assertGreater(bearing, 80)
        self.assertLess(bearing, 100)
        
        # Test north bearing
        point3 = (43.3601, -71.0589)  # 1 degree north
        bearing_north = self.wind_calc._calculate_bearing(point1, point3)
        
        # Should be approximately 0 degrees (due north)
        self.assertLess(bearing_north, 20)
    
    def test_altitude_binning(self):
        """Test altitude binning functionality"""
        wind_vectors = [
            {'altitude': 15200, 'wind_speed': 20, 'wind_direction': 90},
            {'altitude': 15800, 'wind_speed': 25, 'wind_direction': 95},
            {'altitude': 16100, 'wind_speed': 22, 'wind_direction': 85},
        ]
        
        wind_by_altitude = self.wind_calc._bin_wind_data(wind_vectors)
        
        # All should be in 15000m bin (15000-15999m)
        self.assertIn(15000, wind_by_altitude)
        self.assertEqual(wind_by_altitude[15000]['sample_count'], 2)
        
        # Check in 16000m bin
        self.assertIn(16000, wind_by_altitude)
        self.assertEqual(wind_by_altitude[16000]['sample_count'], 1)
    
    def test_tracked_aircraft_management(self):
        """Test adding and managing tracked aircraft"""
        # Add tracked aircraft
        success = self.db.add_tracked_aircraft(self.test_icao, 'TEST001', 'Test balloon')
        self.assertTrue(success)
        
        # Get tracked aircraft
        tracked = self.db.get_tracked_aircraft()
        self.assertEqual(len(tracked), 1)
        self.assertEqual(tracked[0]['icao24'], self.test_icao)
        
        # Update last seen
        self.db.update_aircraft_last_seen(self.test_icao)
        
        # Verify update
        tracked_updated = self.db.get_tracked_aircraft()
        self.assertIsNotNone(tracked_updated[0]['last_seen'])

if __name__ == '__main__':
    unittest.main()