import dash
from dash import dcc, html, Input, Output, State, callback_context, ALL
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import threading
import time
import sqlite3

# Local imports
from config import Config
from database import BalloonDatabase
from data_collector import DataCollector
from wind_calculator import WindCalculator

# Initialize components
db = BalloonDatabase()
collector = DataCollector(db)  # Initialize singleton
wind_calc = WindCalculator(db)

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=['/static/style.css'])
app.title = "Balloon ADSB HUD"

# Global variables for tracking
tracked_balloons = {}  # {icao: {collector: DataCollector, last_update: datetime}}
selected_balloons = set()  # Set of ICAOs to display on charts
last_update = datetime.now()

# App layout
app.layout = html.Div([
    # Header
    html.Div([
        html.H1("🎈 Balloon ADSB Tracking HUD"),
        html.P("Real-time high-altitude balloon tracking and wind analysis with enhanced data visualization")
    ], className="header"),
    
    # Control Panel
    html.Div([
        html.Div([
            html.Div([
                html.Label("Add ICAO24 Hex Code", className="control-label"),
                html.Div([
                    dcc.Input(
                        id='icao-input',
                        type='text',
                        placeholder='e.g., a1b2c3',
                        value='',
                        className='dash-input',
                        style={'flex': '1', 'margin-right': '8px'}
                    ),
                    html.Button([
                        html.Span('➕ ', style={'margin-right': '4px'}),
                        'Add'
                    ], id='add-balloon-btn', className='btn-secondary', style={'white-space': 'nowrap'})
                ], style={'display': 'flex', 'align-items': 'center'})
            ], className="control-group"),
            
            html.Div([
                html.Label(["Tracked Balloons ", html.Span("Multi-Select", className="feature-badge")], className="control-label"),
                html.Div(id='balloon-list', children=[
                    html.P("No balloons tracked yet", style={'color': '#8b949e', 'font-style': 'italic', 'margin': '8px 0'})
                ], style={'max-height': '120px', 'overflow-y': 'auto', 'background': 'rgba(13, 17, 23, 0.5)', 'border': '1px solid #30363d', 'border-radius': '6px', 'padding': '8px'})
            ], className="control-group"),
            
            html.Div([
                html.Button([
                    html.Span('⏹️ ', style={'margin-right': '4px'}),
                    'Stop All'
                ], id='stop-all-btn', className='btn-secondary'),
                html.Button([
                    html.Span('🧪 ', style={'margin-right': '4px'}),
                    'Mock Data'
                ], id='mock-btn', className='btn-secondary'),
                html.Button([
                    html.Span('✅ ', style={'margin-right': '4px'}),
                    'Select All'
                ], id='select-all-btn', className='btn-secondary'),
                html.Button([
                    html.Span('❌ ', style={'margin-right': '4px'}),
                    'Deselect All'
                ], id='deselect-all-btn', className='btn-secondary'),
                html.Button([
                    html.Span('🎈 ', style={'margin-right': '4px'}),
                    'Find All Balloons'
                ], id='find-balloons-btn', className='btn-secondary', title='Search for all B2 category balloons in region'),
            ], style={'display': 'flex', 'gap': '8px', 'align-items': 'end', 'flex-wrap': 'wrap'}),
            
            # Section Divider
            html.Div(className="section-divider"),
            
            html.Div([
                html.Label("Altitude Units", className="control-label"),
                dcc.RadioItems(
                    id='altitude-units',
                    options=[
                        {'label': 'Meters', 'value': 'm'},
                        {'label': 'Feet', 'value': 'ft'}
                    ],
                    value='m',
                    inline=True,
                    style={'color': '#e6edf3'}
                )
            ], className="control-group", style={'margin-top': '10px'}),
            
            html.Div([
                html.Label("Altitude Source", className="control-label"),
                dcc.RadioItems(
                    id='altitude-source',
                    options=[
                        {'label': 'Barometric', 'value': 'altitude'},
                        {'label': 'Geometric (GPS)', 'value': 'geo_altitude'}
                    ],
                    value='altitude',
                    inline=True,
                    style={'color': '#e6edf3'}
                )
            ], className="control-group", style={'margin-top': '10px'}),
            
            html.Div([
                html.Label([
                    "Y-Axis Limits ",
                    html.Span("Optional", className="feature-badge")
                ], className="control-label"),
                html.Div([
                    html.Div([
                        html.Label("Altitude:", className="y-limit-label"),
                        dcc.Input(
                            id='altitude-y-min',
                            type='number',
                            placeholder='Min',
                            className='y-limit-input'
                        ),
                        html.Span(" to ", style={'margin': '0 8px', 'color': '#8b949e'}),
                        dcc.Input(
                            id='altitude-y-max',
                            type='number',
                            placeholder='Max',
                            className='y-limit-input'
                        )
                    ], className='y-limits-row'),
                    html.Div([
                        html.Label("Velocity:", className="y-limit-label"),
                        dcc.Input(
                            id='velocity-y-min',
                            type='number',
                            placeholder='Min',
                            className='y-limit-input'
                        ),
                        html.Span(" to ", style={'margin': '0 8px', 'color': '#8b949e'}),
                        dcc.Input(
                            id='velocity-y-max',
                            type='number',
                            placeholder='Max',
                            className='y-limit-input'
                        )
                    ], className='y-limits-row'),
                    html.Div([
                        html.Label("Wind Alt:", className="y-limit-label"),
                        dcc.Input(
                            id='wind-y-min',
                            type='number',
                            placeholder='Min',
                            className='y-limit-input'
                        ),
                        html.Span(" to ", style={'margin': '0 8px', 'color': '#8b949e'}),
                        dcc.Input(
                            id='wind-y-max',
                            type='number',
                            placeholder='Max',
                            className='y-limit-input'
                        )
                    ], className='y-limits-row')
                ], className="y-limits-section")
            ], className="control-group"),
            
            html.Div([
                html.Label([
                    "Wind Profile Filters ",
                    html.Span("🌪️", style={'margin-left': '4px'})
                ], className="control-label"),
                html.Div([
                    html.Div([
                        html.Label("Time:", className="filter-label"),
                        dcc.Input(
                            id='wind-time-filter',
                            type='number',
                            placeholder='Minutes',
                            min=1,
                            max=2880,  # 48 hours in minutes
                            step=1,
                            className='filter-input'
                        ),
                        html.Label("min", className="filter-unit")
                    ], className='filter-row'),
                    html.Div([
                        html.Label("Distance:", className="filter-label"),
                        dcc.Input(
                            id='wind-distance-filter',
                            type='number',
                            placeholder='Kilometers',
                            min=0.1,
                            max=1000,
                            step=1,
                            className='filter-input'
                        ),
                        html.Label("km", className="filter-unit")
                    ], className='filter-row'),
                    html.Div([
                        html.Label("From balloon:", className="filter-label"),
                        dcc.Dropdown(
                            id='wind-reference-balloon',
                            placeholder='Select reference...',
                            className='filter-dropdown',
                            style={
                                'width': '200px', 
                                'fontSize': '12px',
                                'color': '#e6edf3',
                                'backgroundColor': '#0d1117'
                            },
                            maxHeight=200,
                            optionHeight=35
                        )
                    ], className='filter-row', style={'margin-top': '4px'})
                ], className="wind-filters")
            ], className="control-group"),
            
        ], className="control-row"),
        
        # Status Display
        html.Div([
            html.Div(id='status-display', children=[
                html.Span("●", className="status-indicator status-offline"),
                html.Span("No tracking active", style={'color': '#8b949e'})
            ])
        ], style={'margin-top': '15px'})
    ], className="control-panel"),
    
    # Charts Container
    html.Div([
        # Altitude Chart
        html.Div([
            html.Div([
                html.H3("Altitude Profile", className="chart-title", style={'flex': '1', 'margin': '0'}),
                html.Button("⛶", id='maximize-altitude-btn', title='Maximize Chart', 
                           style={'background': 'none', 'border': 'none', 'color': '#58a6ff', 
                                 'cursor': 'pointer', 'font-size': '16px', 'padding': '4px'})
            ], style={'display': 'flex', 'align-items': 'center', 'justify-content': 'space-between', 
                     'border-bottom': '1px solid #30363d', 'padding-bottom': '8px', 'margin-bottom': '12px'}),
            dcc.Graph(id='altitude-chart', style={'height': 'calc(100% - 40px)'})
        ], className="chart-panel"),
        
        # Vertical Velocity Chart  
        html.Div([
            html.Div([
                html.H3("Vertical Velocity", className="chart-title", style={'flex': '1', 'margin': '0'}),
                html.Button("⛶", id='maximize-velocity-btn', title='Maximize Chart', 
                           style={'background': 'none', 'border': 'none', 'color': '#58a6ff', 
                                 'cursor': 'pointer', 'font-size': '16px', 'padding': '4px'})
            ], style={'display': 'flex', 'align-items': 'center', 'justify-content': 'space-between', 
                     'border-bottom': '1px solid #30363d', 'padding-bottom': '8px', 'margin-bottom': '12px'}),
            dcc.Graph(id='velocity-chart', style={'height': 'calc(100% - 40px)'})
        ], className="chart-panel"),
        
        # Trajectory Map
        html.Div([
            html.Div([
                html.H3("Lateral Trajectory", className="chart-title", style={'flex': '1', 'margin': '0'}),
                html.Button("⛶", id='maximize-trajectory-btn', title='Maximize Chart', 
                           style={'background': 'none', 'border': 'none', 'color': '#58a6ff', 
                                 'cursor': 'pointer', 'font-size': '16px', 'padding': '4px'})
            ], style={'display': 'flex', 'align-items': 'center', 'justify-content': 'space-between', 
                     'border-bottom': '1px solid #30363d', 'padding-bottom': '8px', 'margin-bottom': '12px'}),
            dcc.Graph(id='trajectory-map', style={'height': 'calc(100% - 40px)'})
        ], className="chart-panel"),
        
        # Wind Profile
        html.Div([
            html.Div([
                html.H3("Wind Profile by Altitude", className="chart-title", style={'flex': '1', 'margin': '0'}),
                html.Button("⛶", id='maximize-wind-btn', title='Maximize Chart', 
                           style={'background': 'none', 'border': 'none', 'color': '#58a6ff', 
                                 'cursor': 'pointer', 'font-size': '16px', 'padding': '4px'})
            ], style={'display': 'flex', 'align-items': 'center', 'justify-content': 'space-between', 
                     'border-bottom': '1px solid #30363d', 'padding-bottom': '8px', 'margin-bottom': '12px'}),
            dcc.Graph(id='wind-profile', style={'height': 'calc(100% - 40px)'})
        ], className="chart-panel")
    ], className="charts-container"),
    
    # Auto-refresh interval
    dcc.Interval(
        id='interval-component',
        interval=Config.UPDATE_INTERVAL * 1000,  # in milliseconds
        n_intervals=0
    ),
    
    # Store for tracking state
    dcc.Store(id='tracking-state', data={'tracked_balloons': {}, 'selected_balloons': []}),
    dcc.Store(id='maximized-chart-state', data={'visible': False, 'chart_type': None}),
    
    # Raw Data Modal
    html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.H3(id='raw-data-title', children='Raw ADSB Data', style={'margin': '0', 'color': '#58a6ff'}),
                    html.Button('×', id='close-modal', style={
                        'background': 'none', 'border': 'none', 'font-size': '24px',
                        'color': '#8b949e', 'cursor': 'pointer', 'float': 'right'
                    })
                ], style={'display': 'flex', 'justify-content': 'space-between', 'align-items': 'center', 'margin-bottom': '20px'}),
                
                html.Pre(id='raw-data-content', style={
                    'background': '#0d1117', 
                    'border': '1px solid #30363d',
                    'border-radius': '6px',
                    'padding': '16px',
                    'color': '#e6edf3',
                    'font-family': 'Monaco, Consolas, monospace',
                    'font-size': '12px',
                    'white-space': 'pre-wrap',
                    'max-height': '400px',
                    'overflow-y': 'auto'
                })
            ], style={
                'background': '#21262d',
                'padding': '24px',
                'border-radius': '12px',
                'border': '1px solid #30363d',
                'width': '600px',
                'max-width': '90vw',
                'max-height': '80vh',
                'overflow': 'auto'
            })
        ], style={
            'display': 'flex',
            'justify-content': 'center',
            'align-items': 'center',
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '100%',
            'height': '100%',
            'background': 'rgba(0, 0, 0, 0.7)',
            'z-index': '1000'
        })
    ], id='raw-data-modal', style={'display': 'none'}),
    
    # Maximized Chart Modal
    html.Div([
        html.Div([
            html.Div([
                html.H3(id='maximized-chart-title', style={'margin': '0 0 16px 0', 'color': '#e6edf3'}),
                html.Button('×', id='close-maximized-chart', style={
                    'position': 'absolute',
                    'top': '16px',
                    'right': '16px',
                    'background': 'none',
                    'border': 'none',
                    'color': '#e6edf3',
                    'font-size': '24px',
                    'cursor': 'pointer',
                    'padding': '0',
                    'width': '32px',
                    'height': '32px',
                    'display': 'flex',
                    'align-items': 'center',
                    'justify-content': 'center'
                })
            ], style={'position': 'relative', 'margin-bottom': '16px'}),
            dcc.Graph(id='maximized-chart', style={'height': '70vh', 'width': '100%'})
        ], style={
            'background': '#21262d',
            'padding': '24px',
            'border-radius': '12px',
            'border': '1px solid #30363d',
            'width': '95vw',
            'max-width': '95vw',
            'height': '85vh',
            'max-height': '85vh',
            'position': 'relative'
        })
    ], style={
        'display': 'flex',
        'justify-content': 'center',
        'align-items': 'center',
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'background': 'rgba(0, 0, 0, 0.8)',
        'z-index': '1001',
        'display': 'none'
    }, id='maximized-chart-modal')
])

