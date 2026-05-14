"""
DEPRECATED - DO NOT USE
========================

This file is a backup from the March 2026 SOLID refactoring.
The active handler is handler.py (Terraform: handler.lambda_handler).

Kept for rollback reference only.

DELETION SCHEDULED: 2026-05-01

---
Original docstring:

Press Release Pipeline - URL Enricher Lambda
=================================
Purpose: Construct and validate press release URLs
Triggered by: SQS Enrichment Queue

Single Responsibility: ONLY URL enrichment (construction + validation)
This Lambda was split from Parser for performance and SOLID compliance

Flow:
  1. Receive enrichment job from Parser
  2. Construct URL using company-specific method
  3. Validate constructed URL (HTTP HEAD request)
  4. Route: Valid URL → DynamoDB, Invalid URL → Scrape Queue

SOLID Principles:
- Single Responsibility: Parser parses, Enricher enriches
- Open/Closed: Add URL methods via strategy pattern
- No Hardcoded Values: All constants defined
- Strategy Pattern: URL construction methods
- Dependency Injection: Testable components

Last Updated: 2026-03-09
"""

import json
import logging
import boto3
import os
import requests
import re
from datetime import datetime
from urllib.parse import urlparse

# ============================================================================
# AWS Clients Initialization
# ============================================================================

s3 = boto3.client('s3')
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# ============================================================================
# Environment Variables
# ============================================================================

SCRAPE_QUEUE_URL = os.environ['SCRAPE_QUEUE_URL']
PLAYWRIGHT_QUEUE_URL = os.environ.get('PLAYWRIGHT_QUEUE_URL', '')
REIT_NEWS_TABLE = os.environ['REIT_NEWS_TABLE']
COMPANIES_TABLE = os.environ['COMPANIES_TABLE']
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# ============================================================================
# DynamoDB Tables
# ============================================================================

reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)
companies_table = dynamodb.Table(COMPANIES_TABLE)

# ============================================================================
# Logging Configuration
# ============================================================================

logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# ============================================================================
# Constants - Single Source of Truth
# ============================================================================

# Timeouts
URL_VALIDATION_TIMEOUT = 5  # HTTP HEAD request timeout (seconds)
REDIRECT_TIMEOUT = 10  # Redirect following timeout (seconds)

# Limits
MAX_REDIRECTS = 5  # Maximum redirect chain length

# GCS URL Construction
GCS_URL_PATH_TEMPLATE = '/news-releases/news-release-details/'
GCS_SLUG_WORD_COUNT = 7  # Standard GCS slug length
GCS_SLUG_WORD_COUNT_LONG = 9  # Extended slug for some companies

# Newswire domains (require scraping)
NEWSWIRE_DOMAINS = {
    'globenewswire.com',
    'businesswire.com',
    'prnewswire.com',
    'accesswire.com',
    'prnews.com',
    'marketwired.com'
}

# HTTP Status Codes
HTTP_STATUS_OK = 200
HTTP_STATUS_REDIRECT = 301
HTTP_STATUS_TEMP_REDIRECT = 302
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404

# User Agent
USER_AGENT = 'Mozilla/5.0 (compatible; PressReleasePipeline/1.0; +https://your-domain.com)'

# URL Selection - Landing Page Detection
GENERIC_PAGE_SEGMENTS = {
    'news-releases', 'news', 'press-releases',
    'news-and-events', 'investors', 'press-room',
    'media', 'newsroom', 'investor-relations'
}

# URL Selection - Subject Line Noise Words
SUBJECT_NOISE_WORDS = {
    'the', 'of', 'and', 'to', 'a', 'an', 'in', 'for', 'on',
    'announces', 'reports', 'releases', 'inc', 'corp', 'corporation',
    'company', 'companies', 'press', 'release', 'news'
}


# ============================================================================
# URL Construction - Strategy Pattern
# ============================================================================


def create_slug_from_subject(subject, word_count=GCS_SLUG_WORD_COUNT):
    """
    Create URL slug from email subject

    Single Responsibility: Only creates slug

    Example:
        "Essential Properties: Announces Dividend" → "essential-properties-announces-dividend"

    Args:
        subject: Email subject line
        word_count: Number of words to include in slug

    Returns:
        str: URL slug (lowercase, hyphenated)
    """
    import re

    if not subject:
        return ""

    # Remove common prefixes/noise
    clean = subject.lower()
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', clean)

    # Extract first N words
    words = re.findall(r'\b[a-z0-9]+\b', clean)
    slug_words = words[:word_count]

    # Join with hyphens
    slug = '-'.join(slug_words)

    return slug


