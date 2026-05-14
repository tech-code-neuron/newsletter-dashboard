# Parser Lambda - Function Index

**Purpose:** Quick reference for finding code in parser Lambda (avoid 30+ minute searches).

**Last Updated:** 2026-03-12

---

## Main Handler

### `lambda_handler(event, context)`
- **File:** `handler.py:45-120`
- **Purpose:** Main entry point, processes SQS events
- **Inputs:** SQS event (Records array)
- **Outputs:** Success/failure status
- **Calls:** `process_ses_email()`, `match_company_with_confidence()`, `route_press_release()`

---

## Company Matching

### `match_company_with_confidence(sender_email, sender_name, subject, body)`
- **File:** `company_matching.py:520-645`
- **Purpose:** Multi-signal confidence scoring for company matching
- **Signals:** Domain (90-100%), Exact Name (85%), Partial Name (65-75%), Historical (70-90%), Ticker (40-60%)
- **Returns:** `(company_id, confidence_score, match_type)`
- **Feature Flag:** `USE_CONFIDENCE_SCORING` env var

### `match_company_by_normalized_name(sender_name)`
- **File:** `company_matching.py:215-289`
- **Purpose:** GSI-based exact normalized name lookup
- **Returns:** Company record or None
- **Fast Path:** O(1) DynamoDB GSI query

### `match_company_by_domain(sender_email)`
- **File:** `company_matching.py:320-398`
- **Purpose:** Extract domain from email, lookup in DynamoDB
- **Returns:** Company record or None
- **Handles:** IR platforms (q4inc.com, q4ir.com, investis.com)

### `match_company_by_ticker_mention(subject, body)`
- **File:** `company_matching.py:450-518`
- **Purpose:** Search for ticker symbols in subject/body
- **Returns:** Company record or None
- **Pattern:** Uppercase ticker with parentheses or spaces

---

## Email Parsing

### `extract_urls_from_email(body_html)`
- **File:** `email_parsing.py:145-267`
- **Purpose:** Extract all URLs from HTML email body
- **Filters:** Removes unsubscribe, footer, social media links
- **Returns:** List of URL strings
- **Uses:** BeautifulSoup for HTML parsing

### `parse_email_metadata(ses_message)`
- **File:** `email_parsing.py:45-98`
- **Purpose:** Extract sender, subject, body from SES message
- **Returns:** `(sender_email, sender_name, subject, body_html, body_text)`
- **Handles:** Multipart emails, attachments

---

## Routing Logic

### `route_press_release(company, urls, email_metadata)`
- **File:** `routing.py:480-614`
- **Purpose:** Route to enricher (simple) vs playwright (JavaScript-rendered)
- **Decision:** Domain-based routing table
- **Enricher Route:** Static HTML sites (most REITs)
- **Playwright Route:** JavaScript-rendered investor sites (Ryman, Prologis, etc.)

### `queue_for_enricher(company, urls, email_metadata)`
- **File:** `routing.py:230-298`
- **Purpose:** Send job to enricher SQS queue
- **Payload:** Company ID, ticker, URLs, email metadata
- **Returns:** SQS message ID

### `queue_for_playwright_scraping(company, urls, email_metadata)`
- **File:** `routing.py:117-163`
- **Purpose:** Send job to playwright SQS queue
- **Payload:** Ticker, company name, email metadata
- **Returns:** SQS message ID

---

## Company-Specific Extraction

### `extract_realty_income_title(subject)`
- **File:** `routing.py:369-414`
- **Purpose:** Extract title from "Realty Income Announces..." format
- **Example:** "Realty Income Announces $700 Million..." → "$700 Million..."
- **Pattern:** Removes "Realty Income Announces " prefix
- **Status:** ✅ Code exists, ⚠️ NOT deployed in parser.zip

### `extract_prologis_title(subject)`
- **File:** `routing.py:420-450`
- **Purpose:** Extract title from Prologis email format
- **Pattern:** Custom parsing for Prologis-specific subjects

---

## RSS Feed Processing

### `fetch_rss_feed(company)`
- **File:** `rss_fetcher.py:45-118`
- **Purpose:** Fetch and parse RSS feed for company
- **Returns:** List of press release entries
- **Deduplication:** Checks DynamoDB before saving
- **Fast Path:** 70% of emails, <2s latency

### `sync_rss_feeds_for_all_companies()`
- **File:** `rss_fetcher.py:220-286`
- **Purpose:** Sync all RSS feeds on schedule (EventBridge trigger)
- **Coverage:** 30 companies (24% of total)
- **Batch Size:** 10 companies per invocation
- **Returns:** Count of new press releases found

### `parse_rss_entry(entry)`
- **File:** `rss_fetcher.py:125-189`
- **Purpose:** Extract title, URL, date from RSS entry
- **Handles:** Multiple RSS formats (Atom, RSS 2.0)
- **Returns:** `(title, url, published_date)`

---

## Idempotency

### `check_idempotency(message_id)`
- **File:** `idempotency.py:25-58`
- **Purpose:** Check if email already processed
- **Table:** `reit-newsletter-idempotency`
- **Key:** `idempotency_key` (NOT `id` - this was a bug)
- **Returns:** Boolean (True if already processed)