# Callbacks
@app.callback(
    [Output('tracking-state', 'data'),
     Output('balloon-list', 'children'),
     Output('status-display', 'children'),
     Output('icao-input', 'value')],
    [Input('add-balloon-btn', 'n_clicks'),
     Input('stop-all-btn', 'n_clicks'), 
     Input('mock-btn', 'n_clicks'),
     Input('select-all-btn', 'n_clicks'),
     Input('deselect-all-btn', 'n_clicks'),
     Input('find-balloons-btn', 'n_clicks')],
    [State('icao-input', 'value'),
     State('tracking-state', 'data')]
)
def update_tracking_state(add_clicks, stop_all_clicks, mock_clicks, select_all_clicks, deselect_all_clicks, find_balloons_clicks, icao, current_state):
    global tracked_balloons, selected_balloons
    
    ctx = callback_context
    if not ctx.triggered:
        return current_state, create_balloon_list(current_state), get_multi_balloon_status(current_state), ''
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Initialize state if empty
    if not current_state:
        current_state = {'tracked_balloons': {}, 'selected_balloons': []}
    
    tracked = current_state.get('tracked_balloons', {})
    selected = current_state.get('selected_balloons', [])
    
    if button_id == 'add-balloon-btn' and icao:
        # Add new balloon to tracking
        icao = icao.lower().strip()
        if icao not in tracked:
            # Create new data collector for this balloon
            balloon_collector = DataCollector.get_instance()
            balloon_collector.add_tracked_aircraft(icao, None, "Multi-balloon tracking")
            if not balloon_collector.running:
                balloon_collector.start_collection()
            
            # Store only JSON-serializable data in Dash store
            tracked[icao] = {
                'added_time': datetime.now().isoformat(),
                'status': 'active'
            }
            # Keep collector objects in global variable (not in Dash store)
            tracked_balloons[icao] = balloon_collector
            
            # Auto-select new balloon
            if icao not in selected:
                selected.append(icao)
                selected_balloons.add(icao)
        
        new_state = {'tracked_balloons': tracked, 'selected_balloons': selected}
        return new_state, create_balloon_list(new_state), get_multi_balloon_status(new_state), ''
        
    elif button_id == 'stop-all-btn':
        # Stop all tracking and clean up resources
        for icao, balloon_collector in tracked_balloons.items():
            if hasattr(balloon_collector, 'cleanup'):
                balloon_collector.cleanup()
            else:
                balloon_collector.stop_collection()
        tracked_balloons.clear()
        selected_balloons.clear()
        new_state = {'tracked_balloons': {}, 'selected_balloons': []}
        return new_state, create_balloon_list(new_state), get_multi_balloon_status(new_state), ''
        
    elif button_id == 'mock-btn':
        # Add mock balloon
        mock_icao = 'mock123'
        if mock_icao not in tracked:
            generate_mock_data(mock_icao)
            tracked[mock_icao] = {
                'added_time': datetime.now().isoformat(),
                'status': 'mock'
            }
            # No collector object stored for mock data
            if mock_icao not in selected:
                selected.append(mock_icao)
        
        new_state = {'tracked_balloons': tracked, 'selected_balloons': selected}
        return new_state, create_balloon_list(new_state), get_multi_balloon_status(new_state), ''
        
    elif button_id == 'select-all-btn':
        # Select all tracked balloons
        selected = list(tracked.keys())
        selected_balloons = set(selected)
        new_state = {'tracked_balloons': tracked, 'selected_balloons': selected}
        return new_state, create_balloon_list(new_state), get_multi_balloon_status(new_state), ''
        
    elif button_id == 'deselect-all-btn':
        # Deselect all balloons
        selected = []
        selected_balloons.clear()
        new_state = {'tracked_balloons': tracked, 'selected_balloons': selected}
        return new_state, create_balloon_list(new_state), get_multi_balloon_status(new_state), ''
    
    elif button_id == 'find-balloons-btn':
        # Search for all balloons in region using ADSB Exchange
        try:
            from real_adsb_client import BalloonSpecificADSBClient
            balloon_client = BalloonSpecificADSBClient()
            
            # Define search region (Colorado/New Mexico area where balloons are common)
            lat_min, lat_max = 35.0, 40.0
            lon_min, lon_max = -110.0, -100.0
            
            print(f"🔍 Searching for balloons in Colorado/New Mexico region...")
            print(f"   Region: {lat_min}°N to {lat_max}°N, {lon_min}°W to {lon_max}°W")
            
            # Find balloons in the region
            found_balloons = balloon_client.find_balloons_in_region(lat_min, lat_max, lon_min, lon_max)
            
            balloon_count = 0
            for balloon in found_balloons:
                icao_lower = balloon.get('icao24', '').lower()
                if icao_lower and icao_lower not in tracked:
                    # Add this balloon to tracking
                    balloon_collector = DataCollector.get_instance()
                    callsign = balloon.get('callsign', '').strip() or None
                    description = f"Auto-discovered balloon - Alt: {balloon.get('altitude', 'Unknown')}m"
                    
                    balloon_collector.add_tracked_aircraft(icao_lower, callsign, description)
                    if not balloon_collector.running:
                        balloon_collector.start_collection()
                    
                    tracked[icao_lower] = {
                        'added_time': datetime.now().isoformat(),
                        'status': 'active'
                    }
                    # Add to global tracking
                    tracked_balloons[icao_lower] = balloon_collector
                    selected.append(icao_lower)
                    selected_balloons.add(icao_lower)
                    balloon_count += 1
                    
                    alt_display = f"{balloon.get('altitude', 'Unknown')}m" if balloon.get('altitude') else "Unknown alt"
                    speed_display = f"{balloon.get('velocity', 'Unknown')}m/s" if balloon.get('velocity') else "Unknown speed"
                    print(f"🎈 Found and added balloon: {icao_lower.upper()} ({callsign or 'No callsign'}) - {alt_display}, {speed_display}")
            
            if balloon_count > 0:
                print(f"✅ Added {balloon_count} balloons to tracking from regional search")
                new_state = {'tracked_balloons': tracked, 'selected_balloons': selected}
                return new_state, create_balloon_list(new_state), get_multi_balloon_status(new_state), ''
            else:
                print("ℹ️ No new balloons found in region or all found balloons already tracked")
                
        except Exception as e:
            print(f"❌ Error searching for balloons in region: {e}")
            print("   Make sure ADSB Exchange API key is configured (RAPIDAPI_KEY)")
    
    return current_state, create_balloon_list(current_state), get_multi_balloon_status(current_state), ''

