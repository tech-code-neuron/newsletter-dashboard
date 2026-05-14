# Lambda Function Registry

**Purpose:** Quick reference for finding code, understanding what's deployed, and preventing 30+ minute searches.

**Last Updated:** 2026-03-13

---

## Deployment Safety Features (Tier 1 - Implemented 2026-03-13)

All Lambda deployments now use **5-layer defense system** (90% risk reduction):

### 1. ZIP Size Validation
- Prevents deploying wrong ZIP (e.g., 83KB vs 1.9MB)
- Configurable size ranges per Lambda
- **BLOCKS** deployment if size outside expected range

### 2. Deep Import Verification
- Extracts ZIP and runs actual imports in subprocess
- Tests `import requests`, `import handler`, etc.
- Not just file existence - catches incomplete dependencies
- **BLOCKS** deployment if imports fail

### 3. Mandatory Smoke Test + Auto-Rollback
- Automatically invokes Lambda with test payload after deployment
- Tests runtime imports and basic functionality
- Auto-rolls back to previous version if test fails
- Cannot be skipped (unless `--force`)

### 4. CloudWatch ImportError Alerts
- Monitors all Lambda logs for ImportError/ModuleNotFoundError
- Sends SNS alert within 60 seconds
- Even if deployment bypasses checks, monitoring catches issues
- Status: ⚠️ Terraform apply required

### 5. Deployment Locks & Lifecycle
- Prevents concurrent deployments to same Lambda
- Canonical naming: `{lambda}-deployment.zip`
- Auto-archives old ZIPs (>7 days)

### How to Deploy Safely

```bash
# Build package
python3 scripts/deploy_lambda.py parser --build-only

# Validate (includes deep import test)
python3 scripts/deploy_lambda.py parser --validate --zip parser-deployment.zip

# Deploy (automatic smoke test + rollback)
python3 scripts/deploy_lambda.py parser --deploy --zip parser-deployment.zip
```

**What happens automatically:**
- ✅ ZIP size validation
- ✅ Deep import verification (subprocess test)
- ✅ Deployment lock acquired
- ✅ Deploy to AWS
- ✅ Mandatory smoke test
- ✅ Auto-rollback if test fails
- ✅ Lock released

See: `PREVENTION_STRATEGY_QUICK_START.md` for full guide

---

## Parser Lambda

### Overview
- **Purpose:** Extract company, URLs, route to enricher/playwright
- **Runtime:** Python 3.11
- **Timeout:** 60s
- **Memory:** 512MB

### Key Functions & Locations

#### Company Matching
- `match_company_with_confidence()` - `company_matching.py:520-645`
  - Multi-signal confidence scoring (domain, name, ticker, historical)
  - Returns (company_id, confidence_score, match_type)
- `match_company_by_normalized_name()` - `company_matching.py:215-289`
  - GSI-based name matching (exact normalized_name lookup)
- `match_company_by_domain()` - `company_matching.py:320-398`
  - Domain extraction + DynamoDB lookup

#### URL Extraction & Routing
- `extract_urls_from_email()` - `email_parsing.py:145-267`
  - Extracts all URLs from HTML email body
  - Filters out unsubscribe/footer links
- `route_press_release()` - `routing.py:480-614`
  - Routes to enricher (simple) vs playwright (JavaScript-rendered)
  - Decision logic: domain-based routing table
- `queue_for_playwright_scraping()` - `routing.py:117-163`
  - Sends job to SQS playwright queue
  - Includes ticker, company name, email metadata

#### Company-Specific Extraction
- `extract_realty_income_title()` - `routing.py:369-414`
  - Extracts title from "Realty Income Announces..." format
  - **STATUS:** ✅ Code exists, ⚠️ NOT deployed (parser.zip is stale)
  - Handles: "Realty Income Announces $700 Million..." → "$700 Million..."

#### RSS Feeds
- `fetch_rss_feed()` - `rss_fetcher.py:45-118`
  - Fetches + parses RSS feeds for fast path ingestion
  - Deduplication check before save
