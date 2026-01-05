#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jan  4 18:09:02 2026

@author: charitnarayanan
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

def master_scrape(num_days=30):
    """Scrape the next num_days days of screenings"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')          # Add this
    options.add_argument('--disable-dev-shm-usage') # Add this
    driver = webdriver.Chrome(options=options)
    all_data = []
    
    # Calculate date range
    start_date = datetime.now()
    end_date = start_date + timedelta(days=num_days - 1)
    
    print(f"📅 Scraping from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"   ({num_days} days total)\n")
    
    try:
        for i in range(num_days):
            date_obj = datetime.now() + timedelta(days=i)
            date_str = date_obj.strftime('%Y-%m-%d')
            url = f"https://www.screenslate.com/listings/{date_str}"
            print(f"Scraping: {date_str}...")
            driver.get(url)
            
            try:
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "listings")))
                time.sleep(1)
                
                current_theater = "Unknown Venue"
                for element in driver.find_elements(By.CSS_SELECTOR, "#listings *"):
                    if element.tag_name == 'h3':
                        current_theater = element.text.strip()
                    
                    if 'listing' in (element.get_attribute('class') or ''):
                        try:
                            title = element.find_element(By.CSS_SELECTOR, 'a span').text.strip()
                            link = element.find_element(By.TAG_NAME, 'a').get_attribute('href')
                            spans = element.find_elements(By.TAG_NAME, 'span')
                            director = spans[1].text.replace(' ,', '').strip() if len(spans) > 1 else "N/A"
                            year = spans[2].text.replace(',', '').strip() if len(spans) > 2 else "N/A"
                            
                            # Extract showtimes
                            showtimes = extract_showtimes(element)
                            
                            all_data.append({
                                'date': date_str,
                                'theater': current_theater,
                                'title': title,
                                'director': director,
                                'year': year,
                                'link': link,
                                'showtimes': showtimes
                            })
                        except: 
                            continue
            except: 
                continue
                
        print(f"\n  ✓ Found {len(all_data)} total screenings")
    finally:
        driver.quit()
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
        
        latest_path = save_json(screenings)
        
        print(f"\n{'='*60}")
        print("🎉 SCRAPING COMPLETE!")
        print(f"{'='*60}")
        print(f"\n📄 Latest data: {latest_path}")
        print(f"\nRun 'python build_website.py' to generate the website.")
        print(f"\n{'='*60}\n")
    else:
        print("\n❌ No screenings found. Check your internet connection or Screen Slate availability.")