def create_gcs_url(subject, ir_domain, word_count=GCS_SLUG_WORD_COUNT):
    """
    Create GCS-hosted press release URL

    Single Responsibility: Only constructs GCS URLs

    Pattern: https://{domain}/news-releases/news-release-details/{slug}

    Args:
        subject: Email subject line
        ir_domain: Company IR domain (e.g., "chatham.gcs-web.com")
        word_count: Slug word count (7 or 9)

    Returns:
        str: Constructed URL or None
    """
    if not subject or not ir_domain:
        return None

    slug = create_slug_from_subject(subject, word_count=word_count)
    if not slug:
        return None

    url = f"https://{ir_domain}{GCS_URL_PATH_TEMPLATE}{slug}"

    logger.debug(f"GCS URL constructed: {url}")
    return url


def create_brixmor_aspx_url(subject, ir_domain, email_date=None):
    """
    Create Brixmor-style ASPX URL

    Single Responsibility: Only constructs Brixmor ASPX URLs

    Pattern: https://{domain}/{Slug}/default.aspx
    Note: Slug is CASE-SENSITIVE (preserves capitalization)

    Args:
        subject: Email subject line (PRESERVES CASE)
        ir_domain: Company IR domain
        email_date: Optional email date (unused but accepted for interface compatibility)

    Returns:
        str: Constructed URL or None
    """
    import re

    if not subject or not ir_domain:
        return None

    # Clean subject but PRESERVE CASE
    clean = subject
    clean = re.sub(r'^(re:|fwd?:|fw:)\s*', '', clean, flags=re.IGNORECASE)

    # Extract words (preserve case, remove punctuation)
    words = re.findall(r'\b[A-Za-z0-9]+\b', clean)
    slug_words = words[:GCS_SLUG_WORD_COUNT]

    # Join with hyphens (CASE PRESERVED)
    slug = '-'.join(slug_words)

    url = f"https://{ir_domain}/{slug}/default.aspx"

    logger.debug(f"Brixmor ASPX URL constructed: {url}")
    return url


def create_terreno_aspx_url(subject, ir_domain, email_date=None):
    """
    Create Terreno-style ASPX URL

    Single Responsibility: Only constructs Terreno ASPX URLs

    Pattern: https://{domain}/{slug}/newsdetail.aspx

    Args:
        subject: Email subject line
        ir_domain: Company IR domain
        email_date: Optional email date (unused but accepted for interface compatibility)

    Returns:
        str: Constructed URL or None
    """
    if not subject or not ir_domain:
        return None

    slug = create_slug_from_subject(subject, word_count=GCS_SLUG_WORD_COUNT)
    if not slug:
        return None

    url = f"https://{ir_domain}/{slug}/newsdetail.aspx"

    logger.debug(f"Terreno ASPX URL constructed: {url}")
    return url


# URL Construction Strategy Router (Strategy Pattern)
URL_CONSTRUCTION_STRATEGIES = {
    'gcs_hosted': lambda subject, domain, date=None: create_gcs_url(subject, domain, GCS_SLUG_WORD_COUNT),
    'gcs_custom_domain': lambda subject, domain, date=None: create_gcs_url(subject, domain, GCS_SLUG_WORD_COUNT),
    'gcs_9_word_slug': lambda subject, domain, date=None: create_gcs_url(subject, domain, GCS_SLUG_WORD_COUNT_LONG),
    'brixmor_aspx': create_brixmor_aspx_url,
    'terreno_aspx': create_terreno_aspx_url,
}


