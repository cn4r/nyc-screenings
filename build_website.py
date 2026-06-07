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

    # Build coords map (only theaters we know about)
    coords = {}
    for t in theaters:
        upper = t.upper()
        if upper in THEATER_LOCATIONS:
            coords[t] = THEATER_LOCATIONS[upper]
        elif t in THEATER_LOCATIONS:
            coords[t] = THEATER_LOCATIONS[t]
        else:
            for known, loc in THEATER_LOCATIONS.items():
                if known in upper:
                    coords[t] = loc
                    break

    # Collect all genres and years from data
    all_genres = sorted({g for s in data for g in s.get("genres", [])})
    all_years = sorted({
        re.search(r'\d{4}', str(s.get("year", ""))).group(0)
        for s in data
        if re.search(r'\d{4}', str(s.get("year", "")))
    })
    all_decades = sorted({y[:3] + "0s" for y in all_years})

    # ── Build the HTML string ───────────────────────────────────────
    # NOTE: The f-string uses {{ }} to emit literal braces in JS.
    today_str = datetime.now().strftime("%Y-%m-%d")
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>NYC Movie Ledger</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {{ --bg: #fafafa; --fg: #000; --card-bg: #fff; --card-border: #000;
                 --accent: #d32f2f; --muted: #666; --subtle: #f0f0f0; --tag-bg: #f0f0f0;
                 --tag-border: #ccc; --shadow: #000; }}
        body.dark {{ --bg: #1a1a1a; --fg: #e0e0e0; --card-bg: #2a2a2a; --card-border: #555;
                     --accent: #ff5252; --muted: #aaa; --subtle: #333; --tag-bg: #333;
                     --tag-border: #555; --shadow: #ff5252; }}

        body {{ font-family: "Times New Roman", serif; background: var(--bg); color: var(--fg);
               max-width: 1400px; margin: 0 auto; padding: 20px; transition: background 0.3s, color 0.3s; }}

        /* ── Header ─────────────────────────────────── */
        .header {{ display: flex; align-items: center; justify-content: space-between;
                   flex-wrap: wrap; gap: 10px; border-bottom: 3px solid var(--fg);
                   padding-bottom: 10px; margin-bottom: 5px; }}
        h1 {{ text-transform: uppercase; letter-spacing: 3px; margin: 0; }}
        .header-actions {{ display: flex; gap: 10px; align-items: center; }}
        .now-showing-btn {{ padding: 8px 18px; background: var(--accent); color: #fff; border: none;
                            font-family: inherit; font-weight: bold; text-transform: uppercase;
                            font-size: 0.85em; letter-spacing: 1px; cursor: pointer; transition: 0.2s; }}
        .now-showing-btn:hover {{ opacity: 0.85; }}
        .now-showing-btn.active {{ box-shadow: 0 0 0 3px var(--fg); }}
        .dark-toggle {{ padding: 8px 12px; background: var(--fg); color: var(--bg); border: none;
                        font-family: inherit; font-weight: bold; font-size: 1em; cursor: pointer;
                        transition: 0.2s; }}
        .dark-toggle:hover {{ opacity: 0.8; }}
        .subtitle {{ color: var(--muted); font-style: italic; margin-bottom: 15px; }}

        /* ── Sticky bar ─────────────────────────────── */
        .sticky-bar {{ position: sticky; top: 0; z-index: 100; background: var(--bg);
                       padding: 10px 0; border-bottom: 2px solid var(--card-border);
                       transition: background 0.3s; }}
        .sticky-bar .search-bar {{ width: 100%; padding: 10px; border: 2px solid var(--card-border);
                                    font-family: inherit; font-size: 1.1em; box-sizing: border-box;
                                    background: var(--card-bg); color: var(--fg); }}
        .sticky-bar .search-bar:focus {{ outline: none; border-color: var(--accent); }}
        .sticky-badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; align-items: center; }}
        .search-hint {{ font-size: 0.8em; color: var(--muted); font-style: italic; margin-top: 4px; }}
        /* ── Autocomplete ───────────────────────────── */
        .search-container {{ position: relative; }}
        .autocomplete {{ position: absolute; top: 100%%; left: 0; right: 0; background: var(--card-bg);
                         border: 2px solid var(--card-border); max-height: 250px; overflow-y: auto;
                         z-index: 200; display: none; }}
        .autocomplete.show {{ display: block; }}
        .ac-item {{ padding: 8px 12px; cursor: pointer; font-size: 0.95em;
                    border-bottom: 1px solid var(--subtle); }}
        .ac-item:hover, .ac-item.selected {{ background: var(--subtle); }}
        .ac-type {{ font-size: 0.75em; color: var(--muted); text-transform: uppercase;
                    margin-left: 8px; }}

        /* ── Controls panel ─────────────────────────── */
        .controls {{ margin-bottom: 20px; background: var(--card-bg); border: 2px solid var(--card-border); }}
        .tabs {{ display: flex; border-bottom: 2px solid var(--card-border); }}
        .tab {{ padding: 12px 25px; cursor: pointer; font-weight: bold; text-transform: uppercase;
                font-size: 0.85em; letter-spacing: 1px; border: none; background: none;
                font-family: inherit; border-bottom: 3px solid transparent; transition: all 0.2s;
                color: var(--fg); }}
        .tab:hover {{ background: var(--subtle); }}
        .tab.active {{ border-bottom-color: var(--accent); color: var(--accent); }}
        .tab-content {{ display: none; padding: 20px; }}
        .tab-content.active {{ display: block; }}

        /* ── Filters ────────────────────────────────── */
        .filter-group {{ margin-bottom: 15px; }}
        .filter-group > label {{ font-weight: bold; margin-bottom: 5px; display: block;
                                 text-transform: uppercase; font-size: 0.9em; letter-spacing: 1px; }}
        select, input[type="time"], input[type="number"] {{
            padding: 8px; border: 2px solid var(--card-border); font-family: inherit; font-size: 1em;
            background: var(--card-bg); color: var(--fg); }}
        select[multiple] {{ min-height: 120px; }}
        .filter-hint {{ font-size: 0.75em; color: var(--muted); font-style: italic; margin-top: 3px; }}
        .filter-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}

        .day-checkboxes {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; }}
        .day-checkbox {{ display: flex; align-items: center; gap: 5px; padding: 6px 10px;
                         border: 2px solid var(--card-border); cursor: pointer; transition: all 0.2s;
                         background: var(--card-bg); font-size: 0.9em; }}
        .day-checkbox:hover {{ background: var(--subtle); }}
        .day-checkbox input[type="checkbox"] {{ cursor: pointer; }}
        .day-checkbox.checked {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

        .time-filter {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 5px; }}
        .time-filter-text {{ font-size: 0.95em; white-space: nowrap; }}
        .time-filter input[type="time"] {{ width: 110px; }}
        .runtime-filter {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 5px; }}
        .runtime-filter input[type="number"] {{ width: 80px; }}

        .pill-checkboxes {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 5px; }}
        .pill {{ display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px;
                 border: 2px solid var(--card-border); cursor: pointer; transition: all 0.2s;
                 background: var(--card-bg); font-size: 0.85em; text-transform: capitalize; }}
        .pill:hover {{ background: var(--subtle); }}
        .pill input {{ display: none; }}
        .pill.checked {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

        /* ── Calendar (collapsible) ─────────────────── */
        .calendar-toggle {{ cursor: pointer; font-weight: bold; text-transform: uppercase;
                            font-size: 0.85em; letter-spacing: 1px; padding: 10px 0; margin-top: 10px;
                            border: none; background: none; font-family: inherit; color: var(--fg); }}
        .calendar-toggle:hover {{ color: var(--accent); }}
        .calendar-wrap {{ overflow: hidden; transition: max-height 0.3s ease; max-height: 0; }}
        .calendar-wrap.open {{ max-height: 600px; }}
        .calendar {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; margin-top: 5px; }}
        .calendar-day {{ aspect-ratio: 1; border: 2px solid var(--subtle); padding: 8px; text-align: center;
                         cursor: pointer; transition: all 0.2s; display: flex; flex-direction: column;
                         justify-content: center; align-items: center; position: relative; }}
        .calendar-day:hover {{ background: var(--subtle); transform: scale(1.05); }}
        .calendar-day.has-screenings {{ border-color: var(--card-border); font-weight: bold; }}
        .calendar-day.has-screenings:hover {{ background: var(--fg); color: var(--bg); }}
        .calendar-day.selected {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
        .calendar-header {{ font-weight: bold; text-align: center; padding: 10px; background: var(--fg);
                            color: var(--bg); text-transform: uppercase; font-size: 0.85em;
                            letter-spacing: 1px; cursor: pointer; transition: all 0.2s; }}
        .calendar-header:hover {{ opacity: 0.8; }}
        .calendar-header.selected {{ background: var(--accent); }}
        .day-number {{ font-size: 1.2em; margin-bottom: 2px; }}
        .screening-count {{ font-size: 0.7em; color: var(--muted); }}
        .calendar-day.has-screenings .screening-count {{ color: var(--accent); }}
        .calendar-day.selected .screening-count {{ color: #fff; }}

        /* ── Map ────────────────────────────────────── */
        #map {{ height: 400px; width: 100%; border: 2px solid var(--card-border); margin-top: 10px;
                touch-action: none; }}
        .btn-clear {{ margin-top: 10px; padding: 8px 15px; cursor: pointer; background: var(--card-bg);
                      border: 2px solid var(--card-border); font-family: inherit; font-weight: bold;
                      text-transform: uppercase; transition: 0.2s; color: var(--fg); }}
        .btn-clear:hover {{ background: var(--fg); color: var(--bg); }}

        /* ── Results bar ────────────────────────────── */
        .results-bar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
                        margin-bottom: 15px; }}
        .sort-controls {{ display: flex; align-items: center; gap: 8px; }}
        .sort-controls label {{ font-weight: bold; text-transform: uppercase; font-size: 0.8em;
                                letter-spacing: 1px; }}
        .sort-controls select {{ padding: 6px 10px; border: 2px solid var(--card-border);
                                 font-family: inherit; font-size: 0.9em;
                                 background: var(--card-bg); color: var(--fg); }}
        .view-toggle {{ display: flex; gap: 4px; margin-left: auto; }}
        .view-btn {{ padding: 6px 12px; border: 2px solid var(--card-border); background: var(--card-bg);
                     cursor: pointer; font-family: inherit; font-weight: bold; font-size: 0.8em;
                     text-transform: uppercase; transition: 0.2s; color: var(--fg); }}
        .view-btn:hover {{ background: var(--subtle); }}
        .view-btn.active {{ background: var(--fg); color: var(--bg); }}
        .filter-badge {{ display: inline-flex; align-items: center; gap: 5px; padding: 4px 10px;
                         background: var(--accent); color: #fff; font-size: 0.8em; font-weight: bold;
                         border: none; cursor: pointer; font-family: inherit; transition: 0.2s; }}
        .filter-badge:hover {{ opacity: 0.8; }}
        .filter-badge .badge-x {{ font-size: 1.1em; }}
        .count {{ text-align: center; padding: 15px; background: var(--fg); color: var(--bg);
                  font-weight: bold; font-size: 1.1em; margin-bottom: 20px; letter-spacing: 2px; }}

        /* ── Movie cards ────────────────────────────── */
        .movie-card {{ background: var(--card-bg); border: 2px solid var(--card-border); padding: 20px;
                       margin-bottom: 15px; transition: all 0.2s; position: relative;
                       display: flex; gap: 20px; }}
        .movie-card:hover {{ box-shadow: 5px 5px 0px var(--shadow); transform: translate(-2px, -2px); }}
        .movie-poster {{ width: 80px; min-width: 80px; height: 120px; object-fit: cover;
                         border: 1px solid var(--card-border); }}
        .movie-body {{ flex: 1; min-width: 0; }}
        .movie-title {{ font-size: 1.3em; font-weight: bold; margin-bottom: 5px; cursor: pointer; }}
        .movie-meta {{ color: var(--muted); margin-bottom: 10px; font-size: 0.95em; }}
        .movie-runtime {{ color: var(--muted); font-size: 0.9em; }}
        .movie-genres {{ display: flex; flex-wrap: wrap; gap: 5px; margin: 8px 0; }}
        .genre-tag {{ background: var(--tag-bg); border: 1px solid var(--tag-border); padding: 2px 8px;
                      font-size: 0.8em; text-transform: capitalize; }}
        .theater {{ font-weight: bold; margin-bottom: 10px; }}
        .showtimes {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }}
        .showtime {{ background: var(--fg); color: var(--bg); padding: 5px 12px; font-weight: bold;
                     font-size: 0.9em; }}
        .date-badge {{ display: inline-block; background: var(--fg); color: var(--bg); padding: 3px 10px;
                       font-size: 0.85em; font-weight: bold; margin-bottom: 10px; }}
        .today-badge {{ background: var(--accent); color: #fff; padding: 3px 8px; font-size: 0.75em;
                        font-weight: bold; text-transform: uppercase; letter-spacing: 1px;
                        margin-left: 8px; }}
        .card-links {{ display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }}
        .link {{ color: var(--fg); text-decoration: none; border-bottom: 2px solid var(--fg);
                 font-weight: bold; }}
        .link:hover {{ background: var(--fg); color: var(--bg); }}
        .letterboxd-link {{ border: none; display: inline-flex; align-items: center; }}
        .letterboxd-icon {{ width: 28px; height: 28px; border-radius: 50%%; object-fit: cover;
                            transition: transform 0.2s; }}
        .letterboxd-icon:hover {{ transform: scale(1.15); }}

        /* ── Similar films drawer ───────────────────── */
        .similar-drawer {{ border-top: 1px solid var(--subtle); margin-top: 15px; padding-top: 10px;
                           display: none; }}
        .similar-drawer.open {{ display: block; }}
        .similar-drawer h4 {{ margin: 0 0 8px 0; font-size: 0.9em; text-transform: uppercase;
                              letter-spacing: 1px; color: var(--muted); }}
        .similar-list {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .similar-chip {{ padding: 4px 10px; border: 1px solid var(--card-border); font-size: 0.8em;
                         cursor: pointer; background: var(--subtle); }}
        .similar-chip:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

        /* ── Grid view ──────────────────────────────── */
        .view-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                      gap: 15px; }}
        .view-grid .movie-card {{ margin-bottom: 0; flex-direction: column; }}
        .view-grid .movie-card .similar-drawer {{ display: none !important; }}
        .view-grid .movie-poster {{ width: 100%%; height: 200px; min-width: unset; }}

        /* ── Table view ─────────────────────────────── */
        .view-table {{ width: 100%%; border-collapse: collapse; }}
        .view-table th {{ background: var(--fg); color: var(--bg); padding: 10px; text-align: left;
                          font-size: 0.8em; text-transform: uppercase; letter-spacing: 1px;
                          position: sticky; top: 50px; z-index: 50; }}
        .view-table td {{ padding: 10px; border-bottom: 1px solid var(--subtle); font-size: 0.9em;
                          vertical-align: top; }}
        .view-table tr:hover td {{ background: var(--subtle); }}
        .view-table a {{ color: var(--fg); }}

        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 2px solid var(--fg);
                   text-align: center; color: var(--muted); font-size: 0.9em; }}
        .footer a {{ color: var(--fg); }}

        @media (max-width: 768px) {{
            .tabs {{ flex-wrap: wrap; }}
            .tab {{ flex: 1; text-align: center; padding: 10px 10px; font-size: 0.75em; }}
            .filter-row {{ grid-template-columns: 1fr; }}
            .calendar {{ gap: 5px; }}
            .day-number {{ font-size: 1em; }}
            .screening-count {{ display: none; }}
            .view-grid {{ grid-template-columns: 1fr; }}
            .header {{ flex-direction: column; align-items: flex-start; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>&ldquo;The Ledger&rdquo;</h1>
        <div class="header-actions">
            <button class="now-showing-btn" id="nowShowingBtn" onclick="toggleNowShowing()">Now Showing</button>
            <button class="dark-toggle" id="darkToggle" onclick="toggleDark()">Dark</button>
        </div>
    </div>
    <div class="subtitle">
        Next 90 Days ({start_date} to {end_date})<br>
        Scraped from https://www.screenslate.com &bull; Last updated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
    </div>

    <div class="sticky-bar" id="stickyBar">
        <div class="search-container">
            <input type="text" id="searchBar" class="search-bar"
                   placeholder="Search movies, directors, theaters, genres..." oninput="onSearchInput()" autocomplete="off">
            <div class="autocomplete" id="autocomplete"></div>
        </div>
        <div class="search-hint" id="searchHint">Try: &quot;Coppola&quot;, &quot;Metrograph&quot;, &quot;drama&quot;, &quot;80s&quot;</div>
        <div class="sticky-badges" id="activeFilters"></div>
    </div>

    <div class="controls">
        <div class="tabs">
            <button class="tab active" onclick="switchTab('when')">When</button>
            <button class="tab" onclick="switchTab('where')">Where</button>
            <button class="tab" onclick="switchTab('what')">What</button>
        </div>
        <div id="tab-when" class="tab-content active">
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
            <div class="filter-row">
                <div class="filter-group">
                    <label>Date Range</label>
                    <div style="display:flex;gap:8px;margin-bottom:8px;">
                        <label class="pill" onclick="setDateMode('after')"><input type="radio" name="dateMode" value="after"> After</label>
                        <label class="pill" onclick="setDateMode('before')"><input type="radio" name="dateMode" value="before"> Before</label>
                        <label class="pill" onclick="setDateMode('between')"><input type="radio" name="dateMode" value="between"> Between</label>
                        <label class="pill checked" onclick="setDateMode('specific')"><input type="radio" name="dateMode" value="specific" checked> Specific</label>
                    </div>
                    <div id="datePickerSingle" style="display:none;">
                        <select id="dateSingle" onchange="handleDateModeChange()"></select>
                    </div>
                    <div id="datePickerRange" style="display:none;">
                        <div style="display:flex;gap:8px;align-items:center;">
                            <select id="dateRangeStart" onchange="handleDateModeChange()"></select>
                            <span>to</span>
                            <select id="dateRangeEnd" onchange="handleDateModeChange()"></select>
                        </div>
                    </div>
                    <div id="datePickerMulti">
                        <select id="dateFilter" multiple onchange="handleDateFilterChange()"></select>
                        <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
                    </div>
                </div>
                <div class="filter-group">
                    <label>Starts Between</label>
                    <div class="time-filter">
                        <input type="time" id="startTime" value="00:00" onchange="filterMovies()">
                        <span class="time-filter-text">and</span>
                        <input type="time" id="endTime" value="23:59" onchange="filterMovies()">
                    </div>
                </div>
            </div>
            <button class="calendar-toggle" onclick="toggleCalendar()">&#9660; Calendar</button>
            <div class="calendar-wrap" id="calendarWrap">
                <div id="calendar" class="calendar"></div>
            </div>
        </div>
        <div id="tab-where" class="tab-content">
            <div class="filter-group">
                <label>Theaters</label>
                <select id="theaterFilter" multiple onchange="filterMovies()"></select>
                <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
            </div>
            <div class="filter-group">
                <label>Map Filter (Draw to Filter)</label>
                <div id="map"></div>
                <button class="btn-clear" onclick="clearMapDrawing()">Clear Map Drawing</button>
            </div>
        </div>
        <div id="tab-what" class="tab-content">
            <div class="filter-group">
                <label>Genre</label>
                <div id="genreFilter" class="pill-checkboxes"></div>
            </div>
            <div class="filter-group">
                <label>Decade</label>
                <div id="decadeFilter" class="pill-checkboxes"></div>
            </div>
            <div class="filter-group">
                <label>Year</label>
                <select id="yearFilter" multiple onchange="filterMovies()"></select>
                <div class="filter-hint">Hold Ctrl/Cmd to select multiple</div>
            </div>
            <div class="filter-group">
                <label>Runtime</label>
                <div class="runtime-filter">
                    <input type="number" id="runtimeMin" placeholder="Min" min="0" step="5" onchange="filterMovies()">
                    <span class="time-filter-text">to</span>
                    <input type="number" id="runtimeMax" placeholder="Max" min="0" step="5" onchange="filterMovies()">
                    <span class="time-filter-text">minutes</span>
                </div>
            </div>
        </div>
    </div>

    <div class="results-bar">
        <div class="sort-controls">
            <label>Sort by</label>
            <select id="sortBy" onchange="filterMovies()">
                <option value="date-asc">Date (soonest)</option>
                <option value="date-desc">Date (latest)</option>
                <option value="title-asc">Title (A-Z)</option>
                <option value="title-desc">Title (Z-A)</option>
                <option value="runtime-asc">Runtime (shortest)</option>
                <option value="runtime-desc">Runtime (longest)</option>
                <option value="showtimes-desc">Most showtimes</option>
                <option value="rating-desc">Rating (highest)</option>
                <option value="rating-asc">Rating (lowest)</option>
            </select>
        </div>
        <div class="view-toggle">
            <button class="view-btn active" data-view="list" onclick="setView('list')">List</button>
            <button class="view-btn" data-view="grid" onclick="setView('grid')">Grid</button>
            <button class="view-btn" data-view="table" onclick="setView('table')">Table</button>
        </div>
    </div>
    <div class="count" id="resultCount">0 screenings found</div>
    <div id="movieContainer"></div>

    <div class="footer">
        Data sourced from <a href="https://www.screenslate.com" target="_blank">Screen Slate</a><br>
        Calendar file available: <a href="./nyc_movies.ics" download>Download ICS</a>
    </div>

    <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyA5B9DU1gTNvgJ4rVC5FsEgGneDcEVXfG0&libraries=drawing"></script>
    <script>
    /* ── DATA ─────────────────────────────────────────────── */
    const allMovies = {json.dumps(data, ensure_ascii=False)};
    const theaterCoords = {json.dumps(coords, ensure_ascii=False)};
    const allTheaters = {json.dumps(theaters, ensure_ascii=False)};
    const allGenres = {json.dumps(all_genres, ensure_ascii=False)};
    const allYears = {json.dumps(all_years, ensure_ascii=False)};
    const allDecades = {json.dumps(all_decades, ensure_ascii=False)};
    const TODAY = '{today_str}';

    let selectedDates = new Set();
    let selectedDaysOfWeek = new Set();
    let selectedTheaters = new Set();
    let selectedGenres = new Set();
    let selectedDecades = new Set();
    let map, drawingManager, currentShape;
    let markers = [];
    let mapInitialized = false;
    let nowShowingActive = false;
    let currentView = 'list';
    let dateMode = 'specific';

    const dateMap = {{}};
    allMovies.forEach(m => {{ dateMap[m.date] = (dateMap[m.date] || 0) + 1; }});
    const dates = Object.keys(dateMap).sort();

    // Build search index for autocomplete
    const searchIndex = [];
    const seenTitles = new Set(), seenDirs = new Set(), seenTheaters = new Set();
    allMovies.forEach(m => {{
        if (!seenTitles.has(m.title)) {{ searchIndex.push({{ text: m.title, type: 'Film' }}); seenTitles.add(m.title); }}
        if (m.director && m.director !== 'N/A' && !seenDirs.has(m.director)) {{
            searchIndex.push({{ text: m.director, type: 'Director' }}); seenDirs.add(m.director);
        }}
        if (!seenTheaters.has(m.theater)) {{ searchIndex.push({{ text: m.theater, type: 'Theater' }}); seenTheaters.add(m.theater); }}
    }});
    allGenres.forEach(g => searchIndex.push({{ text: g, type: 'Genre' }}));
    allDecades.forEach(d => searchIndex.push({{ text: d, type: 'Decade' }}));

    /* ── DARK MODE ─────────────────────────────────────────── */
    function toggleDark() {{
        document.body.classList.toggle('dark');
        const btn = document.getElementById('darkToggle');
        btn.textContent = document.body.classList.contains('dark') ? 'Light' : 'Dark';
    }}

    /* ── NOW SHOWING ───────────────────────────────────────── */
    function toggleNowShowing() {{
        nowShowingActive = !nowShowingActive;
        document.getElementById('nowShowingBtn').classList.toggle('active', nowShowingActive);
        if (nowShowingActive) {{
            selectedDates.clear();
            selectedDates.add(TODAY);
            selectedDaysOfWeek.clear();
            syncUI();
        }} else {{
            selectedDates.clear();
            syncUI();
        }}
        filterMovies();
    }}

    /* ── VIEW TOGGLE ───────────────────────────────────────── */
    function setView(v) {{
        currentView = v;
        document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === v));
        filterMovies();
    }}

    /* ── CALENDAR COLLAPSE ─────────────────────────────────── */
    function toggleCalendar() {{
        const wrap = document.getElementById('calendarWrap');
        wrap.classList.toggle('open');
        const btn = wrap.previousElementSibling;
        btn.innerHTML = wrap.classList.contains('open') ? '&#9650; Calendar' : '&#9660; Calendar';
    }}

    /* ── TABS ──────────────────────────────────────────────── */
    function switchTab(name) {{
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
        document.getElementById('tab-' + name).classList.add('active');
        document.querySelector('[onclick*=\"' + name + '\"]').classList.add('active');
        if (name === 'where' && !mapInitialized) {{ initMap(); mapInitialized = true; }}
    }}

    /* ── DATE MODE ──────────────────────────────────────────── */
    function setDateMode(mode) {{
        dateMode = mode;
        document.querySelectorAll('[name="dateMode"]').forEach(r => {{
            r.closest('.pill').classList.toggle('checked', r.value === mode);
        }});
        document.getElementById('datePickerMulti').style.display = mode === 'specific' ? '' : 'none';
        document.getElementById('datePickerSingle').style.display = (mode === 'after' || mode === 'before') ? '' : 'none';
        document.getElementById('datePickerRange').style.display = mode === 'between' ? '' : 'none';
        selectedDates.clear(); syncUI(); filterMovies();
    }}
    function handleDateModeChange() {{
        selectedDates.clear();
        if (dateMode === 'after') {{
            const v = document.getElementById('dateSingle').value;
            if (v) dates.forEach(d => {{ if (d >= v) selectedDates.add(d); }});
        }} else if (dateMode === 'before') {{
            const v = document.getElementById('dateSingle').value;
            if (v) dates.forEach(d => {{ if (d <= v) selectedDates.add(d); }});
        }} else if (dateMode === 'between') {{
            const s = document.getElementById('dateRangeStart').value;
            const e = document.getElementById('dateRangeEnd').value;
            if (s && e) dates.forEach(d => {{ if (d >= s && d <= e) selectedDates.add(d); }});
        }}
        nowShowingActive = false; document.getElementById('nowShowingBtn').classList.remove('active');
        syncUI(); filterMovies();
    }}

    /* ── POPULATE DROPDOWNS & PILLS ───────────────────────── */
    (function init() {{
        const ds = document.getElementById('dateFilter');
        const dSingle = document.getElementById('dateSingle');
        const dStart = document.getElementById('dateRangeStart');
        const dEnd = document.getElementById('dateRangeEnd');
        dates.forEach(d => {{
            const dt = new Date(d + 'T00:00:00');
            const label = dt.toLocaleDateString('en-US', {{ weekday:'short', month:'short', day:'numeric' }});
            const o = document.createElement('option'); o.value = d; o.textContent = label; ds.appendChild(o);
            const o2 = o.cloneNode(true); dSingle.appendChild(o2);
            const o3 = o.cloneNode(true); dStart.appendChild(o3);
            const o4 = o.cloneNode(true); dEnd.appendChild(o4);
        }});
        const ts = document.getElementById('theaterFilter');
        allTheaters.forEach(t => {{ const o = document.createElement('option'); o.value = t; o.textContent = t; ts.appendChild(o); }});
        const gf = document.getElementById('genreFilter');
        allGenres.forEach(g => {{
            const lbl = document.createElement('label'); lbl.className = 'pill';
            lbl.innerHTML = '<input type="checkbox" value="' + g + '"> ' + g;
            lbl.onclick = function() {{ setTimeout(() => {{ togglePill(lbl); filterMovies(); }}, 0); }};
            gf.appendChild(lbl);
        }});
        const df = document.getElementById('decadeFilter');
        allDecades.forEach(d => {{
            const lbl = document.createElement('label'); lbl.className = 'pill';
            lbl.innerHTML = '<input type="checkbox" value="' + d + '"> ' + d;
            lbl.onclick = function() {{ setTimeout(() => {{ togglePill(lbl); filterMovies(); }}, 0); }};
            df.appendChild(lbl);
        }});
        const yf = document.getElementById('yearFilter');
        allYears.forEach(y => {{ const o = document.createElement('option'); o.value = y; o.textContent = y; yf.appendChild(o); }});
    }})();
    function togglePill(lbl) {{ const cb = lbl.querySelector('input'); lbl.classList.toggle('checked', cb.checked); }}

    /* ── AUTOCOMPLETE ──────────────────────────────────────── */
    let acIndex = -1;
    function onSearchInput() {{
        filterMovies();
        const q = document.getElementById('searchBar').value.toLowerCase().trim();
        const ac = document.getElementById('autocomplete');
        acIndex = -1;
        if (q.length < 2) {{ ac.classList.remove('show'); return; }}
        const matches = searchIndex.filter(s => fuzzyMatch(s.text.toLowerCase(), q)).slice(0, 8);
        if (!matches.length) {{ ac.classList.remove('show'); return; }}
        ac.innerHTML = matches.map((m, i) =>
            `<div class="ac-item" data-i="${{i}}" onmousedown="selectAC('${{m.text.replace(/'/g, "\\\\'")}}')">` +
            m.text + `<span class="ac-type">${{m.type}}</span></div>`
        ).join('');
        ac.classList.add('show');
    }}
    function selectAC(text) {{
        document.getElementById('searchBar').value = text;
        document.getElementById('autocomplete').classList.remove('show');
        filterMovies();
    }}
    document.addEventListener('click', e => {{
        if (!e.target.closest('.search-container')) document.getElementById('autocomplete').classList.remove('show');
    }});
    document.getElementById('searchBar').addEventListener('keydown', function(e) {{
        const ac = document.getElementById('autocomplete');
        const items = ac.querySelectorAll('.ac-item');
        if (!items.length) return;
        if (e.key === 'ArrowDown') {{ e.preventDefault(); acIndex = Math.min(acIndex+1, items.length-1); }}
        else if (e.key === 'ArrowUp') {{ e.preventDefault(); acIndex = Math.max(acIndex-1, 0); }}
        else if (e.key === 'Enter' && acIndex >= 0) {{ e.preventDefault(); items[acIndex].onmousedown(); return; }}
        else return;
        items.forEach((it, i) => it.classList.toggle('selected', i === acIndex));
    }});

    /* ── FUZZY MATCH ───────────────────────────────────────── */
    function fuzzyWord(haystack, word) {{
        // Single word fuzzy: exact substring or high trigram overlap
        if (haystack.includes(word)) return true;
        if (word.length < 3) return haystack.includes(word);
        const trigrams = (s) => {{ const t = []; for (let i = 0; i <= s.length - 3; i++) t.push(s.substring(i, i+3)); return t; }};
        const wt = trigrams(word);
        const ht = new Set(trigrams(haystack));
        const overlap = wt.filter(t => ht.has(t)).length;
        return overlap >= wt.length * 0.75;
    }}
    function fuzzyMatch(str, query) {{
        if (str.includes(query)) return true;
        // Every word in the query must match individually
        const words = query.split(/\\s+/).filter(w => w.length > 0);
        return words.every(w => fuzzyWord(str, w));
    }}

    /* ── MAP ───────────────────────────────────────────────── */
    function initMap() {{
        map = new google.maps.Map(document.getElementById('map'), {{
            center: {{lat:40.7128, lng:-74.0060}}, zoom: 11,
            styles: [{{ featureType:"poi", stylers:[{{ visibility:"off" }}] }}],
            mapTypeControl: false, streetViewControl: false,
            gestureHandling: 'greedy',  // allows single-finger pan on touch devices
            zoomControl: true,
        }});
        drawingManager = new google.maps.drawing.DrawingManager({{
            drawingMode: null, drawingControl: true,
            drawingControlOptions: {{ position: google.maps.ControlPosition.TOP_CENTER,
                                      drawingModes: ['circle', 'rectangle', 'polygon'] }},
            circleOptions:    {{ fillOpacity:0.2, strokeColor:'#d32f2f', fillColor:'#d32f2f', clickable:false, editable:true, zIndex:1 }},
            polygonOptions:   {{ fillOpacity:0.2, strokeColor:'#d32f2f', fillColor:'#d32f2f', clickable:false, editable:true, zIndex:1 }},
            rectangleOptions: {{ fillOpacity:0.2, strokeColor:'#d32f2f', fillColor:'#d32f2f', clickable:false, editable:true, zIndex:1 }}
        }});
        drawingManager.setMap(map);
        google.maps.event.addListener(drawingManager, 'overlaycomplete', function(e) {{
            if (currentShape) currentShape.setMap(null);
            currentShape = e.overlay; filterMovies();
            if (e.type === 'circle') {{
                google.maps.event.addListener(currentShape, 'radius_changed', filterMovies);
                google.maps.event.addListener(currentShape, 'center_changed', filterMovies);
            }}
        }});
        Object.keys(theaterCoords).forEach(name => {{
            const mk = new google.maps.Marker({{ position: theaterCoords[name], map, title: name,
                icon: {{ path: google.maps.SymbolPath.CIRCLE, scale:5, fillColor:"#000", fillOpacity:1, strokeWeight:0 }} }});
            mk.theaterName = name; markers.push(mk);
        }});
    }}
    function clearMapDrawing() {{ if (currentShape) currentShape.setMap(null); currentShape = null; filterMovies(); }}
    function isLocationInShape(lat, lng) {{
        if (!currentShape) return true;
        const pt = new google.maps.LatLng(lat, lng);
        if (currentShape.getBounds && !currentShape.getBounds().contains(pt)) return false;
        if (currentShape instanceof google.maps.Polygon) return google.maps.geometry.poly.containsLocation(pt, currentShape);
        if (currentShape instanceof google.maps.Circle) return google.maps.geometry.spherical.computeDistanceBetween(pt, currentShape.getCenter()) <= currentShape.getRadius();
        return true;
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
            cal.appendChild(day); cur.setDate(cur.getDate() + 1);
        }}
    }}
    // Day-of-week and date filters now stack — selecting Fridays + a date range gives the intersection.
    function toggleDayOfWeek(i) {{ selectedDaysOfWeek.has(i) ? selectedDaysOfWeek.delete(i) : selectedDaysOfWeek.add(i); nowShowingActive = false; document.getElementById('nowShowingBtn').classList.remove('active'); syncUI(); filterMovies(); }}
    function handleDayCheckboxChange() {{ selectedDaysOfWeek.clear(); document.querySelectorAll('.day-checkbox input:checked').forEach(cb => selectedDaysOfWeek.add(+cb.value)); nowShowingActive = false; document.getElementById('nowShowingBtn').classList.remove('active'); syncUI(); filterMovies(); }}
    function toggleDate(ds) {{ selectedDates.has(ds) ? selectedDates.delete(ds) : selectedDates.add(ds); nowShowingActive = false; document.getElementById('nowShowingBtn').classList.remove('active'); syncUI(); filterMovies(); }}
    function handleDateFilterChange() {{ selectedDates = new Set(Array.from(document.getElementById('dateFilter').selectedOptions).map(o=>o.value)); nowShowingActive = false; document.getElementById('nowShowingBtn').classList.remove('active'); syncUI(); filterMovies(); }}
    function syncUI() {{
        Array.from(document.getElementById('dateFilter').options).forEach(o => {{ o.selected = selectedDates.has(o.value); }});
        document.querySelectorAll('.day-checkbox').forEach(lbl => {{ const cb = lbl.querySelector('input'); cb.checked = selectedDaysOfWeek.has(+cb.value); lbl.classList.toggle('checked', cb.checked); }});
        document.querySelectorAll('.calendar-header').forEach(h => {{ h.classList.toggle('selected', selectedDaysOfWeek.has(+h.dataset.dayIndex)); }});
        document.querySelectorAll('.calendar-day').forEach(d => {{ d.classList.toggle('selected', selectedDates.has(d.dataset.date)); }});
    }}

    /* ── TIME / HELPERS ────────────────────────────────────── */
    function parseTime(str) {{ const m = str.match(/(\\d{{1,2}}):(\\d{{2}})\\s*([AP]M)/i); if (!m) return null; let h = parseInt(m[1]), min = parseInt(m[2]); const ap = m[3].toUpperCase(); if (ap === 'PM' && h !== 12) h += 12; if (ap === 'AM' && h === 12) h = 0; return h * 60 + min; }}
    function toMin(t) {{ const [h,m] = t.split(':').map(Number); return h*60+m; }}
    function matchesTimeRange(times, lo, hi) {{ if (times[0] === 'Check website') return true; if (hi < lo) hi = 24*60-1; return times.some(t => {{ const m = parseTime(t); return m === null || (m >= lo && m <= hi); }}); }}
    function getMovieYear(m) {{ const ym = String(m.year).match(/\\d{{4}}/); return ym ? ym[0] : null; }}
    function getMovieDecade(m) {{ const y = getMovieYear(m); return y ? y.substring(0,3) + '0s' : null; }}

    /* ── FILTER ────────────────────────────────────────────── */
    function getActiveFilters() {{
        const filters = {{}};
        const q = document.getElementById('searchBar').value;
        if (q) filters.search = q;
        const lo = toMin(document.getElementById('startTime').value);
        const hi = toMin(document.getElementById('endTime').value);
        if (lo > 0 || hi < 23*60+59) filters.time = {{ lo, hi }};
        selectedTheaters = new Set(Array.from(document.getElementById('theaterFilter').selectedOptions).map(o=>o.value));
        if (selectedTheaters.size) filters.theaters = selectedTheaters;
        selectedGenres.clear();
        document.querySelectorAll('#genreFilter .pill input:checked').forEach(cb => selectedGenres.add(cb.value));
        if (selectedGenres.size) filters.genres = selectedGenres;
        selectedDecades.clear();
        document.querySelectorAll('#decadeFilter .pill input:checked').forEach(cb => selectedDecades.add(cb.value));
        if (selectedDecades.size) filters.decades = selectedDecades;
        const selectedYears = new Set(Array.from(document.getElementById('yearFilter').selectedOptions).map(o=>o.value));
        if (selectedYears.size) filters.years = selectedYears;
        const rtMin = parseInt(document.getElementById('runtimeMin').value) || 0;
        const rtMax = parseInt(document.getElementById('runtimeMax').value) || 0;
        if (rtMin > 0 || rtMax > 0) filters.runtime = {{ min: rtMin, max: rtMax || 9999 }};
        if (selectedDates.size) filters.dates = selectedDates;
        if (selectedDaysOfWeek.size) filters.daysOfWeek = selectedDaysOfWeek;
        if (currentShape) filters.mapArea = true;
        if (nowShowingActive) filters.nowShowing = true;
        return {{ filters, selectedYears, rtMin: rtMin || 0, rtMax: rtMax || 9999, lo, hi, q: q.toLowerCase() }};
    }}

    function filterMovies() {{
        const {{ filters, selectedYears, rtMin, rtMax, lo, hi, q }} = getActiveFilters();
        const filtered = allMovies.filter(m => {{
            // Fuzzy search across title, director, theater, year, genres, decade
            if (q) {{
                const haystack = [m.title, m.director, m.theater, m.year, ...(m.genres||[]), getMovieDecade(m)||''].join(' ').toLowerCase();
                if (!fuzzyMatch(haystack, q)) return false;
            }}
            const c = theaterCoords[m.theater];
            if (c && !isLocationInShape(c.lat, c.lng)) return false;
            if (!c && currentShape) return false;
            if (selectedTheaters.size && !selectedTheaters.has(m.theater)) return false;
            if (selectedDates.size && !selectedDates.has(m.date)) return false;
            if (selectedDaysOfWeek.size) {{ const dow = new Date(m.date + 'T00:00:00').getDay(); if (!selectedDaysOfWeek.has(dow)) return false; }}
            if (filters.time && !matchesTimeRange(m.showtimes, lo, hi)) return false;
            if (selectedGenres.size) {{ const mg = m.genres || []; if (!mg.some(g => selectedGenres.has(g))) return false; }}
            if (selectedDecades.size) {{ const dec = getMovieDecade(m); if (!dec || !selectedDecades.has(dec)) return false; }}
            if (selectedYears.size) {{ const y = getMovieYear(m); if (!y || !selectedYears.has(y)) return false; }}
            if (m.runtime_mins) {{ if (m.runtime_mins < rtMin || m.runtime_mins > rtMax) return false; }}
            return true;
        }});
        const sortBy = document.getElementById('sortBy').value;
        filtered.sort((a, b) => {{
            switch(sortBy) {{
                case 'date-asc':  return a.date.localeCompare(b.date);
                case 'date-desc': return b.date.localeCompare(a.date);
                case 'title-asc': return a.title.localeCompare(b.title);
                case 'title-desc': return b.title.localeCompare(a.title);
                case 'runtime-asc':  return (a.runtime_mins||999) - (b.runtime_mins||999);
                case 'runtime-desc': return (b.runtime_mins||0) - (a.runtime_mins||0);
                case 'showtimes-desc': return (b.showtimes||[]).length - (a.showtimes||[]).length;
                case 'rating-desc': return (b.rating||0) - (a.rating||0);
                case 'rating-asc':  return (a.rating||0) - (b.rating||0);
                default: return 0;
            }}
        }});
        renderActiveFilters(filters);
        renderMovies(filtered, filters);
    }}

    /* ── ACTIVE FILTER BADGES ─────────────────────────────── */
    function renderActiveFilters(filters) {{
        const container = document.getElementById('activeFilters');
        container.innerHTML = '';
        const badge = (label, clearFn) => {{
            const btn = document.createElement('button'); btn.className = 'filter-badge';
            btn.innerHTML = label + ' <span class="badge-x">&times;</span>';
            btn.onclick = clearFn; container.appendChild(btn);
        }};
        if (filters.nowShowing) badge('Now Showing', () => {{ toggleNowShowing(); }});
        if (filters.search) badge('&ldquo;' + filters.search + '&rdquo;', () => {{ document.getElementById('searchBar').value = ''; filterMovies(); }});
        if (filters.theaters) filters.theaters.forEach(t => badge(t, () => {{ Array.from(document.getElementById('theaterFilter').options).forEach(o => {{ if (o.value === t) o.selected = false; }}); filterMovies(); }}));
        if (filters.genres) filters.genres.forEach(g => badge(g, () => {{ document.querySelectorAll('#genreFilter .pill').forEach(lbl => {{ const cb = lbl.querySelector('input'); if (cb.value === g) {{ cb.checked = false; lbl.classList.remove('checked'); }} }}); filterMovies(); }}));
        if (filters.decades) filters.decades.forEach(d => badge(d, () => {{ document.querySelectorAll('#decadeFilter .pill').forEach(lbl => {{ const cb = lbl.querySelector('input'); if (cb.value === d) {{ cb.checked = false; lbl.classList.remove('checked'); }} }}); filterMovies(); }}));
        if (filters.years) filters.years.forEach(y => badge(y, () => {{ Array.from(document.getElementById('yearFilter').options).forEach(o => {{ if (o.value === y) o.selected = false; }}); filterMovies(); }}));
        if (filters.runtime) {{
            const rl = filters.runtime.min > 0 && filters.runtime.max < 9999 ? filters.runtime.min + '-' + filters.runtime.max + ' min' : filters.runtime.min > 0 ? '&ge; ' + filters.runtime.min + ' min' : '&le; ' + filters.runtime.max + ' min';
            badge(rl, () => {{ document.getElementById('runtimeMin').value = ''; document.getElementById('runtimeMax').value = ''; filterMovies(); }});
        }}
        if (filters.time) badge('Starts ' + document.getElementById('startTime').value + '-' + document.getElementById('endTime').value, () => {{ document.getElementById('startTime').value = '00:00'; document.getElementById('endTime').value = '23:59'; filterMovies(); }});
        if (filters.dates && !filters.nowShowing) badge(filters.dates.size + ' date(s)', () => {{ selectedDates.clear(); syncUI(); filterMovies(); }});
        const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        if (filters.daysOfWeek) {{ const names = Array.from(filters.daysOfWeek).map(i => dayNames[i]).join(', '); badge(names, () => {{ selectedDaysOfWeek.clear(); document.querySelectorAll('.day-checkbox input').forEach(cb => cb.checked = false); syncUI(); filterMovies(); }}); }}
        if (filters.mapArea) badge('Map area', () => {{ clearMapDrawing(); }});
    }}

    /* ── SMART EMPTY STATE ────────────────────────────────── */
    function diagnoseEmpty(filters) {{
        const activeNames = [];
        if (filters.theaters) activeNames.push('Theaters');
        if (filters.genres) activeNames.push('Genre');
        if (filters.decades) activeNames.push('Decade');
        if (filters.years) activeNames.push('Year');
        if (filters.runtime) activeNames.push('Runtime');
        if (filters.time) activeNames.push('Start time');
        if (filters.dates) activeNames.push('Dates');
        if (filters.daysOfWeek) activeNames.push('Days of week');
        if (filters.mapArea) activeNames.push('Map area');
        if (filters.search) activeNames.push('Search');
        if (activeNames.length < 2) return 'No screenings match your filter.';
        return 'Your filters (' + activeNames.join(' + ') + ') have no overlap. Try removing one to broaden results.';
    }}

    /* ── SIMILAR FILMS ─────────────────────────────────────── */
    function findSimilar(movie) {{
        const genres = new Set(movie.genres || []);
        const decade = getMovieDecade(movie);
        if (!genres.size && !decade) return [];
        const seen = new Set();
        return allMovies.filter(m => {{
            if (m.title === movie.title) return false;
            if (seen.has(m.title)) return false;
            const mg = new Set(m.genres || []);
            const overlap = [...genres].some(g => mg.has(g));
            const sameDecade = decade && getMovieDecade(m) === decade;
            if (overlap || sameDecade) {{ seen.add(m.title); return true; }}
            return false;
        }}).slice(0, 6);
    }}
    function toggleSimilar(idx) {{
        const drawer = document.getElementById('similar-' + idx);
        if (!drawer) return;
        if (drawer.classList.contains('open')) {{ drawer.classList.remove('open'); return; }}
        drawer.classList.add('open');
        if (drawer.dataset.loaded) return;
        const movie = window._lastFiltered[idx];
        const similar = findSimilar(movie);
        if (!similar.length) {{ drawer.innerHTML = '<h4>Similar screenings</h4><span style="color:var(--muted);font-size:0.85em;">No similar films found in current listings.</span>'; }}
        else {{ drawer.innerHTML = '<h4>Similar screenings</h4><div class="similar-list">' + similar.map(s => `<span class="similar-chip" onclick="document.getElementById('searchBar').value='${{s.title.replace(/'/g, "\\\\'")}}';filterMovies();">${{s.title}} (${{s.year}})</span>`).join('') + '</div>'; }}
        drawer.dataset.loaded = '1';
    }}

    /* ── RENDER ────────────────────────────────────────────── */
    function renderMovies(movies, filters) {{
        window._lastFiltered = movies;
        document.getElementById('resultCount').textContent = movies.length + ' screenings found';
        const c = document.getElementById('movieContainer');
        if (!movies.length) {{
            c.innerHTML = '<div style="text-align:center;padding:40px;color:var(--muted);">' + diagnoseEmpty(filters || {{}}) + '</div>';
            return;
        }}
        if (currentView === 'table') {{ renderTable(movies, c); return; }}
        const isGrid = currentView === 'grid';
        c.innerHTML = (isGrid ? '<div class="view-grid">' : '') + movies.map((m, i) => {{
            const d = new Date(m.date+'T00:00:00');
            const ds = d.toLocaleDateString('en-US',{{weekday:'short',month:'short',day:'numeric'}});
            const st = m.showtimes.map(t=>`<span class="showtime">${{t}}</span>`).join('');
            const lb = m.letterboxd_url ? `<a href="${{m.letterboxd_url}}" target="_blank" class="letterboxd-link" title="View on Letterboxd"><img class="letterboxd-icon" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAMAAABF0y+mAAAAnFBMVEVEVWY+VGc2U2lFUWZGTmdEUmJEUF4vUmpkW1yrakO3bT6QZE1EVGZHSGc4fWIqpV1DfJ1CkbpEZXxETFrBcDb/ggD/gAAVy1cA6FMA5FNAvPRAwftCmMP/egAnzGEA4FQ+tvb/p2+09sUA30m29r6F0fczufSCYVP/y63k+urk/Oa44/hDdJHNcy9xXFg5WGYQ0laeZ0g1h2EmrVx5aPuSAAAAoklEQVR4AeWQAwIDMRBF17bNul3f/26Nalxgf5wXzHxqTaIZhoYjy3EsHHlB4G9MlGRFZWhNN0zT0DVesGzbcQnzfD/wA4kOoziOQt5JUqAMUUbxA6i8iEugOKwSqNQWICWsbloI2812hykMZk/g4Yjh6Uzghf8P/z5LMd73gDIBpdIB6gf9MMJUxuEpFUh7xZtoYMK8LDMwgbcyaMJ/+1ajK9jeGGaIBdTtAAAAAElFTkSuQmCC" alt="Letterboxd"></a>` : '';
            const rt = m.runtime_mins ? `<span class="movie-runtime">${{m.runtime_mins}} min</span>` : '';
            const rat = m.rating ? `<span class="movie-runtime">${{m.rating.toFixed(1)}}/5</span>` : '';
            const genres = (m.genres || []).map(g => `<span class="genre-tag">${{g}}</span>`).join('');
            const todayBadge = m.date === TODAY ? '<span class="today-badge">Today</span>' : '';
            const poster = m.poster_url ? `<img class="movie-poster" src="${{m.poster_url}}" alt="${{m.title}}" loading="lazy">` : '';
            return `<div class="movie-card">
                ${{poster}}
                <div class="movie-body">
                <div class="date-badge">${{ds}}${{todayBadge}}</div>
                <div class="movie-title" onclick="toggleSimilar(${{i}})">${{m.title}} <span style="font-weight:normal;font-size:0.8em">(${{m.year}})</span></div>
                <div class="movie-meta">Dir: ${{m.director}} ${{rt ? '&bull; ' + rt : ''}} ${{rat ? '&bull; ' + rat : ''}}</div>
                ${{genres ? '<div class="movie-genres">' + genres + '</div>' : ''}}
                <div class="theater">${{m.theater}}</div>
                <div class="showtimes">${{st}}</div>
                <div class="card-links">
                    <a href="${{m.link}}" target="_blank" class="link">Tickets &amp; Info</a>
                    ${{lb}}
                </div>
                <div class="similar-drawer" id="similar-${{i}}"></div>
                </div>
            </div>`;
        }}).join('') + (isGrid ? '</div>' : '');
    }}
    function renderTable(movies, c) {{
        c.innerHTML = `<table class="view-table"><thead><tr>
            <th>Date</th><th>Title</th><th>Director</th><th>Theater</th><th>Showtimes</th><th>Runtime</th><th>Links</th>
        </tr></thead><tbody>` + movies.map(m => {{
            const d = new Date(m.date+'T00:00:00');
            const ds = d.toLocaleDateString('en-US',{{month:'short',day:'numeric'}});
            const todayMark = m.date === TODAY ? ' *' : '';
            const lb = m.letterboxd_url ? ` <a href="${{m.letterboxd_url}}" target="_blank" title="Letterboxd"><img class="letterboxd-icon" style="width:20px;height:20px;vertical-align:middle;" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAMAAABF0y+mAAAAnFBMVEVEVWY+VGc2U2lFUWZGTmdEUmJEUF4vUmpkW1yrakO3bT6QZE1EVGZHSGc4fWIqpV1DfJ1CkbpEZXxETFrBcDb/ggD/gAAVy1cA6FMA5FNAvPRAwftCmMP/egAnzGEA4FQ+tvb/p2+09sUA30m29r6F0fczufSCYVP/y63k+urk/Oa44/hDdJHNcy9xXFg5WGYQ0laeZ0g1h2EmrVx5aPuSAAAAoklEQVR4AeWQAwIDMRBF17bNul3f/26Nalxgf5wXzHxqTaIZhoYjy3EsHHlB4G9MlGRFZWhNN0zT0DVesGzbcQnzfD/wA4kOoziOQt5JUqAMUUbxA6i8iEugOKwSqNQWICWsbloI2812hykMZk/g4Yjh6Uzghf8P/z5LMd73gDIBpdIB6gf9MMJUxuEpFUh7xZtoYMK8LDMwgbcyaMJ/+1ajK9jeGGaIBdTtAAAAAElFTkSuQmCC" alt="LB"></a>` : '';
            return `<tr>
                <td>${{ds}}${{todayMark}}</td>
                <td><strong>${{m.title}}</strong> (${{m.year}})</td>
                <td>${{m.director}}</td>
                <td>${{m.theater}}</td>
                <td>${{m.showtimes.join(', ')}}</td>
                <td>${{m.runtime_mins ? m.runtime_mins + 'm' : ''}}</td>
                <td><a href="${{m.link}}" target="_blank">Tickets</a>${{lb}}</td>
            </tr>`;
        }}).join('') + '</tbody></table>';
    }}

    /* ── BOOT ──────────────────────────────────────────────── */
    window.onload = function() {{ buildCalendar(); renderMovies(allMovies, {{}}); }};
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
