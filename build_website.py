#!/usr/bin/env python3
"""
NYC Movie Ledger — Website + ICS builder  v2 (refactored)

Reads data/screenings_latest.json and produces:
  • index.html  — interactive filterable calendar site
  • nyc_movies.ics — importable calendar file

Key fixes over v1:
  • Broken regex in the HTML JS parseTime() — was using wrong syntax
  • Better deduplication (normalizes theater names)
  • Handles missing/malformed data gracefully
"""

import os
import json
import re
from datetime import datetime, timedelta
from icalendar import Calendar, Event

# ── CONFIG ──────────────────────────────────────────────────────────
BASE_FOLDER = os.path.dirname(os.path.abspath(__file__)) or os.getcwd()
DATA_FOLDER = os.path.join(BASE_FOLDER, "data")
OUTPUT_FOLDER = BASE_FOLDER
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ── THEATER METADATA ────────────────────────────────────────────────
THEATER_NEIGHBORHOODS = {
    "METROGRAPH": "Lower East Side",
    "FILM FORUM": "West Village",
    "ANTHOLOGY FILM ARCHIVES": "East Village",
    "IFC CENTER": "West Village",
    "MUSEUM OF MODERN ART": "Midtown",
    "BAM ROSE CINEMAS": "Brooklyn",
    "NITEHAWK CINEMA WILLIAMSBURG": "Brooklyn",
    "NITEHAWK CINEMA PROSPECT PARK": "Brooklyn",
    "ALAMO DRAFTHOUSE BROOKLYN": "Brooklyn",
    "ALAMO DRAFTHOUSE LOWER MANHATTAN": "Lower Manhattan",
    "LINCOLN CENTER": "Upper West Side",
    "QUAD CINEMA": "West Village",
    "PARIS THEATER": "Midtown",
    "VILLAGE EAST CINEMA": "East Village",
    "CINEMA VILLAGE": "West Village",
    "LANDMARK SUNSHINE CINEMA": "Lower East Side",
    "ANGELIKA FILM CENTER": "SoHo",
    "REGAL ESSEX CROSSING": "Lower East Side",
    "AMC LINCOLN SQUARE": "Upper West Side",
    "FILM AT LINCOLN CENTER": "Upper West Side",
    "ROXY CINEMA": "TriBeCa",
    "SPECTACLE THEATER": "Brooklyn",
    "SPECTACLE": "Brooklyn",
    "SYNDICATED": "Brooklyn",
    "BAM": "Brooklyn",
    "LOW CINEMA": "East Village",
    "MUSEUM OF THE MOVING IMAGE": "Astoria",
}

THEATER_LOCATIONS = {
    "METROGRAPH": {"lat": 40.7132, "lng": -73.9912},
    "FILM FORUM": {"lat": 40.7282, "lng": -74.0039},
    "ANTHOLOGY FILM ARCHIVES": {"lat": 40.7271, "lng": -73.9897},
    "IFC CENTER": {"lat": 40.7308, "lng": -74.0011},
    "MUSEUM OF MODERN ART": {"lat": 40.7614, "lng": -73.9776},
    "BAM ROSE CINEMAS": {"lat": 40.6861, "lng": -73.9774},
    "BAM": {"lat": 40.6861, "lng": -73.9774},
    "NITEHAWK CINEMA WILLIAMSBURG": {"lat": 40.7161, "lng": -73.9575},
    "NITEHAWK CINEMA PROSPECT PARK": {"lat": 40.6617, "lng": -73.9765},
    "ALAMO DRAFTHOUSE BROOKLYN": {"lat": 40.6908, "lng": -73.9831},
    "ALAMO DRAFTHOUSE LOWER MANHATTAN": {"lat": 40.7101, "lng": -74.0007},
    "LINCOLN CENTER": {"lat": 40.7725, "lng": -73.9835},
    "ROXY CINEMA": {"lat": 40.7202, "lng": -74.0044},
    "ROXY CINEMA NEW YORK": {"lat": 40.7202, "lng": -74.0044},
    "FILM AT LINCOLN CENTER": {"lat": 40.7725, "lng": -73.9835},
    "VILLAGE EAST CINEMA": {"lat": 40.7290, "lng": -73.9866},
    "QUAD CINEMA": {"lat": 40.7360, "lng": -73.9947},
    "PARIS THEATER": {"lat": 40.7634, "lng": -73.9744},
    "ANGELIKA FILM CENTER": {"lat": 40.7258, "lng": -73.9977},
    "SPECTACLE THEATER": {"lat": 40.7138, "lng": -73.9617},
    "SPECTACLE": {"lat": 40.7138, "lng": -73.9617},
    "LOW CINEMA": {"lat": 40.7265, "lng": -73.9895},
    "MUSEUM OF THE MOVING IMAGE": {"lat": 40.7564, "lng": -73.9237},
}


