I was using Cursor IDE with Claude-4-sonnet

Here are main prompt i use for this project

# 1. Initial prompt

You are a senior web scraper 

Your task is in the task assignment

Write a draft script skeleton that will open playwrite page with ZOHO_BOOKS_DEMO_URL
and run playwrite inspetor so i will be able so select and copy needed locator

leave a place in the code where i will paste locator for invoce page, and run action .click() to go there

after that write a same draft running inspector on the invoce page to gather interl how the table is done so i could copy locator and work with them further

also add a draft where i will paste locator for "NEXT" button so if there will me more pages script will be able to go over them all

### How it helped: worked as requested, helped me to get around the Zoho site, collect locators

# 2. Invoce collector code prompt

this is collected locators from the invoce page

```
    # TODO: Replace with actual locators for table elements
    # TABLE_ROWS_LOCATOR = "your_table_rows_locator_here"
    # INVOICE_ID_LOCATOR = "your_invoice_id_locator_here"  
    # CUSTOMER_LOCATOR = "your_customer_locator_here"
    # AMOUNT_LOCATOR = "your_amount_locator_here"
    # PAID_DATE_LOCATOR = "your_paid_date_locator_here"
    # STATUS_LOCATOR = "your_status_locator_here"
    

    # = TODO 2
    # locator for the whole table
    # get_by_text("Date Invoice# Order Number CustomerName Status Due Date Amount Balance Due 16")
    #
    # locator for the columns
    # get_by_role("cell", name="Date", exact=True)
    # get_by_role("cell", name="Invoice#")
    # get_by_role("cell", name="Order Number")
    # get_by_role("cell", name="CustomerName")
    # get_by_role("cell", name="Status")
    # get_by_role("cell", name="Due Date")
    # get_by_role("cell", name="Amount")
    # get_by_role("cell", name="Balance Due")
    #


    # = TODO 3
    # now the table have column namse - Date Invoice# Order Number CustomerName Status Due Date Amount Balance Due
    # and below is the locators for each column for the first row fol cells:
    # locator("[id=\"1\"]").get_by_role("cell", name="Feb 2025") 
    # get_by_role("cell", name="Invoice1", exact=True)
    # locator("[id=\"1\"]").get_by_role("cell").filter(has_text=re.compile(r"^$")).nth(1)
    # locator("[id=\"1\"]").get_by_role("cell", name="Arturo Dach")
    # locator("[id=\"1\"]").get_by_role("cell", name="Draft")
    # locator("[id=\"1\"]").get_by_role("cell", name="Jun 2026")
    # get_by_role("cell", name="$621362").first
    # get_by_role("cell", name="$621362").nth(1)
    #
    # for the column Invoice# we have also a link in the cell with this locator:
    # get_by_role("link", name="Invoice1", exact=True)
    # and for the column Status we have also a link in the cell with this locator:
    # locator("[id=\"1\"]").get_by_text("Draft")
    #
    # for the second row:
    # locator("[id=\"2\"]").get_by_role("cell", name="Feb 2025")
    # get_by_role("cell", name="Invoice2", exact=True)
    # locator("[id=\"2\"]").get_by_role("cell").filter(has_text=re.compile(r"^$")).nth(1)
    # locator("[id=\"2\"]").get_by_role("cell", name="Arturo Dach")
    # locator("[id=\"2\"]").get_by_role("cell", name="Partially Paid")
    # locator("[id=\"2\"]").get_by_role("cell", name="Jun 2026")
    # locator("[id=\"2\"]").get_by_role("cell", name="$35967")
    # locator("[id=\"2\"]").get_by_role("cell", name="$35957")
    #
    #
    # for the column Invoice# we have also a link in the cell with this locator:
    # get_by_role("link", name="Invoice2", exact=True)
    # and for the column Status we have also a link in the cell with this locator:
    # get_by_role("row", name="Select Invoice Invoice2 16").locator("span")
    #
    # Note: for the AMOUNT and BALANCE DUE we have most other row locators ends with .first and .nth(1) (like in the first row)
    # But only in case when the CUSTOMER NAME is the same as in the first row we have in the second row locators without .first and .nth(1)
    # If there is third and forth row they end with .nth(2) and .nth(3)
    # 
    # 
    # 

```
this is the all page element with table itself
```
<div class="product    "><!----><!----><div class="top-band unified-top-band d-print-none" id="top-band"><div class=" logo-container  "><div class="logo-collapse d-flex align-items-center cursor-pointer "><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="icon icon-xlg app-logo"><path d="M361 502.5H24.5c-8 0-14.4-6.5-14.4-14.4V365.8c0-26.7 17-50.5 42.2-59.2l373-128c29-10 48.6-37.3 48.6-68 0-39.6-32.3-71.9-71.9-71.9H39v238.1c0 8-6.5 14.4-14.4 14.4S10 284.9 10 276.9V24.3c0-8 6.5-14.4 14.4-14.4h377.5c55.6 0 100.8 45.2 100.8 100.8 0 43-27.3 81.3-68.1 
(...)
```

As a senior data scrapping specialist - analyse and came up with the best approach to extract needed invoice data from the table

### How it helped: Wrote the invoce collector which worked correctly from the first run

## Note: I didn't realize the zoho demo site was chaning content each time i enter, so i thoght the code didn't wokr and spend some time debugging )

# 3. Clean-up prompt.

ok

look we vere debugging errors but each time you open https://www.zoho.com/books/accounting-software-demo/#/invoices there are different data there - so there were no errors at all

So we need to do two things
- clean up the code. most likely we don't need so much validations and fallbacks. make code much simplier, keeping your gained knowledge of the page, but your goal now is to make code as much shorter, simpler and cleared as possible! 
- in the end of the script - put the open browser window on pause, and pring to the console the resulted csv. wait for 'enter' to continue

### How it helped: Excellent, clean-up the code, and keed the finding from the debugging phase. There was however bug with 'next' button loop, which was fixed by next prompt

# 4. Documentation prompt.

ok we are good!

now please read task_assignment again
write a proffessional, brief, clear and consise <200 words README.md with
- Overview
- Instructions to install and to run the script
- Functional description
- Resulting csv example

### How it helped: As requested - clear and percise README.md