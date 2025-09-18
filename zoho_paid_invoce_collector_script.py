# Zoho Books Paid Invoice Collector Script

import csv
import os
from playwright.sync_api import sync_playwright

# Constants
ZOHO_INVOICES_URL = "https://www.zoho.com/books/accounting-software-demo/#/invoices"
COLUMNS = ["invoice_id", "customer", "amount", "paid_at", "status"]
ACCEPTED_STATUSES = ["Paid", "Partially Paid"]
CSV_FILE = "collected_data/invoices.csv"


def extract_invoices_from_page(page):
    """Extract paid/partially paid invoices from the current page."""
    invoices = []
    
    # Wait for table and find all rows
    page.wait_for_selector("table", timeout=10000)
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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("🌐 Navigating to Zoho Books Invoices...")
        page.goto(ZOHO_INVOICES_URL)
        page.wait_for_load_state("networkidle")
        
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
                next_button.click()
                page.wait_for_load_state("networkidle")
                
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
        
        # Display results and pause
        print(f"\n🎉 Successfully collected {len(all_invoices)} paid/partially paid invoices!")
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


if __name__ == "__main__":
    print("🚀 Zoho Books Paid Invoice Collector")
    print("=" * 50)
    collect_invoices()