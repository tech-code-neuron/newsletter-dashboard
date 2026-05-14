# Infrastructure Scripts

Utility scripts for managing AWS infrastructure.

## Scripts

### update_scraper_types.py

Updates company configurations with appropriate `scraper_type` field.

**Purpose:** Classify companies by scraping method to optimize costs

**Usage:**
```bash
python infrastructure/scripts/update_scraper_types.py
```

**Output:**
- Updates all companies in `reitsheet-companies-config` DynamoDB table
- Sets `scraper_type` to: `simple_http`, `playwright`, or `api`
- Prints distribution summary

**SOLID Compliance:**
- Single Responsibility: Only updates scraper_type field
- Open/Closed: Add companies to sets (no code changes)
- Data-Driven: Company classifications in simple sets

---

### validate_scraper_split_savings.py

Validates cost savings from splitting monolithic scraper into specialized scrapers.

**Purpose:** Ensure scraper split achieves expected cost reduction (>70%)

**Usage:**
```bash
python infrastructure/scripts/validate_scraper_split_savings.py
```

**Output:**
- Company distribution by scraper type
- Current vs optimized monthly costs
- Projected costs at 1000 companies
- Validation: PASS/FAIL based on 70% savings threshold

**Exit Codes:**
- `0` - Validation passed (≥70% savings)
- `1` - Validation failed or error

**SOLID Compliance:**
- Single Responsibility: calculate_costs() and validate_savings() separate
- No Hardcoded Values: All costs/thresholds in constants
- Data-Driven: Reads actual distribution from DynamoDB

---

## Expected Results

**Company Distribution (127 companies):**
- Simple HTTP: ~114 companies (90%)
- Playwright: ~10 companies (8%)
- API: ~3 companies (2%)

**Cost Savings:**
- Current: $12.70/month (all use expensive Playwright)
- Optimized: $2.50/month (90% use cheap simple scraper)
- **Savings: $10.20/month (80% reduction)**

**At 1000 companies:**
- Savings: **$88/month**

---

## Prerequisites

- AWS credentials configured (`~/.aws/credentials`)
- Python 3.11+
- boto3 installed

---

## Troubleshooting

**Error: Table does not exist**
- Ensure `reitsheet-companies-config` table is deployed
- Run `terraform apply` first

**Error: No companies found**
- Sync companies to DynamoDB first
- See `scripts/sync_companies_to_dynamodb.py`

**Validation fails (<70% savings)**
- Check company distribution (need 90%+ simple_http)
- Verify scraper_type assignments are correct