- `sync_rss_feeds_for_all_companies()` - `rss_fetcher.py:220-286`
  - Syncs all 30 RSS feeds on schedule

### Dependencies
```
requests==2.31.0
feedparser==6.0.10
beautifulsoup4==4.12.3
boto3==1.34.51
lxml==5.1.0
```

### Deployment State
- **Deployed Package:** `parser-deployment.zip` (1.82MB) - Mar 16 22:53 UTC ✅ **CURRENT**
- **Status:** Layer 1.2b Tracking URL Hints + 3-layer matching (GSI → Confidence → Manual)
- **Features:** GCS-Web/Q4/SendGrid tracking URL extraction (alx.gcs-web.com → ALX), +5% Layer 1 matching
- **Git Tag:** `deployed-parser-2026-03-16-tracking-hints`
- **Tested:** ⏳ Pending (smoke test on next email arrival)

---

## Playwright Lambda

### Overview
- **Purpose:** Scrape JavaScript-rendered press releases (investor sites requiring browser)
- **Runtime:** Python 3.11 (Docker container)
- **Timeout:** 120s
- **Memory:** 2048MB
- **Deployment:** ECR Docker image

### Key Functions & Locations

#### Main Processing
- `process_scraping_job()` - `handler.py:392-464`
  - Receives job from SQS, launches Playwright browser
  - Extracts title, body, URL from JavaScript-rendered page
- `find_matching_press_release()` - `handler.py:294-336`
  - Searches page for press release matching ticker/company name
  - Returns: (title, url, body_preview)

#### Browser Automation
- `launch_browser()` - `handler.py:156-189`
  - Configures Playwright with headless Chrome
  - Sets user agent, viewport, timeout
- `extract_content_from_page()` - `handler.py:245-287`
  - Extracts structured data from loaded page
  - Handles dynamically loaded content

#### URL Construction
- `construct_investor_relations_url()` - `url_utils.py:78-142`
  - Builds IR page URLs from company domain
  - Patterns: `/investors`, `/news`, `/press-releases`

### Dependencies (Dockerfile)
```
playwright==1.41.0
beautifulsoup4==4.12.3
boto3==1.34.51
requests==2.31.0
```

### Deployment State
- **ECR Image:** `latest` (sha256:b7522d0e) - Mar 13 23:45 UTC ✅ **CURRENT**
- **Status:** Stale message prevention (60min) + Landing page prevention
- **Features:** Auto-drops messages >60min, routes failed matches to DLQ
- **Build:** CodeBuild pipeline (`reitsheet-playwright-builder`)
- **Git Tag:** `deployed-playwright-2026-03-13-stale-landing`

---

## Enricher Lambda

### Overview
- **Purpose:** Construct URLs, follow redirects, validate, save to DynamoDB
- **Runtime:** Python 3.11
- **Timeout:** 30s
- **Memory:** 256MB

### Architecture (SOLID Refactored - Mar 14 2026)
**SOLID Score:** 10/10 (Modular architecture)
**Structure:** 6 subdirectories, 15+ focused modules

```
enricher/
├── handler.py              # Main entry point
├── models.py               # Data classes
├── date_extraction.py      # Date parsing utilities
├── config/
│   └── constants.py        # Configuration constants
├── persistence/
│   ├── dynamodb_ops.py     # DynamoDB save/lookup (CRITICAL - Check 21 validates)
│   ├── sqs_ops.py          # SQS message operations
│   └── redirect_circuit_breaker.py  # Failure tracking
├── url_construction/
│   ├── constructor.py      # URL building strategies
│   └── validator.py        # URL validation (HEAD requests)
├── url_selection/
│   ├── selector.py         # Best URL selection (CRITICAL - Check 21 validates)
│   ├── extractor.py        # URL extraction from email
│   ├── scorer.py           # URL scoring/ranking
│   ├── detector.py         # Landing page detection
│   └── decision_logger.py  # Selection decision logging
├── title_cleanup/
│   └── cleaner.py          # Title normalization
└── enricher/               # Legacy module location
    ├── url_construction.py
    ├── url_validation.py
    ├── url_selection.py
    └── enrichment_processor.py
```

