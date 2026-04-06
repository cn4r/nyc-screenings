#!/usr/bin/env python3
"""
NYC Movie Screenings Scraper — v2 (refactored)
Scrapes screenslate.com/listings for the next N days.

Key improvements over v1:
  • Full-page incremental scrolling (not just 1000px)
  • Per-day retries with exponential back-off
  • Explicit waits for listing elements, not just the container
  • Diagnostic logging so you can see *why* a day came back empty
  • Saves per-day JSON fragments so a crash doesn't lose everything
"""

import os
import sys
import json
import re
import time
import logging
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

# ── CONFIG ──────────────────────────────────────────────────────────
NUM_DAYS = 30
MAX_RETRIES = 3            # retries per day
RETRY_DELAY_BASE = 5       # seconds; doubles each retry
PAGE_LOAD_TIMEOUT = 15     # seconds to wait for #listings
SCROLL_PAUSE = 1.0         # seconds between scroll steps
SCROLL_STEP = 800          # pixels per scroll increment

BASE_FOLDER = os.path.dirname(os.path.abspath(__file__)) or os.getcwd()
DATA_FOLDER = os.path.join(BASE_FOLDER, "data")
os.makedirs(DATA_FOLDER, exist_ok=True)

# ── LOGGING ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scraper")


# ── HELPERS ─────────────────────────────────────────────────────────
TIME_RE = re.compile(r"\d{1,2}:\d{2}\s*[AP]M", re.IGNORECASE)


def _extract_showtimes(element):
    """Pull every HH:MM AM/PM token from an element's visible text."""
    try:
        text = element.text or ""
    except StaleElementReferenceException:
        return ["Check website"]

    times = []
    for m in TIME_RE.finditer(text):
        t = m.group().strip().rstrip(",")
        if t not in times:
            times.append(t)
    return times if times else ["Check website"]


