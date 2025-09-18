# Zoho Books Paid Invoice Collector Script

import csv
import os
import time
import random
import uuid
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
from functools import wraps

# Constants
ZOHO_INVOICES_URL = "https://www.zoho.com/books/accounting-software-demo/#/invoices"
COLUMNS = ["invoice_id", "customer", "amount", "paid_at", "status"]
ACCEPTED_STATUSES = ["Paid", "Partially Paid"]
CSV_FILE = "collected_data/invoices.csv"
IDEMPOTENCY_FILE = "collected_data/session_tracking.json"


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


def generate_session_id():
    """Generate a unique session ID for idempotency."""
    return str(uuid.uuid4())


def load_session_tracking():
    """Load existing session tracking data."""
    if os.path.exists(IDEMPOTENCY_FILE):
        try:
            with open(IDEMPOTENCY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return {}


def save_session_tracking(session_data):
    """Save session tracking data."""
    os.makedirs(os.path.dirname(IDEMPOTENCY_FILE), exist_ok=True)
    with open(IDEMPOTENCY_FILE, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2)


def check_session_completed(session_id):
    """Check if a session was already completed successfully."""
    tracking_data = load_session_tracking()
    session_info = tracking_data.get(session_id, {})
    return session_info.get('status') == 'completed'


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


def save_to_csv(invoices):
    """Save invoices to CSV file."""
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
    
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(invoices)
    
    print(f"💾 Saved {len(invoices)} invoices to {CSV_FILE}")


def collect_invoices():
    """Main function to collect invoices with pagination."""
    # Generate session ID for idempotency
    session_id = generate_session_id()
    print(f"🔑 Session ID: {session_id}")
    
    # Check if this session type was already completed recently
    tracking_data = load_session_tracking()
    
    # Clean up old sessions (keep only last 10)
    if len(tracking_data) > 10:
        sorted_sessions = sorted(tracking_data.items(), 
                               key=lambda x: x[1].get('timestamp', ''), 
                               reverse=True)
        tracking_data = dict(sorted_sessions[:10])
        save_session_tracking(tracking_data)
    
    # Initialize session tracking
    session_info = {
        'session_id': session_id,
        'timestamp': datetime.now().isoformat(),
        'status': 'started',
        'invoices_collected': 0,
        'pages_processed': 0
    }
    
    tracking_data[session_id] = session_info
    save_session_tracking(tracking_data)
    
    try:
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
                
                # Update session tracking
                session_info['pages_processed'] = page_number
                tracking_data[session_id] = session_info
                save_session_tracking(tracking_data)
                
                # Extract invoices from current page
                invoices = extract_invoices_from_page(page)
                all_invoices.extend(invoices)
                
                # Update invoice count in session tracking
                session_info['invoices_collected'] = len(all_invoices)
                tracking_data[session_id] = session_info
                save_session_tracking(tracking_data)
                
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
            save_to_csv(all_invoices)
            
            # Mark session as completed
            session_info['status'] = 'completed'
            session_info['final_invoice_count'] = len(all_invoices)
            session_info['completion_timestamp'] = datetime.now().isoformat()
            tracking_data[session_id] = session_info
            save_session_tracking(tracking_data)
            
            # Display results and pause
            print(f"\n🎉 Successfully collected {len(all_invoices)} paid/partially paid invoices!")
            print(f"📊 Session {session_id} completed successfully")
            print("\n" + "="*60)
            print("COLLECTED DATA:")
            print("="*60)
            
            # Read and display the CSV content
            if os.path.exists(CSV_FILE):
                with open(CSV_FILE, 'r', encoding='utf-8') as f:
                    print(f.read())
            
            print("="*60)
            print("Browser window is paused. Press ENTER to close...")
            input()  # Wait for user input
            
            browser.close()
            
    except Exception as e:
        # Mark session as failed
        session_info['status'] = 'failed'
        session_info['error'] = str(e)
        session_info['failure_timestamp'] = datetime.now().isoformat()
        tracking_data[session_id] = session_info
        save_session_tracking(tracking_data)
        
        print(f"❌ Session {session_id} failed: {e}")
        raise


if __name__ == "__main__":
    print("🚀 Zoho Books Paid Invoice Collector")
    print("=" * 50)
    collect_invoices()