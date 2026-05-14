# Adapting for Your Sector

How to customize the Press Release Pipeline for biotech, energy, fintech, or any other sector.

---

## Overview

This project was originally built for REITs (Real Estate Investment Trusts), but the architecture works for any sector with public companies that issue press releases. This guide walks you through customization.

---

## Step 1: Identify Your Companies

### Make a List
Create a spreadsheet with:
- Company name
- Stock ticker
- Investor Relations URL
- IR email domain (if known)

### Example: Biotech Sector
```
Company           | Ticker | IR URL
------------------|--------|----------------------------------------
Moderna           | MRNA   | https://investors.modernatx.com
Regeneron         | REGN   | https://investor.regeneron.com
Vertex            | VRTX   | https://investors.vrtx.com
BioNTech          | BNTX   | https://investors.biontech.de
```

---

## Step 2: Update Company Configuration

### Edit `config/email_parser_config.py`

Replace the REIT domains with your sector:

```python
# Map IR domains to company tickers
COMPANY_DOMAINS = {
    # Biotech examples
    "investors.modernatx.com": "MRNA",
    "investor.regeneron.com": "REGN",
    "investors.vrtx.com": "VRTX",
    "investors.biontech.de": "BNTX",
    
    # Add your companies here
    "ir.yourcompany.com": "TICK",
}

# Email sender patterns
SENDER_PATTERNS = {
    "moderna": "MRNA",
    "regeneron": "REGN",
    "vertex": "VRTX",
}
```

---

## Step 3: Customize Categories

### Edit `config/categories.py`

Replace or add sector-specific categories:

```python
# Original REIT categories
CATEGORIES = [
    "Earnings",
    "Dividend",
    "M&A",
    "Leadership",
    "Financing",
]

# Biotech categories
CATEGORIES = [
    "Earnings",
    "Clinical Trial",
    "FDA Approval",
    "FDA Rejection",
    "Partnership",
    "Pipeline Update",
    "Drug Launch",
    "M&A",
    "Leadership",
    "Financing",
]

# Energy categories
CATEGORIES = [
    "Earnings",
    "Production Update",
    "Reserve Estimate",
    "Asset Sale",
    "Exploration",
    "M&A",
    "Dividend",
    "ESG/Sustainability",
]
```

---

## Step 4: Update AI Classification Prompt

### Edit `core/categorizer.py`

Find the classification prompt and update for your sector:

```python
prompt = f"""You are analyzing a company press release from the {SECTOR} sector.

Classify this press release into ONE of these categories:
{', '.join(CATEGORIES)}

Consider sector-specific terminology:
- For biotech: Phase 1/2/3 trials, FDA submissions, drug approvals
- For energy: Production volumes, reserves, drilling results
- For fintech: User growth, transaction volume, regulatory approvals

Title: {title}
Content: {content[:2000]}

Respond with just the category name.
"""
```

---

## Step 5: Load Your Companies

### Option A: Manual Entry
Use the Flask dashboard:
1. Go to http://localhost:5001
2. Click **Companies** → **Add Company**
3. Enter ticker, name, and IR URL

### Option B: Bulk Import
Create a JSON file `data/companies.json`:
```json
[
    {
        "ticker": "MRNA",
        "name": "Moderna Inc",
        "ir_url": "https://investors.modernatx.com",
        "sector": "Biotech"
    },
    {
        "ticker": "REGN",
        "name": "Regeneron Pharmaceuticals",
        "ir_url": "https://investor.regeneron.com",
        "sector": "Biotech"
    }
]
```

Then import:
```bash
python scripts/import_companies.py data/companies.json
```

---

## Step 6: Configure Scraping Selectors

### Edit `config/selectors.json`

Add CSS selectors for your companies' IR pages:

```json
{
    "investors.modernatx.com": {
        "press_release_list": ".press-release-item",
        "title": "h3.title",
        "date": ".date",
        "link": "a.read-more"
    },
    "investor.regeneron.com": {
        "press_release_list": ".news-item",
        "title": ".news-title",
        "date": ".news-date",
        "link": "a"
    }
}
```

### Tips for Finding Selectors
1. Open the IR page in Chrome
2. Right-click on a press release title → Inspect
3. Find the CSS class or ID
4. Test with: `document.querySelectorAll('.your-selector')`

---

## Step 7: Sign Up for IR Emails

For each company:
1. Go to their IR page
2. Find "Email Alerts" or "Subscribe"
3. Enter your pipeline email address
4. Select "Press Releases"

See [IR_EMAIL_SETUP.md](IR_EMAIL_SETUP.md) for forwarding configuration.

---

## Step 8: Test the Pipeline

### Test Scraping
```bash
python -c "
from core.scraper import PressReleaseScraper
scraper = PressReleaseScraper()
scraper.scrape_company('MRNA')
"
```

### Test Classification
```bash
python -c "
from core.categorizer import categorize_press_release
result = categorize_press_release(
    'Moderna Announces Phase 3 Trial Results',
    'Moderna today announced positive results from its Phase 3 clinical trial...'
)
print(result)
"
```

### Test Newsletter Generation
```bash
python core/newsletter_generator.py
```

---

## Sector-Specific Tips

### Biotech
- FDA calendar is predictable — set up alerts for PDUFA dates
- ClinicalTrials.gov has structured data you could integrate
- Phase transitions (1→2, 2→3) are major events

### Energy
- Production reports follow quarterly schedules
- Reserve updates are annual
- Consider integrating EIA data

### Fintech
- User/transaction metrics are key
- Regulatory approvals vary by jurisdiction
- Partnership announcements are frequent

### SaaS/Tech
- Focus on ARR, customer count, churn
- Product launches are major events
- Earnings calls matter more than press releases

---

## Testing Your Configuration

### Verify Company Matching
```bash
python -c "
from config.email_parser_config import COMPANY_DOMAINS
print(f'Configured {len(COMPANY_DOMAINS)} companies')
for domain, ticker in list(COMPANY_DOMAINS.items())[:5]:
    print(f'  {domain} → {ticker}')
"
```

### Verify Categories
```bash
python -c "
from config.categories import CATEGORIES
print('Categories:', CATEGORIES)
"
```

### Run Full Pipeline Test
```bash
python scripts/test_pipeline.py --company MRNA
```

---

## Common Issues

### "Company not matched"
- Add domain to `COMPANY_DOMAINS` in email_parser_config.py
- Check for typos in domain name

### "Scraping failed"
- Website may require JavaScript — enable Playwright fallback
- Check if selectors are correct
- Some sites block automated requests

### "Wrong category"
- Update the AI prompt with sector-specific context
- Add more example categories
- Check if category name matches exactly
