# Real ADSB Data Setup for Balloon Tracking

## Current Status ❌

**All free ADSB APIs are currently down (503 errors):**
- ❌ OpenSky Network: 503 Service Temporarily Unavailable
- ❌ ADSB Exchange free tier: Not accessible
- ❌ FlightRadar24 free endpoints: Not accessible

## Solution: Paid ADSB APIs ✅

To get **real data for balloons A27330 and A26F79**, you need a paid API subscription:

### Option 1: ADSB Exchange RapidAPI (Recommended)

**Cost:** ~$10/month for 10,000 requests

**Why it's best for balloon tracking:**
- ✅ No data censoring (shows ALL aircraft including military/blocked)
- ✅ High-altitude balloon coverage
- ✅ Regional search capabilities for Colorado/New Mexico
- ✅ Real-time updates

**Setup Steps:**
1. Go to: https://rapidapi.com/adsbx/api/adsbexchange-com1/
2. Click "Subscribe to Test"
3. Choose "Basic" plan ($10/month, 10,000 requests)
4. Get your RapidAPI key from the dashboard
5. Set environment variable:
   ```bash
   export RAPIDAPI_KEY="your-rapidapi-key-here"
   ```

### Option 2: FlightRadar24 API

**Cost:** ~$9+/month for 30,000+ requests

**Setup Steps:**
1. Go to: https://fr24api.flightradar24.com/
2. Subscribe to a plan
3. Get your API key
4. Set environment variable:
   ```bash
   export FR24_API_KEY="your-fr24-api-key-here"
   ```

## After API Setup

1. **Set the environment variable** (choose one):
   ```bash
   export RAPIDAPI_KEY="your-key"
   # OR
   export FR24_API_KEY="your-key"
   ```

2. **Restart the application:**
   ```bash
   docker-compose down && docker-compose up --build
   ```

3. **Verify it's working:**
   - Look for messages like "✅ Paid ADSB APIs available for balloon tracking"
   - Check for "✅ Found balloon A27330/A26F79 via paid API"

## Expected Behavior

**With paid API configured:**
```
🔄 Trying paid APIs for balloon A27330...
✅ Found balloon A27330 via paid API
✅ Retrieved real data for balloon A27330
Updated data for a27330: Alt=15240m (Source: ADSBExchange_RapidAPI)
```

**Without paid API (current state):**
```
❌ Real balloon A27330 - No real ADSB data found from any source!
```

## Technical Details

The system now includes:
- **Enhanced real ADSB client** that prioritizes paid APIs for balloons A27330/A26F79
- **Fallback prevention** - no mock data for real balloons
- **Regional search** - searches Colorado/New Mexico area if direct ICAO lookup fails
- **Multiple paid API support** - can use ADSB Exchange, FlightRadar24, or both

## Test Script

Run this to test your setup:
```bash
python src/paid_adsb_client.py
```

## Cost Analysis

For continuous balloon tracking:
- **Update interval:** 15 seconds
- **Requests per hour:** 240 (4 per minute × 60 minutes)  
- **Monthly requests:** ~175,000 (720 hours × 240)

**ADSB Exchange Basic ($10/month):** 10,000 requests = ~1.4 days of tracking
**ADSB Exchange Pro (~$50/month):** 100,000 requests = ~2 weeks of tracking
**ADSB Exchange Enterprise:** Unlimited - best for continuous tracking

💡 **Recommendation:** Start with Basic plan to test, then upgrade if needed for continuous tracking.