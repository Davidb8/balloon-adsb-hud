"""
Paid ADSB API clients for real balloon tracking when free APIs are down
"""
import requests
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
from enum import Enum

class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open" 
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Circuit breaker pattern for API resilience"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, expected_exception=Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self):
        """Check if enough time has passed to attempt reset"""
        return (
            self.last_failure_time is not None and
            datetime.now() - self.last_failure_time >= timedelta(seconds=self.recovery_timeout)
        )
    
    def _on_success(self):
        """Reset circuit breaker on successful call"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
    
    def _on_failure(self):
        """Handle failure and potentially open circuit"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN

class ADSBExchangeRapidAPIClient:
    """ADSB Exchange via RapidAPI - $10/month for 10,000 requests"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('RAPIDAPI_KEY')
        if not self.api_key:
            raise ValueError("RAPIDAPI_KEY environment variable must be set for ADSB Exchange access")
        self.base_url = "https://adsbexchange-com1.p.rapidapi.com"
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": "adsbexchange-com1.p.rapidapi.com"
        }
        self.last_request_time = 0
        self.min_request_interval = 0.5
        
        # Circuit breaker for resilience
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=(requests.exceptions.RequestException, requests.exceptions.Timeout)
        )
    
    def _rate_limit(self):
        """Rate limiting to preserve API credits"""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _retry_with_backoff(self, func, max_retries: int = 3, base_delay: float = 1.0):
        """Retry function with exponential backoff"""
        for attempt in range(max_retries):
            try:
                return self.circuit_breaker.call(func)
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    raise e
                
                delay = base_delay * (2 ** attempt)
                print(f"API call failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s: {e}")
                time.sleep(delay)
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Get aircraft data by ICAO24 from ADSB Exchange RapidAPI"""
        if not self.api_key:
            print("❌ ADSB Exchange requires RapidAPI key - set RAPIDAPI_KEY environment variable")
            return None
        
        def _api_call():
            self._rate_limit()
            return self._make_api_request(icao24)
        
        try:
            return self._retry_with_backoff(_api_call)
        except Exception as e:
            print(f"❌ All retry attempts failed for {icao24.upper()}: {e}")
            return None
    
    def _make_api_request(self, icao24: str) -> Optional[Dict]:
        """Make the actual API request"""
        try:
            # Use v2/hex endpoint as per user's example
            url = f"{self.base_url}/v2/hex/{icao24.lower()}/"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code == 429:
                raise requests.exceptions.RequestException("API rate limit exceeded")
            elif response.status_code == 403:
                raise requests.exceptions.RequestException("API key invalid or expired")
            elif response.status_code == 404:
                print(f"❌ Aircraft {icao24.upper()} not found")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # v2 API returns direct aircraft object, not array
            if data.get('hex'):
                parsed = self._parse_adsbx_v2_aircraft(data)
                parsed['data_source'] = 'ADSBExchange_RapidAPI'
                print(f"✅ Retrieved {icao24.upper()} from ADSB Exchange RapidAPI")
                return parsed
            elif data.get('ac') and len(data['ac']) > 0:
                # Fallback to old format
                aircraft = data['ac'][0]
                parsed = self._parse_adsbx_aircraft(aircraft)
                parsed['data_source'] = 'ADSBExchange_RapidAPI'
                print(f"✅ Retrieved {icao24.upper()} from ADSB Exchange RapidAPI")
                return parsed
            else:
                print(f"❌ No data for {icao24.upper()} in ADSB Exchange")
                return None
        
        except requests.exceptions.RequestException:
            # Re-raise for circuit breaker handling
            raise
        except Exception as e:
            print(f"❌ ADSB Exchange RapidAPI error: {e}")
            return None
    
    def get_aircraft_in_region(self, lat_min: float, lat_max: float, 
                              lon_min: float, lon_max: float) -> List[Dict]:
        """Get all aircraft in a bounding box region"""
        if not self.api_key:
            return []
        
        self._rate_limit()
        
        try:
            # ADSB Exchange regional endpoint
            url = f"{self.base_url}/lat/{lat_min}/{lat_max}/lon/{lon_min}/{lon_max}/"
            
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code in [429, 403]:
                print(f"❌ API access denied: {response.status_code}")
                return []
            
            response.raise_for_status()
            data = response.json()
            
            aircraft_list = []
            if data.get('ac'):
                for aircraft in data['ac']:
                    parsed = self._parse_adsbx_aircraft(aircraft)
                    if parsed:
                        parsed['data_source'] = 'ADSBExchange_RapidAPI'
                        aircraft_list.append(parsed)
            
            print(f"✅ Retrieved {len(aircraft_list)} aircraft from regional search")
            return aircraft_list
        
        except Exception as e:
            print(f"❌ Regional search error: {e}")
            return []
    
    def _parse_adsbx_v2_aircraft(self, aircraft: Dict) -> Optional[Dict]:
        """Parse ADSB Exchange v2 API aircraft data to our format"""
        try:
            now = datetime.now().timestamp()
            
            # Convert altitude from feet to meters for database consistency
            alt_baro_feet = aircraft.get('alt_baro')
            alt_baro_meters = alt_baro_feet * 0.3048 if alt_baro_feet is not None else None
            
            return {
                'icao24': aircraft.get('hex', '').lower(),
                'callsign': aircraft.get('flight', '').strip(),
                'origin_country': None,
                'time_position': now,
                'last_contact': now,
                'longitude': aircraft.get('lon'),
                'latitude': aircraft.get('lat'),
                'altitude': alt_baro_meters,  # Convert to meters for database
                'baro_altitude': alt_baro_meters,  # Keep both for compatibility
                'on_ground': aircraft.get('ground', False),
                'velocity': aircraft.get('gs'),  # ground speed in knots
                'track': aircraft.get('track'),
                'vertical_rate': aircraft.get('baro_rate'),  # vertical speed in fpm
                'sensors': None,
                'geo_altitude': aircraft.get('alt_geom') * 0.3048 if aircraft.get('alt_geom') else None,
                'squawk': aircraft.get('squawk'),
                'spi': aircraft.get('spi', False),
                'position_source': 0,
                # Additional raw ADSB fields
                'registration': aircraft.get('r'),  # Aircraft registration (N-number)
                'category': aircraft.get('category'),  # Aircraft category (B2, etc.)
                'emergency': aircraft.get('emergency'),  # Emergency status
                'geom_rate': aircraft.get('geom_rate'),  # Geometric vertical rate
                'nic': aircraft.get('nic'),  # Navigation Integrity Category
                'nac_p': aircraft.get('nac_p'),  # Navigation Accuracy Category - Position
                'nac_v': aircraft.get('nac_v'),  # Navigation Accuracy Category - Velocity
                'sil': aircraft.get('sil'),  # Source Integrity Level
                'gva': aircraft.get('gva'),  # Geometric Vertical Accuracy
                'sda': aircraft.get('sda'),  # System Design Assurance
                'messages': aircraft.get('messages'),  # Total messages received
                'rssi': aircraft.get('rssi')  # Received Signal Strength Indicator
            }
        except Exception as e:
            print(f"❌ Error parsing ADSB Exchange v2 data: {e}")
            return None

    def _parse_adsbx_aircraft(self, aircraft: Dict) -> Optional[Dict]:
        """Parse ADSB Exchange aircraft data to our format"""
        try:
            now = datetime.now().timestamp()
            
            return {
                'icao24': aircraft.get('hex', '').lower(),
                'callsign': aircraft.get('flight', '').strip(),
                'origin_country': None,
                'time_position': now,
                'last_contact': now,
                'longitude': aircraft.get('lon'),
                'latitude': aircraft.get('lat'),
                'altitude': aircraft.get('alt_baro'),  # Match database schema
                'baro_altitude': aircraft.get('alt_baro'),
                'on_ground': aircraft.get('ground', False),
                'velocity': aircraft.get('gs'),  # ground speed
                'track': aircraft.get('track'),
                'vertical_rate': aircraft.get('vs'),  # vertical speed
                'sensors': None,
                'geo_altitude': aircraft.get('alt_geom'),
                'squawk': aircraft.get('squawk'),
                'spi': aircraft.get('spi', False),
                'position_source': 0
            }
        except Exception as e:
            print(f"❌ Error parsing ADSB Exchange data: {e}")
            return None


