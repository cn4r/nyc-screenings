#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jan  4 18:09:02 2026

@author: charitnarayanan

v1.1 — Added full-page scrolling, per-day retries, and better error handling
       to fix missing days in the calendar.
"""

import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import time
import re
import json
import requests
from bs4 import BeautifulSoup, Comment
from urllib.parse import quote

# --- SETUP ---
BASE_FOLDER = os.getcwd()
DATA_FOLDER = os.path.join(BASE_FOLDER, "data")

# Create folders if they don't exist
for folder in [BASE_FOLDER, DATA_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"✓ Created folder: {folder}")

MAX_RETRIES = 3
RETRY_DELAY = 5

def extract_showtimes(element):
    """Extract all showtimes from a listing element"""
    showtimes = []
    try:
        # Look for showtime containers
        showtime_divs = element.find_elements(By.CSS_SELECTOR, '.showtimes, [class*="showtime"], div:has(span)')
        
        for div in showtime_divs:
            # Find all span elements that might contain times
            time_spans = div.find_elements(By.TAG_NAME, 'span')
            for span in time_spans:
                text = span.text.strip()
                # Use findall to capture ALL times in the text
                times = re.findall(r'\d{1,2}:\d{2}\s*[AP]M', text, re.IGNORECASE)
                for t in times:
                    clean_time = t.rstrip(',').strip()
                    if clean_time and clean_time not in showtimes:  # Avoid duplicates
                        showtimes.append(clean_time)
        
        # If no showtimes found in structured elements, search parent text
        if not showtimes:
            parent_text = element.text
            times = re.findall(r'\d{1,2}:\d{2}\s*[AP]M', parent_text, re.IGNORECASE)
            for t in times:
                clean_time = t.rstrip(',').strip()
                if clean_time and clean_time not in showtimes:  # Avoid duplicates
                    showtimes.append(clean_time)
    
    except Exception as e:
        pass
    
    return showtimes if showtimes else ['Check website']

def scroll_full_page(driver):
    """Scroll the entire page incrementally to trigger lazy-loaded content."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(0.8)
        new_height = driver.execute_script("return document.body.scrollHeight")
        current_pos = driver.execute_script("return window.pageYOffset + window.innerHeight")
        if current_pos >= new_height or new_height == last_height:
            break
        last_height = new_height
    # Scroll back to top
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)

def make_driver():
    """Create a headless Chrome driver."""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument("--window-size=1920,1080")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver

def scrape_single_day(driver, date_str):
    """Scrape one day of listings. Returns list of screening dicts."""
    url = f"https://www.screenslate.com/listings/{date_str}"
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "listings"))
        )
    except Exception:
        print(f"  ⚠ No #listings container found")
        return []

    # Full-page scroll to trigger lazy loading
    scroll_full_page(driver)
    time.sleep(1.5)

    daily_data = []
    current_theater = "Unknown Venue"

    listings_container = driver.find_element(By.ID, "listings")
    elements = listings_container.find_elements(By.CSS_SELECTOR, "*")

    for element in elements:
        if element.tag_name == 'h3':
            current_theater = element.text.strip()

        cls = element.get_attribute('class') or ''
        if 'listing' in cls:
            try:
                title_el = element.find_element(By.CSS_SELECTOR, 'a span')
                title = title_el.text.strip()
                link = element.find_element(By.TAG_NAME, 'a').get_attribute('href')

                spans = element.find_elements(By.TAG_NAME, 'span')
                director = spans[1].text.replace(' ,', '').strip() if len(spans) > 1 else "N/A"
                year = spans[2].text.replace(',', '').strip() if len(spans) > 2 else "N/A"

                showtimes = extract_showtimes(element)

                daily_data.append({
                    'date': date_str,
                    'theater': current_theater,
                    'title': title,
                    'director': director,
                    'year': year,
                    'link': link,
                    'showtimes': showtimes
                })
            except Exception:
                continue

    return daily_data

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
})