# Callback for handling balloon selection checkboxes
@app.callback(
    Output('tracking-state', 'data', allow_duplicate=True),
    [Input({'type': 'balloon-checkbox', 'index': dash.dependencies.ALL}, 'value'),
     Input({'type': 'remove-balloon', 'index': dash.dependencies.ALL}, 'n_clicks')],
    [State('tracking-state', 'data')],
    prevent_initial_call=True
)
def handle_balloon_selection(checkbox_values, remove_clicks, current_state):
    global tracked_balloons, selected_balloons
    
    ctx = callback_context
    if not ctx.triggered:
        return current_state
    
    tracked = current_state.get('tracked_balloons', {})
    selected = current_state.get('selected_balloons', [])
    
    # Handle checkbox changes
    if ctx.triggered[0]['prop_id'].find('balloon-checkbox') != -1:
        # Update selected balloons based on checkbox states
        selected = []
        selected_balloons.clear()
        
        for i, icao in enumerate(tracked.keys()):
            if i < len(checkbox_values) and checkbox_values[i]:
                selected.append(icao)
                selected_balloons.add(icao)
    
    # Handle remove button clicks
    elif ctx.triggered[0]['prop_id'].find('remove-balloon') != -1:
        # Find which balloon to remove
        trigger_info = ctx.triggered[0]['prop_id']
        try:
            import json
            balloon_info = json.loads(trigger_info.split('.')[0])
            icao_to_remove = balloon_info['index']
            
            if icao_to_remove in tracked:
                # Stop and clean up collector if it exists in global variable
                if icao_to_remove in tracked_balloons:
                    balloon_collector = tracked_balloons[icao_to_remove]
                    if hasattr(balloon_collector, 'cleanup'):
                        balloon_collector.cleanup()
                    else:
                        balloon_collector.stop_collection()
                    del tracked_balloons[icao_to_remove]
                
                # Remove from tracking state
                del tracked[icao_to_remove]
                
                # Remove from selection
                if icao_to_remove in selected:
                    selected.remove(icao_to_remove)
                selected_balloons.discard(icao_to_remove)
        except:
            pass  # Ignore parsing errors
    
    return {'tracked_balloons': tracked, 'selected_balloons': selected}

# Callback to update wind reference balloon dropdown options
@app.callback(
    [Output('wind-reference-balloon', 'options'),
     Output('wind-reference-balloon', 'value')],
    [Input('tracking-state', 'data')]
)
def update_wind_reference_options(tracking_state):
    tracked = tracking_state.get('tracked_balloons', {})
    
    if not tracked:
        return [], None
    
    options = [
        {'label': f'{icao.upper()} ({data.get("status", "active")})', 'value': icao}
        for icao, data in tracked.items()
    ]
    
    # Keep current value if it's still valid, otherwise select first balloon
    current_value = None
    if tracked:
        current_value = list(tracked.keys())[0]  # Default to first balloon
    
    return options, current_value


