import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ADSB API Configuration - Only ADSB Exchange now
    RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
    
    # Balloon Configuration
    TRACKED_BALLOONS = {
        'aceec8': {'name': 'HBAL784', 'type': 'high_altitude', 'description': 'High-altitude balloon'},
        'aceb11': {'name': 'HBAL783', 'type': 'high_altitude', 'description': 'High-altitude balloon'},
        'acf27f': {'name': 'HBAL785', 'type': 'high_altitude', 'description': 'High-altitude balloon'},
        'a26f79': {'name': 'Balloon-1', 'type': 'standard', 'description': 'Standard tracking balloon'},
        'a27330': {'name': 'Balloon-2', 'type': 'standard', 'description': 'Standard tracking balloon'}
    }
    
    # Application Configuration
    UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', 5))
    DATABASE_PATH = os.getenv('DATABASE_PATH', './data/balloons.db')
    PORT = int(os.getenv('PORT', 8050))
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Wind Calculation Parameters
    ALTITUDE_BIN_SIZE = int(os.getenv('ALTITUDE_BIN_SIZE', 500))
    MIN_SAMPLES_PER_BIN = int(os.getenv('MIN_SAMPLES_PER_BIN', 3))
    SMOOTHING_WINDOW = int(os.getenv('SMOOTHING_WINDOW', 5))
    
    # Data Retention
    MAX_DATA_AGE_HOURS = int(os.getenv('MAX_DATA_AGE_HOURS', 24))
    CLEANUP_INTERVAL_MINUTES = int(os.getenv('CLEANUP_INTERVAL_MINUTES', 60))