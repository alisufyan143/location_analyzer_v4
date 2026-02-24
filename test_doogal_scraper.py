"""
Doogal Scraper — Persistent Session Test
========================================
Tests scraping Doogal using a SINGLE persistent headful browser session.
This verifies if Doogal is tarpitting us due to constant fresh-context creation.
"""

import time
import re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

DOOGAL_URL = "https://www.doogal.co.uk/ShowMap?postcode={postcode}"

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"
INFO = "ℹ️  INFO"

results_summary = []

def log(status, test_name, detail=""):
    tag = f"[{status}]"
    print(f"  {tag:12s} {test_name}")
    if detail:
        print(f"{'':14s} → {detail}")
    results_summary.append((status, test_name, detail))

def section(title):
    print(f"\n{'═' * 70}")
    print(f"  {title}")
    print(f"{'═' * 70}")

def extract_income(html: str) -> int:
    """Parses income from the HTML DOM."""
    soup = BeautifulSoup(html, "html.parser")
    for th in soup.find_all("th"):
        text = th.get_text(strip=True)
        if "average household income" in text.lower():
            next_td = th.find_next_sibling("td")
            if next_td:
                # specific progress bar span
                span = next_td.find("span", class_="show")
                if span:
                    match = re.search(r"£([\d,]+)", span.get_text(strip=True))
                    if match: return int(match.group(1).replace(",", ""))
                # fallback td text
                match = re.search(r"£([\d,]+)", next_td.get_text())
                if match: return int(match.group(1).replace(",", ""))
    
    # 2nd strategy
    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        if "average household income" in text.lower():
            next_td = td.find_next_sibling("td")
            if next_td:
                match = re.search(r"£([\d,]+)", next_td.get_text())
                if match: return int(match.group(1).replace(",", ""))
                
    # Regex fallback
    match = re.search(r"average\s+household\s+income.*?£([\d,]+)", soup.get_text(), re.IGNORECASE | re.DOTALL)
    if match: return int(match.group(1).replace(",", ""))
    return 0

def run_tests():
    print("🔬 Doogal Scraper — PERSISTENT Browser Test Suite\n")
    
    with sync_playwright() as pw:
        print("[System] Launching a single persistent Headful browser...")
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        tests = [
            ("TEST 1: Standard Postcode (London)", "SW1A 1AA"),
            ("TEST 2: New Tab Same Session (Manchester)", "M1 1AE"),
            ("TEST 3: New Tab Same Session (Birmingham)", "B1 1DD"),
        ]
        
        for name, pc in tests:
            section(name)
            url = DOOGAL_URL.format(postcode=pc.replace(" ", "%20"))
            
            start = time.time()
            print(f"      [~] Navigating to {url} (Opening New Tab)...")
            
            # Spawn a new tab in the same browser context
            page = context.new_page()
            try:
                page.goto(url, timeout=15000, wait_until="domcontentloaded")
                page.wait_for_timeout(15000)
                income = extract_income(page.content())
                elapsed = time.time() - start
                if income > 0: log(PASS, f"'{pc}'", f"Income: £{income:,} ({elapsed:.1f}s)")
                else: log(FAIL, f"'{pc}'", f"No income found ({elapsed:.1f}s)")
            except Exception as e:
                log(FAIL, f"'{pc}'", f"Error: {e} ({time.time() - start:.1f}s)")
            finally:
                page.close()

        print("\n[System] Finishing tests. Playwright context manager will now close the browser automatically.")

if __name__ == "__main__":
    run_tests()
