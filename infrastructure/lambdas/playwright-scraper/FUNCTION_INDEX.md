# Playwright Lambda - Function Index

**Purpose:** Quick reference for finding code in playwright scraper Lambda.

**Last Updated:** 2026-03-13

---

## Main Handler

### `lambda_handler(event, context)`
- **File:** `handler.py:45-98`
- **Purpose:** Main entry point, processes SQS scraping jobs
- **Inputs:** SQS event (job from parser with ticker, company name)
- **Outputs:** Press release data saved to DynamoDB
- **Calls:** `process_scraping_job()`, `launch_browser()`, `find_matching_press_release()`

---

## Core Processing

### `process_scraping_job(job)`
- **File:** `handler.py:392-464`
- **Purpose:** Main orchestration - launch browser, find press release, extract content
- **Flow:** Launch browser → Navigate to IR page → Find matching PR → Extract title/body/URL → Save to DynamoDB
- **Returns:** Press release data or None if not found
- **Timeout:** 120s (Lambda timeout)

### `find_matching_press_release(page, ticker, company_name)`
- **File:** `handler.py:294-336`
- **Purpose:** Search page for press release matching ticker/company name
- **Strategy:** Looks for links containing ticker or company name keywords
- **Returns:** `(title, url, body_preview)` or None
- **Handles:** Dynamic content (waits for page load)

---

## Browser Automation

### `launch_browser()`
- **File:** `handler.py:156-189`
- **Purpose:** Configure and launch Playwright browser
- **Config:**
  - Headless Chrome
  - User agent: Mozilla/5.0 (realistic browser)
  - Viewport: 1280x720
  - Timeout: 30s per page load
- **Returns:** Browser instance
- **Cleanup:** Auto-closes browser on function exit

### `navigate_to_investor_page(browser, company_domain)`
- **File:** `handler.py:195-245`
- **Purpose:** Navigate to company's investor relations page
- **Patterns Tried:**
  1. `/investors/news`
  2. `/press-releases`
  3. `/newsroom`
  4. `/media`
- **Returns:** Page object or None if all patterns fail
- **Timeout:** 10s per pattern attempt

---

## Content Extraction

### `extract_content_from_page(page, url)`
- **File:** `handler.py:245-287`
- **Purpose:** Extract structured data from loaded press release page
- **Extracts:**
  - Title (h1, .title, article title)
  - Body (article content, .content, main text)
  - URL (canonical URL)
- **Returns:** `(title, body, url)`
- **Handles:** Dynamically loaded content (waits for selectors)

### `extract_title(page)`
- **File:** `handler.py:340-378`
- **Purpose:** Extract press release title from page
- **Selectors Tried:**
  1. `h1` tag
  2. `.press-release-title`
  3. `article h1`
  4. `.article-title`
- **Fallback:** Page title (document.title)
- **Returns:** Title string or "Unknown Title"

### `extract_body_preview(page)`
- **File:** `handler.py:382-420`
- **Purpose:** Extract first 500 characters of press release body
- **Selectors Tried:**
  1. `article` tag
  2. `.press-release-content`
  3. `.article-body`
  4. `main` tag
- **Returns:** Body preview (first 500 chars) or empty string

---

## URL Construction

### `construct_investor_relations_url(company_domain)`
- **File:** `url_utils.py:78-142`
- **Purpose:** Build IR page URL from company domain
- **Patterns:**
  - `https://{domain}/investors`
  - `https://{domain}/news`
  - `https://{domain}/press-releases`
  - `https://ir.{domain}/news-releases`
- **Returns:** List of possible URLs to try
- **Used By:** `navigate_to_investor_page()`

### `is_investor_relations_url(url)`
- **File:** `url_utils.py:45-72`
- **Purpose:** Verify if URL is an investor relations page
- **Patterns:** `/investors`, `/ir/`, `/news`, `/press`
- **Returns:** Boolean

---

## Database Operations

### `save_press_release_to_dynamodb(company_id, title, url, body)`
- **File:** `handler.py:468-520`
- **Purpose:** Save scraped press release to DynamoDB
- **Table:** `reit-newsletter-press-releases`
- **Attributes:**
  - company_id (partition key)
  - press_release_id (UUID, sort key)
  - title
  - url
  - body_preview
  - scraped_at (ISO timestamp)
  - source = "playwright"
- **Deduplication:** Checks if URL already exists before saving
- **Returns:** Press release ID or None if duplicate

---

## Error Handling

### `handle_playwright_timeout(error, context)`
- **File:** `handler.py:525-565`
- **Purpose:** Handle timeout errors gracefully
- **Actions:**
  - Log timeout details (page, selector, duration)
  - Take screenshot (saved to /tmp/)
  - Return partial data if available
- **Returns:** Partial results or None

### `handle_navigation_error(error, url)`
- **File:** `handler.py:570-598`
- **Purpose:** Handle navigation failures (404, timeout, DNS)
- **Actions:**
  - Log error details
  - Try alternative URL patterns
  - Fall back to simple scraper if all patterns fail
- **Returns:** Success boolean

---

## Company-Specific Overrides

### `get_custom_selectors_for_company(company_domain)`
- **File:** `company_overrides.py:25-98`
- **Purpose:** Company-specific CSS selectors for tricky sites
- **Examples:**
  - Ryman: `.press-release-container h1`, `.press-release-body`
  - Prologis: `.news-article-title`, `.news-article-content`
