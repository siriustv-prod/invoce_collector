# Zoho Books Paid Invoice Collector

## Overview
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
cd respaid_test
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

Script process:
1. Opens Zoho Books Demo
2. Navigates to invoices automatically
3. Collects Paid/Partially Paid invoices across pages
4. Saves to `collected_data/invoices.csv`
5. Displays results and pauses

## Features
- Smart pagination across all pages
- Accurate filtering for Paid/Partially Paid status
- Complete data extraction
- Robust error handling

## CSV Output
```csv
invoice_id,customer,amount,paid_at,status
Invoice2,Hattie Grady,$25116,15 Apr 2025,Partially Paid
Invoice16,Vladimir,$451995,15 Apr 2025,Paid
```