class FlightRadar24APIClient:
    """FlightRadar24 API - $9+/month for 30,000+ requests"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('FR24_API_KEY')
        self.base_url = "https://fr24api.flightradar24.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}" if self.api_key else None
        }
        self.last_request_time = 0
        self.min_request_interval = 0.5
    
    def _rate_limit(self):
        """Rate limiting to preserve API credits"""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Get aircraft data by ICAO24 from FlightRadar24 API"""
        if not self.api_key:
            print("❌ FlightRadar24 requires API key - set FR24_API_KEY environment variable")
            return None
        
        self._rate_limit()
        
        try:
            # FR24 flight feed endpoint with filter
            url = f"{self.base_url}/feed"
            params = {
                'icao24': icao24.upper(),
                'limit': 1
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
            
            if response.status_code == 429:
                print("❌ FR24 API rate limit exceeded")
                return None
            elif response.status_code == 403:
                print("❌ FR24 API key invalid or expired")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # FR24 API structure may vary - this is a placeholder implementation
            if data and isinstance(data, dict):
                for flight_id, flight_data in data.items():
                    if isinstance(flight_data, list) and len(flight_data) > 16:
                        if flight_data[16] and flight_data[16].lower() == icao24.lower():
                            parsed = self._parse_fr24_aircraft(flight_data)
                            parsed['data_source'] = 'FlightRadar24_API'
                            print(f"✅ Retrieved {icao24.upper()} from FlightRadar24 API")
                            return parsed
            
            print(f"❌ No data for {icao24.upper()} in FlightRadar24")
            return None
        
        except Exception as e:
            print(f"❌ FlightRadar24 API error: {e}")
            return None
    
    def _parse_fr24_aircraft(self, aircraft: List) -> Dict:
        """Parse FR24 aircraft data to our format"""
        now = datetime.now().timestamp()
        
        return {
            'icao24': aircraft[16].lower() if len(aircraft) > 16 else None,
            'callsign': aircraft[12].strip() if len(aircraft) > 12 and aircraft[12] else None,
            'origin_country': None,
            'time_position': aircraft[9] if len(aircraft) > 9 else now,
            'last_contact': now,
            'longitude': aircraft[1] if len(aircraft) > 1 else None,
            'latitude': aircraft[0] if len(aircraft) > 0 else None,
            'altitude': aircraft[3] if len(aircraft) > 3 else None,
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


class PaidADSBClient:
    """Multi-source client that tries paid ADSB APIs"""
    
    def __init__(self, rapidapi_key: str = None, fr24_key: str = None):
        self.clients = []
        
        # Initialize available paid clients
        if rapidapi_key or os.getenv('RAPIDAPI_KEY'):
            try:
                adsbx_client = ADSBExchangeRapidAPIClient(rapidapi_key)
                self.clients.append(adsbx_client)
                print("✅ ADSB Exchange RapidAPI client initialized")
            except Exception as e:
                print(f"❌ Failed to initialize ADSB Exchange client: {e}")
        
        if fr24_key or os.getenv('FR24_API_KEY'):
            try:
                fr24_client = FlightRadar24APIClient(fr24_key)
                self.clients.append(fr24_client)
                print("✅ FlightRadar24 API client initialized")
            except Exception as e:
                print(f"❌ Failed to initialize FlightRadar24 client: {e}")
        
        if not self.clients:
            print("❌ No paid API clients available - set RAPIDAPI_KEY or FR24_API_KEY")
    
    def get_aircraft_by_icao(self, icao24: str) -> Optional[Dict]:
        """Try paid APIs in order of preference"""
        for client in self.clients:
            try:
                result = client.get_aircraft_by_icao(icao24)
                if result:
                    return result
            except Exception as e:
                print(f"❌ {client.__class__.__name__} failed: {e}")
                continue
        
        return None
    
    def find_balloon_in_region(self, icao24: str) -> Optional[Dict]:
        """Search for balloon in Colorado/New Mexico region using paid APIs"""
        # Colorado/New Mexico bounding box
        lat_min, lat_max = 35.0, 40.0
        lon_min, lon_max = -110.0, -100.0
        
        for client in self.clients:
            if hasattr(client, 'get_aircraft_in_region'):
                try:
                    aircraft_list = client.get_aircraft_in_region(lat_min, lat_max, lon_min, lon_max)
                    
                    # Search for our target balloon
                    for aircraft in aircraft_list:
                        if aircraft.get('icao24', '').lower() == icao24.lower():
                            print(f"🎯 Found balloon {icao24.upper()} in regional search!")
                            return aircraft
                    
                except Exception as e:
                    print(f"❌ Regional search failed for {client.__class__.__name__}: {e}")
                    continue
        
        return None


def setup_paid_apis():
    """Setup instructions for paid APIs"""
    instructions = """
    
    📋 PAID ADSB API SETUP INSTRUCTIONS
    =====================================
    
    The free ADSB APIs are currently down. To get real balloon data, set up a paid API:
    
    🔹 OPTION 1: ADSB Exchange via RapidAPI (~$10/month)
       1. Go to: https://rapidapi.com/adsbx/api/adsbexchange-com1/
       2. Subscribe to a plan (Basic: $10/month for 10,000 requests)
       3. Get your RapidAPI key from the dashboard
       4. Set environment variable: export RAPIDAPI_KEY="your-key-here"
    
    🔹 OPTION 2: FlightRadar24 API (~$9+/month)
       1. Go to: https://fr24api.flightradar24.com/
       2. Subscribe to a plan (Basic: $9/month for 30,000 requests)
       3. Get your API key from the dashboard  
       4. Set environment variable: export FR24_API_KEY="your-key-here"
    
    💡 RECOMMENDATION:
    ADSB Exchange RapidAPI is recommended because:
    - No censoring of aircraft data (shows all aircraft including blocked ones)
    - Reliable high-altitude balloon tracking
    - Regional search capabilities for Colorado/New Mexico area
    
    🚀 AFTER SETUP:
    Restart the Docker container to use the new API keys:
    docker-compose down && docker-compose up --build
    
    """
    print(instructions)
    return instructions

if __name__ == "__main__":
    # Show setup instructions
    setup_paid_apis()
    
    # Test if any paid APIs are configured
    client = PaidADSBClient()
    
    if client.clients:
        print("Testing paid API access...")
        test_result = client.get_aircraft_by_icao('a27330')
        
        if test_result:
            print(f"✅ Successfully retrieved balloon data: {test_result['data_source']}")
        else:
            print("❌ No balloon data found (balloon may not be transmitting)")
    else:
        print("❌ No paid APIs configured - follow setup instructions above")