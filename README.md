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
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
playwright install chromium
```

## Usage

### Basic Usage
```bash
python zoho_paid_invoce_collector_script.py
# → Saves to: collected_data/invoices.csv
```

### With Idempotency Key (Recommended)
```bash
# First run - scrapes fresh data
python zoho_paid_invoce_collector_script.py --idempotency-key "daily-run-2025-09-18"
# → Saves to: collected_data/invoices_daily-run-2025-09-18.csv

# Second run within 1 hour - replays cached result (no scraping)
python zoho_paid_invoce_collector_script.py --idempotency-key "daily-run-2025-09-18"
```

**Process:** Opens Zoho Books Demo → Navigates to invoices → Collects Paid/Partially Paid invoices across pages → Saves to key-specific CSV file

## Features
- Smart pagination and accurate filtering
- **Retry mechanism** with exponential backoff for 429/5xx errors  
- **Tiny idempotency** - prevents duplicate runs within 1-hour TTL
- **Dynamic CSV filenames** - each key gets its own CSV file
- Robust error handling

## Idempotency
- **Simple**: `--idempotency-key` flag prevents running the same job twice
- **1-hour TTL**: Cached results expire after 1 hour
- **Minimal cache**: Stores `{key → {timestamp, summary}}` in `collected_data/.idem_cache.json`
- **Key-specific files**: Each key gets `invoices_{key}.csv`

## Testing
```bash
pytest tests/ -v
```

**Test Coverage:** Retry mechanism, tiny idempotency keys, cache operations, job lifecycle, integration behavior

## CSV Output
```csv
invoice_id,customer,amount,paid_at,status
Invoice2,Hattie Grady,$25116,15 Apr 2025,Partially Paid
Invoice16,Vladimir,$451995,15 Apr 2025,Paid
```