@app.callback(
    [Output('altitude-chart', 'figure'),
     Output('velocity-chart', 'figure'),
     Output('trajectory-map', 'figure'),
     Output('wind-profile', 'figure')],
    [Input('interval-component', 'n_intervals'),
     Input('altitude-units', 'value'),
     Input('altitude-source', 'value'),
     Input('altitude-y-min', 'value'),
     Input('altitude-y-max', 'value'),
     Input('velocity-y-min', 'value'),
     Input('velocity-y-max', 'value'),
     Input('wind-y-min', 'value'),
     Input('wind-y-max', 'value'),
     Input('wind-time-filter', 'value'),
     Input('wind-distance-filter', 'value'),
     Input('wind-reference-balloon', 'value')],
    [State('tracking-state', 'data')]
)
def update_charts(n_intervals, altitude_units, altitude_source, 
                 alt_y_min, alt_y_max, vel_y_min, vel_y_max, wind_y_min, wind_y_max,
                 wind_time_filter, wind_distance_filter, wind_reference_balloon, tracking_state):
    # Handle multi-balloon data
    selected_balloons_list = tracking_state.get('selected_balloons', [])
    
    # Create empty figures
    empty_fig = create_empty_figure()
    
    if not selected_balloons_list:
        return empty_fig, empty_fig, empty_fig, empty_fig
    
    try:
        # Create multi-balloon figures
        alt_fig = create_multi_balloon_altitude_chart(selected_balloons_list, altitude_units, altitude_source, alt_y_min, alt_y_max)
        vel_fig = create_multi_balloon_velocity_chart(selected_balloons_list, altitude_units, vel_y_min, vel_y_max)
        traj_fig = create_multi_balloon_trajectory_map(selected_balloons_list)
        wind_fig = create_multi_balloon_wind_profile(selected_balloons_list, altitude_source, altitude_units, wind_y_min, wind_y_max, wind_time_filter, wind_distance_filter, wind_reference_balloon)
        
        return alt_fig, vel_fig, traj_fig, wind_fig
        
    except Exception as e:
        import traceback
        print(f"Error updating multi-balloon charts: {e}")
        print(f"Full traceback: {traceback.format_exc()}")
        return empty_fig, empty_fig, empty_fig, empty_fig

def get_status_display(state):
    """Generate status display based on tracking state"""
    if not state.get('active'):
        return [
            html.Span("●", className="status-indicator status-offline"),
            html.Span("No tracking active", style={'color': '#8b949e'})
        ]
    
    icao = state.get('icao', 'Unknown')
    is_mock = state.get('mock', False)
    
    if is_mock:
        return [
            html.Span("●", className="status-indicator status-warning"),
            html.Span(f"Mock data mode - {icao}", style={'color': '#d29922'})
        ]
    
    # Check if we have recent data
    latest_data = db.get_latest_data(icao)
    if latest_data and (datetime.now().timestamp() - latest_data['timestamp']) < 300:  # 5 minutes
        return [
            html.Span("●", className="status-indicator status-online"),
            html.Span(f"Tracking {icao.upper()} - Data: {datetime.fromtimestamp(latest_data['timestamp']).strftime('%H:%M:%S')}", 
                     style={'color': '#3fb950'})
        ]
    else:
        return [
            html.Span("●", className="status-indicator status-warning"),
            html.Span(f"Tracking {icao.upper()} - No recent data", style={'color': '#d29922'})
        ]

def create_empty_figure():
    """Create empty figure with dark theme"""
    fig = go.Figure()
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='#161b22',
        plot_bgcolor='#0d1117',
        font=dict(color='#c9d1d9'),
        xaxis=dict(gridcolor='#30363d'),
        yaxis=dict(gridcolor='#30363d'),
        annotations=[
            dict(
                text="No data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False,
                font=dict(color='#8b949e', size=16)
            )
        ]
    )
    return fig

def create_altitude_chart(aircraft_data, altitude_units='m', altitude_source='altitude', y_min=None, y_max=None):
    """Create altitude vs time chart with configurable units and source"""
    if not aircraft_data:
        return create_empty_figure()
    
    df = pd.DataFrame(aircraft_data)
    # Use the selected altitude source, fallback to barometric if geo not available
    if altitude_source == 'geo_altitude' and 'geo_altitude' in df.columns:
        df = df.dropna(subset=['geo_altitude', 'timestamp'])
        altitude_col = 'geo_altitude'
        source_label = 'Geometric (GPS)'
    else:
        df = df.dropna(subset=['altitude', 'timestamp'])
        altitude_col = 'altitude'
        source_label = 'Barometric'
    
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.sort_values('timestamp')
    
    # Convert altitude based on units
    if altitude_units == 'ft':
        df['display_altitude'] = df[altitude_col] * 3.28084  # meters to feet
        unit_label = 'feet'
        unit_abbr = 'ft'
    else:
        df['display_altitude'] = df[altitude_col]  # already in meters
        unit_label = 'meters'
        unit_abbr = 'm'
    
    fig = go.Figure()
    
    # Altitude line
    fig.add_trace(go.Scatter(
        x=df['datetime'],
        y=df['display_altitude'],
        mode='lines+markers',
        name=f'{source_label} Altitude ({unit_abbr})',
        line=dict(color='#58a6ff', width=2),
        marker=dict(size=4, color='#58a6ff'),
        hovertemplate=f'<b>%{{x}}</b><br>{source_label} Altitude: %{{y:,.0f}} {unit_abbr}<extra></extra>'
    ))
    
    # Current position marker
    if len(df) > 0:
        latest = df.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[latest['datetime']],
            y=[latest['display_altitude']],
            mode='markers',
            name='Current',
            marker=dict(size=12, color='#f85149', symbol='circle'),
            hovertemplate=f'<b>Current</b><br>%{{x}}<br>Altitude: %{{y:,.0f}} {unit_abbr}<extra></extra>'
        ))
    
    # Set y-axis configuration
    yaxis_config = dict(title=f'{source_label} Altitude ({unit_label})', gridcolor='#30363d')
    if y_min is not None or y_max is not None:
        yaxis_config['range'] = [y_min, y_max]
    
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='#161b22',
        plot_bgcolor='#0d1117',
        font=dict(color='#c9d1d9'),
        xaxis=dict(title='Time', gridcolor='#30363d'),
        yaxis=yaxis_config,
        showlegend=False,
        margin=dict(l=60, r=20, t=20, b=60)
    )
    
    return fig

def create_velocity_chart(icao, altitude_units='m', y_min=None, y_max=None):
    """Create velocity chart showing both vertical rate and ground speed from session data"""
    try:
        # Get session data only (no historical data)
        aircraft_data = db.get_aircraft_data_since_session(icao)
        
        if not aircraft_data:
            return create_empty_figure()
        
        df = pd.DataFrame(aircraft_data)
        df = df.dropna(subset=['timestamp'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.sort_values('timestamp')
        
        if len(df) == 0:
            return create_empty_figure()
        
        fig = go.Figure()
        
        # Vertical velocity from raw ADSB data (convert based on unit preference)
        if 'vertical_rate' in df.columns and df['vertical_rate'].notna().any():
            # ADSB vertical_rate is typically in ft/min, convert based on preference
            vertical_rates = df['vertical_rate'].fillna(0)
            
            if altitude_units == 'ft':
                # Convert ft/min to ft/s (divide by 60)
                vertical_rates_display = vertical_rates / 60.0
                unit_label = 'ft/s'
            else:
                # Convert ft/min to m/s (1 ft/min = 0.00508 m/s)
                vertical_rates_display = vertical_rates * 0.00508
                unit_label = 'm/s'
            
            colors = ['#3fb950' if v >= 0 else '#f85149' for v in vertical_rates_display]
            fig.add_trace(go.Scatter(
                x=df['datetime'],
                y=vertical_rates_display,
                mode='lines+markers',
                name='Vertical Rate',
                line=dict(color='#58a6ff', width=2),
                marker=dict(size=4, color=colors),
                fill='tozeroy',
                fillcolor='rgba(88, 166, 255, 0.1)',
                hovertemplate=f'<b>%{{x}}</b><br>Vertical Rate: %{{y:.2f}} {unit_label}<extra></extra>'
            ))
            
            # Zero line
            fig.add_hline(y=0, line_dash="dash", line_color="#8b949e", opacity=0.5)
            y_title = f'Vertical Rate ({unit_label})'
        else:
            # Fallback to ground speed if no vertical rate
            if 'velocity' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df['datetime'],
                    y=df['velocity'],
                    mode='lines+markers',
                    name='Ground Speed',
                    line=dict(color='#58a6ff', width=2),
                    marker=dict(size=4, color='#58a6ff'),
                    hovertemplate='<b>%{x}</b><br>Ground Speed: %{y:.1f} m/s<extra></extra>'
                ))
                y_title = 'Ground Speed (m/s)'
            else:
                return create_empty_figure()
        
        # Set y-axis configuration
        yaxis_config = dict(title=y_title, gridcolor='#30363d')
        if y_min is not None or y_max is not None:
            yaxis_config['range'] = [y_min, y_max]
        
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='#161b22',
            plot_bgcolor='#0d1117',
            font=dict(color='#c9d1d9'),
            xaxis=dict(title='Time', gridcolor='#30363d'),
            yaxis=yaxis_config,
            showlegend=False,
            margin=dict(l=60, r=20, t=20, b=60)
        )
        
        return fig
        
    except Exception as e:
        print(f"Error creating velocity chart: {e}")
        return create_empty_figure()

