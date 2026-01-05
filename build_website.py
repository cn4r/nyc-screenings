import os
import json
from datetime import datetime, timedelta
from icalendar import Calendar, Event
import re

# --- SETUP ---
BASE_FOLDER = os.getcwd()
DATA_FOLDER = os.path.join(BASE_FOLDER, "data")
OUTPUT_FOLDER = BASE_FOLDER

# Create output folder if it doesn't exist
if not os.path.exists(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)
    print(f"✓ Created folder: {OUTPUT_FOLDER}")

def load_data():
    """Load the latest scraped data"""
    latest_path = os.path.join(DATA_FOLDER, 'screenings_latest.json')
    
    if not os.path.exists(latest_path):
        print(f"❌ No data found at {latest_path}")
        print("Run 'python scraper.py' first to scrape data.")
        return None
    
    with open(latest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"✓ Loaded {len(data)} screenings from {latest_path}")
    return data

def deduplicate_screenings(data):
    """Remove duplicate screenings (same movie, date, theater) and filter out Unknown Venue"""
    seen = {}
    deduplicated = []
    
    for screening in data:
        # Skip "Unknown Venue" entries
        if screening['theater'] == "Unknown Venue":
            continue
            
        # Create unique key: date + theater + title
        key = f"{screening['date']}|{screening['theater']}|{screening['title']}"
        
        if key not in seen:
            seen[key] = screening
            deduplicated.append(screening)
        else:
            # If duplicate found, merge showtimes
            existing = seen[key]
            for showtime in screening.get('showtimes', []):
                if showtime not in existing['showtimes']:
                    existing['showtimes'].append(showtime)
    
    print(f"✓ Deduplicated and filtered: {len(data)} → {len(deduplicated)} screenings")
    return deduplicated

def save_ics(data):
    """Generate ICS calendar file"""
    cal = Calendar()
    cal.add('prodid', '-//NYC Movie Calendar//')
    cal.add('version', '2.0')
    
    for s in data:
        for showtime in s.get('showtimes', ['19:00']):
            if showtime == 'Check website':
                showtime = '7:00PM'
            
            event = Event()
            event.add('summary', f"{s['title']} @ {s['theater']}")
            event.add('description', f"Dir: {s['director']} ({s['year']})\n{s['link']}")
            
            # Parse date and time
            date_obj = datetime.strptime(s['date'], '%Y-%m-%d')
            
            # Parse time from formats like "6:30PM" or "6:30 PM"
            time_match = re.search(r'(\d{1,2}):(\d{2})\s*([AP]M)', showtime, re.IGNORECASE)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                meridiem = time_match.group(3).upper()
                
                if meridiem == 'PM' and hour != 12:
                    hour += 12
                elif meridiem == 'AM' and hour == 12:
                    hour = 0
                
                start_time = datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute)
                event.add('dtstart', start_time)
                event.add('dtend', start_time + timedelta(hours=2))
            else:
                event.add('dtstart', date_obj)
            
            event.add('location', s['theater'])
            event.add('url', s['link'])
            cal.add_component(event)
    
    filepath = os.path.join(OUTPUT_FOLDER, "nyc_movies.ics")
    with open(filepath, "wb") as f:
        f.write(cal.to_ical())
    
    print(f"✓ Calendar saved: {filepath}")
    return filepath

