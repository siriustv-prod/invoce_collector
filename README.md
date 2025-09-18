# Zoho Books Paid Invoice Collector

Automated script that collects **Paid** and **Partially Paid** invoices from [Zoho Books Demo Company](https://www.zoho.com/books/accounting-software-demo/#/home/dashboard) and exports to CSV. Uses Playwright for web automation without API dependencies.

## Demo
[Loom video demo](https://www.loom.com/share/a592cc87e14546bf8af0d631abaf5466)

## Structure
- [task_assignment](task_assignment.md) - project task
- [prompts.md](prompts.md) - development prompts
- [/timeproof](timeproof) - timeline & screenshots
- [zoho_paid_invoce_collector_script.py](zoho_paid_invoce_collector_script.py) - python script

## Installation & Setup
```bash
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

## Usage
```bash
python zoho_paid_invoce_collector_script.py
```

**Process:** Opens Zoho Books Demo → Navigates to invoices → Collects Paid/Partially Paid invoices across pages → Saves to `collected_data/invoices.csv`

## Features
- Smart pagination and accurate filtering
- **Retry mechanism** with exponential backoff for 429/5xx errors  
- **Idempotency key** session tracking for operation transparency
- Robust error handling

## Testing
```bash
# Run tests
pytest tests/ -v

# Test specific functionality
pytest tests/test_retry_and_idempotency.py -v
```

**Test Coverage:** Retry mechanism, idempotency keys, session lifecycle, safe operations, integration behavior

## CSV Output
```csv
invoice_id,customer,amount,paid_at,status
Invoice2,Hattie Grady,$25116,15 Apr 2025,Partially Paid
Invoice16,Vladimir,$451995,15 Apr 2025,Paid
```