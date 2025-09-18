# Zoho Books Paid Invoice Collector Script

import csv
import os
import time
import random
import json
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright
from functools import wraps

# Constants
ZOHO_INVOICES_URL = "https://www.zoho.com/books/accounting-software-demo/#/invoices"
COLUMNS = ["invoice_id", "customer", "amount", "paid_at", "status"]
ACCEPTED_STATUSES = ["Paid", "Partially Paid"]
CSV_BASE_DIR = "collected_data"

# --- tiny idempotency (job-level only) ---
IDEM_FILE = "collected_data/.idem_cache.json"
IDEM_TTL_SECONDS = 3600  # 1 hour


def get_csv_filename(idempotency_key):
    """Generate CSV filename based on idempotency key."""
    if idempotency_key:
        # Sanitize key for filename (replace invalid chars with underscores)
        safe_key = "".join(c if c.isalnum() or c in '-_' else '_' for c in idempotency_key)
        return f"{CSV_BASE_DIR}/invoices_{safe_key}.csv"
    else:
        return f"{CSV_BASE_DIR}/invoices.csv"


def exponential_backoff_retry(max_attempts=3, base_delay=1, max_delay=16):
    """Decorator to add exponential backoff retry for 429/5xx errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            delay = base_delay
            
            while attempts < max_attempts:
                try:
                    result = func(*args, **kwargs)
                    
                    # Check if this is a page response and has status code
                    if hasattr(result, 'status'):
                        try:
                            status_code = int(result.status)
                            if status_code >= 500:
                                raise Exception(f"Server error: {status_code}")
                            elif status_code == 429:
                                raise Exception(f"Rate limited: {status_code}")
                        except (ValueError, TypeError):
                            # If status is not a number (e.g., Mock object), skip status check
                            pass
                    
                    return result
                    
                except Exception as e:
                    attempts += 1
                    error_msg = str(e).lower()
                    
                    # Only retry on specific errors
                    should_retry = (
                        '429' in error_msg or 
                        'rate limited' in error_msg or
                        'server error' in error_msg or
                        '5' in error_msg and ('error' in error_msg or 'server' in error_msg) or
                        'timeout' in error_msg or
                        'network' in error_msg or
                        'connection' in error_msg
                    )
                    
                    if attempts >= max_attempts or not should_retry:
                        print(f"❌ Operation failed after {attempts} attempts: {e}")
                        raise
                    
                    jitter = random.uniform(0.5, 1.5)
                    sleep_time = min(delay * jitter, max_delay)
                    print(f"⏳ Retry {attempts}/{max_attempts} in {sleep_time:.1f}s due to: {e}")
                    time.sleep(sleep_time)
                    delay *= 2
            
            return None
        return wrapper
    return decorator


def _idem_load():
    """Load idempotency cache."""
    try:
        with open(IDEM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _idem_save(data):
    """Save idempotency cache."""
    os.makedirs(os.path.dirname(IDEM_FILE), exist_ok=True)
    with open(IDEM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def maybe_replay(idem_key):
    """Check if we can replay a previous result for this idempotency key."""
    if not idem_key:
        return None
    data = _idem_load()
    entry = data.get(idem_key)
    if not entry:
        return None
    if time.time() - entry["ts"] > IDEM_TTL_SECONDS:
        return None
    print(f"🔄 Replaying previous result for key '{idem_key}' (within TTL).")
    return entry["summary"]


def record_result(idem_key, summary):
    """Record the result for this idempotency key."""
    if not idem_key:
        return
    data = _idem_load()
    data[idem_key] = {"ts": time.time(), "summary": summary}
    _idem_save(data)


@exponential_backoff_retry(max_attempts=3)
def safe_goto(page, url):
    """Navigate to URL with retry mechanism."""
    print(f"🌐 Navigating to {url}")
    response = page.goto(url)
    page.wait_for_load_state("networkidle")
    return response


@exponential_backoff_retry(max_attempts=3)
def safe_wait_for_selector(page, selector, timeout=10000):
    """Wait for selector with retry mechanism."""
    return page.wait_for_selector(selector, timeout=timeout)


@exponential_backoff_retry(max_attempts=3)
def safe_click(page, locator):
    """Click element with retry mechanism."""
    locator.click()
    page.wait_for_load_state("networkidle")
    return True


def extract_invoices_from_page(page):
    """Extract paid/partially paid invoices from the current page."""
    invoices = []
    
    # Wait for table and find all rows with retry mechanism
    safe_wait_for_selector(page, "table", timeout=10000)
    rows = page.locator("tbody tr")
    
    print(f"   Found {rows.count()} rows")
    
    for i in range(rows.count()):
        row = rows.nth(i)
        cells = row.get_by_role("cell")
        
        if cells.count() < 8:  # Skip incomplete rows
            continue
            
        # Extract data based on table structure:
        # Cell 1: DATE, Cell 2: INVOICE#, Cell 4: CUSTOMER, Cell 5: STATUS, Cell 7: AMOUNT
        invoice_data = {
            'invoice_id': cells.nth(2).text_content().strip(),
            'customer': cells.nth(4).text_content().strip(),
            'amount': cells.nth(7).text_content().strip(),
            'paid_at': cells.nth(1).text_content().strip(),
            'status': cells.nth(5).text_content().strip()
        }
        
        # Only collect Paid or Partially Paid invoices
        if invoice_data['status'] in ACCEPTED_STATUSES:
            invoices.append(invoice_data)
            print(f"   ✅ {invoice_data['status']}: {invoice_data['invoice_id']} - {invoice_data['customer']} - {invoice_data['amount']}")
    
    return invoices


def save_to_csv(invoices, csv_file):
    """Save invoices to CSV file."""
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(invoices)
    
    print(f"💾 Saved {len(invoices)} invoices to {csv_file}")


def collect_invoices(csv_file):
    """Main function to collect invoices with pagination."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate with retry mechanism
        safe_goto(page, ZOHO_INVOICES_URL)
        
        all_invoices = []
        page_number = 1
        max_pages = 5  # Safety limit
        
        while page_number <= max_pages:
            print(f"📄 Processing page {page_number}...")
            
            # Extract invoices from current page
            invoices = extract_invoices_from_page(page)
            all_invoices.extend(invoices)
            
            # Check for next page
            next_button = page.locator("#pagination").get_by_role("button").nth(2)
            
            if next_button.is_visible() and not next_button.get_attribute("disabled"):
                # Store current page content to compare after click
                current_content = page.locator("tbody").text_content()
                
                print(f"   Going to page {page_number + 1}...")
                # Use safe_click for retry mechanism
                safe_click(page, next_button)
                
                # Wait a bit more and check if content actually changed
                page.wait_for_timeout(1000)
                new_content = page.locator("tbody").text_content()
                
                if current_content == new_content:
                    print("   Content didn't change - reached last page")
                    break
                
                page_number += 1
            else:
                print("   No more pages")
                break
    
        # Save results
        save_to_csv(all_invoices, csv_file)
        
        # Display results and pause
        print(f"\n🎉 Successfully collected {len(all_invoices)} paid/partially paid invoices!")
        print("\n" + "="*60)
        print("COLLECTED DATA:")
        print("="*60)
        
        # Read and display the CSV content
        if os.path.exists(csv_file):
            with open(csv_file, 'r', encoding='utf-8') as f:
                print(f.read())
        
        print("="*60)
        print("Browser window is paused. Press ENTER to close...")
        input()  # Wait for user input
        
        browser.close()
        
        return all_invoices


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--idempotency-key", help="Optional key to dedupe this job")
    args = parser.parse_args()

    # Generate CSV filename based on idempotency key
    csv_file = get_csv_filename(args.idempotency_key)

    # Try replay
    replay = maybe_replay(args.idempotency_key)
    if replay:
        print(f"✅ Done (replayed): {replay}")
        raise SystemExit(0)

    print("🚀 Zoho Books Paid Invoice Collector")
    print("=" * 50)
    invoices = collect_invoices(csv_file)

    # Summarize and record
    summary = {"rows": len(invoices), "csv": csv_file}
    record_result(args.idempotency_key, summary)
    print(f"✅ Done (fresh): {summary}")