def _scroll_to_bottom(driver):
    """Scroll the full page in increments so lazy-loaded content appears."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script(f"window.scrollBy(0, {SCROLL_STEP});")
        time.sleep(SCROLL_PAUSE)
        new_height = driver.execute_script("return document.body.scrollHeight")
        current_pos = driver.execute_script("return window.pageYOffset + window.innerHeight")
        if current_pos >= new_height or new_height == last_height:
            break
        last_height = new_height
    # Scroll back to top (some sites re-render on scroll position)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)


def _make_driver():
    """Create a headless Chrome driver with sensible defaults."""
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver


# ── CORE SCRAPE LOGIC ───────────────────────────────────────────────
def scrape_day(driver, date_str):
    """
    Scrape a single day's listings. Returns a list of dicts.
    Raises on hard failure so the retry wrapper can catch it.
    """
    url = f"https://www.screenslate.com/listings/{date_str}"
    driver.get(url)

    # 1. Wait for the listings container
    try:
        WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "listings"))
        )
    except TimeoutException:
        log.warning(f"  {date_str}: #listings container never appeared")
        return []

    # 2. Scroll the entire page to trigger lazy loading
    _scroll_to_bottom(driver)

    # 3. Small extra pause for any XHR / hydration
    time.sleep(1.5)

    # 4. Parse the listings container
    listings_el = driver.find_element(By.ID, "listings")

    #    Strategy: iterate through children in document order.
    #    <h3> = theater name; elements with class containing "listing" = a film.
    #    Fallback: also look for <article> or <div class="...listing...">
    results = []
    current_theater = "Unknown Venue"

    children = listings_el.find_elements(By.XPATH, "./*")
    if not children:
        # Broader fallback: maybe the listings are nested deeper
        children = listings_el.find_elements(By.CSS_SELECTOR, "h3, [class*='listing']")

    for el in children:
        tag = el.tag_name.lower()

        # ── Theater header ──
        if tag == "h3":
            text = (el.text or "").strip()
            if text:
                current_theater = text
            continue

        # ── Listing element ──
        cls = (el.get_attribute("class") or "").lower()
        if "listing" not in cls:
            # Could be a wrapper div; check children
            inner = el.find_elements(By.CSS_SELECTOR, "h3, [class*='listing']")
            for inner_el in inner:
                inner_tag = inner_el.tag_name.lower()
                if inner_tag == "h3":
                    text = (inner_el.text or "").strip()
                    if text:
                        current_theater = text
                else:
                    _parse_listing(inner_el, date_str, current_theater, results)
            continue

        _parse_listing(el, date_str, current_theater, results)

    return results


def _parse_listing(el, date_str, theater, out_list):
    """Extract one screening record from a listing element."""
    try:
        # Title is usually in the first <a><span>
        try:
            title_el = el.find_element(By.CSS_SELECTOR, "a span")
            title = title_el.text.strip()
        except NoSuchElementException:
            # Fallback: first <a> text
            a_el = el.find_element(By.TAG_NAME, "a")
            title = a_el.text.strip()

        if not title:
            return

        # Link
        try:
            link = el.find_element(By.TAG_NAME, "a").get_attribute("href") or ""
        except NoSuchElementException:
            link = ""

        # Director & year from subsequent <span> elements
        spans = el.find_elements(By.TAG_NAME, "span")
        director = "N/A"
        year = "N/A"
        if len(spans) > 1:
            director = spans[1].text.replace(" ,", "").strip() or "N/A"
        if len(spans) > 2:
            year = spans[2].text.replace(",", "").strip() or "N/A"

        showtimes = _extract_showtimes(el)

        out_list.append(
            {
                "date": date_str,
                "theater": theater,
                "title": title,
                "director": director,
                "year": year,
                "link": link,
                "showtimes": showtimes,
            }
        )
    except (NoSuchElementException, StaleElementReferenceException):
        pass


# ── MAIN ────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("NYC MOVIE SCREENINGS SCRAPER  v2")
    log.info("=" * 60)

    all_data = []
    failed_days = []

    driver = _make_driver()

    try:
        for i in range(NUM_DAYS):
            date_obj = datetime.now() + timedelta(days=i)
            date_str = date_obj.strftime("%Y-%m-%d")

            day_data = []
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    day_data = scrape_day(driver, date_str)
                    if day_data:
                        break
                    # Got zero results — might be legit (no screenings) or a load failure
                    if attempt < MAX_RETRIES:
                        delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                        log.info(
                            f"  {date_str}: 0 results on attempt {attempt}/{MAX_RETRIES}, "
                            f"retrying in {delay}s…"
                        )
                        time.sleep(delay)
                        # Restart driver every few retries to clear state
                        if attempt == 2:
                            driver.quit()
                            driver = _make_driver()
                except Exception as e:
                    log.warning(f"  {date_str}: attempt {attempt} error — {e}")
                    if attempt < MAX_RETRIES:
                        delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                        time.sleep(delay)
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = _make_driver()

            if day_data:
                log.info(f"  {date_str}: ✓ {len(day_data)} screenings")
                all_data.extend(day_data)
                # Save per-day fragment for safety
                frag_path = os.path.join(DATA_FOLDER, f"day_{date_str}.json")
                with open(frag_path, "w", encoding="utf-8") as f:
                    json.dump(day_data, f, ensure_ascii=False, indent=2)
            else:
                log.warning(f"  {date_str}: ✗ no screenings after {MAX_RETRIES} attempts")
                failed_days.append(date_str)

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # ── Save combined output ────────────────────────────────────────
    if all_data:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ts_path = os.path.join(DATA_FOLDER, f"screenings_{ts}.json")
        latest_path = os.path.join(DATA_FOLDER, "screenings_latest.json")

        for path in (ts_path, latest_path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

        log.info("")
        log.info("=" * 60)
        log.info(f"✓ {len(all_data)} total screenings saved")
        log.info(f"  timestamped : {ts_path}")
        log.info(f"  latest      : {latest_path}")
        if failed_days:
            log.warning(f"  ✗ empty days : {', '.join(failed_days)}")
        log.info("=" * 60)
        log.info("Run 'python build_website.py' to generate the website.")
    else:
        log.error("No screenings found at all. Check connection / site availability.")

    return all_data, failed_days


if __name__ == "__main__":
    main()
