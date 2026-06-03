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
from bs4 import BeautifulSoup
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
    slug = title.lower()
    # Remove content in parentheses (like "35mm" notes)
    slug = re.sub(r'\s*\([^)]*\)\s*', ' ', slug)
    # Replace & with and (Letterboxd doesn't always do this, but handles both)
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
                'genres': [], 'runtime_mins': None, 'rating': None, 'rating_count': None}

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
        else:
            s['letterboxd_url'] = None
            s['genres'] = []
            s['runtime_mins'] = None
            s['rating'] = None
            s['rating_count'] = None

    return data


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
    
    # Always scrape next 30 days
    NUM_DAYS = 30
    screenings = master_scrape(NUM_DAYS)
    
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
        print("\n❌ No screenings found. Check your internet connection or Screen Slate availability.")