def create_trajectory_map(aircraft_data):
    """Create 2D trajectory map"""
    if not aircraft_data:
        return create_empty_figure()
    
    df = pd.DataFrame(aircraft_data)
    df = df.dropna(subset=['latitude', 'longitude', 'altitude'])
    df = df.sort_values('timestamp')
    
    if len(df) == 0:
        return create_empty_figure()
    
    fig = go.Figure()
    
    # Trajectory path colored by altitude
    fig.add_trace(go.Scattermapbox(
        lat=df['latitude'],
        lon=df['longitude'],
        mode='lines+markers',
        marker=dict(
            size=6,
            color=df['altitude'],
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="Altitude (m)")
        ),
        line=dict(width=2, color='#58a6ff'),
        name='Trajectory'
    ))
    
    # Current position
    if len(df) > 0:
        latest = df.iloc[-1]
        fig.add_trace(go.Scattermapbox(
            lat=[latest['latitude']],
            lon=[latest['longitude']],
            mode='markers',
            marker=dict(size=15, color='#f85149', symbol='circle'),
            name='Current Position'
        ))
    
    # Calculate center and zoom
    center_lat = df['latitude'].mean()
    center_lon = df['longitude'].mean()
    
    fig.update_layout(
        mapbox=dict(
            style='carto-darkmatter',
            center=dict(lat=center_lat, lon=center_lon),
            zoom=8
        ),
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='#161b22',
        uirevision='trajectory_map'  # Preserve user interactions (zoom, pan)
    )
    
    return fig