def resolve_screenslate_links(data):
    """For screenslate.com links, follow them and extract the actual theater URL."""
    # Collect unique screenslate URLs
    ss_urls = set()
    for s in data:
        link = s.get('link', '')
        if 'screenslate.com' in link and '/screenings/' not in link:
            ss_urls.add(link)

    if not ss_urls:
        return data

    print(f"\nResolving {len(ss_urls)} Screen Slate links to actual ticket URLs...")
    url_map = {}
    for i, url in enumerate(ss_urls):
        try:
            resp = SESSION.get(url, timeout=10)
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Look for external links — Screen Slate pages typically have a
            # "Website" or "Series Site" link to the actual theater
            external_link = None
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = (a.get_text() or '').strip().lower()
                if text in ('website', 'series site', 'venue site', 'buy tickets',
                            'tickets', 'more info', 'official site'):
                    if 'screenslate.com' not in href:
                        external_link = href
                        break
            # Fallback: find any link that looks like a theater domain
            if not external_link:
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if (href.startswith('http') and 'screenslate.com' not in href
                            and 'instagram.com' not in href and 'twitter.com' not in href
                            and 'facebook.com' not in href and 'patreon.com' not in href
                            and 'twitch.tv' not in href and 'shop.' not in href):
                        external_link = href
                        break
            if external_link:
                url_map[url] = external_link
            if (i + 1) % 20 == 0:
                print(f"  Resolved {i + 1}/{len(ss_urls)}...")
            time.sleep(0.5)
        except Exception as e:
            pass

    resolved = 0
    for s in data:
        link = s.get('link', '')
        if link in url_map:
            s['link'] = url_map[link]
            resolved += 1

    print(f"  Resolved {resolved}/{len(data)} screenings to actual ticket URLs")
    return data


def _make_letterboxd_slug(title):
    """Convert a movie title to a Letterboxd-style URL slug."""
    import unicodedata
    slug = title.lower()
    # Remove content in parentheses (like "35mm" notes)
    slug = re.sub(r'\s*\([^)]*\)\s*', ' ', slug)
    # Remove apostrophes/quotes without adding spaces (L'Âge -> LÂge)
    slug = slug.replace("'", "").replace("'", "").replace("`", "")
    # Transliterate accented characters (Â->a, é->e, ñ->n, etc.)
    slug = unicodedata.normalize('NFKD', slug).encode('ascii', 'ignore').decode('ascii')
    # Replace & with and
    slug = slug.replace('&', 'and').replace('+', 'and')
    # Keep only alphanumeric, spaces, hyphens
    slug = re.sub(r"[^a-z0-9\s-]", '', slug)
    # Collapse whitespace and convert to hyphens
    slug = re.sub(r'\s+', '-', slug.strip())
    # Remove trailing/leading/multiple hyphens
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug


def _parse_letterboxd_page(url):
    """Fetch a Letterboxd page and extract all metadata. Returns dict or None."""
    try:
        resp = SESSION.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        text = resp.text

        info = {'url': url, 'page_year': None, 'page_director_slug': None,
                'genres': [], 'runtime_mins': None, 'rating': None, 'rating_count': None,
                'poster_url': None}

        # JSON-LD
        ld_match = re.search(
            r'application/ld\+json[^>]*>(.*?)</script>', text, re.DOTALL
        )
        if ld_match:
            try:
                raw = ld_match.group(1).strip()
                for prefix in ['/* <![CDATA[ */', '/* ]]> */']:
                    raw = raw.replace(prefix, '')
                ld = json.loads(raw.strip())
                info['ld_name'] = ld.get('name', '')
                info['poster_url'] = ld.get('image')
                directors = ld.get('director', [])
                if isinstance(directors, list) and directors:
                    same_as = directors[0].get('sameAs', '')
                    dm = re.search(r'/director/([^/"]+)/', same_as)
                    if dm:
                        info['page_director_slug'] = dm.group(1)
                released = ld.get('releasedEvent')
                if isinstance(released, list) and released:
                    start = released[0].get('startDate', '')
                    ym = re.search(r'(\d{4})', start)
                    if ym:
                        info['page_year'] = ym.group(1)
                agg = ld.get('aggregateRating', {})
                if agg:
                    try:
                        info['rating'] = float(agg.get('ratingValue', 0)) or None
                        info['rating_count'] = int(agg.get('ratingCount', 0)) or None
                    except (ValueError, TypeError):
                        pass
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback to HTML link patterns
        if not info['page_year']:
            ym = re.search(r'/films/year/(\d{4})/', text)
            info['page_year'] = ym.group(1) if ym else None
        if not info['page_director_slug']:
            dm = re.search(r'/director/([^/"]+)/', text)
            info['page_director_slug'] = dm.group(1) if dm else None

        # Genre
        info['genres'] = sorted(set(re.findall(r'/films/genre/([^/"]+)/', text)))

        # Runtime
        rt = re.search(r'(\d{2,3})&nbsp;mins?', text)
        if rt:
            info['runtime_mins'] = int(rt.group(1))

        return info
    except Exception:
        return None


