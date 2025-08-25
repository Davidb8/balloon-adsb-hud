"""
Alternative ADSB data sources - real APIs only
"""
import requests
import time
import json
from datetime import datetime
from typing import Dict, List, Optional

class ADSBExchangeClient:
    """ADSB Exchange API client (requires RapidAPI key)"""
    
    def __init__(self, api_key: str = None):
        self.base_url = "https://adsbexchange-com1.p.rapidapi.com"
        self.api_key = api_key
        self.headers = {
            "X-RapidAPI-Key": api_key if api_key else "demo-key",
            "X-RapidAPI-Host": "adsbexchange-com1.p.rapidapi.com"
        }
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Get aircraft data by ICAO24 from ADSB Exchange"""
        if not self.api_key:
            print("ADSB Exchange requires API key")
            return None
            
        try:
            url = f"{self.base_url}/icao/{icao24}/"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get('ac') and len(data['ac']) > 0:
                return self._parse_adsbx_aircraft(data['ac'][0])
            return None
            
        except Exception as e:
            print(f"ADSB Exchange API error: {e}")
            return None
    
    def _parse_adsbx_aircraft(self, aircraft: Dict) -> Dict:
        """Parse ADSB Exchange aircraft data to OpenSky format"""
        now = datetime.now().timestamp()
        
        return {
            'icao24': aircraft.get('hex', '').lower(),
            'callsign': aircraft.get('flight', '').strip(),
            'origin_country': None,
            'time_position': now,
            'last_contact': now,
            'longitude': aircraft.get('lon'),
            'latitude': aircraft.get('lat'),
            'baro_altitude': aircraft.get('alt_baro'),
            'on_ground': aircraft.get('ground', False),
            'velocity': aircraft.get('gs'),
            'true_track': aircraft.get('track'),
            'vertical_rate': aircraft.get('vs'),
            'sensors': None,
            'geo_altitude': aircraft.get('alt_geom'),
            'squawk': aircraft.get('squawk'),
            'spi': aircraft.get('spi', False),
            'position_source': 0
        }

class FlightRadar24Client:
    """Flight Radar 24 API client (free tier)"""
    
    def __init__(self):
        self.base_url = "https://data-live.flightradar24.com/zones/fcgi/feed.js"
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Get aircraft data from FlightRadar24"""
        try:
            # FR24 uses a different format - get all aircraft and filter
            response = requests.get(self.base_url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Search through aircraft data
            for flight_id, aircraft_data in data.items():
                if flight_id.startswith('full_count') or flight_id.startswith('version'):
                    continue
                
                if isinstance(aircraft_data, list) and len(aircraft_data) > 0:
                    # FR24 format: [lat, lon, track, alt, speed, squawk, radar, aircraft_type, reg, timestamp, origin, destination, flight, ?, ?, ?, hex, ?]
                    if len(aircraft_data) > 16 and aircraft_data[16]:
                        aircraft_hex = aircraft_data[16].lower()
                        if aircraft_hex == icao24.lower():
                            return self._parse_fr24_aircraft(aircraft_data)
            
            return None
            
        except Exception as e:
            print(f"FlightRadar24 API error: {e}")
            return None
    
    def _parse_fr24_aircraft(self, aircraft: List) -> Dict:
        """Parse FR24 aircraft data to OpenSky format"""
        now = datetime.now().timestamp()
        
        return {
            'icao24': aircraft[16].lower() if len(aircraft) > 16 else None,
            'callsign': aircraft[12].strip() if len(aircraft) > 12 and aircraft[12] else None,
            'origin_country': None,
            'time_position': aircraft[9] if len(aircraft) > 9 else now,
            'last_contact': now,
            'longitude': aircraft[1] if len(aircraft) > 1 else None,
            'latitude': aircraft[0] if len(aircraft) > 0 else None,
            'baro_altitude': aircraft[3] if len(aircraft) > 3 else None,
            'on_ground': False,
            'velocity': aircraft[4] if len(aircraft) > 4 else None,
            'true_track': aircraft[2] if len(aircraft) > 2 else None,
            'vertical_rate': None,
            'sensors': None,
            'geo_altitude': aircraft[3] if len(aircraft) > 3 else None,
            'squawk': aircraft[5] if len(aircraft) > 5 else None,
            'spi': False,
            'position_source': 0
        }

class FallbackDataCollector:
    """Data collector that tries multiple real ADSB data sources only"""
    
    def __init__(self, adsbx_api_key: str = None):
        self.sources = []
        
        # Only add real API sources if they have proper credentials
        if adsbx_api_key:
            self.sources.append(ADSBExchangeClient(adsbx_api_key))
        
        # FlightRadar24 free tier (may have rate limits)
        self.sources.append(FlightRadar24Client())
        
        if not self.sources:
            print("❌ No real ADSB API sources available - configure API keys")
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Try multiple real ADSB data sources until one works"""
        if not self.sources:
            print("❌ No real ADSB data sources configured")
            return None
        
        for source in self.sources:
            try:
                data = source.get_aircraft_by_icao(icao24)
                if data and data.get('latitude') and data.get('longitude'):
                    data['data_source'] = source.__class__.__name__
                    print(f"✅ Retrieved data from {source.__class__.__name__}")
                    return data
            except Exception as e:
                print(f"❌ Data source {source.__class__.__name__} failed: {e}")
                continue
        
        print(f"❌ No real data found for {icao24.upper()} from any alternative source")
        return None