def create_wind_profile(icao, altitude_source='altitude', y_min=None, y_max=None, time_filter_hours=None, distance_filter_km=None):
    """Create wind profile chart: Altitude (y) vs Wind Direction (x) scatter plot"""
    try:
        # Get aircraft data from session and calculate wind from trajectory
        aircraft_data = db.get_aircraft_data_since_session(icao)
        
        if len(aircraft_data) < 2:
            return create_empty_figure()
        
        # Calculate wind vectors from GPS trajectory
        wind_vectors = []
        df = pd.DataFrame(aircraft_data)
        
        # Use the selected altitude source, fallback to barometric if geo not available
        if altitude_source == 'geo_altitude' and 'geo_altitude' in df.columns:
            altitude_col = 'geo_altitude'
            source_label = 'Geometric (GPS)'
        else:
            altitude_col = 'altitude'
            source_label = 'Barometric'
        
        df = df.dropna(subset=['latitude', 'longitude', altitude_col, 'timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Apply time filter if specified (convert minutes to seconds)
        if time_filter_hours is not None and time_filter_hours > 0:
            from datetime import datetime, timedelta
            cutoff_time = datetime.now().timestamp() - (time_filter_hours * 60)  # minutes to seconds
            df = df[df['timestamp'] >= cutoff_time]
            print(f"🕒 Time filter: {len(df)} points in last {time_filter_hours} minutes")
        
        # Apply distance filter if specified
        if distance_filter_km is not None and distance_filter_km > 0 and len(df) > 0:
            from geopy.distance import geodesic
            # Use the most recent position as reference
            latest_point = df.iloc[-1]
            ref_lat, ref_lon = latest_point['latitude'], latest_point['longitude']
            
            # Calculate distances and filter
            distances = []
            for _, row in df.iterrows():
                try:
                    dist = geodesic((ref_lat, ref_lon), (row['latitude'], row['longitude'])).kilometers
                    distances.append(dist)
                except:
                    distances.append(float('inf'))  # Invalid coordinates
            
            df['distance_km'] = distances
            df = df[df['distance_km'] <= distance_filter_km]
            print(f"📍 Distance filter: {len(df)} points within {distance_filter_km} km")
        
        if len(df) < 2:
            return create_empty_figure()
        
        # Calculate wind from consecutive GPS points
        from geopy.distance import geodesic
        import math
        
        for i in range(1, len(df)):
            prev_point = df.iloc[i-1]
            curr_point = df.iloc[i]
            
            dt = curr_point['timestamp'] - prev_point['timestamp']
            if dt <= 0 or dt > 300:  # Skip invalid time differences
                continue
            
            # Calculate movement vector (wind effect on balloon)
            prev_pos = (prev_point['latitude'], prev_point['longitude'])
            curr_pos = (curr_point['latitude'], curr_point['longitude'])
            
            distance = geodesic(prev_pos, curr_pos).meters
            
            # Calculate bearing (wind direction)
            lat1, lon1 = math.radians(prev_point['latitude']), math.radians(prev_point['longitude'])
            lat2, lon2 = math.radians(curr_point['latitude']), math.radians(curr_point['longitude'])
            
            dlon = lon2 - lon1
            y = math.sin(dlon) * math.cos(lat2)
            x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
            bearing = math.degrees(math.atan2(y, x))
            bearing = (bearing + 360) % 360
            
            horizontal_speed = distance / dt  # m/s
            avg_altitude = (prev_point[altitude_col] + curr_point[altitude_col]) / 2
            
            if horizontal_speed > 1:  # Only include significant movement
                wind_vectors.append({
                    'altitude': avg_altitude,
                    'wind_direction': bearing,
                    'wind_speed': horizontal_speed
                })
        
        if not wind_vectors:
            return create_empty_figure()
        
        fig = go.Figure()
        
        # Create scatter plot: altitude vs wind direction
        altitudes = [v['altitude'] for v in wind_vectors]
        directions = [v['wind_direction'] for v in wind_vectors]
        speeds = [v['wind_speed'] for v in wind_vectors]
        
        # Use wind direction data as-is (0-360 degrees)
        # Color points by wind speed
        fig.add_trace(go.Scatter(
            x=directions,
            y=altitudes,
            mode='markers',
            name='Wind Profile',
            marker=dict(
                size=5,  # Reduced from 8
                color=speeds,
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(
                    title='Wind Speed (m/s)',
                    titlefont=dict(color='#c9d1d9'),
                    tickfont=dict(color='#c9d1d9')
                ),
                line=dict(width=1, color='#c9d1d9')
            ),
            hovertemplate=f'<b>Wind Profile</b><br>Direction: %{{x:.0f}}°<br>{source_label} Altitude: %{{y:.0f}}m<br>Speed: %{{marker.color:.1f}} m/s<extra></extra>'
        ))
        
        # Add cardinal direction reference lines
        cardinal_directions = [0, 90, 180, 270]  # N, E, S, W
        cardinal_labels = ['N (0°)', 'E (90°)', 'S (180°)', 'W (270°)']
        
        for direction, label in zip(cardinal_directions, cardinal_labels):
            fig.add_vline(
                x=direction,
                line_dash="dot",
                line_color="#8b949e",
                opacity=0.5,
                annotation_text=label,
                annotation_position="top",
                annotation_font_size=10,
                annotation_font_color="#8b949e"
            )
        
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='#161b22',
            plot_bgcolor='#0d1117',
            font=dict(color='#c9d1d9'),
            xaxis=dict(
                title='Wind Direction (degrees)',
                gridcolor='#30363d',
                range=[-20, 380],  # Fixed range with padding on both sides
                tickmode='linear',
                dtick=45,
                tickvals=list(range(0, 361, 45)),
                ticktext=[f"{d}°" for d in range(0, 361, 45)],
                showgrid=True,
                zeroline=False,
                fixedrange=True  # Disable zooming/panning on x-axis
            ),
            yaxis=dict(title=f'{source_label} Altitude (m)', gridcolor='#30363d', 
                      range=[y_min, y_max] if (y_min is not None and y_max is not None) else None,  # Auto-scale if no limits set
                      fixedrange=False),  # Allow zooming on y-axis
            showlegend=False,
            margin=dict(l=60, r=20, t=20, b=60),
            dragmode='zoom'  # Allow zooming but disable panning
        )
        
        return fig
        
    except Exception as e:
        print(f"Error creating wind profile: {e}")
        return create_empty_figure()

def generate_mock_data(icao):
    """Generate mock balloon data for testing"""
    import random
    
    # Clear existing data
    try:
        with sqlite3.connect(db.db_path) as conn:
            conn.execute('DELETE FROM aircraft_data WHERE icao24 = ?', (icao,))
            conn.commit()
    except:
        pass
    
    # Generate ascending balloon trajectory
    base_time = datetime.now().timestamp() - 3600  # Start 1 hour ago
    base_lat = 42.3601  # Boston area
    base_lon = -71.0589
    
    for i in range(72):  # 72 points over 1 hour (50 second intervals)
        timestamp = base_time + (i * 50)
        
        # Simulate balloon ascent with wind drift
        altitude = 1000 + (i * 600) + random.uniform(-200, 200)  # Ascending
        lat_drift = (i * 0.001) + random.uniform(-0.0005, 0.0005)  # Wind drift
        lon_drift = (i * 0.0008) + random.uniform(-0.0005, 0.0005)
        
        mock_data = {
            'icao24': icao,
            'callsign': 'MOCK001',
            'time_position': timestamp,
            'last_contact': timestamp,
            'longitude': base_lon + lon_drift,
            'latitude': base_lat + lat_drift,
            'altitude': altitude,
            'on_ground': False,
            'velocity': random.uniform(15, 45),
            'true_track': random.uniform(45, 135),  # Generally eastward
            'vertical_rate': random.uniform(5, 15),  # Ascending
        }
        
        db.add_aircraft_data(mock_data)
    
    print(f"Generated mock data for {icao}")


# Helper functions for multi-balloon support
def create_balloon_list(tracking_state):
    """Create the balloon list UI with checkboxes and remove buttons"""
    tracked = tracking_state.get('tracked_balloons', {})
    selected = tracking_state.get('selected_balloons', [])
    
    if not tracked:
        return [html.P("No balloons tracked yet", style={'color': '#8b949e', 'font-style': 'italic', 'margin': '8px 0'})]
    
    balloon_items = []
    for icao, balloon_data in tracked.items():
        status = balloon_data.get('status', 'active')
        status_color = '#3fb950' if status == 'active' else '#d29922' if status == 'mock' else '#f85149'
        status_icon = '🟢' if status == 'active' else '🟡' if status == 'mock' else '🔴'
        
        balloon_items.append(
            html.Div([
                dcc.Checklist(
                    id={'type': 'balloon-checkbox', 'index': icao},
                    options=[{'label': '', 'value': icao}],
                    value=[icao] if icao in selected else [],
                    style={'display': 'inline-block', 'margin-right': '8px'}
                ),
                html.Span(f"{status_icon} {icao.upper()}", style={'color': status_color, 'font-weight': '600'}),
                html.Button("📊", 
                    id={'type': 'raw-data-btn', 'index': icao},
                    title='Show raw ADSB data',
                    style={
                        'background': 'none', 'border': 'none', 'color': '#58a6ff', 
                        'cursor': 'pointer', 'margin-left': '8px', 'font-size': '12px'
                    }
                ),
                html.Button("❌", 
                    id={'type': 'remove-balloon', 'index': icao},
                    style={
                        'background': 'none', 'border': 'none', 'color': '#f85149', 
                        'cursor': 'pointer', 'margin-left': '4px', 'font-size': '12px'
                    }
                )
            ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '4px'})
        )
    
    return balloon_items

def get_multi_balloon_status(tracking_state):
    """Get status display for multi-balloon tracking"""
    tracked = tracking_state.get('tracked_balloons', {})
    selected = tracking_state.get('selected_balloons', [])
    
    if not tracked:
        return [
            html.Span("●", className="status-indicator status-offline"),
            html.Span("No balloons tracked", style={'color': '#8b949e'})
        ]
    
    active_count = len([b for b in tracked.values() if b.get('status') == 'active'])
    mock_count = len([b for b in tracked.values() if b.get('status') == 'mock'])
    selected_count = len(selected)
    
    status_parts = []
    if active_count > 0:
        status_parts.append(f"{active_count} active")
    if mock_count > 0:
        status_parts.append(f"{mock_count} mock")
    
    status_text = ", ".join(status_parts) if status_parts else "No active balloons"
    status_class = "status-online" if active_count > 0 else "status-warning" if mock_count > 0 else "status-offline"
    
    return [
        html.Span("●", className=f"status-indicator {status_class}"),
        html.Span(f"{status_text} | {selected_count} selected for display", style={'color': '#e6edf3'})
    ]

def convert_altitude(altitude, from_unit, to_unit):
    """Convert altitude between meters and feet"""
    if from_unit == to_unit or altitude is None:
        return altitude
    
    if from_unit == 'm' and to_unit == 'ft':
        return altitude * 3.28084  # meters to feet
    elif from_unit == 'ft' and to_unit == 'm':
        return altitude / 3.28084  # feet to meters
    
    return altitude

def create_multi_balloon_altitude_chart(selected_balloons_list, altitude_units='m', altitude_source='altitude', y_min=None, y_max=None):
    """Create altitude chart with data from multiple selected balloons"""
    fig = go.Figure()
    
    if not selected_balloons_list:
        return create_empty_figure()
    
    colors = ['#58a6ff', '#3fb950', '#f85149', '#d29922', '#da70d6', '#ff6347', '#32cd32', '#ffa500']
    
    for i, icao in enumerate(selected_balloons_list):
        aircraft_data = db.get_aircraft_data_since_session(icao)
        
        if not aircraft_data:
            continue
        
        df = pd.DataFrame(aircraft_data)
        df = df.dropna(subset=['timestamp'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.sort_values('timestamp')
        
        if len(df) == 0:
            continue
        
        # Get altitude data
        altitude_col = altitude_source if altitude_source in df.columns else 'altitude'
        if altitude_col not in df.columns:
            continue
        
        # Filter out rows with null altitude values
        df_alt = df.dropna(subset=[altitude_col])
        if len(df_alt) == 0:
            continue
            
        altitudes = df_alt[altitude_col]
        
        # Convert altitude units for display
        if altitude_units == 'ft':
            altitudes = altitudes * 3.28084  # Convert from meters to feet
            
        color = colors[i % len(colors)]
        
        fig.add_trace(go.Scatter(
            x=df_alt['datetime'],
            y=altitudes,
            mode='lines+markers',
            name=f'{icao.upper()}',
            line=dict(color=color, width=2),
            marker=dict(size=4, color=color),
            hovertemplate=f'<b>{icao.upper()}</b><br>%{{x}}<br>Altitude: %{{y:.0f}} {altitude_units}<extra></extra>'
        ))
    
    unit_label = "feet" if altitude_units == 'ft' else "meters"
    source_label = "Barometric" if altitude_source == 'altitude' else "GPS"
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e6edf3'),
        xaxis=dict(
            title='Time',
            gridcolor='#30363d',
            color='#e6edf3'
        ),
        yaxis=dict(
            title=f'{source_label} Altitude ({unit_label})',
            gridcolor='#30363d',
            color='#e6edf3',
            range=[y_min, y_max] if y_min is not None and y_max is not None else None
        ),
        margin=dict(l=50, r=20, t=20, b=50),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(33, 38, 45, 0.8)',
            bordercolor='#30363d',
            borderwidth=1
        )
    )
    
    return fig

def create_multi_balloon_velocity_chart(selected_balloons_list, altitude_units='m', y_min=None, y_max=None):
    """Create velocity chart with data from multiple selected balloons"""
    fig = go.Figure()
    
    if not selected_balloons_list:
        return create_empty_figure()
    
    colors = ['#58a6ff', '#3fb950', '#f85149', '#d29922', '#da70d6', '#ff6347', '#32cd32', '#ffa500']
    
    # Determine unit label for y-axis
    if altitude_units == 'ft':
        unit_label = 'ft/s'
    else:
        unit_label = 'm/s'
    
    for i, icao in enumerate(selected_balloons_list):
        aircraft_data = db.get_aircraft_data_since_session(icao)
        
        if not aircraft_data:
            continue
        
        df = pd.DataFrame(aircraft_data)
        df = df.dropna(subset=['timestamp'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.sort_values('timestamp')
        
        if len(df) == 0:
            continue
        
        color = colors[i % len(colors)]
        
        # Vertical velocity from raw ADSB data (convert based on unit preference)
        if 'vertical_rate' in df.columns and df['vertical_rate'].notna().any():
            # ADSB vertical_rate is typically in ft/min, convert based on preference
            vertical_rates = df['vertical_rate'].fillna(0)
            
            if altitude_units == 'ft':
                # Convert ft/min to ft/s (divide by 60)
                vertical_rates_display = vertical_rates / 60.0
            else:
                # Convert ft/min to m/s (1 ft/min = 0.00508 m/s)
                vertical_rates_display = vertical_rates * 0.00508
            
            fig.add_trace(go.Scatter(
                x=df['datetime'],
                y=vertical_rates_display,
                mode='lines+markers',
                name=f'{icao.upper()}',
                line=dict(color=color, width=2),
                marker=dict(size=4, color=color),
                hovertemplate=f'<b>{icao.upper()}</b><br>%{{x}}<br>Vertical Rate: %{{y:.2f}} {unit_label}<extra></extra>'
            ))
        elif 'velocity' in df.columns:
            # Fallback to ground speed if no vertical rate
            fig.add_trace(go.Scatter(
                x=df['datetime'],
                y=df['velocity'],
                mode='lines+markers',
                name=f'{icao.upper()} (Ground Speed)',
                line=dict(color=color, width=2),
                marker=dict(size=4, color=color),
                hovertemplate=f'<b>{icao.upper()}</b><br>%{{x}}<br>Ground Speed: %{{y:.1f}} m/s<extra></extra>'
            ))
    
    # Zero line for vertical velocity
    fig.add_hline(y=0, line_dash="dash", line_color="#8b949e", opacity=0.5)
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e6edf3'),
        xaxis=dict(
            title='Time',
            gridcolor='#30363d',
            color='#e6edf3'
        ),
        yaxis=dict(
            title=f'Vertical Rate ({unit_label})',
            gridcolor='#30363d',
            color='#e6edf3',
            range=[y_min, y_max] if y_min is not None and y_max is not None else None  # Auto-scale if no limits set
        ),
        margin=dict(l=50, r=20, t=20, b=50),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(33, 38, 45, 0.8)',
            bordercolor='#30363d',
            borderwidth=1
        )
    )
    
    return fig

def create_multi_balloon_trajectory_map(selected_balloons_list):
    """Create trajectory map with data from multiple selected balloons"""
    fig = go.Figure()
    
    if not selected_balloons_list:
        return create_empty_figure()
    
    colors = ['#58a6ff', '#3fb950', '#f85149', '#d29922', '#da70d6', '#ff6347', '#32cd32', '#ffa500']
    
    for i, icao in enumerate(selected_balloons_list):
        aircraft_data = db.get_aircraft_data_since_session(icao)
        
        if not aircraft_data:
            continue
        
        df = pd.DataFrame(aircraft_data)
        df = df.dropna(subset=['latitude', 'longitude'])
        df = df.sort_values('timestamp')
        
        if len(df) == 0:
            continue
        
        color = colors[i % len(colors)]
        
        # Plot trajectory
        fig.add_trace(go.Scattermapbox(
            lat=df['latitude'],
            lon=df['longitude'],
            mode='lines+markers',
            name=f'{icao.upper()}',
            line=dict(width=3, color=color),
            marker=dict(size=8, color=color),
            hovertemplate=f'<b>{icao.upper()}</b><br>Lat: %{{lat:.4f}}<br>Lon: %{{lon:.4f}}<extra></extra>'
        ))
        
        # Mark start and end points
        if len(df) > 0:
            # Start point
            fig.add_trace(go.Scattermapbox(
                lat=[df['latitude'].iloc[0]],
                lon=[df['longitude'].iloc[0]],
                mode='markers',
                name=f'{icao.upper()} Start',
                marker=dict(size=12, color='white', symbol='circle'),
                showlegend=False,
                hovertemplate=f'<b>{icao.upper()} Start</b><br>Lat: %{{lat:.4f}}<br>Lon: %{{lon:.4f}}<extra></extra>'
            ))
            
            # Current/end point
            fig.add_trace(go.Scattermapbox(
                lat=[df['latitude'].iloc[-1]],
                lon=[df['longitude'].iloc[-1]],
                mode='markers',
                name=f'{icao.upper()} Current',
                marker=dict(size=15, color=color, symbol='circle'),
                showlegend=False,
                hovertemplate=f'<b>{icao.upper()} Current</b><br>Lat: %{{lat:.4f}}<br>Lon: %{{lon:.4f}}<extra></extra>'
            ))
    
    # Calculate center point for all balloons
    all_lats = []
    all_lons = []
    for icao in selected_balloons_list:
        aircraft_data = db.get_aircraft_data_since_session(icao)
        if aircraft_data:
            df = pd.DataFrame(aircraft_data)
            df = df.dropna(subset=['latitude', 'longitude'])
            if len(df) > 0:
                all_lats.extend(df['latitude'].tolist())
                all_lons.extend(df['longitude'].tolist())
    
    if all_lats and all_lons:
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)
    else:
        center_lat, center_lon = 39.8283, -98.5795  # Center of USA
    
    fig.update_layout(
        mapbox=dict(
            style='open-street-map',
            center=dict(lat=center_lat, lon=center_lon),
            zoom=8
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(33, 38, 45, 0.8)',
            bordercolor='#30363d',
            borderwidth=1
        ),
        uirevision='trajectory_map'  # Preserve zoom/pan state
    )
    
    return fig