# ── DATA LOADING / CLEANING ────────────────────────────────────────
def load_data():
    path = os.path.join(DATA_FOLDER, "screenings_latest.json")
    if not os.path.exists(path):
        print(f"❌ No data at {path} — run scraper.py first.")
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"✓ Loaded {len(data)} screenings from {path}")
    return data


def deduplicate(data):
    """Remove dupes (same movie+date+theater), merge showtimes, drop Unknown Venue."""
    seen = {}
    out = []
    for s in data:
        if s["theater"] == "Unknown Venue":
            continue
        key = f"{s['date']}|{s['theater']}|{s['title']}"
        if key not in seen:
            seen[key] = s
            out.append(s)
        else:
            # Merge showtimes
            existing = seen[key]
            for t in s.get("showtimes", []):
                if t not in existing["showtimes"]:
                    existing["showtimes"].append(t)
    print(f"✓ Deduplicated: {len(data)} → {len(out)} screenings")
    return out


def _neighborhood_for(theater):
    upper = theater.upper()
    for known, hood in THEATER_NEIGHBORHOODS.items():
        if known in upper:
            return hood
    return "Other"


# ── ICS GENERATION ──────────────────────────────────────────────────
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)", re.IGNORECASE)


def save_ics(data):
    cal = Calendar()
    cal.add("prodid", "-//NYC Movie Calendar//")
    cal.add("version", "2.0")

    for s in data:
        for showtime in s.get("showtimes", ["19:00"]):
            if showtime == "Check website":
                showtime = "7:00PM"

            event = Event()
            event.add("summary", f"{s['title']} @ {s['theater']}")
            event.add(
                "description",
                f"Dir: {s['director']} ({s['year']})\n{s['link']}",
            )

            date_obj = datetime.strptime(s["date"], "%Y-%m-%d")
            m = _TIME_RE.search(showtime)
            if m:
                hour, minute, meridiem = int(m.group(1)), int(m.group(2)), m.group(3).upper()
                if meridiem == "PM" and hour != 12:
                    hour += 12
                elif meridiem == "AM" and hour == 12:
                    hour = 0
                start = datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute)
                event.add("dtstart", start)
                event.add("dtend", start + timedelta(hours=2))
            else:
                event.add("dtstart", date_obj)

            event.add("location", s["theater"])
            event.add("url", s["link"])
            cal.add_component(event)

    fp = os.path.join(OUTPUT_FOLDER, "nyc_movies.ics")
    with open(fp, "wb") as f:
        f.write(cal.to_ical())
    print(f"✓ Calendar saved: {fp}")


