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
        showtime_divs = element.find_elements(By.CSS_SELECTOR, '.showtimes, [class*="showtime"], div:has(span)')
        for div in showtime_divs:
            time_spans = div.find_elements(By.TAG_NAME, 'span')
            for span in time_spans:
                text = span.text.strip()
                times = re.findall(r'\d{1,2}:\d{2}\s*[AP]M', text, re.IGNORECASE)
                for t in times:
                    clean_time = t.rstrip(',').strip()
                    if clean_time and clean_time not in showtimes:
                        showtimes.append(clean_time)
        if not showtimes:
            parent_text = element.text
            times = re.findall(r'\d{1,2}:\d{2}\s*[AP]M', parent_text, re.IGNORECASE)
            for t in times:
                clean_time = t.rstrip(',').strip()
                if clean_time and clean_time not in showtimes:
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
        print(f"  No #listings container found")
        return []
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

def master_scrape(num_days=30):
    """Scrape the next num_days days of screenings with retries."""
    driver = make_driver()
    all_data = []
    failed_days = []
    start_date = datetime.now()
    print(f"Scraping {num_days} days starting from {start_date.strftime('%Y-%m-%d')}\n")
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
                            if attempt == MAX_RETRIES - 1:
                                try:
                                    driver.quit()
                                except Exception:
                                    pass
                                driver = make_driver()
                        else:
                            print(f" -- giving up")
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
        print(f"\nFailed days: {', '.join(failed_days)}")
    return all_data

def save_json(data):
    """Save raw data as JSON"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filepath = os.path.join(DATA_FOLDER, f'screenings_{timestamp}.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    latest_path = os.path.join(DATA_FOLDER, 'screenings_latest.json')
    with open(latest_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Data saved: {filepath}")
    print(f"Latest data: {latest_path}")
    return latest_path

# --- EXECUTE ---
if __name__ == "__main__":
    print("=" * 60)
    print("NYC MOVIE SCREENINGS SCRAPER")
    print("=" * 60)
    print(f"\nData folder: {DATA_FOLDER}\n")
    NUM_DAYS = 30
    screenings = master_scrape(NUM_DAYS)
    if screenings:
        print(f"\n{'='*60}")
        print(f"Found {len(screenings)} total screenings")
        print(f"{'='*60}\n")
        latest_path = save_json(screenings)
        print(f"\n{'='*60}")
        print("SCRAPING COMPLETE!")
        print(f"{'='*60}")
        print(f"\nLatest data: {latest_path}")
        print(f"\nRun 'python build_website.py' to generate the website.")
        print(f"\n{'='*60}\n")
    else:
        print("\nNo screenings found. Check your internet connection or Screen Slate availability.")