def create_multi_balloon_wind_profile(selected_balloons_list, altitude_source='altitude', altitude_units='m', y_min=None, y_max=None, time_filter_minutes=None, distance_filter_km=None, reference_balloon=None):
    """Create wind profile chart with data from multiple selected balloons with proper unit conversion"""
    fig = go.Figure()
    
    if not selected_balloons_list:
        return create_empty_figure()
    
    colors = ['#58a6ff', '#3fb950', '#f85149', '#d29922', '#da70d6', '#ff6347', '#32cd32', '#ffa500']
    
    for i, icao in enumerate(selected_balloons_list):
        # Apply time filter if specified (convert minutes to seconds)
        time_filter_seconds = None
        if time_filter_minutes is not None and time_filter_minutes > 0:
            time_filter_seconds = time_filter_minutes * 60
        
        # Only use reference balloon if both reference balloon AND distance filter are specified
        reference_icao = None
        if reference_balloon and distance_filter_km and distance_filter_km > 0:
            reference_icao = reference_balloon
        
        wind_data = wind_calc.calculate_wind_profile(icao, altitude_source, time_filter_seconds, distance_filter_km, reference_icao)
        
        if not wind_data:
            continue
        
        df = pd.DataFrame(wind_data)
        if len(df) == 0:
            continue
        
        # Convert altitude units for display 
        altitudes = df['altitude_bin']
        if altitude_units == 'ft':
            altitudes = altitudes * 3.28084  # Convert from meters to feet
            df['altitude_display'] = altitudes
        else:
            df['altitude_display'] = altitudes
        
        # Use wind direction data as-is (0-360 degrees)
        wind_dirs = df['wind_direction'].values
        altitudes_display = df['altitude_display'].values
        
        color = colors[i % len(colors)]
        
        fig.add_trace(go.Scatter(
            x=wind_dirs,
            y=altitudes_display,
            mode='markers',
            name=f'{icao.upper()}',
            marker=dict(
                size=5,  # Reduced from 8
                color=color,
                opacity=0.7,
                symbol='circle'
            ),
            hovertemplate=f'<b>{icao.upper()}</b><br>Wind Dir: %{{x:.0f}}°<br>Altitude: %{{y:.0f}} {altitude_units}<extra></extra>'
        ))
    
    # Add cardinal direction reference lines
    cardinal_directions = [0, 90, 180, 270]  # N, E, S, W
    cardinal_labels = ['N (0°)', 'E (90°)', 'S (180°)', 'W (270°)']
    
    for direction, label in zip(cardinal_directions, cardinal_labels):
        fig.add_vline(
            x=direction,
            line_dash="dot",
            line_color="#8b949e",
            opacity=0.5,
            annotation_text=label,
            annotation_position="top",
            annotation_font_size=10,
            annotation_font_color="#8b949e"
        )
    
    unit_label = "feet" if altitude_units == 'ft' else "meters"
    source_label = "Barometric" if altitude_source == 'altitude' else "GPS"
    
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#e6edf3'),
        xaxis=dict(
            title='Wind Direction (degrees)',
            gridcolor='#30363d',
            color='#e6edf3',
            range=[-20, 380],  # Fixed range with padding on both sides
            tickmode='linear',
            dtick=45,
            tickvals=list(range(0, 361, 45)),
            ticktext=[f"{d}°" for d in range(0, 361, 45)],
            showgrid=True,
            zeroline=False,
            fixedrange=True  # Disable zooming/panning on x-axis
        ),
        yaxis=dict(
            title=f'{source_label} Altitude ({unit_label})',
            gridcolor='#30363d',
            color='#e6edf3',
            range=[y_min, y_max] if y_min is not None and y_max is not None else None,  # Auto-scale if no limits set
            fixedrange=False  # Allow zooming on y-axis
        ),
        margin=dict(l=50, r=20, t=20, b=50),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor='rgba(33, 38, 45, 0.8)',
            bordercolor='#30363d',
            borderwidth=1
        ),
        dragmode='zoom'  # Allow zooming but disable panning
    )
    
    return fig