def _verify_letterboxd(info, expected_year, expected_director):
    """Check if parsed Letterboxd info matches expected year/director."""
    if not info:
        return False

    page_year = info['page_year']
    page_director_slug = info['page_director_slug']

    year_ok = False
    if page_year and expected_year and expected_year != 'N/A':
        clean_year = re.search(r'\d{4}', str(expected_year))
        if clean_year:
            year_ok = page_year == clean_year.group(0)
    elif not expected_year or expected_year == 'N/A':
        year_ok = True

    dir_ok = False
    if page_director_slug and expected_director and expected_director != 'N/A':
        expected_slug = re.sub(r"[^a-z0-9\s-]", '', expected_director.lower())
        expected_slug = re.sub(r'\s+', '-', expected_slug.strip())
        dir_ok = (expected_slug == page_director_slug
                  or expected_slug in page_director_slug
                  or page_director_slug in expected_slug
                  or expected_slug.split('-')[-1] in page_director_slug)
    elif not expected_director or expected_director == 'N/A':
        dir_ok = True

    # If page has no year/director, accept if the page exists and has a name
    if not page_year and not page_director_slug:
        return bool(info.get('ld_name'))

    return year_ok or dir_ok


def enrich_letterboxd(data):
    """Add Letterboxd URLs, genres, and runtime to screenings."""
    title_map = {}
    for s in data:
        title = s['title']
        if title not in title_map:
            title_map[title] = s

    print(f"\nLooking up {len(title_map)} unique titles on Letterboxd...")
    # title -> {letterboxd_url, genres, runtime_mins} or None
    info_cache = {}
    checked = 0

    for title, sample in title_map.items():
        slug = _make_letterboxd_slug(title)
        if not slug:
            info_cache[title] = None
            continue

        year = sample.get('year', 'N/A')
        director = sample.get('director', 'N/A')

        matched_info = None
        # Try base slug first
        url = f"https://letterboxd.com/film/{slug}/"
        info = _parse_letterboxd_page(url)
        if _verify_letterboxd(info, year, director):
            matched_info = info
        else:
            # Try slug-{year}
            clean_year = re.search(r'\d{4}', str(year))
            if clean_year:
                url2 = f"https://letterboxd.com/film/{slug}-{clean_year.group(0)}/"
                info2 = _parse_letterboxd_page(url2)
                if _verify_letterboxd(info2, year, director):
                    matched_info = info2

        info_cache[title] = matched_info
        checked += 1
        if checked % 25 == 0:
            print(f"  Checked {checked}/{len(title_map)} titles...")
        time.sleep(0.3)

    found = sum(1 for v in info_cache.values() if v)
    print(f"  Found Letterboxd pages for {found}/{len(title_map)} unique titles")

    for s in data:
        info = info_cache.get(s['title'])
        if info:
            s['letterboxd_url'] = info['url']
            s['genres'] = info.get('genres', [])
            s['runtime_mins'] = info.get('runtime_mins')
            s['rating'] = info.get('rating')
            s['rating_count'] = info.get('rating_count')
            s['poster_url'] = info.get('poster_url')
        else:
            s['letterboxd_url'] = None
            s['genres'] = []
            s['runtime_mins'] = None
            s['rating'] = None
            s['rating_count'] = None
            s['poster_url'] = None

    return data