def save_html(data):
    """Generate interactive HTML website with search and calendar view"""
    # Calculate date range for display
    dates_in_data = sorted(set(s['date'] for s in data))
    start_date = dates_in_data[0] if dates_in_data else datetime.now().strftime('%Y-%m-%d')
    end_date = dates_in_data[-1] if dates_in_data else datetime.now().strftime('%Y-%m-%d')
    
    # Get unique theaters
    theaters = sorted(set(s['theater'] for s in data))
    
    # Map theaters to neighborhoods
    theater_neighborhoods = {
        'METROGRAPH': 'Lower East Side',
        'FILM FORUM': 'West Village',
        'ANTHOLOGY FILM ARCHIVES': 'East Village',
        'IFC CENTER': 'West Village',
        'MUSEUM OF MODERN ART': 'Midtown',
        'BAM ROSE CINEMAS': 'Brooklyn',
        'NITEHAWK CINEMA WILLIAMSBURG': 'Brooklyn',
        'NITEHAWK CINEMA PROSPECT PARK': 'Brooklyn',
        'ALAMO DRAFTHOUSE BROOKLYN': 'Brooklyn',
        'LINCOLN CENTER': 'Upper West Side',
        'QUAD CINEMA': 'West Village',
        'PARIS THEATER': 'Midtown',
        'VILLAGE EAST CINEMA': 'East Village',
        'CINEMA VILLAGE': 'West Village',
        'LANDMARK SUNSHINE CINEMA': 'Lower East Side',
        'ANGELIKA FILM CENTER': 'SoHo',
        'REGAL ESSEX CROSSING': 'Lower East Side',
        'AMC LINCOLN SQUARE': 'Upper West Side',
        'FILM AT LINCOLN CENTER': 'Upper West Side',
        'ROXY CINEMA': 'TriBeCa',
        'SPECTACLE THEATER': 'Brooklyn',
        'SYNDICATED': 'Brooklyn',
        'VIDEOLOGY': 'Brooklyn',
        'BROOKLYN ACADEMY OF MUSIC': 'Brooklyn',
        'COBBLE HILL CINEMAS': 'Brooklyn',
        'PAVILION THEATER': 'Brooklyn',
        'KENT THEATER': 'Brooklyn',
        'VIDEOLOGY BAR': 'Brooklyn',
    }
    
    # --- ADDED: THEATER COORDINATES FOR MAP ---
    theater_locations = {
        'METROGRAPH': {"lat": 40.7132, "lng": -73.9912},
        'FILM FORUM': {"lat": 40.7282, "lng": -74.0039},
        'ANTHOLOGY FILM ARCHIVES': {"lat": 40.7271, "lng": -73.9897},
        'IFC CENTER': {"lat": 40.7308, "lng": -74.0011},
        'MUSEUM OF MODERN ART': {"lat": 40.7614, "lng": -73.9776},
        'BAM ROSE CINEMAS': {"lat": 40.6861, "lng": -73.9774},
        'NITEHAWK CINEMA WILLIAMSBURG': {"lat": 40.7161, "lng": -73.9575},
        'NITEHAWK CINEMA PROSPECT PARK': {"lat": 40.6617, "lng": -73.9765},
        'ALAMO DRAFTHOUSE BROOKLYN': {"lat": 40.6908, "lng": -73.9831},
        'LINCOLN CENTER': {"lat": 40.7725, "lng": -73.9835},
        'ROXY CINEMA': {"lat": 40.7202, "lng": -74.0044},
        'FILM AT LINCOLN CENTER': {"lat": 40.7725, "lng": -73.9835},
        'VILLAGE EAST CINEMA': {"lat": 40.7290, "lng": -73.9866},
        'QUAD CINEMA': {"lat": 40.7360, "lng": -73.9947},
        'PARIS THEATER': {"lat": 40.7634, "lng": -73.9744},
        'ANGELIKA FILM CENTER': {"lat": 40.7258, "lng": -73.9977},
        'SPECTACLE THEATER': {"lat": 40.7138, "lng": -73.9617}
    }

    # Add theaters to neighborhoods, defaulting to "Other" for unknown
    for theater in theaters:
        theater_upper = theater.upper()
        found = False
        for known_theater in theater_neighborhoods:
            if known_theater in theater_upper:
                found = True
                break
        if not found:
            theater_neighborhoods[theater] = 'Other'
    
    # Get unique neighborhoods
    neighborhoods = sorted(set(theater_neighborhoods.values()))
    
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>NYC Movie Ledger</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ 
                font-family: "Times New Roman", serif; 
                background: #fafafa; 
                color: #000; 
                max-width: 1400px; 
                margin: 40px auto; 
                padding: 20px; 
            }}
            h1 {{ 
                border-bottom: 3px solid #000; 
                text-transform: uppercase; 
                letter-spacing: 3px; 
                padding-bottom: 10px;
            }}
            .subtitle {{
                color: #666;
                font-style: italic;
                margin-bottom: 20px;
            }}
            .controls {{ 
                margin-bottom: 30px; 
                padding: 20px; 
                background: #fff;
                border: 2px solid #000; 
            }}
            .search-bar {{
                width: 100%;
                padding: 12px;
                border: 2px solid #000;
                font-family: inherit;
                font-size: 1.1em;
                margin-bottom: 15px;
                box-sizing: border-box;
            }}
            .search-bar:focus {{
                outline: none;
                border-color: #d32f2f;
            }}
            .filters {{
                display: grid;
                grid-template-columns: 1fr 1fr 1fr 1fr 1fr;
                gap: 15px;
            }}
            .filter-group {{
                display: flex;
                flex-direction: column;
            }}
            .filter-group label {{
                font-weight: bold;
                margin-bottom: 5px;
                text-transform: uppercase;
                font-size: 0.9em;
                letter-spacing: 1px;
            }}
            select, input[type="time"] {{
                padding: 8px;
                border: 2px solid #000;
                font-family: inherit;
                font-size: 1em;
            }}
            
            /* Multi-select styling */
            select[multiple] {{
                min-height: 120px;
            }}
            
            /* Day of Week Checkboxes */
            .day-checkboxes {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 5px;
            }}
            .day-checkbox {{
                display: flex;
                align-items: center;
                gap: 5px;
                padding: 6px 10px;
                border: 2px solid #000;
                cursor: pointer;
                transition: all 0.2s;
                background: #fff;
                font-size: 0.9em;
            }}
            .day-checkbox:hover {{
                background: #f0f0f0;
            }}
            .day-checkbox input[type="checkbox"] {{
                cursor: pointer;
            }}
            .day-checkbox.checked {{
                background: #d32f2f;
                color: #fff;
                border-color: #d32f2f;
            }}
            
            .filter-hint {{
                font-size: 0.75em;
                color: #999;
                font-style: italic;
                margin-top: 3px;
            }}
            
            /* Time filter styling */
            .time-filter {{
                display: flex;
                align-items: center;
                gap: 10px;
                flex-wrap: wrap;
                margin-top: 5px;
            }}
            .time-filter-text {{
                font-size: 0.95em;
                white-space: nowrap;
            }}
            .time-filter input[type="time"] {{
                width: 110px;
            }}
            
            /* Calendar Grid */
            .calendar {{
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 10px;
                margin-bottom: 30px;
                background: #fff;
                padding: 20px;
                border: 2px solid #000;
            }}
            .calendar-day {{
                aspect-ratio: 1;
                border: 2px solid #ddd;
                padding: 8px;
                text-align: center;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                position: relative;
            }}
            .calendar-day:hover {{
                background: #f0f0f0;
                transform: scale(1.05);
            }}
            .calendar-day.has-screenings {{
                border-color: #000;
                background: #fff;
                font-weight: bold;
            }}
            .calendar-day.has-screenings:hover {{
                background: #000;
                color: #fff;
            }}
            .calendar-day.selected {{
                background: #d32f2f;
                color: #fff;
                border-color: #d32f2f;
            }}
            .calendar-day.empty {{
                border: none;
                cursor: default;
            }}
            .calendar-day.empty:hover {{
                background: transparent;
                transform: none;
            }}
            .calendar-header {{
                font-weight: bold;
                text-align: center;
                padding: 10px;
                background: #000;
                color: #fff;
                text-transform: uppercase;
                font-size: 0.85em;
                letter-spacing: 1px;
                cursor: pointer;
                transition: all 0.2s;
            }}
            .calendar-header:hover {{
                background: #333;
            }}
            .calendar-header.selected {{
                background: #d32f2f;
            }}
            .day-number {{
                font-size: 1.2em;
                margin-bottom: 2px;
            }}
            .screening-count {{
                font-size: 0.7em;
                color: #666;
            }}
            .calendar-day.has-screenings .screening-count {{
                color: #d32f2f;
            }}
            .calendar-day.selected .screening-count {{
                color: #fff;
            }}
            
            .movie-card {{
                background: #fff;
                border: 2px solid #000;
                padding: 20px;
                margin-bottom: 15px;
                transition: all 0.2s;
            }}
            .movie-card:hover {{
                box-shadow: 5px 5px 0px #000;
                transform: translate(-2px, -2px);
            }}
            .movie-title {{
                font-size: 1.3em;
                font-weight: bold;
                margin-bottom: 5px;
            }}
            .movie-meta {{
                color: #666;
                margin-bottom: 10px;
                font-size: 0.95em;
            }}
            .theater {{
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .showtimes {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin: 10px 0;
            }}
            .showtime {{
                background: #000;
                color: #fff;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 0.9em;
            }}
            .date-badge {{
                display: inline-block;
                background: #000;
                color: #fff;
                padding: 3px 10px;
                font-size: 0.85em;
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .link {{
                color: #000;
                text-decoration: none;
                border-bottom: 2px solid #000;
                font-weight: bold;
            }}
            .link:hover {{
                background: #000;
                color: #fff;
            }}
            .count {{
                text-align: center;
                padding: 15px;
                background: #000;
                color: #fff;
                font-weight: bold;
                font-size: 1.1em;
                margin-bottom: 20px;
                letter-spacing: 2px;
            }}
            .search-hint {{
                font-size: 0.85em;
                color: #999;
                font-style: italic;
                margin-top: 5px;
            }}
            .footer {{
                margin-top: 40px;
                padding-top: 20px;
                border-top: 2px solid #000;
                text-align: center;
                color: #666;
                font-size: 0.9em;
            }}
            
            /* MAP CONTAINER STYLES */
            #map-container {{
                margin-bottom: 25px;
                border: 2px solid #000;
                background: #fff;
                padding: 15px;
            }}
            #map {{
                height: 400px;
                width: 100%;
                border: 2px solid #000;
            }}
            .btn-clear {{
                margin-top: 10px;
                padding: 8px 15px;
                cursor: pointer;
                background: #fff;
                border: 2px solid #000;
                font-family: inherit;
                font-weight: bold;
                text-transform: uppercase;
                transition: 0.2s;
            }}
            .btn-clear:hover {{
                background: #000;
                color: #fff;
            }}
            
            @media (max-width: 768px) {{
                .filters {{
                    grid-template-columns: 1fr;
                }}
                .calendar {{
                    grid-template-columns: repeat(7, 1fr);
                    gap: 5px;
                }}
                .day-number {{
                    font-size: 1em;
                }}
                .screening-count {{
                    display: none;
                }}
            }}
        </style>
    </head>
    <body>
        <h1>"The Ledger"</h1>
        <div class="subtitle">
            Next 30 Days ({start_date} to {end_date})<br>
            Scraped from https://www.screenslate.com • Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
        </div>
        
        <div class="controls">
            <input 
                type="text" 
                id="searchBar" 
                class="search-bar" 
                placeholder="Search movies, directors, theaters..."
                oninput="filterMovies()"
            >
            <div class="search-hint">Try: "Coppola", "Metrograph", "Pulp Fiction", "1994"</div>
            
            <div class="filters">
                <div class="filter-group">
                    <label>Days of Week (Multi-Select)</label>
                    <div class="day-checkboxes">
                        <label class="day-checkbox">
                            <input type="checkbox" value="0" onchange="handleDayCheckboxChange()"> Sun
                        </label>
                        <label class="day-checkbox">
                            <input type="checkbox" value="1" onchange="handleDayCheckboxChange()"> Mon
                        </label>
                        <label class="day-checkbox">
                            <input type="checkbox" value="2" onchange="handleDayCheckboxChange()"> Tue
                        </label>
                        <label class="day-checkbox">
                            <input type="checkbox" value="3" onchange="handleDayCheckboxChange()"> Wed
                        </label>
                        <label class="day-checkbox">
                            <input type="checkbox" value="4" onchange="handleDayCheckboxChange()"> Thu
                        </label>
                        <label class="day-checkbox">
                            <input type="checkbox" value="5" onchange="handleDayCheckboxChange()"> Fri
                        </label>
                        <label class="day-checkbox">
                            <input type="checkbox" value="6" onchange="handleDayCheckboxChange()"> Sat
                        </label>
                    </div>
                </div>
                
                <div class="filter-group">
                    <label>Specific Dates (Multi-Select)</label>
                    <select id="dateFilter" multiple onchange="handleDateFilterChange()">
                    </select>
                    <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
                </div>
                
                <div class="filter-group">
                    <label>Theaters (Multi-Select)</label>
                    <select id="theaterFilter" multiple onchange="filterMovies()">
                    </select>
                    <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
                </div>
                
                <div class="filter-group">
                    <label>Neighborhoods (Multi-Select)</label>
                    <select id="neighborhoodFilter" multiple onchange="handleNeighborhoodChange()">
                    </select>
                    <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
                </div>
                
                <div class="filter-group">
                    <label>Time Filter</label>
                    <div class="time-filter">
                        <span class="time-filter-text">Start time is between</span>
                        <input type="time" id="startTime" value="00:00" onchange="filterMovies()">
                        <span class="time-filter-text">and</span>
                        <input type="time" id="endTime" value="23:59" onchange="filterMovies()">
                    </div>
                </div>
            </div>
        </div>
        
        <div id="calendar" class="calendar"></div>
        
        <div id="map-container">
            <div style="font-weight:bold; margin-bottom:10px; text-transform:uppercase;">Map Filter (Draw to Filter)</div>
            <div id="map"></div>
            <button class="btn-clear" onclick="clearSelection()">Clear Map Drawing</button>
        </div>
        
        <div class="count" id="resultCount">0 screenings found</div>
        
        <div id="movieContainer"></div>
        
        <div class="footer">
            Data sourced from <a href="https://www.screenslate.com" target="_blank" style="color:#000;">Screen Slate</a><br>
            Calendar file available: <a href="./nyc_movies.ics" download style="color:#000;">Download ICS</a>
        </div>

        <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyA5B9DU1gTNvgJ4rVC5FsEgGneDcEVXfG0&libraries=drawing"></script>
        <script>
        const allMovies = {json.dumps(data)};
        const theaterCoords = {json.dumps(theater_locations)};
        let selectedDates = new Set();
        let selectedDaysOfWeek = new Set();
        let selectedTheaters = new Set();
        let selectedNeighborhoods = new Set();
        
        // Map Variables
        let map, drawingManager, currentShape;
        let markers = [];
        
        // Theater to neighborhood mapping
        const theaterNeighborhoods = {json.dumps(theater_neighborhoods)};
        
        // Get unique theaters
        const allTheaters = {json.dumps(theaters)};
        
        // Get unique neighborhoods
        const allNeighborhoods = {json.dumps(neighborhoods)};
        
        // Get unique dates and count screenings per date
        const dateMap = {{}};
        allMovies.forEach(m => {{
            if (!dateMap[m.date]) {{
                dateMap[m.date] = 0;
            }}
            dateMap[m.date]++;
        }});
        
        const dates = Object.keys(dateMap).sort();
        
        // Populate date dropdown
        const dateSelect = document.getElementById('dateFilter');
        dates.forEach(date => {{
            const option = document.createElement('option');
            option.value = date;
            const d = new Date(date + 'T00:00:00');
            option.textContent = d.toLocaleDateString('en-US', {{ weekday: 'short', month: 'short', day: 'numeric' }});
            dateSelect.appendChild(option);
        }});
        
        // Populate theater dropdown
        const theaterSelect = document.getElementById('theaterFilter');
        allTheaters.forEach(theater => {{
            const option = document.createElement('option');
            option.value = theater;
            option.textContent = theater;
            theaterSelect.appendChild(option);
        }});
        
        // Populate neighborhood dropdown
        const neighborhoodSelect = document.getElementById('neighborhoodFilter');
        allNeighborhoods.forEach(neighborhood => {{
            const option = document.createElement('option');
            option.value = neighborhood;
            option.textContent = neighborhood;
            neighborhoodSelect.appendChild(option);
        }});
        
        // --- MAP FUNCTIONS ---
        function initMap() {{
            map = new google.maps.Map(document.getElementById('map'), {{
                center: {{lat: 40.7128, lng: -74.0060}},
                zoom: 11,
                styles: [{{ "featureType": "poi", "stylers": [{{ "visibility": "off" }}] }}],
                mapTypeControl: false,
                streetViewControl: false
            }});

            drawingManager = new google.maps.drawing.DrawingManager({{
                drawingMode: null,
                drawingControl: true,
                drawingControlOptions: {{
                    position: google.maps.ControlPosition.TOP_CENTER,
                    drawingModes: ['polygon', 'circle', 'rectangle']
                }},
                circleOptions: {{ fillOpacity: 0.2, strokeColor: '#d32f2f', fillColor: '#d32f2f' }},
                polygonOptions: {{ fillOpacity: 0.2, strokeColor: '#d32f2f', fillColor: '#d32f2f' }},
                rectangleOptions: {{ fillOpacity: 0.2, strokeColor: '#d32f2f', fillColor: '#d32f2f' }}
            }});
            drawingManager.setMap(map);

            google.maps.event.addListener(drawingManager, 'overlaycomplete', function(event) {{
                if (currentShape) currentShape.setMap(null);
                currentShape = event.overlay;
                filterMovies();
                
                // Trigger filter updates if shape is edited
                if (event.type === 'circle') {{
                    google.maps.event.addListener(currentShape, 'radius_changed', filterMovies);
                    google.maps.event.addListener(currentShape, 'center_changed', filterMovies);
                }}
            }});

            // Add theater markers
            Object.keys(theaterCoords).forEach(name => {{
                const marker = new google.maps.Marker({{
                    position: theaterCoords[name],
                    map: map,
                    title: name,
                    icon: {{
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 5,
                        fillColor: "#000",
                        fillOpacity: 1,
                        strokeWeight: 0
                    }}
                }});
                marker.theaterName = name;
                markers.push(marker);
            }});
        }}

        function clearSelection() {{
            if (currentShape) currentShape.setMap(null);
            currentShape = null;
            filterMovies();
        }}

        function isLocationInShape(lat, lng) {{
            if (!currentShape) return true;
            const pt = new google.maps.LatLng(lat, lng);
            
            if (currentShape.getBounds) {{ 
                if (!currentShape.getBounds().contains(pt)) return false;
            }}
            
            if (currentShape instanceof google.maps.Polygon) {{
                return google.maps.geometry.poly.containsLocation(pt, currentShape);
            }} else if (currentShape instanceof google.maps.Circle) {{
                const dist = google.maps.geometry.spherical.computeDistanceBetween(pt, currentShape.getCenter());
                return dist <= currentShape.getRadius();
            }}
            return true;
        }}
        
        function handleNeighborhoodChange() {{
            // Get selected neighborhoods
            const selectedOptions = Array.from(document.getElementById('neighborhoodFilter').selectedOptions);
            selectedNeighborhoods.clear();
            selectedOptions.forEach(option => {{
                selectedNeighborhoods.add(option.value);
            }});
            
            // Auto-select theaters in those neighborhoods
            if (selectedNeighborhoods.size > 0) {{
                selectedTheaters.clear();
                allTheaters.forEach(theater => {{
                    const neighborhood = theaterNeighborhoods[theater];
                    if (selectedNeighborhoods.has(neighborhood)) {{
                        selectedTheaters.add(theater);
                    }}
                }});
                
                // Update theater dropdown
                Array.from(theaterSelect.options).forEach(option => {{
                    option.selected = selectedTheaters.has(option.value);
                }});
            }} else {{
                // If no neighborhoods selected, clear theater filter
                selectedTheaters.clear();
                Array.from(theaterSelect.options).forEach(option => {{
                    option.selected = false;
                }});
            }}
            
            filterMovies();
        }}
        
        // Build Calendar
        function buildCalendar() {{
            const calendar = document.getElementById('calendar');
            const firstDate = new Date(dates[0] + 'T00:00:00');
            const lastDate = new Date(dates[dates.length - 1] + 'T00:00:00');
            
            const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            dayNames.forEach((day, index) => {{
                const header = document.createElement('div');
                header.className = 'calendar-header';
                header.textContent = day;
                header.onclick = () => toggleDayOfWeek(index);
                header.dataset.dayIndex = index;
                calendar.appendChild(header);
            }});
            
            const startDate = new Date(firstDate);
            startDate.setDate(startDate.getDate() - startDate.getDay());
            
            const endDate = new Date(lastDate);
            endDate.setDate(endDate.getDate() + (6 - endDate.getDay()));
            
            let currentDate = new Date(startDate);
            while (currentDate <= endDate) {{
                const dateStr = currentDate.toISOString().split('T')[0];
                const day = document.createElement('div');
                day.className = 'calendar-day';
                day.dataset.date = dateStr;
                
                if (dateMap[dateStr]) {{
                    day.classList.add('has-screenings');
                    day.innerHTML = `
                        <div class="day-number">${{currentDate.getDate()}}</div>
                        <div class="screening-count">${{dateMap[dateStr]}} films</div>
                    `;
                    day.onclick = (e) => toggleDate(dateStr, e);
                }} else {{
                    day.innerHTML = `<div class="day-number">${{currentDate.getDate()}}</div>`;
                    day.style.opacity = '0.3';
                    day.style.cursor = 'default';
                    day.onclick = null;
                }}
                
                calendar.appendChild(day);
                currentDate.setDate(currentDate.getDate() + 1);
            }}
        }}
        
        function toggleDayOfWeek(dayIndex) {{
            if (selectedDaysOfWeek.has(dayIndex)) {{
                selectedDaysOfWeek.delete(dayIndex);
            }} else {{
                selectedDaysOfWeek.add(dayIndex);
            }}
            
            selectedDates.clear();
            updateDateSelectUI();
            updateDayOfWeekUI();
            
            document.querySelectorAll('.calendar-day').forEach(day => {{
                day.classList.remove('selected');
            }});
            
            filterMovies();
        }}
        
        function handleDayCheckboxChange() {{
            selectedDaysOfWeek.clear();
            document.querySelectorAll('.day-checkbox input[type="checkbox"]:checked').forEach(checkbox => {{
                selectedDaysOfWeek.add(parseInt(checkbox.value));
            }});
            
            selectedDates.clear();
            updateDateSelectUI();
            updateDayOfWeekUI();
            
            document.querySelectorAll('.day-checkbox').forEach(label => {{
                const checkbox = label.querySelector('input[type="checkbox"]');
                if (checkbox.checked) {{
                    label.classList.add('checked');
                }} else {{
                    label.classList.remove('checked');
                }}
            }});
            
            document.querySelectorAll('.calendar-day').forEach(day => {{
                day.classList.remove('selected');
            }});
            
            filterMovies();
        }}
        
        function toggleDate(dateStr, event) {{
            if (selectedDates.has(dateStr)) {{
                selectedDates.delete(dateStr);
            }} else {{
                selectedDates.add(dateStr);
            }}
            
            if (selectedDates.size > 0) {{
                selectedDaysOfWeek.clear();
                updateDayOfWeekUI();
            }}
            
            updateDateSelectUI();
            updateCalendarUI();
            filterMovies();
        }}
        
        function handleDateFilterChange() {{
            const selectedOptions = Array.from(document.getElementById('dateFilter').selectedOptions);
            selectedDates.clear();
            selectedOptions.forEach(option => {{
                selectedDates.add(option.value);
            }});
            
            if (selectedDates.size > 0) {{
                selectedDaysOfWeek.clear();
                updateDayOfWeekUI();
            }}
            
            updateCalendarUI();
            filterMovies();
        }}
        
        function updateDateSelectUI() {{
            const dateSelect = document.getElementById('dateFilter');
            Array.from(dateSelect.options).forEach(option => {{
                option.selected = selectedDates.has(option.value);
            }});
        }}
        
        function updateDayOfWeekUI() {{
            document.querySelectorAll('.day-checkbox input[type="checkbox"]').forEach(checkbox => {{
                const checkboxDay = parseInt(checkbox.value);
                checkbox.checked = selectedDaysOfWeek.has(checkboxDay);
            }});
            document.querySelectorAll('.day-checkbox').forEach(label => {{
                const checkbox = label.querySelector('input[type="checkbox"]');
                if (checkbox.checked) {{
                    label.classList.add('checked');
                }} else {{
                    label.classList.remove('checked');
                }}
            }});
            
            document.querySelectorAll('.calendar-header').forEach(header => {{
                const headerDay = parseInt(header.dataset.dayIndex);
                if (selectedDaysOfWeek.has(headerDay)) {{
                    header.classList.add('selected');
                }} else {{
                    header.classList.remove('selected');
                }}
            }});
        }}
        
        function updateCalendarUI() {{
            document.querySelectorAll('.calendar-day').forEach(day => {{
                if (selectedDates.has(day.dataset.date)) {{
                    day.classList.add('selected');
                }} else {{
                    day.classList.remove('selected');
                }}
            }});
        }}
        
        function parseTime(timeStr) {{
            const match = timeStr.match(/(\d{1,2}):(\d{2})\s*([AP]M)/i);
            if (!match) return null;
            
            let hour = parseInt(match[1]);
            const minute = parseInt(match[2]);
            const meridiem = match[3].toUpperCase();
            
            if (meridiem === 'PM' && hour !== 12) hour += 12;
            if (meridiem === 'AM' && hour === 12) hour = 0;
            
            return hour * 60 + minute;
        }}
        
        function timeStringToMinutes(timeStr) {{
            const [hours, minutes] = timeStr.split(':').map(Number);
            return hours * 60 + minutes;
        }}
        
        function matchesTimeRange(showtimes, startMinutes, endMinutes) {{
            if (showtimes[0] === 'Check website') return true;
            
            return showtimes.some(time => {{
                const minutes = parseTime(time);
                if (minutes === null) return true;
                
                if (endMinutes < startMinutes) {{
                    endMinutes = 24 * 60 - 1;
                }}
                
                return minutes >= startMinutes && minutes <= endMinutes;
            }});
        }}
        
        function matchesSearch(movie, query) {{
            if (!query) return true;
            
            const searchText = query.toLowerCase();
            const searchableContent = [
                movie.title,
                movie.director,
                movie.theater,
                movie.year
            ].join(' ').toLowerCase();
            
            return searchableContent.includes(searchText);
        }}
        
        function filterMovies() {{
            const searchQuery = document.getElementById('searchBar').value;
            const startTime = document.getElementById('startTime').value;
            const endTime = document.getElementById('endTime').value;
            
            // Get selected theaters
            const theaterOptions = Array.from(document.getElementById('theaterFilter').selectedOptions);
            selectedTheaters.clear();
            theaterOptions.forEach(option => {{
                selectedTheaters.add(option.value);
            }});
            
            // Time range conversion
            const startMinutes = timeStringToMinutes(startTime);
            const endMinutes = timeStringToMinutes(endTime);
            
            const filtered = allMovies.filter(m => {{
                // 1. Search Filter
                if (!matchesSearch(m, searchQuery)) return false;
                
                // 2. Map Filter (Geospatial)
                const coords = theaterCoords[m.theater];
                // If the theater has coords, check if it's in the shape. 
                // If it doesn't have coords (uncommon), or no shape is drawn, return true.
                const inArea = coords ? isLocationInShape(coords.lat, coords.lng) : (!currentShape);
                if (!inArea) return false;
                
                // 3. Theater Filter
                if (selectedTheaters.size > 0 && !selectedTheaters.has(m.theater)) return false;
                
                // 4. Date Filter (Specific Dates)
                if (selectedDates.size > 0 && !selectedDates.has(m.date)) return false;
                
                // 5. Day of Week Filter
                if (selectedDaysOfWeek.size > 0) {{
                    const dateObj = new Date(m.date + 'T00:00:00');
                    if (!selectedDaysOfWeek.has(dateObj.getDay())) return false;
                }}
                
                // 6. Time Filter
                if (!matchesTimeRange(m.showtimes, startMinutes, endMinutes)) return false;
                
                return true;
            }});
            
            renderMovies(filtered);
        }}

        function renderMovies(movies) {{
            const container = document.getElementById('movieContainer');
            const resultCount = document.getElementById('resultCount');
            
            resultCount.textContent = `${{movies.length}} screenings found`;
            
            if (movies.length === 0) {{
                container.innerHTML = '<div style="text-align:center; padding:40px; color:#666;">No screenings match your filters.</div>';
                return;
            }}
            
            container.innerHTML = movies.map(m => {{
                const showtimesHtml = m.showtimes.map(t => 
                    `<span class="showtime">${{t}}</span>`
                ).join('');
                
                const d = new Date(m.date + 'T00:00:00');
                const dateStr = d.toLocaleDateString('en-US', {{ weekday: 'short', month: 'short', day: 'numeric' }});
                
                return `
                    <div class="movie-card">
                        <div class="date-badge">${{dateStr}}</div>
                        <div class="movie-title">${{m.title}} <span style="font-weight:normal; font-size:0.8em;">(${{m.year}})</span></div>
                        <div class="movie-meta">Dir: ${{m.director}}</div>
                        <div class="theater">${{m.theater}}</div>
                        <div class="showtimes">${{showtimesHtml}}</div>
                        <a href="${{m.link}}" target="_blank" class="link">Tickets & Info</a>
                    </div>
                `;
            }}).join('');
        }}
        
        window.onload = function() {{
            buildCalendar();
            initMap();
            renderMovies(allMovies);
        }};
        </script>
    </body>
    </html>
    """
    
    filepath = os.path.join(OUTPUT_FOLDER, "index.html")
    with open(filepath, "w", encoding='utf-8') as f:
        f.write(html_template)
    
    print(f"✓ Website updated with Google Maps Drawing Filter: {filepath}")
    return filepath

if __name__ == "__main__":
    raw_data = load_data()
    if raw_data:
        clean_data = deduplicate_screenings(raw_data)
        save_ics(clean_data)
        save_html(clean_data)