### `mark_as_processed(message_id, company_id)`
- **File:** `idempotency.py:62-95`
- **Purpose:** Mark email as processed
- **TTL:** 7 days
- **Attributes:** message_id, company_id, processed_at

---

## Confidence Scoring (New System)

### `DomainMatchSignal.calculate(sender_email, company)`
- **File:** `confidence_scoring.py:45-98`
- **Score:** 90-100% (exact domain), 95% (IR platform), 100% (third-party investor relations)
- **Logic:** Extracts domain, compares to company.ir_domain

### `ExactNameMatchSignal.calculate(sender_name, company)`
- **File:** `confidence_scoring.py:102-145`
- **Score:** 85%
- **Logic:** Normalized sender name == company.normalized_name

### `PartialNameMatchSignal.calculate(sender_name, company)`
- **File:** `confidence_scoring.py:148-210`
- **Score:** 65-75% (containment), 70% (word overlap)
- **Logic:** Fuzzy matching on normalized names

### `HistoricalPatternSignal.calculate(sender_email, company)`
- **File:** `confidence_scoring.py:214-268`
- **Score:** 70-90% based on past match frequency
- **Logic:** Queries historical matches from DynamoDB

### `TickerMentionSignal.calculate(subject, body, company)`
- **File:** `confidence_scoring.py:272-320`
- **Score:** 40-60% (ticker in subject), 40% (ticker in body)
- **Logic:** Searches for ticker symbol in text

---

## Utilities

### `normalize_company_name(name)`
- **File:** `company_matching.py:78-125`
- **Purpose:** Normalize company name for matching
- **Removes:** Inc., Corp., LLC, punctuation, extra whitespace
- **Returns:** Lowercase normalized string

### `extract_domain(email)`
- **File:** `company_matching.py:130-165`
- **Purpose:** Extract domain from email address
- **Handles:** IR platforms (maps to actual company domain)
- **Returns:** Domain string

### `is_press_release_url(url)`
- **File:** `routing.py:55-98`
- **Purpose:** Identify if URL is a press release
- **Patterns:** `/news/`, `/press-releases/`, `/investors/`
- **Returns:** Boolean

---

## Quick Lookup Guide

### "How do I find code for..."

**Company matching by email domain?**
→ `company_matching.py:320` (`match_company_by_domain()`)

**Company matching with confidence scores?**
→ `company_matching.py:520` (`match_company_with_confidence()`)

**Extracting URLs from email?**
→ `email_parsing.py:145` (`extract_urls_from_email()`)

**Routing to enricher vs playwright?**
→ `routing.py:480` (`route_press_release()`)

**Realty Income title extraction?**
→ `routing.py:369` (`extract_realty_income_title()`)

**RSS feed processing?**
→ `rss_fetcher.py:45` (`fetch_rss_feed()`)

**Idempotency checking?**
→ `idempotency.py:25` (`check_idempotency()`)

---

## File Organization

```
parser/
├── handler.py (main entry point, orchestration)
├── company_matching.py (all company matching logic)
├── routing.py (enricher/playwright routing + company-specific extraction)
├── email_parsing.py (URL extraction, metadata parsing)
├── rss_fetcher.py (RSS feed processing)
├── idempotency.py (deduplication)
├── confidence_scoring.py (multi-signal matching)
├── requirements.txt (dependencies)
└── FUNCTION_INDEX.md (this file)
```

---

## Common Tasks

### Add new company-specific extraction
1. Create function in `routing.py` (pattern: `extract_<company>_title()`)
2. Add to routing logic in `route_press_release()`
3. Update this index
4. Deploy with validation

### Add new confidence signal
1. Create class in `confidence_scoring.py` (extends `ConfidenceSignal`)
2. Implement `calculate()` method
3. Add to signal list in `match_company_with_confidence()`
4. Update this index
5. Deploy with validation

### Modify company matching logic
1. Edit `company_matching.py`
2. Update confidence scoring if needed
3. Test with: `python3 scripts/test_parser.py --search "Company Name"`
4. Validate: `python3 scripts/deploy_lambda.py parser --validate`
5. Deploy: `python3 scripts/deploy_lambda.py parser --deploy`

---

## Dependencies

```
requests==2.31.0
feedparser==6.0.10
beautifulsoup4==4.12.3
boto3==1.34.51
lxml==5.1.0
```

**Validation:** Package size should be >1.5MB with all dependencies.

---

## Testing

### Unit Tests (Planned)
- `tests/test_company_matching.py` - Company matching logic
- `tests/test_confidence_scoring.py` - Signal calculations
- `tests/test_routing.py` - Enricher vs Playwright routing

### Integration Tests
```bash
# Test with real email
python3 scripts/test_parser.py --search "Realty Income"

# Check CloudWatch logs
aws logs tail /aws/lambda/reit-newsletter-parser --follow
```

---

**Maintenance:** Update this index after:
- Adding new functions (add to relevant section)
- Refactoring file structure (update file paths)
- Major logic changes (update descriptions)
- Deployment (update "Status" notes)