# ── HTML GENERATION ─────────────────────────────────────────────────
def save_html(data):
    dates_in_data = sorted({s["date"] for s in data})
    start_date = dates_in_data[0] if dates_in_data else datetime.now().strftime("%Y-%m-%d")
    end_date = dates_in_data[-1] if dates_in_data else datetime.now().strftime("%Y-%m-%d")

    theaters = sorted({s["theater"] for s in data})

    # Build neighborhood map for every theater in the data
    tn_map = {}
    for t in theaters:
        tn_map[t] = _neighborhood_for(t)
    neighborhoods = sorted(set(tn_map.values()))

    # Build coords map (only theaters we know about)
    coords = {}
    for t in theaters:
        upper = t.upper()
        if upper in THEATER_LOCATIONS:
            coords[t] = THEATER_LOCATIONS[upper]
        elif t in THEATER_LOCATIONS:
            coords[t] = THEATER_LOCATIONS[t]
        else:
            # Try partial match
            for known, loc in THEATER_LOCATIONS.items():
                if known in upper:
                    coords[t] = loc
                    break

    # ── Build the HTML string ───────────────────────────────────────
    # NOTE: The f-string uses {{ }} to emit literal braces in JS.
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>NYC Movie Ledger</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: "Times New Roman", serif; background: #fafafa; color: #000;
               max-width: 1400px; margin: 40px auto; padding: 20px; }}
        h1 {{ border-bottom: 3px solid #000; text-transform: uppercase;
              letter-spacing: 3px; padding-bottom: 10px; }}
        .subtitle {{ color: #666; font-style: italic; margin-bottom: 20px; }}
        .controls {{ margin-bottom: 30px; padding: 20px; background: #fff; border: 2px solid #000; }}
        .search-bar {{ width: 100%; padding: 12px; border: 2px solid #000; font-family: inherit;
                       font-size: 1.1em; margin-bottom: 15px; box-sizing: border-box; }}
        .search-bar:focus {{ outline: none; border-color: #d32f2f; }}
        .filters {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 15px; }}
        .filter-group {{ display: flex; flex-direction: column; }}
        .filter-group label {{ font-weight: bold; margin-bottom: 5px; text-transform: uppercase;
                               font-size: 0.9em; letter-spacing: 1px; }}
        select, input[type="time"] {{ padding: 8px; border: 2px solid #000; font-family: inherit; font-size: 1em; }}
        select[multiple] {{ min-height: 120px; }}
        .day-checkboxes {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; }}
        .day-checkbox {{ display: flex; align-items: center; gap: 5px; padding: 6px 10px;
                         border: 2px solid #000; cursor: pointer; transition: all 0.2s;
                         background: #fff; font-size: 0.9em; }}
        .day-checkbox:hover {{ background: #f0f0f0; }}
        .day-checkbox input[type="checkbox"] {{ cursor: pointer; }}
        .day-checkbox.checked {{ background: #d32f2f; color: #fff; border-color: #d32f2f; }}
        .filter-hint {{ font-size: 0.75em; color: #999; font-style: italic; margin-top: 3px; }}
        .time-filter {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 5px; }}
        .time-filter-text {{ font-size: 0.95em; white-space: nowrap; }}
        .time-filter input[type="time"] {{ width: 110px; }}

        .calendar {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px;
                     margin-bottom: 30px; background: #fff; padding: 20px; border: 2px solid #000; }}
        .calendar-day {{ aspect-ratio: 1; border: 2px solid #ddd; padding: 8px; text-align: center;
                         cursor: pointer; transition: all 0.2s; display: flex; flex-direction: column;
                         justify-content: center; align-items: center; position: relative; }}
        .calendar-day:hover {{ background: #f0f0f0; transform: scale(1.05); }}
        .calendar-day.has-screenings {{ border-color: #000; background: #fff; font-weight: bold; }}
        .calendar-day.has-screenings:hover {{ background: #000; color: #fff; }}
        .calendar-day.selected {{ background: #d32f2f; color: #fff; border-color: #d32f2f; }}
        .calendar-day.empty {{ border: none; cursor: default; }}
        .calendar-day.empty:hover {{ background: transparent; transform: none; }}
        .calendar-header {{ font-weight: bold; text-align: center; padding: 10px; background: #000;
                            color: #fff; text-transform: uppercase; font-size: 0.85em;
                            letter-spacing: 1px; cursor: pointer; transition: all 0.2s; }}
        .calendar-header:hover {{ background: #333; }}
        .calendar-header.selected {{ background: #d32f2f; }}
        .day-number {{ font-size: 1.2em; margin-bottom: 2px; }}
        .screening-count {{ font-size: 0.7em; color: #666; }}
        .calendar-day.has-screenings .screening-count {{ color: #d32f2f; }}
        .calendar-day.selected .screening-count {{ color: #fff; }}

        .movie-card {{ background: #fff; border: 2px solid #000; padding: 20px;
                       margin-bottom: 15px; transition: all 0.2s; }}
        .movie-card:hover {{ box-shadow: 5px 5px 0px #000; transform: translate(-2px, -2px); }}
        .movie-title {{ font-size: 1.3em; font-weight: bold; margin-bottom: 5px; }}
        .movie-meta {{ color: #666; margin-bottom: 10px; font-size: 0.95em; }}
        .theater {{ font-weight: bold; margin-bottom: 10px; }}
        .showtimes {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }}
        .showtime {{ background: #000; color: #fff; padding: 5px 12px; font-weight: bold; font-size: 0.9em; }}
        .date-badge {{ display: inline-block; background: #000; color: #fff; padding: 3px 10px;
                       font-size: 0.85em; font-weight: bold; margin-bottom: 10px; }}
        .link {{ color: #000; text-decoration: none; border-bottom: 2px solid #000; font-weight: bold; }}
        .link:hover {{ background: #000; color: #fff; }}
        .count {{ text-align: center; padding: 15px; background: #000; color: #fff;
                  font-weight: bold; font-size: 1.1em; margin-bottom: 20px; letter-spacing: 2px; }}
        .search-hint {{ font-size: 0.85em; color: #999; font-style: italic; margin-top: 5px; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 2px solid #000;
                   text-align: center; color: #666; font-size: 0.9em; }}

        #map-container {{ margin-bottom: 25px; border: 2px solid #000; background: #fff; padding: 15px; }}
        #map {{ height: 400px; width: 100%; border: 2px solid #000; }}
        .btn-clear {{ margin-top: 10px; padding: 8px 15px; cursor: pointer; background: #fff;
                      border: 2px solid #000; font-family: inherit; font-weight: bold;
                      text-transform: uppercase; transition: 0.2s; }}
        .btn-clear:hover {{ background: #000; color: #fff; }}

        @media (max-width: 768px) {{
            .filters {{ grid-template-columns: 1fr; }}
            .calendar {{ gap: 5px; }}
            .day-number {{ font-size: 1em; }}
            .screening-count {{ display: none; }}
        }}
    </style>
</head>
<body>
    <h1>&ldquo;The Ledger&rdquo;</h1>
    <div class="subtitle">
        Next 30 Days ({start_date} to {end_date})<br>
        Scraped from https://www.screenslate.com &bull; Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
    </div>

    <div class="controls">
        <input type="text" id="searchBar" class="search-bar"
               placeholder="Search movies, directors, theaters..." oninput="filterMovies()">
        <div class="search-hint">Try: &quot;Coppola&quot;, &quot;Metrograph&quot;, &quot;Pulp Fiction&quot;, &quot;1994&quot;</div>
        <div class="filters">
            <div class="filter-group">
                <label>Days of Week</label>
                <div class="day-checkboxes">
                    <label class="day-checkbox"><input type="checkbox" value="0" onchange="handleDayCheckboxChange()"> Sun</label>
                    <label class="day-checkbox"><input type="checkbox" value="1" onchange="handleDayCheckboxChange()"> Mon</label>
                    <label class="day-checkbox"><input type="checkbox" value="2" onchange="handleDayCheckboxChange()"> Tue</label>
                    <label class="day-checkbox"><input type="checkbox" value="3" onchange="handleDayCheckboxChange()"> Wed</label>
                    <label class="day-checkbox"><input type="checkbox" value="4" onchange="handleDayCheckboxChange()"> Thu</label>
                    <label class="day-checkbox"><input type="checkbox" value="5" onchange="handleDayCheckboxChange()"> Fri</label>
                    <label class="day-checkbox"><input type="checkbox" value="6" onchange="handleDayCheckboxChange()"> Sat</label>
                </div>
            </div>
            <div class="filter-group">
                <label>Specific Dates</label>
                <select id="dateFilter" multiple onchange="handleDateFilterChange()"></select>
                <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
            </div>
            <div class="filter-group">
                <label>Theaters</label>
                <select id="theaterFilter" multiple onchange="filterMovies()"></select>
                <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
            </div>
            <div class="filter-group">
                <label>Neighborhoods</label>
                <select id="neighborhoodFilter" multiple onchange="handleNeighborhoodChange()"></select>
                <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
            </div>
            <div class="filter-group">
                <label>Time Filter</label>
                <div class="time-filter">
                    <span class="time-filter-text">Between</span>
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
    /* ── DATA ─────────────────────────────────────────────── */
    const allMovies = {json.dumps(data, ensure_ascii=False)};
    const theaterCoords = {json.dumps(coords, ensure_ascii=False)};
    const theaterNeighborhoods = {json.dumps(tn_map, ensure_ascii=False)};
    const allTheaters = {json.dumps(theaters, ensure_ascii=False)};
    const allNeighborhoods = {json.dumps(neighborhoods, ensure_ascii=False)};

    let selectedDates = new Set();
    let selectedDaysOfWeek = new Set();
    let selectedTheaters = new Set();
    let selectedNeighborhoods = new Set();
    let map, drawingManager, currentShape;
    let markers = [];

    const dateMap = {{}};
    allMovies.forEach(m => {{ dateMap[m.date] = (dateMap[m.date] || 0) + 1; }});
    const dates = Object.keys(dateMap).sort();

    /* ── POPULATE DROPDOWNS ───────────────────────────────── */
    (function init() {{
        const ds = document.getElementById('dateFilter');
        dates.forEach(d => {{
            const o = document.createElement('option');
            o.value = d;
            const dt = new Date(d + 'T00:00:00');
            o.textContent = dt.toLocaleDateString('en-US', {{ weekday:'short', month:'short', day:'numeric' }});
            ds.appendChild(o);
        }});
        const ts = document.getElementById('theaterFilter');
        allTheaters.forEach(t => {{ const o = document.createElement('option'); o.value = t; o.textContent = t; ts.appendChild(o); }});
        const ns = document.getElementById('neighborhoodFilter');
        allNeighborhoods.forEach(n => {{ const o = document.createElement('option'); o.value = n; o.textContent = n; ns.appendChild(o); }});
    }})();

    /* ── MAP ───────────────────────────────────────────────── */
    function initMap() {{
        map = new google.maps.Map(document.getElementById('map'), {{
            center: {{lat:40.7128, lng:-74.0060}}, zoom: 11,
            styles: [{{ featureType:"poi", stylers:[{{ visibility:"off" }}] }}],
            mapTypeControl: false, streetViewControl: false
        }});
        drawingManager = new google.maps.drawing.DrawingManager({{
            drawingMode: null, drawingControl: true,
            drawingControlOptions: {{ position: google.maps.ControlPosition.TOP_CENTER,
                                      drawingModes: ['polygon','circle','rectangle'] }},
            circleOptions:    {{ fillOpacity:0.2, strokeColor:'#d32f2f', fillColor:'#d32f2f' }},
            polygonOptions:   {{ fillOpacity:0.2, strokeColor:'#d32f2f', fillColor:'#d32f2f' }},
            rectangleOptions: {{ fillOpacity:0.2, strokeColor:'#d32f2f', fillColor:'#d32f2f' }}
        }});
        drawingManager.setMap(map);
        google.maps.event.addListener(drawingManager, 'overlaycomplete', function(e) {{
            if (currentShape) currentShape.setMap(null);
            currentShape = e.overlay;
            filterMovies();
            if (e.type === 'circle') {{
                google.maps.event.addListener(currentShape, 'radius_changed', filterMovies);
                google.maps.event.addListener(currentShape, 'center_changed', filterMovies);
            }}
        }});
        Object.keys(theaterCoords).forEach(name => {{
            const mk = new google.maps.Marker({{
                position: theaterCoords[name], map, title: name,
                icon: {{ path: google.maps.SymbolPath.CIRCLE, scale:5,
                         fillColor:"#000", fillOpacity:1, strokeWeight:0 }}
            }});
            mk.theaterName = name;
            markers.push(mk);
        }});
    }}
    function clearSelection() {{ if (currentShape) currentShape.setMap(null); currentShape = null; filterMovies(); }}
    function isLocationInShape(lat, lng) {{
        if (!currentShape) return true;
        const pt = new google.maps.LatLng(lat, lng);
        if (currentShape.getBounds && !currentShape.getBounds().contains(pt)) return false;
        if (currentShape instanceof google.maps.Polygon)
            return google.maps.geometry.poly.containsLocation(pt, currentShape);
        if (currentShape instanceof google.maps.Circle) {{
            const dist = google.maps.geometry.spherical.computeDistanceBetween(pt, currentShape.getCenter());
            return dist <= currentShape.getRadius();
        }}
        return true;
    }}

    /* ── NEIGHBORHOOD FILTER ──────────────────────────────── */
    function handleNeighborhoodChange() {{
        selectedNeighborhoods = new Set(Array.from(document.getElementById('neighborhoodFilter').selectedOptions).map(o=>o.value));
        if (selectedNeighborhoods.size > 0) {{
            selectedTheaters.clear();
            allTheaters.forEach(t => {{ if (selectedNeighborhoods.has(theaterNeighborhoods[t])) selectedTheaters.add(t); }});
            Array.from(document.getElementById('theaterFilter').options).forEach(o => {{ o.selected = selectedTheaters.has(o.value); }});
        }} else {{
            selectedTheaters.clear();
            Array.from(document.getElementById('theaterFilter').options).forEach(o => {{ o.selected = false; }});
        }}
        filterMovies();
    }}

    /* ── CALENDAR ─────────────────────────────────────────── */
    function buildCalendar() {{
        const cal = document.getElementById('calendar');
        const first = new Date(dates[0] + 'T00:00:00');
        const last  = new Date(dates[dates.length-1] + 'T00:00:00');
        ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach((d,i) => {{
            const h = document.createElement('div'); h.className = 'calendar-header';
            h.textContent = d; h.onclick = () => toggleDayOfWeek(i); h.dataset.dayIndex = i;
            cal.appendChild(h);
        }});
        const s = new Date(first); s.setDate(s.getDate() - s.getDay());
        const e = new Date(last);  e.setDate(e.getDate() + (6 - e.getDay()));
        let cur = new Date(s);
        while (cur <= e) {{
            const ds = cur.toISOString().split('T')[0];
            const day = document.createElement('div');
            day.className = 'calendar-day'; day.dataset.date = ds;
            if (dateMap[ds]) {{
                day.classList.add('has-screenings');
                day.innerHTML = `<div class="day-number">${{cur.getDate()}}</div><div class="screening-count">${{dateMap[ds]}} films</div>`;
                day.onclick = () => toggleDate(ds);
            }} else {{
                day.innerHTML = `<div class="day-number">${{cur.getDate()}}</div>`;
                day.style.opacity = '0.3'; day.style.cursor = 'default';
            }}
            cal.appendChild(day);
            cur.setDate(cur.getDate() + 1);
        }}
    }}
    function toggleDayOfWeek(i) {{
        selectedDaysOfWeek.has(i) ? selectedDaysOfWeek.delete(i) : selectedDaysOfWeek.add(i);
        selectedDates.clear(); syncUI(); filterMovies();
    }}
    function handleDayCheckboxChange() {{
        selectedDaysOfWeek.clear();
        document.querySelectorAll('.day-checkbox input:checked').forEach(cb => selectedDaysOfWeek.add(+cb.value));
        selectedDates.clear(); syncUI(); filterMovies();
    }}
    function toggleDate(ds) {{
        selectedDates.has(ds) ? selectedDates.delete(ds) : selectedDates.add(ds);
        if (selectedDates.size) {{ selectedDaysOfWeek.clear(); }}
        syncUI(); filterMovies();
    }}
    function handleDateFilterChange() {{
        selectedDates = new Set(Array.from(document.getElementById('dateFilter').selectedOptions).map(o=>o.value));
        if (selectedDates.size) selectedDaysOfWeek.clear();
        syncUI(); filterMovies();
    }}
    function syncUI() {{
        // date select
        Array.from(document.getElementById('dateFilter').options).forEach(o => {{ o.selected = selectedDates.has(o.value); }});
        // day-of-week checkboxes
        document.querySelectorAll('.day-checkbox').forEach(lbl => {{
            const cb = lbl.querySelector('input');
            cb.checked = selectedDaysOfWeek.has(+cb.value);
            lbl.classList.toggle('checked', cb.checked);
        }});
        // calendar headers
        document.querySelectorAll('.calendar-header').forEach(h => {{
            h.classList.toggle('selected', selectedDaysOfWeek.has(+h.dataset.dayIndex));
        }});
        // calendar days
        document.querySelectorAll('.calendar-day').forEach(d => {{
            d.classList.toggle('selected', selectedDates.has(d.dataset.date));
        }});
    }}

    /* ── TIME PARSING (FIXED REGEX) ───────────────────────── */
    function parseTime(str) {{
        const m = str.match(/(\\d{{1,2}}):(\\d{{2}})\\s*([AP]M)/i);
        if (!m) return null;
        let h = parseInt(m[1]), min = parseInt(m[2]);
        const ap = m[3].toUpperCase();
        if (ap === 'PM' && h !== 12) h += 12;
        if (ap === 'AM' && h === 12) h = 0;
        return h * 60 + min;
    }}
    function toMin(t) {{ const [h,m] = t.split(':').map(Number); return h*60+m; }}
    function matchesTimeRange(times, lo, hi) {{
        if (times[0] === 'Check website') return true;
        if (hi < lo) hi = 24*60-1;
        return times.some(t => {{ const m = parseTime(t); return m === null || (m >= lo && m <= hi); }});
    }}

    /* ── FILTER ────────────────────────────────────────────── */
    function filterMovies() {{
        const q = document.getElementById('searchBar').value.toLowerCase();
        const lo = toMin(document.getElementById('startTime').value);
        const hi = toMin(document.getElementById('endTime').value);
        selectedTheaters = new Set(Array.from(document.getElementById('theaterFilter').selectedOptions).map(o=>o.value));

        const filtered = allMovies.filter(m => {{
            if (q && ![m.title,m.director,m.theater,m.year].join(' ').toLowerCase().includes(q)) return false;
            const c = theaterCoords[m.theater];
            if (c && !isLocationInShape(c.lat, c.lng)) return false;
            if (!c && currentShape) return false;
            if (selectedTheaters.size && !selectedTheaters.has(m.theater)) return false;
            if (selectedDates.size && !selectedDates.has(m.date)) return false;
            if (selectedDaysOfWeek.size) {{
                const dow = new Date(m.date + 'T00:00:00').getDay();
                if (!selectedDaysOfWeek.has(dow)) return false;
            }}
            if (!matchesTimeRange(m.showtimes, lo, hi)) return false;
            return true;
        }});
        renderMovies(filtered);
    }}

    /* ── RENDER ────────────────────────────────────────────── */
    function renderMovies(movies) {{
        document.getElementById('resultCount').textContent = movies.length + ' screenings found';
        const c = document.getElementById('movieContainer');
        if (!movies.length) {{ c.innerHTML = '<div style="text-align:center;padding:40px;color:#666;">No screenings match your filters.</div>'; return; }}
        c.innerHTML = movies.map(m => {{
            const d = new Date(m.date+'T00:00:00');
            const ds = d.toLocaleDateString('en-US',{{weekday:'short',month:'short',day:'numeric'}});
            const st = m.showtimes.map(t=>`<span class="showtime">${{t}}</span>`).join('');
            return `<div class="movie-card">
                <div class="date-badge">${{ds}}</div>
                <div class="movie-title">${{m.title}} <span style="font-weight:normal;font-size:0.8em">(${{m.year}})</span></div>
                <div class="movie-meta">Dir: ${{m.director}}</div>
                <div class="theater">${{m.theater}}</div>
                <div class="showtimes">${{st}}</div>
                <a href="${{m.link}}" target="_blank" class="link">Tickets &amp; Info</a>
            </div>`;
        }}).join('');
    }}

    /* ── BOOT ──────────────────────────────────────────────── */
    window.onload = function() {{ buildCalendar(); initMap(); renderMovies(allMovies); }};
    </script>
</body>
</html>"""

    fp = os.path.join(OUTPUT_FOLDER, "index.html")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ Website saved: {fp}")


# ── MAIN ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    raw = load_data()
    if raw:
        clean = deduplicate(raw)
        save_ics(clean)
        save_html(clean)