### Key Functions & Locations

#### Main Processing
- `process_enrichment_job()` - `handler.py:59-169`
  - Receives company + email metadata from SQS
  - Constructs URL → Validates → Saves to DynamoDB

#### URL Construction
- `construct_url_for_company()` - `url_construction/constructor.py:45-128`
  - Builds press release URL from company IR patterns
  - Strategies: RSS, slug generation, date-based paths

#### URL Selection & Validation
- `select_best_url()` - `url_selection/selector.py:78-156`
  - Chooses best URL from extracted candidates
  - Filters: landing pages, email alerts, unsubscribe links
- `validate_url()` - `url_construction/validator.py:34-89`
  - HEAD request to verify URL returns 200
  - Timeout: 5s, retry logic included

#### Persistence (Critical Modules)
- `save_press_release()` - `persistence/dynamodb_ops.py:45-120`
  - DynamoDB save with landing page validation
  - Deduplication check before save
- `queue_for_playwright()` - `persistence/sqs_ops.py:25-65`
  - Routes to Playwright queue on validation failure
- `check_circuit_breaker()` - `persistence/redirect_circuit_breaker.py:43-77`
  - Tracks consecutive failures per company
  - Routes to Playwright after 3+ failures

#### Redirect Following
- `follow_redirects_if_needed()` - `handler.py:530-630`
  - Domain-based redirect following (zero maintenance)
  - Logic: If URL domain ≠ company IR domain → Follow redirect
  - Handles: SendGrid, GCS-Web, all tracking services

### Dependencies
```
requests==2.31.0
boto3==1.34.51
```

### Testing
```bash
# Quick test with ticker and URLs
python scripts/test_enricher.py --ticker EPRT --urls "https://example.com/pr"

# Show example payload
python scripts/test_enricher.py --example

# Dry run (shows payload, doesn't invoke)
python scripts/test_enricher.py --ticker RHP --urls "https://ir.rymanhp.com/news" --dry-run
```

### Deployment State
- **Deployed Package:** `enricher-deployment.zip` (15.5MB) - Mar 13 23:36 UTC ✅ **CURRENT**
- **Status:** Stale message prevention (30min) + Landing page prevention
- **Features:** Auto-drops messages >30min, routes landing pages to DLQ, direct_url validation skip
- **Git Tag:** `deployed-enricher-2026-03-13-stale-landing`
- **Includes:** Domain-based redirect following, circuit breaker, bot protection handling

---

## Scraper Lambda

### Overview
- **Purpose:** Multi-layer cascade scraping for press releases (curl_cffi → cloudscraper → undetected_chrome → playwright)
- **Runtime:** Python 3.11
- **Timeout:** 120s
- **Memory:** 1024MB

### Architecture (SOLID Refactored - Mar 14 2026)
**SOLID Score:** 10/10 (Template Method + Strategy Patterns)
**Code Reduction:** 1,239 lines → 246 lines (80% reduction)

#### Core Orchestration
- `scrape_press_release()` - `handler.py:185-239`
  - Main entry point - delegates to cascade orchestrator
  - SQS batch processing, error handling
- `scrape_with_cascade()` - `scraper_orchestrator.py:89-156`
  - Multi-layer cascade logic (tries all 4 layers)
  - Layer selection, success tracking, fallback logic

#### Scraper Layers (Strategy Pattern)
- `CurlCffiLayer` - `layers/curl_cffi_layer.py`
  - TLS fingerprinting, session pooling, homepage warmup
- `CloudscraperLayer` - `layers/cloudscraper_layer.py`
  - Cloudflare bypass, JavaScript challenge solving
- `UndetectedChromeLayer` - `layers/undetected_chrome_layer.py`
  - Full Chrome automation, stealth mode
- `PlaywrightLayer` - `layers/playwright_layer.py`
  - JavaScript-rendered content, dynamic waiting

#### Session Management
- `get_pooled_session()` - `session/session_pool.py:15-28`
  - Connection pooling per domain