def construct_url_for_company(company, email_subject, email_date=None):
    """
    Construct URL using company-specific method

    Single Responsibility: Orchestrates URL construction

    Strategy Pattern: Routes to appropriate construction method

    Args:
        company: Company dictionary from DynamoDB
        email_subject: Email subject line
        email_date: Optional email date

    Returns:
        tuple: (url, method_used) or (None, None)
    """
    ticker = company.get('ticker', 'UNKNOWN')
    ir_domain = company.get('ir_domain')
    method = company.get('url_construction_method')

    if not ir_domain:
        logger.warning(f"No IR domain for {ticker}")
        return None, None

    if not method or method == 'direct_url':
        logger.debug(f"No URL construction method for {ticker}")
        return None, None

    # Strategy Pattern: O(1) lookup instead of if-elif chain
    strategy = URL_CONSTRUCTION_STRATEGIES.get(method)

    if not strategy:
        logger.warning(f"Unknown construction method: {method} for {ticker}")
        return None, None

    try:
        url = strategy(email_subject, ir_domain, email_date)
        return url, method
    except Exception as e:
        logger.error(f"Error constructing URL for {ticker} using {method}: {e}")
        return None, None


# ============================================================================
# URL Validation
# ============================================================================


def validate_url_exists(url):
    """
    Validate URL is accessible (HTTP 200)

    Single Responsibility: Only validates URLs

    Uses HTTP HEAD request for efficiency (no body download)

    Args:
        url: URL to validate

    Returns:
        tuple: (is_valid, final_url, status_code)
    """
    try:
        response = requests.head(
            url,
            timeout=URL_VALIDATION_TIMEOUT,
            allow_redirects=True,
            headers={'User-Agent': USER_AGENT}
        )

        final_url = response.url if response.history else url
        is_valid = response.status_code == HTTP_STATUS_OK

        logger.debug(f"URL validation: {status_code} for {url[:60]}...")
        return is_valid, final_url, response.status_code

    except requests.Timeout:
        logger.warning(f"URL validation timeout: {url[:60]}...")
        return False, url, 0
    except Exception as e:
        logger.warning(f"URL validation failed: {e}")
        return False, url, 0


# ============================================================================
# Database Operations
# ============================================================================


def save_to_dynamodb(url, metadata):
    """
    Save press release to DynamoDB

    Single Responsibility: Only saves to database

    Args:
        url: Press release URL
        metadata: Metadata dict (ticker, subject, idempotency_key, etc.)

    Returns:
        bool: Success
    """
    ticker = metadata.get('ticker', 'UNKNOWN')

    # Check if URL already exists for this ticker (deduplication)
    if url_exists_for_ticker(url, ticker):
        logger.info(f"Skipping duplicate URL: {ticker} - {url[:60]}...")
        return True  # Return success (not an error, just already saved)

    try:
        item = {
            'press_release_id': metadata['idempotency_key'],
            'ticker': metadata.get('ticker', 'UNKNOWN'),
            'title': metadata.get('subject', ''),
            'url': url,
            'first_seen_at': datetime.utcnow().isoformat(),
            'source': 'enricher_validated',
            'needs_scraping': False,
            'construction_method': metadata.get('construction_method', 'unknown')
        }

        reit_news_table.put_item(Item=item)

        logger.info(f"✓ Saved to DynamoDB: {metadata.get('ticker')} - {url[:60]}...")
        return True

    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {e}", exc_info=True)
        return False


def url_exists_for_ticker(url, ticker):
    """
    Check if URL already exists for this ticker in DynamoDB

    Single Responsibility: Only checks for URL existence

    Prevents duplicate URLs from being saved multiple times
    (e.g., BRX saved 6x, CLDT saved 9x - fixes 78% duplicate issue)

    Uses GSI ticker-url-index for O(1) lookup.
    Falls back gracefully if GSI doesn't exist.

    Args:
        url: Press release URL
        ticker: Company ticker symbol

    Returns:
        bool: True if URL already exists for ticker, False otherwise
    """
    try:
        # Query by ticker and URL (requires GSI: ticker-url-index)
        response = reit_news_table.query(
            IndexName='ticker-url-index',
            KeyConditionExpression='ticker = :ticker AND #url = :url',
            ExpressionAttributeNames={'#url': 'url'},  # 'url' is reserved word
            ExpressionAttributeValues={
                ':ticker': ticker,
                ':url': url
            },
            Limit=1
        )

        exists = len(response.get('Items', [])) > 0

        if exists:
            logger.info(f"Duplicate URL detected: {ticker} - {url[:60]}... (skipping)")

        return exists

    except Exception as e:
        # If GSI doesn't exist, fall back to allowing save
        logger.warning(f"Error checking URL existence (GSI may not exist): {e}")
        return False  # Safe default: allow save


# ============================================================================
# Queue Operations
# ============================================================================