# Raw Data Modal Callbacks
@app.callback(
    [Output('raw-data-modal', 'style'),
     Output('raw-data-title', 'children'),
     Output('raw-data-content', 'children')],
    [Input({'type': 'raw-data-btn', 'index': ALL}, 'n_clicks'),
     Input('close-modal', 'n_clicks')],
    [State('raw-data-modal', 'style')],
    prevent_initial_call=True
)
def handle_raw_data_modal(raw_data_clicks, close_clicks, current_style):
    global tracked_balloons
    
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update
    
    triggered_id = ctx.triggered[0]['prop_id']
    
    if 'close-modal' in triggered_id:
        # Close modal
        return {'display': 'none'}, dash.no_update, dash.no_update
    
    # Check if raw data button was clicked
    if 'raw-data-btn' in triggered_id and any(raw_data_clicks):
        # Find which button was clicked
        for i, clicks in enumerate(raw_data_clicks):
            if clicks and clicks > 0:
                # Extract the ICAO from the button ID
                import json
                button_info = json.loads(triggered_id.split('.')[0])
                icao = button_info['index']
                
                # Get the latest raw data for this balloon
                try:
                    from paid_adsb_client import ADSBExchangeRapidAPIClient
                    client = ADSBExchangeRapidAPIClient()
                    raw_data = client.get_aircraft_by_icao(icao)
                    
                    if raw_data:
                        # Format the raw data nicely
                        import json
                        formatted_data = json.dumps(raw_data, indent=2, sort_keys=True)
                        title = f"Raw ADSB Data - {icao.upper()}"
                        
                        # Show modal
                        modal_style = {
                            'display': 'flex',
                            'justify-content': 'center',
                            'align-items': 'center',
                            'position': 'fixed',
                            'top': '0',
                            'left': '0',
                            'width': '100%',
                            'height': '100%',
                            'background': 'rgba(0, 0, 0, 0.7)',
                            'z-index': '1000'
                        }
                        
                        return modal_style, title, formatted_data
                    else:
                        # No data available
                        modal_style = {
                            'display': 'flex',
                            'justify-content': 'center',
                            'align-items': 'center',
                            'position': 'fixed',
                            'top': '0',
                            'left': '0',
                            'width': '100%',
                            'height': '100%',
                            'background': 'rgba(0, 0, 0, 0.7)',
                            'z-index': '1000'
                        }
                        title = f"Raw ADSB Data - {icao.upper()}"
                        content = f"No raw data available for {icao.upper()}\nThe balloon may not be transmitting or may be out of range."
                        
                        return modal_style, title, content
                        
                except Exception as e:
                    # Error getting data
                    modal_style = {
                        'display': 'flex',
                        'justify-content': 'center',
                        'align-items': 'center',
                        'position': 'fixed',
                        'top': '0',
                        'left': '0',
                        'width': '100%',
                        'height': '100%',
                        'background': 'rgba(0, 0, 0, 0.7)',
                        'z-index': '1000'
                    }
                    title = f"Raw ADSB Data - {icao.upper()} (Error)"
                    content = f"Error retrieving raw data for {icao.upper()}:\n{str(e)}"
                    
                    return modal_style, title, content
                    
                break
    
    return dash.no_update, dash.no_update, dash.no_update

# Maximized Chart Callbacks
@app.callback(
    [Output('maximized-chart-modal', 'style'),
     Output('maximized-chart', 'figure'),
     Output('maximized-chart-title', 'children'),
     Output('maximized-chart-state', 'data')],
    [Input('maximize-altitude-btn', 'n_clicks'),
     Input('maximize-velocity-btn', 'n_clicks'),
     Input('maximize-trajectory-btn', 'n_clicks'),
     Input('maximize-wind-btn', 'n_clicks'),
     Input('close-maximized-chart', 'n_clicks')],
    [State('maximized-chart-state', 'data'),
     State('altitude-chart', 'figure'),
     State('velocity-chart', 'figure'),
     State('trajectory-map', 'figure'),
     State('wind-profile', 'figure'),
     State('tracking-state', 'data')]
)
def handle_chart_maximize(alt_btn, vel_btn, traj_btn, wind_btn, close_click, 
                         current_state, alt_fig, vel_fig, traj_fig, wind_fig, tracking_state):
    ctx = callback_context
    if not ctx.triggered:
        return {'display': 'none'}, {}, '', {'visible': False, 'chart_type': None}
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Close modal
    if trigger_id == 'close-maximized-chart':
        return {'display': 'none'}, {}, '', {'visible': False, 'chart_type': None}
    
    # Show modal with clicked chart
    modal_style = {
        'display': 'flex',
        'justify-content': 'center',
        'align-items': 'center',
        'position': 'fixed',
        'top': '0',
        'left': '0',
        'width': '100%',
        'height': '100%',
        'background': 'rgba(0, 0, 0, 0.8)',
        'z-index': '1001'
    }
    
    if trigger_id == 'maximize-altitude-btn':
        return modal_style, alt_fig, 'Altitude Profile - Maximized', {'visible': True, 'chart_type': 'altitude'}
    elif trigger_id == 'maximize-velocity-btn':
        return modal_style, vel_fig, 'Vertical Velocity - Maximized', {'visible': True, 'chart_type': 'velocity'}
    elif trigger_id == 'maximize-trajectory-btn':
        return modal_style, traj_fig, 'Flight Trajectory - Maximized', {'visible': True, 'chart_type': 'trajectory'}
    elif trigger_id == 'maximize-wind-btn':
        return modal_style, wind_fig, 'Wind Profile - Maximized', {'visible': True, 'chart_type': 'wind'}
    
    return {'display': 'none'}, {}, '', {'visible': False, 'chart_type': None}

if __name__ == '__main__':
    print("Starting Balloon ADSB HUD...")
    print(f"Server running on port {Config.PORT}")
    
    app.run(
        host='0.0.0.0',
        port=Config.PORT,
        debug=Config.DEBUG
    )