def scrape_metrograph():
    """Scrape Metrograph listings from metrograph.com/calendar/ (no Selenium needed).

    Structure: div#calendar-list-day-YYYY-MM-DD contains div.film-thumbnail items.
    Each film div has h4 (title), metadata text (Director / Year / Runtime / Format),
    and <a> links to film pages and ticket pages with showtime text.
    """
    print("\nScraping Metrograph...")
    all_data = []
    try:
        resp = SESSION.get("https://metrograph.com/calendar/", timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')

        day_divs = soup.find_all('div', class_='calendar-list-day')
        for day_div in day_divs:
            # Date from id: "calendar-list-day-2026-06-06"
            div_id = day_div.get('id', '')
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', div_id)
            if not date_match:
                continue
            date_str = date_match.group(1)

            films = day_div.find_all('div', class_=re.compile('film-thumbnail'))
            for film_div in films:
                h4 = film_div.find('h4')
                title = h4.get_text(strip=True) if h4 else None
                if not title:
                    continue

                # Film page link
                film_link = None
                for a in film_div.find_all('a', href=True):
                    if '/film/' in a['href']:
                        href = a['href']
                        film_link = href if href.startswith('http') else f"https://metrograph.com{href}"
                        break

                # Metadata: "Director / Year / Runtime / Format" in the div text
                full_text = film_div.get_text(' ', strip=True)
                # Extract director/year/runtime from pattern after title
                meta_match = re.search(
                    r'(?:' + re.escape(title) + r')\s*(.+?)(?:\d{1,2}:\d{2}[ap]m|$)',
                    full_text, re.IGNORECASE
                )
                director = 'N/A'
                year = 'N/A'
                runtime = None
                if meta_match:
                    meta = meta_match.group(1)
                    parts = [p.strip() for p in meta.split('/')]
                    if parts:
                        director = parts[0] if parts[0] else 'N/A'
                    if len(parts) > 1:
                        ym = re.search(r'(19\d{2}|20[0-2]\d)', parts[1])
                        if ym:
                            year = ym.group(1)
                    if len(parts) > 2:
                        rm = re.search(r'(\d{2,3})\s*min', parts[2])
                        if rm:
                            runtime = int(rm.group(1))

                # Showtimes from links
                showtimes = []
                for a in film_div.find_all('a', href=True):
                    t = a.get_text(strip=True)
                    tm = re.match(r'(\d{1,2}:\d{2}\s*[ap]m)', t, re.IGNORECASE)
                    if tm:
                        showtimes.append(tm.group(1))
                if not showtimes:
                    # Try from full text
                    showtimes = re.findall(r'\d{1,2}:\d{2}\s*[ap]m', full_text, re.IGNORECASE)
                if not showtimes:
                    showtimes = ['Check website']

                # Ticket link (prefer direct ticket URL over film page)
                ticket_link = film_link
                for a in film_div.find_all('a', href=True):
                    if 'visSelectTickets' in a['href'] or 'Ticketing' in a['href']:
                        ticket_link = a['href']
                        break

                all_data.append({
                    'date': date_str,
                    'theater': 'METROGRAPH',
                    'title': title,
                    'director': director,
                    'year': year,
                    'link': ticket_link or film_link or 'https://metrograph.com/calendar/',
                    'showtimes': showtimes,
                })

    except Exception as e:
        print(f"  Metrograph scrape error: {e}")

    print(f"  Got {len(all_data)} Metrograph screenings")
    return all_data


def scrape_roxy_cinema():
    """Scrape Roxy Cinema New York from roxycinemanewyork.com/now-showing/ (no Selenium needed).

    Structure: div.grid__listings--group per day, h3.events__date for date,
    div.detailed-screening__card per screening with time, title, meta, ticket link.
    """
    print("\nScraping Roxy Cinema New York...")
    all_data = []
    try:
        resp = SESSION.get("https://www.roxycinemanewyork.com/now-showing/", timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        now = datetime.now()
        groups = soup.find_all('div', class_='grid__listings--group')

        for group in groups:
            date_el = group.find('h3', class_='events__date')
            if not date_el:
                continue
            date_str_raw = date_el.get_text(strip=True)  # e.g. 'Saturday, June 06'

            # Assign year: pick the earliest year where the date is today or future
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            date_obj = None
            for yr in [now.year, now.year + 1]:
                try:
                    candidate = datetime.strptime(f'{date_str_raw} {yr}', '%A, %B %d %Y')
                    if candidate >= today:
                        date_obj = candidate
                        break  # take earliest valid year
                except ValueError:
                    continue
            if not date_obj:
                continue
            date_str = date_obj.strftime('%Y-%m-%d')

            cards = group.find_all('div', class_='detailed-screening__card')
            for card in cards:
                # Showtime
                actions = card.find('div', class_='detailed-screening__actions')
                showtime_text = actions.get_text(strip=True) if actions else ''
                st_match = re.search(r'(\d{1,2}:\d{2}[AP]M)', showtime_text, re.IGNORECASE)
                showtime = st_match.group(1) if st_match else 'Check website'

                # Ticket link (prefer Veezi)
                ticket_link = 'https://www.roxycinemanewyork.com/now-showing/'
                for a in card.find_all('a', href=True):
                    if 'veezi' in a['href'] or 'ticketing' in a['href'].lower():
                        ticket_link = a['href']
                        break
                else:
                    cta = card.find('a', class_='detailed-screening__cta')
                    if cta:
                        ticket_link = cta['href']

                # Title — strip series suffix like '| I Paused My Game to be Here'
                title_el = card.find('h3', class_='detailed-screening__title')
                if not title_el:
                    continue
                title = re.sub(r'\s*\|.*$', '', title_el.get_text(strip=True)).strip()
                if not title:
                    continue

                # Meta: 'Drama, History, Thriller | 2025 | 136MIN'
                info_el = card.find('p', class_='detailed-screening__info')
                info = info_el.get_text(strip=True) if info_el else ''
                year = 'N/A'
                for part in info.split('|'):
                    ym = re.search(r'(19\d{2}|20[0-2]\d)', part)
                    if ym:
                        year = ym.group(1)
                        break

                # Merge showtimes for same title+date
                existing = next((d for d in all_data
                                 if d['date'] == date_str and d['title'] == title), None)
                if existing:
                    if showtime not in existing['showtimes']:
                        existing['showtimes'].append(showtime)
                else:
                    all_data.append({
                        'date': date_str,
                        'theater': 'ROXY CINEMA NEW YORK',
                        'title': title,
                        'director': 'N/A',
                        'year': year,
                        'link': ticket_link,
                        'showtimes': [showtime],
                    })

    except Exception as e:
        print(f"  Roxy Cinema scrape error: {e}")

    print(f"  Got {len(all_data)} Roxy Cinema screenings")
    return all_data


def scrape_paris_theater(driver=None):
    """Scrape Paris Theater from paristheaternyc.com.

    The site was rebuilt as a client-rendered Next.js app whose daily schedule
    widget loads from an API that never fires in a headless browser, so the
    regular day-by-day grid is not reachable. What *is* embedded in the page is
    the CMS payload of dated special screenings (previews, Q&As), which is what
    this returns. The `driver` argument is accepted but unused.
    """
    print("\nScraping Paris Theater...")
    all_data = []
    try:
        resp = SESSION.get("https://www.paristheaternyc.com", timeout=25)
        # The payload is JSON embedded in a JS string, so unescape it first
        payload = resp.text.replace('\\"', '"')
        payload = payload.encode('utf-8', 'ignore').decode('unicode_escape', 'ignore')

        events = re.findall(
            r'"EventName":"(.*?)".*?"EventDate":"(\d{4}-\d{2}-\d{2})"'
            r'.*?"TicketLink":"(.*?)".*?"EventTime":"(.*?)"',
            payload,
        )

        seen = set()
        for name, date_str, ticket, event_time in events:
            if (name, date_str, event_time) in seen:
                continue
            seen.add((name, date_str, event_time))

            # Names read "INK | Q&A with Danny Boyle" — the film is the first part
            title = name.split('|')[0].strip() or name.strip()
            if not title:
                continue

            tm = re.match(r'(\d{1,2})(?::(\d{2}))?\s*([apAP]\.?[mM])', event_time.strip())
            showtime = (
                f"{tm.group(1)}:{tm.group(2) or '00'} {tm.group(3).replace('.', '').upper()}"
                if tm else (event_time.strip() or 'Check website')
            )

            all_data.append({
                'date': date_str,
                'theater': 'PARIS THEATER',
                'title': title,
                'director': 'N/A',
                'year': 'N/A',
                'link': ticket.strip() or 'https://www.paristheaternyc.com',
                'showtimes': [showtime],
            })

    except Exception as e:
        print(f"  Paris Theater scrape error: {e}")

    print(f"  Got {len(all_data)} Paris Theater screenings")
    return all_data
# --- DIRECT THEATER SCRAPERS ---------------------------------------------
# Screen Slate (the old aggregator source) began returning
# "403 Automated access is not allowed" in Nov 2026, so each venue it used to
# cover is now scraped from its own public calendar instead.

def _infer_date(month_name, day, today=None):
    """Build YYYY-MM-DD from a month name + day, guessing the year.

    Calendars omit the year, so assume the nearest upcoming occurrence: if
    using the current year lands us more than 60 days in the past, it's next
    year's listing (a December page viewed in January, say).
    """
    today = today or datetime.now()
    for fmt in ('%b', '%B'):
        try:
            month = datetime.strptime(month_name[:3] if fmt == '%b' else month_name, fmt).month
            break
        except ValueError:
            continue
    else:
        return None

    for year in (today.year, today.year + 1):
        try:
            d = datetime(year, month, int(day))
        except ValueError:
            return None
        if (d - today).days > -60:
            return d.strftime('%Y-%m-%d')
    return None


def _dedupe_times(times):
    """Drop duplicates but keep original order (responsive markup repeats times)."""
    seen = set()
    out = []
    for t in times:
        key = t.upper().replace(' ', '')
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def scrape_ifc_center():
    """Scrape IFC Center from ifccenter.com (no Selenium needed).

    Structure: div.daily-schedule holds an h3 date ("Thu Nov 26") and an li per
    film with div.details > h3 > a (title) and ul.times > li > a (showtimes).
    Covers roughly the next week.
    """
    print("\nScraping IFC Center...")
    all_data = []
    try:
        resp = SESSION.get("https://www.ifccenter.com/", timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')

        for day_div in soup.find_all(class_='daily-schedule'):
            header = day_div.find('h3')
            if not header:
                continue
            # Header reads "Thu Nov 26" — month and day are the last two words
            parts = header.get_text(strip=True).split()
            if len(parts) < 3:
                continue
            date_str = _infer_date(parts[-2], parts[-1])
            if not date_str:
                continue

            for li in day_div.find_all('li', recursive=True):
                details = li.find('div', class_='details')
                if not details:
                    continue
                title_a = details.find('h3')
                title_a = title_a.find('a') if title_a else None
                if not title_a:
                    continue
                title = title_a.get_text(strip=True)
                if not title:
                    continue

                showtimes, ticket_link = [], None
                times_ul = details.find('ul', class_='times')
                if times_ul:
                    for ta in times_ul.find_all('a', href=True):
                        t = ta.get_text(strip=True)
                        if re.match(r'\d{1,2}:\d{2}\s*[apAP][mM]', t):
                            showtimes.append(t)
                            ticket_link = ticket_link or ta['href'].strip()

                all_data.append({
                    'date': date_str,
                    'theater': 'IFC CENTER',
                    'title': title,
                    'director': 'N/A',
                    'year': 'N/A',
                    'link': ticket_link or title_a.get('href') or 'https://www.ifccenter.com/',
                    'showtimes': _dedupe_times(showtimes) or ['Check website'],
                })

    except Exception as e:
        print(f"  IFC Center scrape error: {e}")

    print(f"  Got {len(all_data)} IFC Center screenings")
    return all_data


def scrape_film_forum():
    """Scrape Film Forum from filmforum.org (no Selenium needed).

    The homepage carries a week of schedule in div#tabs-N blocks; the day of
    month sits in an HTML comment at the top of each block. Times are printed
    bare ("2:30"), without am/pm, so they're normalized below.
    """
    print("\nScraping Film Forum...")
    all_data = []
    try:
        resp = SESSION.get("https://filmforum.org/", timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')
        today = datetime.now()

        for tab in soup.find_all('div', id=re.compile(r'^tabs-\d+$')):
            # Day-of-month lives in a comment like <!-- 26 -->
            day = None
            for node in tab.children:
                if isinstance(node, Comment):
                    cm = re.search(r'\d{1,2}', node)
                    if cm:
                        day = int(cm.group(0))
                        break
            if day is None:
                continue

            # Tabs run forward from today, so pick the month that fits
            date_str = None
            for delta_month in (0, 1):
                month = today.month + delta_month
                year = today.year + (month > 12)
                month = month - 12 if month > 12 else month
                try:
                    cand = datetime(year, month, day)
                except ValueError:
                    continue
                if (cand - today).days > -2:
                    date_str = cand.strftime('%Y-%m-%d')
                    break
            if not date_str:
                continue

            for p in tab.find_all('p'):
                strong = p.find('strong')
                title_a = strong.find('a', href=True) if strong else None
                if not title_a:
                    continue
                title = title_a.get_text(strip=True)
                if not title:
                    continue

                showtimes = []
                for span in p.find_all('span'):
                    raw = span.get_text(strip=True)
                    tm = re.match(r'(\d{1,2}):(\d{2})', raw)
                    if not tm:
                        continue
                    hour, minute = int(tm.group(1)), tm.group(2)
                    # Film Forum lists times bare, with no am/pm anywhere on the
                    # page. Always read them as PM.
                    showtimes.append(f"{hour}:{minute} PM")

                if not showtimes:
                    continue

                all_data.append({
                    'date': date_str,
                    'theater': 'FILM FORUM',
                    'title': title,
                    'director': 'N/A',
                    'year': 'N/A',
                    'link': title_a['href'],
                    'showtimes': _dedupe_times(showtimes),
                })

    except Exception as e:
        print(f"  Film Forum scrape error: {e}")

    print(f"  Got {len(all_data)} Film Forum screenings")
    return all_data


def scrape_anthology(months_ahead=2):
    """Scrape Anthology Film Archives from anthologyfilmarchives.org.

    Monthly calendar table: td.calendar_day holds the day number, each
    li.calendar_event holds a showtime followed by the title link.
    """
    print("\nScraping Anthology Film Archives...")
    all_data = []
    base = "https://anthologyfilmarchives.org"
    today = datetime.now()

    for offset in range(months_ahead + 1):
        month = today.month + offset
        year = today.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        try:
            resp = SESSION.get(
                f"{base}/film_screenings/calendar",
                params={'month': month, 'year': year},
                timeout=20,
            )
            soup = BeautifulSoup(resp.text, 'html.parser')

            for cell in soup.find_all('td', class_='calendar_day'):
                day_span = cell.find('span', class_='day')
                day = (day_span.get_text(strip=True) if day_span else cell.get('name') or '')
                if not day.isdigit():
                    continue
                try:
                    date_str = datetime(year, month, int(day)).strftime('%Y-%m-%d')
                except ValueError:
                    continue

                for li in cell.find_all('li', class_='calendar_event'):
                    a = li.find('a', href=True)
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    # Strip trailing notes like "(Director in person!)"
                    title = re.sub(r'\s*\([^)]*\)\s*$', '', title).strip()
                    if not title:
                        continue

                    # Showtime is the bare text before the title link
                    lead = li.get_text(' ', strip=True)
                    tm = re.match(r'(\d{1,2}:\d{2}\s*[apAP][mM])', lead)
                    showtimes = [tm.group(1)] if tm else ['Check website']

                    href = a['href']
                    all_data.append({
                        'date': date_str,
                        'theater': 'ANTHOLOGY FILM ARCHIVES',
                        'title': title,
                        'director': 'N/A',
                        'year': 'N/A',
                        'link': href if href.startswith('http') else base + href,
                        'showtimes': showtimes,
                    })
        except Exception as e:
            print(f"  Anthology {year}-{month:02d} error: {e}")

    print(f"  Got {len(all_data)} Anthology screenings")
    return all_data


def scrape_film_at_lincoln_center():
    """Scrape Film at Lincoln Center from filmlinc.org.

    Film pages carry a "Showtimes" block ("Thu, Nov 26" followed by times) plus
    a DIRECTOR / YEAR / RUNTIME metadata list, so this collects film slugs from
    the calendar pages and then reads each film page.
    """
    print("\nScraping Film at Lincoln Center...")
    all_data = []
    base = "https://www.filmlinc.org"
    slugs = set()

    try:
        for listing in ("/calendar/", "/now-playing/"):
            try:
                resp = SESSION.get(base + listing, timeout=25)
                for m in re.finditer(r'href="(/films/[^"#?]+/)"', resp.text):
                    slugs.add(m.group(1))
            except Exception as e:
                print(f"  FLC listing {listing} error: {e}")

        print(f"  Found {len(slugs)} film pages")

        for slug in sorted(slugs):
            try:
                resp = SESSION.get(base + slug, timeout=25)
                lines = BeautifulSoup(resp.text, 'html.parser').get_text('\n', strip=True).split('\n')

                director, year = 'N/A', 'N/A'
                for i, line in enumerate(lines):
                    if line.strip().upper() == 'DIRECTOR' and i + 1 < len(lines):
                        director = lines[i + 1].strip() or 'N/A'
                    elif line.strip().upper() == 'YEAR' and i + 1 < len(lines):
                        ym = re.search(r'(19\d{2}|20\d{2})', lines[i + 1])
                        if ym:
                            year = ym.group(1)

                title = 'N/A'
                for line in lines:
                    if line.strip() and line.strip().lower() not in ('skip to main content',):
                        title = line.strip()
                        break
                h1 = BeautifulSoup(resp.text, 'html.parser').find('h1')
                if h1 and h1.get_text(strip=True):
                    title = h1.get_text(strip=True)

                # Walk the Showtimes block: date headers then times beneath each
                try:
                    start = next(i for i, l in enumerate(lines) if l.strip().lower() == 'showtimes')
                except StopIteration:
                    continue

                by_date = {}
                current = None
                for line in lines[start + 1:]:
                    s = line.strip()
                    dm = re.match(r'^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,\s*(\w{3,})\.?\s+(\d{1,2})$', s)
                    if dm:
                        current = _infer_date(dm.group(1), dm.group(2))
                        by_date.setdefault(current, [])
                        continue
                    tm = re.match(r'^(\d{1,2}:\d{2}\s*[apAP][mM])$', s)
                    if tm and current:
                        by_date[current].append(tm.group(1))
                        continue
                    if s.upper() in ('OC', 'MORE SHOWTIMES', ''):
                        continue
                    if s.upper() in ('DIRECTOR', 'YEAR', 'COUNTRY', 'RUNTIME', 'LANGUAGE'):
                        break

                for date_str, times in by_date.items():
                    if not date_str or not times:
                        continue
                    all_data.append({
                        'date': date_str,
                        'theater': 'FILM AT LINCOLN CENTER',
                        'title': title,
                        'director': director,
                        'year': year,
                        'link': base + slug,
                        'showtimes': _dedupe_times(times),
                    })
            except Exception as e:
                print(f"  FLC {slug} error: {e}")

    except Exception as e:
        print(f"  Film at Lincoln Center scrape error: {e}")

    print(f"  Got {len(all_data)} Film at Lincoln Center screenings")
    return all_data


def scrape_bam(driver):
    """Scrape BAM from bam.org/calendar (needs Selenium — calendar is JS-rendered).

    Rendered structure: div.calendarblock carries the date in its id
    ("2026-11-01") and one button.eventblock per event, with the title in
    data-name and showtimes in ul.timeblock > li.cal_time.
    """
    print("\nScraping BAM...")
    all_data = []
    try:
        driver.get("https://www.bam.org/calendar?v=film")
        time.sleep(8)
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        for block in soup.find_all('div', class_='calendarblock'):
            date_str = block.get('id', '')
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date_str):
                continue

            for ev in block.find_all('button', class_='eventblock'):
                if (ev.get('data-genre') or '').strip().lower() != 'film':
                    continue
                title = (ev.get('data-name') or '').strip()
                if not title:
                    name_span = ev.find('span', class_='cal_event')
                    title = name_span.get_text(strip=True) if name_span else ''
                if not title:
                    continue

                showtimes = []
                for li in ev.find_all('li', class_='cal_time'):
                    t = li.get_text(strip=True)
                    if t:
                        # BAM prints "4pm" / "7:30pm"
                        tm = re.match(r'(\d{1,2})(?::(\d{2}))?\s*([apAP][mM])', t)
                        showtimes.append(
                            f"{tm.group(1)}:{tm.group(2) or '00'} {tm.group(3).upper()}" if tm else t
                        )

                link = (ev.get('data-buylink') or ev.get('data-morelink') or '').strip()
                if link.startswith('/'):
                    link = 'https://www.bam.org' + link

                all_data.append({
                    'date': date_str,
                    'theater': 'BAM',
                    'title': title,
                    'director': 'N/A',
                    'year': 'N/A',
                    'link': link or 'https://www.bam.org/film',
                    'showtimes': _dedupe_times(showtimes) or ['Check website'],
                })

    except Exception as e:
        print(f"  BAM scrape error: {e}")

    print(f"  Got {len(all_data)} BAM screenings")
    return all_data


def master_scrape(num_days=30):
    """Scrape the next num_days days of screenings with retries."""
    driver = make_driver()
    all_data = []
    failed_days = []
    
    start_date = datetime.now()
    print(f"📅 Scraping {num_days} days starting from {start_date.strftime('%Y-%m-%d')}\n")
    
    try:
        for i in range(num_days):
            date_obj = datetime.now() + timedelta(days=i)
            date_str = date_obj.strftime('%Y-%m-%d')
            
            day_data = []
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    print(f"Scraping: {date_str} (attempt {attempt})...", end=" ", flush=True)
                    day_data = scrape_single_day(driver, date_str)
                    
                    if day_data:
                        print(f"Found {len(day_data)}")
                        break
                    else:
                        print(f"0 results", end="")
                        if attempt < MAX_RETRIES:
                            delay = RETRY_DELAY * attempt
                            print(f", retrying in {delay}s...")
                            time.sleep(delay)
                            # Restart driver on last retry attempt
                            if attempt == MAX_RETRIES - 1:
                                try:
                                    driver.quit()
                                except Exception:
                                    pass
                                driver = make_driver()
                        else:
                            print(f" — giving up")
                
                except Exception as e:
                    print(f"Error: {e}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempt)
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = make_driver()
            
            if day_data:
                all_data.extend(day_data)
            else:
                failed_days.append(date_str)
    
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    
    if failed_days:
        print(f"\n⚠ Failed days: {', '.join(failed_days)}")
    
    return all_data

def save_json(data):
    """Save raw data as JSON"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filepath = os.path.join(DATA_FOLDER, f'screenings_{timestamp}.json')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Also save as "latest" for easy access
    latest_path = os.path.join(DATA_FOLDER, 'screenings_latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Data saved: {filepath}")
    print(f"✓ Latest data: {latest_path}")
    return latest_path

# --- EXECUTE ---
if __name__ == "__main__":
    print("=" * 60)
    print("🎬 NYC MOVIE SCREENINGS SCRAPER")
    print("=" * 60)
    print(f"\n📂 Data folder: {DATA_FOLDER}\n")
    
    # Screen Slate used to supply most venues, but as of Nov 2026 it returns
    # "403 Automated access is not allowed", so every theater is scraped
    # directly from its own calendar. master_scrape() is kept below in case
    # that ever changes.
    screenings = []

    for scrape in (scrape_metrograph, scrape_roxy_cinema, scrape_ifc_center,
                   scrape_film_forum, scrape_anthology,
                   scrape_film_at_lincoln_center):
        try:
            screenings.extend(scrape())
        except Exception as e:
            print(f"  ! {scrape.__name__} failed: {e}")

    # Venues whose calendars only exist after JS runs
    driver = make_driver()
    try:
        for scrape in (scrape_bam, scrape_paris_theater):
            try:
                screenings.extend(scrape(driver))
            except Exception as e:
                print(f"  ! {scrape.__name__} failed: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # Monthly calendars (Anthology, BAM) include days already past; the site
    # bills itself as the next 90 days, so keep only today onward.
    today_str = datetime.now().strftime('%Y-%m-%d')
    horizon = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
    before = len(screenings)
    screenings = [s for s in screenings if today_str <= s.get('date', '') <= horizon]
    if before != len(screenings):
        print(f"\n  Dropped {before - len(screenings)} screenings outside today..+90d")

    if screenings:
        print(f"\n{'='*60}")
        print(f"✓ Found {len(screenings)} total screenings")
        print(f"{'='*60}\n")

        screenings = resolve_screenslate_links(screenings)
        screenings = enrich_letterboxd(screenings)

        latest_path = save_json(screenings)
        
        print(f"\n{'='*60}")
        print("🎉 SCRAPING COMPLETE!")
        print(f"{'='*60}")
        print(f"\n📄 Latest data: {latest_path}")
        print(f"\nRun 'python build_website.py' to generate the website.")
        print(f"\n{'='*60}\n")
    else:
        print("\n❌ No screenings found. Check your internet connection or whether the theater sites changed.")
