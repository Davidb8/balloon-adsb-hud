# 🎈 Balloon ADSB Tracking HUD

A real-time visualization dashboard for tracking high-altitude balloons using ADSB data, with advanced wind layer analysis for altitude-based navigation.

## Features

- **Real-time ADSB tracking** via ADSB Exchange API
- **Four visualization panels**:
  - Altitude profile over time
  - Vertical velocity analysis
  - 2D lateral trajectory mapping
  - Wind speed/direction profiles by altitude
- **Wind layer analysis** calculated from GPS trajectory data
- **Containerized deployment** with Docker and Conda
- **Local SQLite storage** for data persistence
- **Mock data mode** for testing and demonstrations

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Git

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd balloon-adsb-hud
   ```

2. **Create environment configuration**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` to configure:
   - ADSB Exchange API key (required for balloon tracking)
   - Update intervals and data retention settings

3. **Build and run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

4. **Access the application**:
   Open your browser to `http://localhost:8050`

## Usage

### Tracking Real Balloons

1. **Get ICAO24 hex code** of your balloon's ADSB transponder
2. **Enter the ICAO24** in the input field (e.g., `a1b2c3`)
3. **Optional**: Add a callsign for identification
4. **Click "Start Tracking"** to begin real-time data collection

### Mock Data Mode

For testing without a real balloon:
1. **Click "Use Mock Data"** to generate simulated balloon flight
2. **View the four visualization panels** update with synthetic data
3. **Test wind calculations** and altitude analysis features

### Understanding the Visualizations

#### Altitude Profile
- Shows balloon altitude over time
- Red marker indicates current position
- Useful for tracking ascent/descent phases

#### Vertical Velocity
- Displays rate of climb/descent
- Green areas = ascending, red areas = descending
- Calculated using moving window for smoothing

#### Lateral Trajectory
- 2D map showing balloon's horizontal path
- Color-coded by altitude (darker = higher)
- Red marker shows current position

#### Wind Profile
- Wind speed vs altitude layers
- Calculated from GPS trajectory drift
- Binned by altitude intervals (default 500m)
- Essential for altitude-based navigation planning

## Configuration

### Environment Variables

Edit `.env` file to customize:

```bash
# ADSB API Configuration
RAPIDAPI_KEY=your-key      # Required: ADSB Exchange RapidAPI key

# Application Settings
UPDATE_INTERVAL=5          # Seconds between API calls
PORT=8050                  # Web interface port
DEBUG=True                 # Enable debug mode

# Wind Calculation Parameters
ALTITUDE_BIN_SIZE=500      # Altitude bins in meters
MIN_SAMPLES_PER_BIN=3      # Minimum data points per altitude bin
SMOOTHING_WINDOW=5         # Smoothing window for calculations

# Data Retention
MAX_DATA_AGE_HOURS=24      # Hours to keep historical data
CLEANUP_INTERVAL_MINUTES=60 # How often to clean old data
```

### ADSB Exchange API

- **Paid tier**: Starting at $10/month for 10,000 requests
- **No data censoring**: Shows all aircraft including military/restricted
- **High reliability**: Better uptime than free alternatives
- **Regional search**: Supports searching specific geographic regions

Get your API key at: https://rapidapi.com/adsbx/api/adsbexchange-com1/

## Technical Details

### Wind Calculation Algorithm

The system calculates wind speed and direction from balloon GPS trajectory:

1. **GPS Trajectory Analysis**: Uses consecutive GPS positions to calculate movement vectors
2. **Balloon Assumption**: Assumes balloon velocity ≈ wind velocity (high drag coefficient)
3. **Vector Averaging**: Combines multiple measurements per altitude bin
4. **Altitude Binning**: Groups data by configurable altitude intervals
5. **Temporal Smoothing**: Applies moving windows to reduce noise

### Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Dash Web UI   │◄───│   Flask Backend  │◄───│  ADSB API       │
│   (Plotly)      │    │   (SQLite DB)    │    │  (ADSB Exchange)│
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                       ┌──────────────────┐
                       │ Wind Calculator  │
                       │ (Trajectory →    │
                       │  Wind Analysis)  │
                       └──────────────────┘
```

### Data Storage

- **SQLite database** stores all tracking data locally
- **Automatic cleanup** removes data older than configured retention period
- **Real-time updates** via Dash callback system
- **Data export** capabilities for further analysis

## Development

### Local Development Setup

1. **Set up Conda environment**:
   ```bash
   conda env create -f conda-environment.yml
   conda activate balloon-hud
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run application**:
   ```bash
   cd src
   python app.py
   ```

### Testing

Run the test suite:
```bash
cd tests
python -m unittest test_wind_calculations.py
```

Tests cover:
- Database operations
- Wind calculation algorithms
- Trajectory analysis
- Data validation

### Project Structure

```
balloon-adsb-hud/
├── docker-compose.yml          # Container orchestration
├── Dockerfile                  # Container definition
├── conda-environment.yml       # Conda dependencies
├── requirements.txt            # Python packages
├── .env.example               # Configuration template
├── src/
│   ├── app.py                 # Main Dash application
│   ├── config.py              # Configuration management
│   ├── database.py            # SQLite operations
│   ├── data_collector.py      # ADSB API client
│   └── wind_calculator.py     # Wind analysis algorithms
├── static/
│   └── style.css              # Custom UI styling
├── data/                      # SQLite database storage
├── tests/
│   └── test_wind_calculations.py # Unit tests
└── README.md                  # This file
```

## API Limitations

### ADSB Exchange RapidAPI
- **Basic**: $10/month, 10,000 requests
- **Pro**: $50/month, 100,000 requests  
- **Enterprise**: Contact for unlimited access

### Rate Limiting
- Built-in rate limiting prevents API abuse
- Configurable update intervals (minimum 1 second)
- Automatic retry logic for transient failures

## Balloon Integration

### ADSB Transponder Requirements

Your balloon needs:
- **Mode S transponder** broadcasting on 1090 MHz
- **GPS receiver** for position data
- **Power system** for continuous operation during flight
- **Antenna** suitable for 1090 MHz transmission

### Recommended Equipment
- **uAvionix pingUSB** (lightweight ADSB transponder)
- **Stratux** (DIY ADSB solution)
- **Commercial aviation transponders** (heavier but more reliable)

### Regulatory Considerations
- Check local aviation regulations for ADSB requirements
- Some regions require transponder registration
- Coordinate with air traffic control for high-altitude flights

## Troubleshooting

### Common Issues

**No data appearing**:
- Verify ICAO24 hex code is correct (6 characters, case-insensitive)  
- Check that balloon is currently transmitting ADSB
- Ensure ADSB Exchange API key is configured correctly
- Try mock data mode to verify application functionality

**Slow updates**:
- Check your ADSB Exchange API rate limits
- Increase `UPDATE_INTERVAL` in configuration
- Consider upgrading to higher tier for more API calls

**Wind calculations seem incorrect**:
- Ensure sufficient GPS points (minimum 3 per altitude bin)
- Check for GPS accuracy issues
- Verify balloon is truly drifting with wind (not powered flight)

### Logs and Debugging

Enable debug mode in `.env`:
```bash
DEBUG=True
```

View container logs:
```bash
docker-compose logs -f balloon-hud
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- **ADSB Exchange** for providing comprehensive ADSB data access
- **Plotly Dash** for the interactive visualization framework
- **High-altitude balloon community** for inspiration and requirements

## Support

For issues, questions, or feature requests:
1. Check existing GitHub issues
2. Create a new issue with detailed description
3. Include logs and configuration details
4. Specify balloon equipment and flight details

---

**Happy ballooning!** 🎈✈️