- **Returns:** Dictionary of selectors or None

### `apply_company_overrides(page, company_domain)`
- **File:** `company_overrides.py:102-145`
- **Purpose:** Apply custom scraping logic for specific companies
- **Actions:** Custom wait conditions, JavaScript execution, etc.
- **Returns:** Modified page object

---

## Quick Lookup Guide

### "How do I find code for..."

**Launching Playwright browser?**
→ `handler.py:156` (`launch_browser()`)

**Finding press release on page?**
→ `handler.py:294` (`find_matching_press_release()`)

**Extracting title from page?**
→ `handler.py:340` (`extract_title()`)

**Extracting body from page?**
→ `handler.py:382` (`extract_body_preview()`)

**Saving to DynamoDB?**
→ `handler.py:468` (`save_press_release_to_dynamodb()`)

**Handling timeouts?**
→ `handler.py:525` (`handle_playwright_timeout()`)

**Company-specific selectors?**
→ `company_overrides.py:25` (`get_custom_selectors_for_company()`)

---

## File Organization

```
playwright-scraper/
├── handler.py (main entry point, browser automation, extraction)
├── url_utils.py (URL construction, validation)
├── company_overrides.py (company-specific scraping logic)
├── Dockerfile (container definition)
├── requirements.txt (dependencies)
└── FUNCTION_INDEX.md (this file)
```

---

## Common Tasks

### Add new company-specific scraping logic
1. Edit `company_overrides.py`
2. Add selectors to `get_custom_selectors_for_company()`
3. Test with: `python3 scripts/test_playwright.py --url "https://ir.company.com"`
4. Build Docker image: `docker build -t playwright-scraper .`
5. Push to ECR: `docker push <ecr-repo>/playwright-scraper:latest`
6. Update DEPLOYED_STATE.md

### Modify extraction selectors
1. Edit `handler.py` (`extract_title()` or `extract_body_preview()`)
2. Add new selectors to try
3. Test with real company page
4. Build + push Docker image

### Debug timeout issues
1. Check CloudWatch logs: `aws logs tail /aws/lambda/reit-newsletter-playwright --follow`
2. Look for timeout context (page, selector)
3. Screenshots saved to /tmp/ (check Lambda logs)
4. Add custom selectors in `company_overrides.py`

---

## Dependencies (Dockerfile)

```
playwright==1.41.0
beautifulsoup4==4.12.3
boto3==1.34.51
requests==2.31.0
```

**Playwright Browser:** Chromium (installed via Playwright)

**Container Size:** ~1.5GB (includes Chromium dependencies)

---

## Deployment

### Build Docker Image
```bash
cd infrastructure/lambdas/playwright-scraper
docker build -t playwright-scraper .
```

### Test Locally
```bash
docker run -e AWS_ACCESS_KEY_ID=xxx -e AWS_SECRET_ACCESS_KEY=yyy \
  playwright-scraper \
  '{"Records":[{"body":"{\"ticker\":\"RHP\",\"company_name\":\"Ryman Hospitality\"}"}]}'
```

### Push to ECR
```bash
# Tag for ECR
docker tag playwright-scraper:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/reit-newsletter-playwright:latest

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Push
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/reit-newsletter-playwright:latest
```

### Verify Deployment
```bash
# Check Lambda points to latest image
aws lambda get-function --function-name reit-newsletter-playwright --query 'Code.ImageUri'

# Smoke test
python3 scripts/test_playwright.py --url "https://ir.rymanhp.com"
```

---

## Testing

### Integration Tests
```bash
# Test with Ryman (known JavaScript-rendered site)
python3 scripts/test_playwright.py --url "https://ir.rymanhp.com" --ticker "RHP"

# Check CloudWatch logs
aws logs tail /aws/lambda/reit-newsletter-playwright --follow
```

### Manual Testing (Docker)
```bash
# Run locally with test payload
docker run -e AWS_ACCESS_KEY_ID=xxx playwright-scraper \
  '{"Records":[{"body":"{\"ticker\":\"RHP\",\"company_name\":\"Ryman\"}"}]}'
```

---

## Performance

- **Average Execution Time:** 15-30s (browser launch + page load + extraction)
- **Memory Usage:** 1024-2048MB (Chromium is heavy)
- **Timeout:** 120s (Lambda max timeout)
- **Cold Start:** 10-15s (Docker container init)

**Optimization Ideas:**
- Pre-warm browser instances (not implemented)
- Cache browser binaries (Docker layer caching)
- Reduce screenshot resolution (smaller /tmp/ usage)

---

## Known Issues

### Issue 1: Some sites block headless browsers
**Impact:** Navigation fails with 403/bot detection
**Workaround:** Set realistic user agent, viewport size
**Long-term:** Add stealth plugin to Playwright

### Issue 2: Dynamic content takes >30s to load
**Impact:** Timeout before content appears
**Workaround:** Increase wait timeout for specific selectors
**Long-term:** Add retry logic with exponential backoff

---

**Maintenance:** Update this index after:
- Adding new extraction selectors
- Adding company-specific overrides
- Refactoring browser automation logic
- Deployment changes