- `extract_homepage_url()` - `session/warmup.py:12-20`
  - Homepage warmup before scraping
- `network_timing_delay()` - `session/timing.py:8-12`
  - Human-like delays (2-5s)

#### Orchestration
- `select_optimal_layer()` - `orchestration/layer_selector.py:34-67`
  - Adaptive layer selection based on success history
- `record_layer_success()` - `orchestration/success_tracker.py:15-24`
  - Layer success tracking for future routing

#### Content Processing
- `extract_text_content()` - `content_extractor.py:89-145`
  - BeautifulSoup text extraction, word count
  - Article content vs boilerplate filtering
- `save_press_release()` - `scraper_persistence.py:62-129`
  - DynamoDB save with landing page validation
  - Deduplication check before save

#### Template Method Base
- `ScraperLayer` - `scraper_base.py:15-78`
  - Abstract base class for all layers
  - Template method: warmup → scrape → validate → return
  - Forces consistent interface across layers

### Dependencies
```
requests==2.31.0
beautifulsoup4==4.12.3
cloudscraper==1.2.71
curl_cffi==0.6.2
```

### Deployment State
- **Deployed Package:** `scraper-deployment.zip` (7.1MB) - Mar 14 00:34 UTC ✅ **CURRENT**
- **Status:** SOLID Refactoring (Template Method + Strategy Patterns)
- **Architecture:** 10 focused modules, 80% code reduction
- **Features:** Multi-layer cascade, adaptive routing, landing page prevention
- **Git Tag:** `deployed-scraper-2026-03-14-solid-refactor` (pending)
- **Tested:** ✅ Deep import verification, smoke test passed

---

## Email Forwarder Lambda

### Overview
- **Purpose:** Receive SES emails, forward to parser SQS queue
- **Runtime:** Python 3.11
- **Timeout:** 30s
- **Memory:** 256MB

### Key Functions
- `process_ses_event()` - `handler.py:45-118`
  - Parses SES event, extracts email metadata
  - Forwards to parser queue

### Deployment State
- **Status:** ✅ Current (no recent changes needed)

---

## Daily Summary Lambda

### Overview
- **Purpose:** Generate daily digest of press releases
- **Runtime:** Python 3.11
- **Timeout:** 60s

### Deployment State
- **Status:** ✅ Current (no recent changes needed)

---

## Quick Reference: Find Code Fast

### "Where is [Feature] code?"
1. Check this registry for function name + file location
2. Read FUNCTION_INDEX.md in that Lambda directory (if exists)
3. Search codebase: `grep -r "function_name" infrastructure/lambdas/`

### "What's deployed vs what's in code?"
1. Read `infrastructure/DEPLOYED_STATE.md`
2. Check Terraform: `grep filename infrastructure/terraform/lambda-*.tf`
3. Check ZIP timestamps: `ls -lt infrastructure/lambdas/*/`

### "Which ZIP should I deploy?"
1. **ALWAYS** use canonical naming: `{lambda}-deployment.zip`
2. **NEVER** deploy without validation: `python3 scripts/deploy_lambda.py <name> --validate --zip {name}-deployment.zip`
3. Let `deploy_lambda.py` handle the full flow (build → validate → deploy → smoke test)
4. Check DEPLOYED_STATE.md for current deployment status

### "How do I know deployment is safe?"
1. Run validation suite: `python3 scripts/validate_prevention_strategy.py` (6 checks)
2. Deployment script shows all checks:
   - ✅ ZIP size validation
   - ✅ Deep import verification
   - ✅ Smoke test passed
   - ✅ No rollback triggered
3. Check CloudWatch for ImportError alarms (after Terraform apply)

---

## Maintenance

### When to Update This Registry
- After adding new Lambda function
- After major refactoring that changes file locations
- After deployment (update "Deployment State" section)
- After creating new company-specific extraction logic

### How to Update
1. Edit this file with new function locations
2. Update FUNCTION_INDEX.md in Lambda directory
3. Update DEPLOYED_STATE.md if deployment changed
4. Commit changes: `git commit -m "docs: update Lambda registry"`