def queue_for_scraping(url, metadata):
    """
    Queue URL for scraping

    Single Responsibility: Only queues messages

    Args:
        url: URL to scrape
        metadata: Metadata dict

    Returns:
        bool: Success
    """
    try:
        message = {
            'url': url,
            'ticker': metadata.get('ticker', 'UNKNOWN'),
            'email_subject': metadata.get('subject', ''),
            'idempotency_key': metadata['idempotency_key'],
            'queued_at': datetime.utcnow().isoformat()
        }

        response = sqs.send_message(
            QueueUrl=SCRAPE_QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        logger.info(f"✓ Queued for scraping: {url[:60]}... (MessageId: {response['MessageId']})")
        return True

    except Exception as e:
        logger.error(f"Error queuing for scraping: {e}", exc_info=True)
        return False


# ============================================================================
# URL Classification
# ============================================================================


def classify_url(url):
    """
    Classify URL type

    Single Responsibility: Only classifies URLs

    Args:
        url: URL to classify

    Returns:
        str: 'newswire', 'direct', or 'unknown'
    """
    domain = urlparse(url).netloc.lower()

    # Remove www. prefix for consistent matching
    domain = domain.replace('www.', '')

    if any(nw in domain for nw in NEWSWIRE_DOMAINS):
        return 'newswire'
    else:
        return 'direct'


# ============================================================================
# Company Lookup
# ============================================================================


def get_company_config(ticker):
    """
    Get company configuration from DynamoDB

    Single Responsibility: Only retrieves company config

    Args:
        ticker: Company ticker symbol

    Returns:
        dict: Company configuration or None
    """
    try:
        response = companies_table.get_item(Key={'ticker': ticker})

        if 'Item' not in response:
            logger.warning(f"No company config found for {ticker}")
            return None

        return response['Item']

    except Exception as e:
        logger.error(f"Error fetching company config: {e}")
        return None


# ============================================================================
# Main Processing Logic
# ============================================================================


# ============================================================================
# URL Selection Helper Functions
# ============================================================================

def is_landing_page(url):
    """
    Check if URL is a generic landing page (no specific content)

    Landing page indicators:
    - Last path segment is a generic term (e.g., '/news-releases')
    - Very short path (domain + 1-2 segments)

    Args:
        url: Full URL string

    Returns:
        bool: True if URL appears to be a landing page
    """
    path = url.rstrip('/').split('/')

    # Get last non-empty segment
    last_segment = None
    for segment in reversed(path):
        if segment and segment not in ['http:', 'https:', '']:
            last_segment = segment
            break

    if not last_segment:
        return True

    # Case 1: Last segment is a generic term
    if last_segment.lower() in GENERIC_PAGE_SEGMENTS:
        return True

    # Case 2: Very short path (domain + 1 segment or less)
    path_segments = [s for s in path[3:] if s]  # Skip protocol + domain
    if len(path_segments) <= 1:
        return True

    return False


def extract_significant_words(subject_line):
    """
    Extract meaningful words from subject line for URL matching

    Filters out:
    - Common noise words ('the', 'of', 'and', etc.)
    - Generic PR words ('announces', 'reports', 'releases')
    - Short words (<3 chars, except numbers)

    Args:
        subject_line: Email subject line

    Returns:
        list: Significant words (lowercase)
    """
    if not subject_line:
        return []

    # Extract words (lowercase, keep alphanumeric including numbers)
    words = re.findall(r'\b[a-z0-9]+\b', subject_line.lower())

    # Filter noise + keep words >= 3 chars (or numbers)
    significant = [
        w for w in words
        if (w not in SUBJECT_NOISE_WORDS and len(w) >= 3) or w.isdigit()
    ]

    return significant


def score_url_by_subject(url, subject_line):
    """
    Score URL by how many subject words appear in the URL path

    Args:
        url: Full URL string
        subject_line: Email subject line

    Returns:
        int: Number of subject words found in URL
    """
    significant_words = extract_significant_words(subject_line)

    # Get the URL path (lowercase for matching)
    url_path = url.rstrip('/').lower()

    # Count matches
    matches = sum(1 for word in significant_words if word in url_path)

    return matches


def get_path_depth(url):
    """
    Count path segments after domain

    Args:
        url: Full URL string

    Returns:
        int: Number of path segments
    """
    path_segments = [s for s in url.split('/')[3:] if s]
    return len(path_segments)


def is_utility_page(url):
    """
    Check if URL is unsubscribe/preferences/etc.

    Args:
        url: Full URL string

    Returns:
        bool: True if URL is a utility page
    """
    utility_patterns = [
        '/unsubscribe', '/email-alert', '/preferences',
        '/manage-alerts', '/manage-subscriptions', '/opt-out'
    ]
    return any(pattern in url.lower() for pattern in utility_patterns)


def score_url(url, subject_line, press_release_url=''):
    """
    Score URL by specificity + subject match

    Scoring system:
    - Subject line matching: +100 per word (primary signal)
    - Path depth: +10 per segment (tiebreaker)
    - Landing page: -500 (heavy penalty)
    - Exact match to DB press_release_url: -800 (VERY heavy penalty - usually landing page)
    - Utility page: -1000 (exclusion)

    Args:
        url: Full URL string
        subject_line: Email subject line
        press_release_url: Database press_release_url field (to detect landing pages)

    Returns:
        int: URL score (higher = better match)
    """
    score = 0

    # 1. Subject line matching (primary signal)
    subject_matches = score_url_by_subject(url, subject_line)
    score += subject_matches * 100

    # 2. Path depth (tiebreaker - deeper = more specific)
    depth = get_path_depth(url)
    score += depth * 10

    # 3. Landing page penalty
    if is_landing_page(url):
        score -= 500

    # 4. HEAVY penalty if URL exactly matches database press_release_url (usually a landing page)
    if press_release_url and url.rstrip('/') == press_release_url.rstrip('/'):
        score -= 800
        logger.debug(f"URL matches database press_release_url exactly (landing page): -800 penalty")

    # 5. Utility page penalty
    if is_utility_page(url):
        score -= 1000

    return score


# ============================================================================
# URL Selection - Main Function
# ============================================================================

def select_best_url_from_email(urls, company, subject_line=''):
    """
    Select the URL that best matches the company's press release domain

    Single Responsibility: Only selects URLs based on domain matching + content scoring

    Strategy (Zero-Maintenance Redirect Following + Smart Selection):
        1. For each URL:
           - If domain matches company IR domain → Use directly (no redirect)
           - If domain is external → Follow redirect (likely tracking link)
        2. Filter resolved URLs to company domain
        3. Smart selection:
           - If first URL is specific (not landing page) → Use it (90% case)
           - If first URL is landing page → Score all URLs by subject + depth
           - Choose highest scoring URL

    This approach works with ANY tracking service (SendGrid, GCS-Web, etc.)
    without maintaining a whitelist of tracking domains.

    Priority (after redirect resolution):
        1. URLs matching press_release_url domain/path pattern
        2. URLs matching press_release_url domain (with landing page detection)
        3. URLs matching ir_domain (with landing page detection)
        4. First URL (fallback)

    Landing Page Detection:
        - URL ends with generic terms (/news-releases, /news, etc.)
        - URL has very short path (domain + 1 segment)

    Subject Line Scoring (when landing page detected):
        - Extract significant words from subject
        - Count matches in URL path
        - Prefer URLs with more subject words + deeper paths

    Args:
        urls: List of URLs from email
        company: Company config dict with press_release_url, ir_domain
        subject_line: Email subject line (for content matching when needed)

    Returns:
        str: Best matching URL
    """
    if not urls:
        return None

    if len(urls) == 1:
        return urls[0]

    press_release_url = company.get('press_release_url', '')
    ir_domain = company.get('ir_domain', '')

    # Extract domain and path pattern from press_release_url
    pr_domain = None
    pr_path_pattern = None

    if press_release_url:
        parsed = urlparse(press_release_url)
        pr_domain = parsed.netloc
        pr_path_parts = parsed.path.split('/')
        # Get the main path component (e.g., "/news-1/news-releases/")
        pr_path_pattern = '/'.join([p for p in pr_path_parts if p and p != 'default.aspx'])

    # Smart redirect following: Follow redirects for URLs NOT on company IR domain
    # This handles ANY tracking service without maintaining a whitelist
    resolved_urls = []
    for url in urls:
        parsed_url = urlparse(url)

        # Check if URL is already on company's IR domain
        is_company_domain = False
        if ir_domain and ir_domain in parsed_url.netloc:
            is_company_domain = True
        elif pr_domain and pr_domain in parsed_url.netloc:
            is_company_domain = True

        # If URL is external (not company domain), follow redirect
        # This catches ALL tracking services automatically (SendGrid, GCS-Web, etc.)
        if not is_company_domain:
            try:
                logger.info(f"Following external URL (likely tracking): {url[:60]}...")
                response = requests.head(url, allow_redirects=True, timeout=REDIRECT_TIMEOUT)
                final_url = response.url
                resolved_urls.append((final_url, url))  # (final_url, original_url)
                logger.info(f"  → Resolved to: {final_url[:80]}...")
            except Exception as e:
                logger.warning(f"Failed to resolve URL ({e}), using original")
                resolved_urls.append((url, url))
        else:
            # Already on company domain, no redirect needed
            logger.debug(f"URL already on company domain, using directly: {url[:60]}...")
            resolved_urls.append((url, url))

    # Phase 1: Filter to domain-matching URLs
    # Collect ALL URLs matching company domain (don't filter by path pattern - let scoring decide)
    domain_matching_urls = []

    # Priority 1: Match press_release_url domain (all URLs, not just path pattern)
    if pr_domain:
        for final_url, original_url in resolved_urls:
            parsed_url = urlparse(final_url)
            if pr_domain in parsed_url.netloc and not is_utility_page(final_url):
                domain_matching_urls.append(final_url)
        if domain_matching_urls:
            logger.info(f"✓ Found {len(domain_matching_urls)} URLs matching PR domain: {pr_domain}")

    # Priority 2: Match ir_domain (if no PR domain or no matches)
    if not domain_matching_urls and ir_domain:
        for final_url, original_url in resolved_urls:
            parsed_url = urlparse(final_url)
            if ir_domain in parsed_url.netloc and not is_utility_page(final_url):
                domain_matching_urls.append(final_url)
        if domain_matching_urls:
            logger.info(f"✓ Found {len(domain_matching_urls)} URLs matching IR domain: {ir_domain}")

    # Fallback: Use all resolved URLs (excluding utility pages)
    if not domain_matching_urls:
        domain_matching_urls = [
            final for final, orig in resolved_urls
            if not is_utility_page(final)
        ]
        logger.info(f"✓ Fallback: Using all {len(domain_matching_urls)} non-utility URLs")

    # Phase 2: Smart URL selection with landing page detection
    if domain_matching_urls:
        first_url = domain_matching_urls[0]

        # Simple case: First URL is specific (not a landing page)
        if not is_landing_page(first_url):
            logger.info(f"✓ Selected specific URL (not landing page): {first_url[:80]}...")
            return first_url

        # Landing page detected: Score all URLs by subject line + specificity
        logger.info(f"⚠ Landing page detected, scoring all URLs by subject line + specificity")

        scored_urls = [
            (url, score_url(url, subject_line, press_release_url))
            for url in domain_matching_urls
        ]

        # Log scores for debugging
        for url, url_score in scored_urls:
            logger.info(f"  URL score {url_score}: {url[:80]}...")

        # Choose highest scoring URL
        best_url, best_score = max(scored_urls, key=lambda x: x[1])
        logger.info(f"✓ Selected best URL (score={best_score}): {best_url[:80]}...")
        return best_url

    # Final fallback: First resolved URL
    first_final, first_original = resolved_urls[0]
    logger.warning(f"No domain match found, using first URL: {first_final[:80]}...")
    return first_final


def process_enrichment_job(job):
    """
    Process one enrichment job

    Single Responsibility: Orchestrates enrichment workflow

    Workflow:
        1. Get company config
        2. Try URL construction
        3. Validate constructed URL
        4. If valid → Save to DynamoDB
        5. If invalid → Fall back to email URLs
        6. Select best URL from email (domain matching)
        7. Classify URL → Route to scraper or save

    Args:
        job: Enrichment job dict from Parser

    Returns:
        dict: Result with status and details
    """
    ticker = job.get('ticker')
    email_subject = job.get('email_subject')
    email_date = job.get('email_date', '')
    idempotency_key = job.get('idempotency_key')
    urls = job.get('urls', [])

    logger.info(f"📧 Processing enrichment for {ticker}")

    # Step 1: Get company configuration
    company = get_company_config(ticker)

    if not company:
        logger.error(f"Company config not found: {ticker}")
        return {'status': 'failed', 'reason': 'company_not_found'}

    # Step 2: Try URL construction
    constructed_url, method = construct_url_for_company(company, email_subject, email_date)

    if constructed_url:
        logger.info(f"Constructed URL using {method}: {constructed_url[:60]}...")

        # Step 3: Validate constructed URL
        is_valid, final_url, status_code = validate_url_exists(constructed_url)

        if is_valid:
            # Step 4a: Save to DynamoDB (no scraping needed)
            metadata = {
                'ticker': ticker,
                'subject': email_subject,
                'idempotency_key': idempotency_key,
                'construction_method': method
            }
            success = save_to_dynamodb(final_url, metadata)
            return {'status': 'saved', 'url': final_url, 'method': 'constructed'}
        else:
            logger.warning(f"Constructed URL invalid ({status_code}), falling back to email URLs")

    # Step 4b: Use URLs from email body
    if not urls:
        logger.warning(f"No URLs found for {ticker}")
        return {'status': 'failed', 'reason': 'no_url'}

    # NEW: Select best URL based on domain matching + subject line scoring
    selected_url = select_best_url_from_email(urls, company, email_subject)

    if not selected_url:
        logger.warning(f"No valid URL selected for {ticker}")
        return {'status': 'failed', 'reason': 'no_valid_url'}

    url_type = classify_url(selected_url)

    metadata = {
        'ticker': ticker,
        'subject': email_subject,
        'idempotency_key': idempotency_key
    }

    if url_type == 'newswire':
        # Newswire → Queue for scraping
        success = queue_for_scraping(selected_url, metadata)
        return {'status': 'queued_scraping', 'url': selected_url, 'method': 'email_newswire'}
    else:
        # Direct link → Save to DynamoDB
        success = save_to_dynamodb(selected_url, metadata)
        return {'status': 'saved', 'url': selected_url, 'method': 'email_direct'}


# ============================================================================
# Lambda Handler
# ============================================================================


def lambda_handler(event, context):
    """
    Main Lambda handler - process enrichment jobs from SQS

    Single Responsibility: Orchestrates batch processing

    Expected SQS Event Format:
    {
        "Records": [{
            "body": "{\"ticker\":\"EPRT\",\"email_subject\":\"...\",\"urls\":[\"http://...\"],\"idempotency_key\":\"abc123\"}",
            "messageId": "xyz"
        }]
    }

    Message Body Format (JSON string from Parser):
    {
        "ticker": "EPRT",                    # REQUIRED: Company ticker
        "email_subject": "...",               # REQUIRED: Email subject line
        "email_date": "2026-03-09",          # Optional: Email date
        "idempotency_key": "abc123",         # REQUIRED: Unique identifier
        "urls": ["http://..."]               # REQUIRED: URLs to enrich
    }

    Returns:
        dict: Batch processing results for SQS partial failure handling
    """
    logger.info(f"📨 Received {len(event['Records'])} enrichment job(s)")

    results = {
        'saved': 0,
        'queued_scraping': 0,
        'failed': 0
    }

    batch_failures = []

    for record in event['Records']:
        try:
            # Validate SQS record structure
            if 'body' not in record:
                raise ValueError(
                    "Invalid SQS record format: missing 'body' field. "
                    "Expected: {\"Records\":[{\"body\":\"...\"}]}"
                )

            # Parse SQS message
            job = json.loads(record['body'])

            # Validate required fields
            required_fields = ['ticker', 'urls', 'idempotency_key']
            missing_fields = [f for f in required_fields if f not in job]
            if missing_fields:
                raise ValueError(
                    f"Invalid message body: missing required fields {missing_fields}. "
                    f"Expected format: {{\"ticker\":\"...\",\"urls\":[...],\"idempotency_key\":\"...\"}}"
                )
            result = process_enrichment_job(job)

            status = result.get('status', 'failed')
            results[status] = results.get(status, 0) + 1

        except Exception as e:
            logger.error(f"Error processing job: {e}", exc_info=True)
            results['failed'] += 1

            # Mark message for retry
            batch_failures.append({
                'itemIdentifier': record['messageId']
            })

    logger.info(f"✅ Enrichment complete: {results}")

    return {
        'statusCode': 200,
        'batchItemFailures': batch_failures,
        'body': json.dumps(results)
    }
