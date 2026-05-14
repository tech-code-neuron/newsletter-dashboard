"""
Press Release Pipeline - Email Parser Lambda
==================================
Triggered by: SQS Parse Queue
Purpose: Extract press release links from incoming emails
Flow:
  1. Receive message from parse queue (contains S3 location)
  2. Download email from S3
  3. Check idempotency (prevent duplicate processing)
  4. Parse email body and extract URLs
  5. Classify URLs as direct company links or newswire redirects
  6. Route: Direct links → DynamoDB, Newswire → Scrape Queue
  7. Mark as processed in idempotency table

Supported Newswires:
  - GlobeNewswire (globenewswire.com)
  - Business Wire (businesswire.com)
  - PR Newswire (prnewswire.com)
  - Accesswire (accesswire.com)

Last Updated: 2026-03-09 19:45 UTC (Google-grade O(1) domain-first matching)
"""

import json
import email
import hashlib
import re
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser
import boto3
import os
import logging
import requests
from urllib.parse import urlparse

# Initialize AWS clients
s3 = boto3.client('s3')
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# Environment variables
S3_BUCKET = os.environ['S3_BUCKET_NAME']
SCRAPE_QUEUE_URL = os.environ['SCRAPE_QUEUE_URL']
PLAYWRIGHT_QUEUE_URL = os.environ.get('PLAYWRIGHT_QUEUE_URL', '')  # Optional: for JS-rendered companies
INBOUND_LOG_TABLE = os.environ['INBOUND_LOG_TABLE']
REIT_NEWS_TABLE = os.environ['REIT_NEWS_TABLE']
COMPANIES_TABLE = os.environ['COMPANIES_TABLE']
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configure logging
logger = logging.getLogger()
logger.setLevel(getattr(logging, LOG_LEVEL))

# DynamoDB tables
inbound_log_table = dynamodb.Table(INBOUND_LOG_TABLE)
reit_news_table = dynamodb.Table(REIT_NEWS_TABLE)
companies_table = dynamodb.Table(COMPANIES_TABLE)

# Cache all companies at module level (loaded once per Lambda container lifecycle)
COMPANIES_CACHE = None
COMPANIES_BY_NAME_INDEX = None  # O(1) lookup by company name
COMPANIES_BY_DOMAIN_INDEX = None  # O(1) lookup by IR domain
COMPANIES_BY_NORMALIZED_NAME = None  # Fuzzy name matching (punctuation-agnostic)
DOMAIN_TO_TICKER_INDEX = None  # O(1) domain → ticker (source of truth)
TICKER_TO_COMPANY_INDEX = None  # O(1) ticker → company (for reverse lookup)

# ============================================================================
# Constants - Single Source of Truth
# ============================================================================

# GCS URL Crafting
GCS_DOMAIN_IDENTIFIER = 'gcs-web.com'
GCS_NOTIFICATION_IDENTIFIER = 'notification'
GCS_URL_PATH_TEMPLATE = '/news-releases/news-release-details/'
GCS_SLUG_WORD_COUNT = 7

# Timeouts and TTL
REDIRECT_TIMEOUT_SECONDS = 30
IDEMPOTENCY_TTL_DAYS = 30

# Newswire domains (redirects that need scraping)
NEWSWIRE_DOMAINS = {
    'globenewswire.com',
    'businesswire.com',
    'prnewswire.com',
    'accesswire.com',
    'prnews.com',
    'marketwired.com'
}

# Redirect domains (follow to get final URL before matching)
# These are short/tracking URLs that redirect to actual press releases
REDIRECT_DOMAINS = {
    'ir.stockpr.com',  # Veris Residential and others use this redirect service
    'stockpr.com'
}

# URL extraction regex
URL_PATTERN = re.compile(r'https?://[^\s<>"]+')

# Press release URL patterns (must contain at least one)
PRESS_RELEASE_PATTERNS = [
    '/news/',
    '/press-release/',
    '/press_release/',
    '/pressrelease/',
    '/investor',
    '/detail/',
    '/release/',
    '/releases/',
    '/press/',
    '/newsroom/',
    '/media/'
]

# Third-party IR platforms (host press releases for multiple companies)
THIRD_PARTY_IR_PLATFORMS = [
    'ir.stockpr.com',     # StockPR investor relations platform
    'ir.equisolve.com',   # Equisolve platform
    'notification.gcs-web.com',  # GCS notifications
    'q4inc.com',          # Q4 platform
]

# Companies requiring JavaScript rendering (Playwright scraper)
# SOLID: Open/Closed - Add companies here without modifying code
JAVASCRIPT_RENDERED_COMPANIES = {
    'EPRT'  # Essential Properties - SvelteKit framework
    # Add more tickers as needed
}

# Patterns to exclude (images, unsubscribe, preferences, etc.)
# Generated from analysis of 157 real S3 emails - see scripts/analyze_all_s3_emails.py
# Analysis results: 49/157 emails (31%) are activation/signup, 56% of URLs should be excluded
EXCLUDE_PATTERNS = [
    # Image/media files
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.pdf',
    '/logo', '/icon', '/image',
    '/alerts_logos/',  # GCS alert logo directory

    # Email management
    '/unsubscribe', '/preferences', '/subscribe',
    '/subpref', '/manage', '/optout',
    '/email-pref', '/manage-subscription',
    '/email-alert-unsubscription',  # Email unsubscribe pages

    # Email activation/verification (CRITICAL - 70 occurrences in real data)
    '/email-alert-activation/',  # 70 occurrences
    '/emailnotification/',
    '/email-activation/',
    '/email-verification/',
    '/email-confirm/',
    '/activate-alert',
    '/confirm-subscription',
    '/verify-email',
    'token=',  # Email verification tokens
    '/contact-ir/emailnotification',
    '/email-notification/',  # 11 occurrences
    '/email-alerts/',  # 11 occurrences
    '/investor-email-alerts/',  # 42 occurrences (often signup pages, not PRs)

    # Tracking/analytics (110 occurrences!)
    '/wf/open',  # 110 occurrences - email open tracking
    '/wf/click',  # Email click tracking
    '/open/',  # 110 occurrences - tracking pixels
    '/track',
    '/pixel',
    '/beacon',
    # NOTE: ct.sendgrid.net removed - can contain notification redirects

    # CDN/asset URLs
    'cloudfront.net',
    '/files/design/',
    '/files/theme/',
    '/sites/g/files/',
    '/resources/',  # 42 occurrences (often static resources, not PRs)

    # Social media
    'facebook.com', 'twitter.com', 'linkedin.com',
    'instagram.com', 'youtube.com',

    # Events/calendar (not press releases)
    '/calendar/', '/event/', '/webcast/', '/conference/',
    '/events-presentations/',  # Tanger-specific

    # Common non-PR pages
    '/default.aspx',  # 70 occurrences (often activation/confirmation pages)
    '/investors/$',  # Landing page only (not /investors/news/)
    '/investor-relations/$',  # IR landing page only
    '/financial-information',  # Financial info pages (not PRs)
    '/sec-filings',  # SEC filings page (not press releases)
    '/press-releases/$',  # Press releases list page (not specific PR)
    '/news-releases/$',  # News releases list page (not specific PR)
]


def is_press_release_url(url):
    """
    Check if URL is likely a press release (not logo/unsubscribe/etc.)
    Uses blacklist approach: exclude known junk, keep substantial URLs
    Allows tracking/notification URLs through (will be resolved later)
    """
    url_lower = url.lower()

    # Exclude known non-press-release patterns
    for pattern in EXCLUDE_PATTERNS:
        if pattern in url_lower:
            return False

    # Check if URL matches positive press release patterns
    has_pr_pattern = any(pattern in url_lower for pattern in PRESS_RELEASE_PATTERNS)

    # If has press release keyword pattern, definitely keep it
    if has_pr_pattern:
        return True

    # Allow tracking/notification URLs (they redirect to press releases)
    if 'notification' in url_lower or 'click' in url_lower or 'redirect' in url_lower:
        return True

    # Parse URL to check if it's just a homepage
    try:
        path = url_lower.split('//')[1].split('?')[0]  # Get domain+path without query
        path_after_domain = '/'.join(path.split('/')[1:])  # Get everything after domain

        # If no path after domain, it's just homepage
        if not path_after_domain or path_after_domain == '':
            return False

        # If path has substantial content (not just "/" or single char), keep it
        if len(path_after_domain) > 10:
            return True

    except IndexError:
        # If URL parsing fails, err on the side of keeping it
        return True

    return False


def is_confirmation_email(subject, body_text=''):
    """
    Check if email is a confirmation/validation/signup OR SEC filing notification
    that should be skipped (not a press release)

    Returns: True if email should be skipped, False if it should be processed
    """
    if not subject:
        return False

    subject_lower = subject.lower()
    body_lower = body_text.lower() if body_text else ''

    # Confirmation/validation keywords + SEC filing notifications
    SKIP_KEYWORDS = [
        # Confirmation/activation emails
        'validate account',
        'confirm',
        'signup',
        'sign up',
        'registration',
        'verify',
        'activate',
        'subscription confirmation',
        'please confirm',
        'email validation',
        'validate your',
        'confirm your email',
        'confirm subscription',
        'welcome to',
        'verify your',

        # SEC filings (not press releases)
        'form 8-k',
        'form 10-q',
        'form 10-k',
        'new form 8-k',
        'new form 10-q',
        'new form 10-k',
        'sec filing',
        'filed with sec',
        'filed a form',
    ]

    # Check subject line
    for keyword in SKIP_KEYWORDS:
        if keyword in subject_lower:
            logger.info(f"Skipping confirmation email (subject): '{subject[:80]}'")
            return True

    # If subject doesn't have keywords, check body (first 500 chars)
    if body_lower:
        body_sample = body_lower[:500]
        for keyword in SKIP_KEYWORDS:
            if keyword in body_sample:
                logger.info(f"Skipping confirmation email (body): '{subject[:80]}'")
                return True

    return False


def normalize_company_name(name):
    """
    Normalize company name for fuzzy matching
    Handles punctuation, suffixes, case variations

    Examples:
        "Alexander's, Inc." → "alexanders"
        "Terreno Realty Corporation" → "terreno realty"
        "SL Green Realty Corp." → "sl green realty"

    Returns: Normalized lowercase string
    """
    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower()

    # Remove common suffixes
    suffixes = [
        r'\s+inc\.?$', r'\s+corp\.?$', r'\s+corporation$',
        r'\s+llc\.?$', r'\s+l\.p\.?$', r'\s+lp\.?$',
        r'\s+ltd\.?$', r'\s+limited$', r'\s+plc\.?$',
        r'\s+trust$', r'\s+reit$'
    ]
    for suffix in suffixes:
        normalized = re.sub(suffix, '', normalized)

    # Remove all punctuation except spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized.strip()


def extract_domain_from_url(url):
    """
    Extract domain from URL, handling common patterns

    Examples:
        "https://investors.terreno.com/press-releases" → "terreno.com"
        "https://alx.gcs-web.com/news" → "alx.gcs-web.com"
        "http://www.realty.com" → "realty.com"

    Returns: Domain string (lowercase, www removed)
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www prefix
        if domain.startswith('www.'):
            domain = domain[4:]

        return domain
    except:
        return None


def extract_all_domains_from_company(company):
    """
    Extract all possible domains from company record
    Returns list of domains (for comprehensive domain index)

    Smart parent domain extraction: Skip parent domains for shared hosting platforms
    (e.g., don't add "gcs-web.com" when domain is "alx.gcs-web.com")

    Examples:
        ir_domain: "investors.terreno.com" → ["terreno.com", "investors.terreno.com"]
        ir_domain: "alx.gcs-web.com" → ["alx.gcs-web.com"] (no parent, shared platform)
    """
    # Shared IR hosting platforms (don't add parent domain for these)
    SHARED_PLATFORMS = {
        'gcs-web.com',       # Global Compliance Services
        'q4web.com',         # Q4 Web Systems
        'q4inc.com',         # Q4 Inc
        'equisolve.com',     # Equisolve
        'investis.com',      # Investis Digital
        'irwebpage.com',     # IR Webpage
        'vcall.com',         # VCall
    }

    domains = set()

    # From ir_domain field
    if company.get('ir_domain'):
        domain = company['ir_domain'].lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        domains.add(domain)

        # Add parent domain ONLY if not a shared platform
        parts = domain.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            if parent_domain not in SHARED_PLATFORMS:
                domains.add(parent_domain)

    # From press_release_url
    if company.get('press_release_url'):
        domain = extract_domain_from_url(company['press_release_url'])
        if domain:
            domains.add(domain)
            # Add parent domain ONLY if not a shared platform
            parts = domain.split('.')
            if len(parts) > 2:
                parent_domain = '.'.join(parts[-2:])
                if parent_domain not in SHARED_PLATFORMS:
                    domains.add(parent_domain)

    # From ir_url (legacy field)
    if company.get('ir_url'):
        domain = extract_domain_from_url(company['ir_url'])
        if domain:
            domains.add(domain)

    return list(domains)


def extract_sender_name(from_field):
    """
    Extract sender name from From field
    Example: "Chatham Lodging Trust <alerts@em.equisolve.com>" -> "Chatham Lodging Trust"
    """
    if not from_field:
        return None

    # Try to extract name from "Name <email>" format
    match = re.match(r'^(.+?)\s*<.+>$', from_field)
    if match:
        return match.group(1).strip().strip('"').strip("'")

    # If no angle brackets, return as-is (might be just email)
    return from_field.strip()


def match_company_by_urls(urls):
    """
    Match company by domains found in URLs
    Google-grade: Domain matching as source of truth, O(1) lookups

    Priority:
        1. Direct domain match in DOMAIN_TO_TICKER_INDEX (O(1))
        2. Domain match after following redirects (O(1) after HTTP request)

    Returns: (company_dict, matched_url) or (None, None)
    """
    if not urls or not DOMAIN_TO_TICKER_INDEX or not TICKER_TO_COMPANY_INDEX:
        return None, None

    # Strategy 1: Direct domain matching (no redirects needed) - O(1)
    for url in urls:
        domain = extract_domain_from_url(url)
        if not domain:
            continue

        # Check exact domain match - O(1)
        ticker = DOMAIN_TO_TICKER_INDEX.get(domain)
        if ticker:
            # O(1) lookup of company by ticker
            company = TICKER_TO_COMPANY_INDEX.get(ticker)
            if company:
                logger.info(f"✓ Domain match (O(1)): {domain} → {ticker}")
                return company, url

        # Check parent domain (e.g., subdomain.example.com → example.com) - O(1)
        parts = domain.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            ticker = DOMAIN_TO_TICKER_INDEX.get(parent_domain)
            if ticker:
                company = TICKER_TO_COMPANY_INDEX.get(ticker)
                if company:
                    logger.info(f"✓ Parent domain match (O(1)): {domain} ({parent_domain}) → {ticker}")
                    return company, url

    # Strategy 2: Follow redirects for notification URLs
    for url in urls:
        # Skip if already direct matched
        domain = extract_domain_from_url(url)
        if DOMAIN_TO_TICKER_INDEX.get(domain):
            continue

        # Check if this looks like a redirect URL
        if 'notification' in url or 'sendgrid' in url or '/ls/click' in url:
            logger.info(f"Following redirect for notification URL: {url[:80]}...")
            final_url = follow_redirect_url(url, timeout=5)

            if final_url and final_url != url:
                final_domain = extract_domain_from_url(final_url)
                if final_domain:
                    ticker = DOMAIN_TO_TICKER_INDEX.get(final_domain)  # O(1)
                    if ticker:
                        company = TICKER_TO_COMPANY_INDEX.get(ticker)  # O(1)
                        if company:
                            logger.info(f"✓ Redirect domain match (O(1)): {url[:50]}... → {final_domain} → {ticker}")
                            return company, final_url

    return None, None


def match_company_by_name(sender_name):
    """
    Match company by sender name using multi-strategy fuzzy matching
    Google-grade: Handles punctuation, suffix variations

    Strategy (in priority order):
    1. Exact match via index (O(1)) - fastest
    2. Normalized fuzzy match (O(1)) - handles "Alexander's" vs "Alexander's, Inc."
    3. Partial match (first word) - fallback for unusual names

    Returns: company dict or None
    """
    if not sender_name or not COMPANIES_BY_NAME_INDEX:
        return None

    sender_lower = sender_name.lower().strip()

    # Strategy 1: Try exact match - O(1) lookup
    company = COMPANIES_BY_NAME_INDEX.get(sender_lower)
    if company:
        logger.info(f"Exact name match (O(1)): '{sender_name}' → {company['ticker']}")
        return company

    # Strategy 2: Try normalized fuzzy match (NEW: handles punctuation)
    normalized_sender = normalize_company_name(sender_name)
    if normalized_sender and COMPANIES_BY_NORMALIZED_NAME:
        company = COMPANIES_BY_NORMALIZED_NAME.get(normalized_sender)
        if company:
            logger.info(f"✓ Fuzzy name match: '{sender_name}' → '{normalized_sender}' → {company['ticker']}")
            return company

    # Strategy 3: Fallback to partial match (first word)
    sender_words = sender_lower.split()
    if sender_words:
        first_word = sender_words[0]
        for name, company in COMPANIES_BY_NAME_INDEX.items():
            if first_word in name:
                logger.info(f"Partial name match: '{sender_name}' ('{first_word}') → {company['ticker']}")
                return company

    return None


def create_gcs_url_from_subject(subject, ir_domain):
    """
    Craft GCS press release URL from email subject
    Pattern: {domain}/news-releases/news-release-details/{slug}
    Slug: first N words, lowercase, hyphenated, no punctuation
    """
    try:
        # Remove common email prefixes
        subject = re.sub(r'^(RE:|FW:|Fwd:)\s*', '', subject, flags=re.IGNORECASE)

        # Remove punctuation and split into words
        words = re.findall(r'\b[a-zA-Z0-9]+\b', subject)

        # Take first N words (constant), lowercase, join with hyphens
        slug = '-'.join(words[:GCS_SLUG_WORD_COUNT]).lower()

        # Construct GCS URL using constant
        url = f"https://{ir_domain}{GCS_URL_PATH_TEMPLATE}{slug}"

        logger.info(f"Crafted GCS URL from subject: {url}")
        return url

    except Exception as e:
        logger.error(f"Error crafting GCS URL: {e}")
        return None


def create_brixmor_aspx_url(subject, ir_domain, email_date=None):
    """
    Craft Brixmor ASPX press release URL from email subject
    Pattern: {domain}/news-presentations/press-releases/news-details/{YYYY}/{SUBJECT-SLUG}/default.aspx

    Subject format: "Brixmor - ACTUAL TITLE HERE"
    Extract title after "Brixmor - " prefix
    NOTE: Slug preserves original capitalization (case-sensitive URLs)
    """
    try:
        from datetime import datetime

        # Remove common email prefixes
        subject = re.sub(r'^(RE:|FW:|Fwd:)\s*', '', subject, flags=re.IGNORECASE)

        # Extract title after "Brixmor - " prefix
        if ' - ' in subject:
            _, title = subject.split(' - ', 1)
        else:
            title = subject

        # Remove punctuation and split into words (keep ALL words, not just first 7)
        words = re.findall(r'\b[a-zA-Z0-9]+\b', title)

        # Create slug - PRESERVE CAPITALIZATION (case-sensitive URLs!)
        slug = '-'.join(words)

        # Get year (from email date or current year)
        year = email_date.year if email_date else datetime.utcnow().year

        # Construct Brixmor ASPX URL
        url = f"https://{ir_domain}/news-presentations/press-releases/news-details/{year}/{slug}/default.aspx"

        logger.info(f"Crafted Brixmor ASPX URL: {url}")
        return url

    except Exception as e:
        logger.error(f"Error crafting Brixmor ASPX URL: {e}")
        return None


def create_terreno_aspx_url(subject, ir_domain, email_date=None):
    """
    Craft Terreno ASPX press release URL from email subject
    Pattern: {domain}/news-presentations/press-releases/press-release/{YYYY}/{SUBJECT-SLUG}/default.aspx

    Note the path: news-presentations/press-releases/press-release (yes, both plural and singular)
    """
    try:
        from datetime import datetime

        # Remove common email prefixes
        subject = re.sub(r'^(RE:|FW:|Fwd:)\s*', '', subject, flags=re.IGNORECASE)

        # Extract title after company prefix if present
        if ' - ' in subject:
            _, title = subject.split(' - ', 1)
        else:
            title = subject

        # Remove punctuation and split into words
        words = re.findall(r'\b[a-zA-Z0-9]+\b', title)

        # Create slug - PRESERVE CAPITALIZATION
        slug = '-'.join(words)

        # Get year
        year = email_date.year if email_date else datetime.utcnow().year

        # Construct Terreno ASPX URL (note: press-releases/press-release)
        url = f"https://{ir_domain}/news-presentations/press-releases/press-release/{year}/{slug}/default.aspx"

        logger.info(f"Crafted Terreno ASPX URL: {url}")
        return url

    except Exception as e:
        logger.error(f"Error crafting Terreno ASPX URL: {e}")
        return None


def create_gcs_9_word_url(subject, ir_domain):
    """
    Craft GCS press release URL with 9-word slug
    Pattern: {domain}/news-releases/news-release-details/{slug}
    Slug: first 9 words, lowercase, hyphenated, no punctuation

    Used by: Alexander's (ALX)
    """
    try:
        # Remove common email prefixes
        subject = re.sub(r'^(RE:|FW:|Fwd:)\s*', '', subject, flags=re.IGNORECASE)

        # Remove punctuation and split into words
        words = re.findall(r'\b[a-zA-Z0-9]+\b', subject)

        # Take first 9 words, lowercase, join with hyphens
        slug = '-'.join(words[:9]).lower()

        # Construct GCS URL
        url = f"https://{ir_domain}/news-releases/news-release-details/{slug}"

        logger.info(f"Crafted GCS 9-word URL: {url}")
        return url

    except Exception as e:
        logger.error(f"Error crafting GCS 9-word URL: {e}")
        return None


def validate_url_exists(url, timeout=5):
    """
    Validate that a constructed URL exists (not 404/Not Found)

    Use Case: Test if a crafted URL (from subject line) actually exists
              before saving it to the database

    Args:
        url: URL to validate
        timeout: Request timeout in seconds (default 5)

    Returns:
        tuple: (exists: bool, status_code: int or None)
        - exists=True if URL returns 2xx/3xx (valid)
        - exists=False if 404/410/Not Found (construction failed)
        - 403 returns exists=True (blocked but exists, not a construction error)
    """
    try:
        logger.info(f"Validating URL exists: {url}")

        # Use HEAD request to avoid downloading full page
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        status = response.status_code

        # Success codes: 200-399 (valid URL)
        if 200 <= status < 400:
            logger.info(f"✓ URL exists (status {status}): {url}")
            return (True, status)

        # 403 Forbidden: Blocked but exists (not a construction error)
        elif status == 403:
            logger.warning(f"⚠️  URL blocked (403) but exists: {url}")
            return (True, status)

        # 404/410 Not Found: Construction failed
        elif status in [404, 410]:
            logger.warning(f"✗ URL not found (status {status}): {url}")
            return (False, status)

        # Other error codes: treat as construction failure
        else:
            logger.warning(f"✗ URL error (status {status}): {url}")
            return (False, status)

    except requests.exceptions.Timeout:
        logger.error(f"Timeout validating URL: {url}")
        return (False, None)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error validating URL {url}: {e}")
        return (False, None)
    except Exception as e:
        logger.error(f"Unexpected error validating URL {url}: {e}")
        return (False, None)


def update_company_construction_method(ticker, new_method, reason=""):
    """
    Update company's URL construction method in DynamoDB

    Use Case: Auto-correct when construction method fails and redirect_follow works

    Args:
        ticker: Company ticker symbol
        new_method: New url_construction_method value (e.g., 'redirect_follow')
        reason: Optional explanation for the update (logged)

    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        logger.info(f"Updating {ticker} url_construction_method to '{new_method}' - {reason}")

        # Update DynamoDB
        companies_table = dynamodb.Table(COMPANIES_TABLE_NAME)
        companies_table.update_item(
            Key={'ticker': ticker},
            UpdateExpression='SET url_construction_method = :method',
            ExpressionAttributeValues={':method': new_method}
        )

        logger.info(f"✓ Successfully updated {ticker} construction method to '{new_method}'")
        return True

    except Exception as e:
        logger.error(f"✗ Failed to update {ticker} construction method: {e}")
        return False


def scrape_eprt_press_release_url(title, press_releases_page_url, timeout=10):
    """
    EPRT-specific: Scrape press releases list page to find URL matching title

    EPRT emails don't contain the actual press release URL, only a link to the
    list page. This function scrapes the list page and finds the PR matching the title.

    Args:
        title: Press release title from email subject
        press_releases_page_url: URL to press releases list page
        timeout: Request timeout in seconds

    Returns:
        str: Press release URL if found, None otherwise
    """
    try:
        logger.info(f"EPRT scraper: Searching for title: {title[:80]}")

        # Fetch press releases list page
        response = requests.get(press_releases_page_url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

        if response.status_code != 200:
            logger.error(f"EPRT scraper: Failed to fetch list page (status {response.status_code})")
            return None

        # Parse HTML using regex (no dependencies needed)
        html = response.text

        # Extract all <a> tags with href containing /news/
        # Pattern: <a href="/news/..." ... >Title</a>
        import re
        link_pattern = r'<a[^>]*href=["\']([^"\']*\/news\/[^"\']*)["\'][^>]*>(.*?)<\/a>'
        matches = re.findall(link_pattern, html, re.IGNORECASE | re.DOTALL)

        # Normalize the search title
        normalized_title = ' '.join(title.lower().split())

        for href, link_text in matches:
            # Clean up link text (remove HTML tags, normalize whitespace)
            link_text_clean = re.sub(r'<[^>]+>', '', link_text)
            link_text_clean = ' '.join(link_text_clean.lower().split())

            # Check if titles match (allow partial match for truncated email subjects)
            if normalized_title in link_text_clean or link_text_clean in normalized_title:
                # Construct full URL
                from urllib.parse import urljoin
                full_url = urljoin(press_releases_page_url, href)

                logger.info(f"✓ EPRT scraper: Found matching PR: {full_url}")
                return full_url

        logger.warning(f"EPRT scraper: No matching press release found for title: {title[:80]}")
        return None

    except requests.exceptions.Timeout:
        logger.error(f"EPRT scraper: Timeout fetching {press_releases_page_url}")
        return None
    except Exception as e:
        logger.error(f"EPRT scraper: Error: {e}")
        return None


def follow_redirect_url(url, max_redirects=5, timeout=10):
    """
    Follow URL redirects using HEAD request
    Returns final URL after following all redirects

    Use Case: Email notification URLs (ct.sendgrid.net, notification.gcs-web.com)
              that redirect to actual press release pages

    Args:
        url: Starting URL (may be a tracking/notification redirect)
        max_redirects: Maximum number of redirects to follow (default 5)
        timeout: Request timeout in seconds (default 10)

    Returns: Final URL after redirects, or None if error
    """
    try:
        logger.info(f"Following redirects for: {url}")

        # Use HEAD request to avoid downloading full page
        response = requests.head(url, allow_redirects=True, timeout=timeout)

        final_url = response.url
        redirect_count = len(response.history)

        if redirect_count > 0:
            logger.info(f"Followed {redirect_count} redirect(s) to: {final_url}")
        else:
            logger.info(f"No redirects, final URL: {final_url}")

        return final_url

    except requests.exceptions.Timeout:
        logger.error(f"Timeout following redirects for: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error following redirects for {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error following redirects for {url}: {e}")
        return None


def extract_email_metadata(email_content):
    """
    Extract metadata from email: From, Subject, URLs
    Single Responsibility: Parse email headers and body
    Returns: dict with 'from_field', 'subject', 'urls'
    """
    try:
        # Parse email
        msg = BytesParser(policy=policy.default).parsebytes(email_content)

        # Extract metadata
        metadata = {
            'from_field': msg.get('From', ''),
            'subject': msg.get('Subject', ''),
            'urls': []
        }

        # Extract URLs from body
        urls = set()
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    urls.update(URL_PATTERN.findall(body))
                elif content_type == 'text/html' and not urls:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    urls.update(URL_PATTERN.findall(body))
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            urls.update(URL_PATTERN.findall(body))

        # Clean URLs (remove trailing punctuation, URL tracking params)
        cleaned_urls = []
        for url in urls:
            url = url.rstrip('.,;:!?)')
            url = re.sub(r'[?&](utm_|ref=|source=).*$', '', url)
            cleaned_urls.append(url)

        metadata['urls'] = list(set(cleaned_urls))
        return metadata

    except Exception as e:
        logger.error(f"Error extracting email metadata: {e}")
        raise


def classify_url(url):
    """
    Classify URL as direct company link or newswire redirect
    Returns: ('direct', url) or ('newswire', url)
    """
    url_lower = url.lower()

    # Check if URL is from a newswire service
    for domain in NEWSWIRE_DOMAINS:
        if domain in url_lower:
            return ('newswire', url)

    # Direct company link
    return ('direct', url)


def build_company_indices(companies):
    """
    Build O(1) lookup indices for companies
    Google-grade: Multi-strategy matching with domain as source of truth
    ALL lookups are O(1) for maximum efficiency

    Returns: (name_index, domain_index, normalized_name_index,
              domain_to_ticker_index, ticker_to_company_index)

    Indices:
        1. name_index: Exact company name → company (O(1))
        2. domain_index: IR domain → company (O(1))
        3. normalized_name_index: Fuzzy name → company (O(1), punctuation-agnostic)
        4. domain_to_ticker_index: Any domain → ticker (O(1), source of truth)
        5. ticker_to_company_index: Ticker → company (O(1), reverse lookup)
    """
    name_index = {}
    domain_index = {}
    normalized_name_index = {}
    domain_to_ticker_index = {}
    ticker_to_company_index = {}

    for company in companies:
        ticker = company.get('ticker')
        if not ticker:
            continue

        # 0. Index by ticker (NEW: O(1) reverse lookup)
        ticker_to_company_index[ticker] = company

        # 1. Index by exact company name
        company_name = company.get('name', '').lower().strip()
        if company_name:
            name_index[company_name] = company

        # 2. Index by IR domain
        ir_domain = company.get('ir_domain', '').lower().strip()
        if ir_domain:
            domain_index[ir_domain] = company

        # 3. Index by normalized name (fuzzy matching)
        if company.get('name'):
            normalized = normalize_company_name(company['name'])
            if normalized:
                normalized_name_index[normalized] = company

        # 4. Index ALL domains → ticker (comprehensive domain mapping)
        all_domains = extract_all_domains_from_company(company)
        for domain in all_domains:
            if domain:
                domain_to_ticker_index[domain] = ticker
                logger.debug(f"Domain index: {domain} → {ticker}")

    logger.info(f"✓ O(1) indices: {len(ticker_to_company_index)} tickers, {len(domain_to_ticker_index)} domains")
    return (name_index, domain_index, normalized_name_index,
            domain_to_ticker_index, ticker_to_company_index)


def load_all_companies():
    """
    Load all companies from DynamoDB and build O(1) indices
    Google-grade: All lookups are O(1) for maximum efficiency
    Returns: list of company dicts
    """
    global COMPANIES_CACHE, COMPANIES_BY_NAME_INDEX, COMPANIES_BY_DOMAIN_INDEX
    global COMPANIES_BY_NORMALIZED_NAME, DOMAIN_TO_TICKER_INDEX, TICKER_TO_COMPANY_INDEX

    if COMPANIES_CACHE is not None:
        return COMPANIES_CACHE

    try:
        logger.info("Loading companies from DynamoDB...")
        response = companies_table.scan()
        COMPANIES_CACHE = response.get('Items', [])

        # Build O(1) lookup indices (Google-grade multi-strategy)
        (COMPANIES_BY_NAME_INDEX,
         COMPANIES_BY_DOMAIN_INDEX,
         COMPANIES_BY_NORMALIZED_NAME,
         DOMAIN_TO_TICKER_INDEX,
         TICKER_TO_COMPANY_INDEX) = build_company_indices(COMPANIES_CACHE)

        logger.info(f"✓ Loaded {len(COMPANIES_CACHE)} companies with O(1) Google-grade indices")
        return COMPANIES_CACHE
    except Exception as e:
        logger.error(f"Error loading companies: {e}")
        return []


def follow_redirect_to_final_url(url, timeout=REDIRECT_TIMEOUT_SECONDS):
    """
    Follow redirects to get the final URL without triggering bot detection
    Only extracts the final URL - doesn't render page or execute JavaScript

    Returns: final URL or None if error
    """
    try:
        # Set headers to look like a real browser (remove DNT to avoid detection)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none'
        }

        # Use GET with stream=True (requests library handles redirects automatically)
        # stream=True means we don't download the body, just get headers
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=timeout, stream=True)
        final_url = response.url
        response.close()  # Close without downloading body

        logger.info(f"Successfully resolved redirect: {url[:80]}... -> {final_url}")
        return final_url

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout following redirect (>{timeout}s): {url[:100]}")
        return None
    except Exception as e:
        logger.warning(f"Could not follow redirect for {url[:100]}: {type(e).__name__}: {str(e)[:100]}")
        return None


def find_company_for_url(url):
    """
    Match URL to company using O(1) domain index lookup
    Single Responsibility: URL-to-company matching

    Returns: (company dict, True, final_url) if match found, (None, False, None) otherwise
    """
    if not url or not COMPANIES_BY_DOMAIN_INDEX:
        return None, False, None

    try:
        # Extract domain from URL
        parsed = urlparse(url)
        url_domain = parsed.netloc.lower()

        # Try O(1) exact domain match
        company = COMPANIES_BY_DOMAIN_INDEX.get(url_domain)
        if company:
            logger.info(f"Direct URL match (O(1)): {url_domain} -> {company['ticker']}")
            return company, True, url

        # Fallback: check if domain is contained in any company domain (subdomain matching)
        # This handles cases like "www.acresreit.com" vs "acresreit.com"
        for ir_domain, company in COMPANIES_BY_DOMAIN_INDEX.items():
            if ir_domain in url_domain or url_domain in ir_domain:
                logger.info(f"Subdomain match: {url_domain} -> {company['ticker']}")
                return company, True, url

        # If no match and it's a tracking/redirect URL, try following redirect
        # Includes: notification URLs, click trackers, and known redirect services
        is_redirect_url = (
            'notification' in url_domain or
            'click' in url_domain or
            'redirect' in url_domain or
            any(redirect_domain in url_domain for redirect_domain in REDIRECT_DOMAINS)
        )

        if is_redirect_url:
            logger.info(f"Redirect URL detected, following redirect: {url[:80]}")
            final_url = follow_redirect_to_final_url(url)

            if final_url and final_url != url:
                logger.info(f"Redirect resolved: {url[:80]} -> {final_url[:80]}")
                # Recursively check final URL
                return find_company_for_url(final_url)

    except Exception as e:
        logger.error(f"Error matching URL to company: {e}")

    return None, False, None


def check_idempotency(idempotency_key):
    """
    Check if this email has already been processed
    Returns: True if already processed, False otherwise
    """
    try:
        response = inbound_log_table.get_item(Key={'idempotency_key': idempotency_key})
        return 'Item' in response
    except Exception as e:
        logger.error(f"Error checking idempotency: {e}")
        raise


def mark_as_processed(idempotency_key, metadata):
    """
    Mark email as processed in idempotency table
    Sets TTL to auto-delete after configured days
    """
    try:
        ttl = int((datetime.utcnow() + timedelta(days=IDEMPOTENCY_TTL_DAYS)).timestamp())
        inbound_log_table.put_item(
            Item={
                'idempotency_key': idempotency_key,
                'processed_at': datetime.utcnow().isoformat(),
                'ttl': ttl,
                **metadata
            }
        )
    except Exception as e:
        logger.error(f"Error marking as processed: {e}")
        raise


def save_direct_link(url, metadata):
    """
    Save direct company press release link to DynamoDB
    Generates press_release_id from URL hash
    """
    try:
        press_release_id = hashlib.sha256(url.encode()).hexdigest()
        first_seen_at = datetime.utcnow().isoformat()

        reit_news_table.put_item(
            Item={
                'press_release_id': press_release_id,
                'first_seen_at': first_seen_at,
                'url': url,
                'source_type': 'direct',
                **metadata
            }
        )

        logger.info(f"Saved direct link: {url}")

    except Exception as e:
        logger.error(f"Error saving direct link: {e}")
        raise


def queue_for_scraping(url, metadata):
    """
    Send newswire URL to scrape queue for redirect resolution
    """
    try:
        message = {
            'url': url,
            'source_type': 'newswire',
            'queued_at': datetime.utcnow().isoformat(),
            **metadata
        }

        sqs.send_message(
            QueueUrl=SCRAPE_QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        logger.info(f"Queued for scraping: {url}")

    except Exception as e:
        logger.error(f"Error queueing for scraping: {e}")
        raise


def queue_for_playwright_scraping(ticker, email_subject, email_date, idempotency_key):
    """
    Send JavaScript-rendered company to Playwright queue

    SOLID: Single Responsibility - Only handles Playwright queue messaging

    Args:
        ticker: Company ticker symbol (e.g., 'EPRT')
        email_subject: Email subject line (for matching to scraped titles)
        email_date: Email date (for reference)
        idempotency_key: Unique key for deduplication
    """
    if not PLAYWRIGHT_QUEUE_URL:
        logger.warning("⚠️  PLAYWRIGHT_QUEUE_URL not configured - skipping Playwright queue")
        return

    try:
        message = {
            'ticker': ticker,
            'email_subject': email_subject,
            'email_date': email_date,
            'idempotency_key': idempotency_key,
            'queued_at': datetime.utcnow().isoformat()
        }

        sqs.send_message(
            QueueUrl=PLAYWRIGHT_QUEUE_URL,
            MessageBody=json.dumps(message)
        )

        logger.info(f"🎬 Queued for Playwright scraping: {ticker} - {email_subject[:50]}...")

    except Exception as e:
        logger.error(f"❌ Error queueing for Playwright scraping: {e}")
        raise


def lambda_handler(event, context):
    """
    Main Lambda handler
    Processes SQS messages containing S3 email locations
    """
    logger.info(f"Received {len(event['Records'])} messages")

    # Track failures for partial batch response
    batch_item_failures = []

    for record in event['Records']:
        message_id = record['messageId']

        try:
            # Parse message body
            body = json.loads(record['body'])
            bucket = body['bucket']
            key = body['key']
            idempotency_key = body['idempotency_key']

            logger.info(f"Processing: {bucket}/{key}")

            # Check if already processed (idempotency)
            if check_idempotency(idempotency_key):
                logger.info(f"Already processed: {idempotency_key}")
                continue

            # Load all companies (cached after first load)
            companies = load_all_companies()

            # Download email from S3
            response = s3.get_object(Bucket=bucket, Key=key)
            email_content = response['Body'].read()

            # Extract email metadata (From, Subject, URLs)
            email_meta = extract_email_metadata(email_content)
            logger.info(f"From: {email_meta['from_field'][:80]}")
            logger.info(f"Subject: {email_meta['subject'][:80]}")
            logger.info(f"Found {len(email_meta['urls'])} URLs")

            # Skip confirmation/validation emails (CRITICAL: prevents 31% false positives)
            if is_confirmation_email(email_meta['subject'], email_meta.get('body_text', '')):
                logger.info(f"✓ Skipped confirmation email: {idempotency_key}")
                metadata = {
                    'email_key': key,
                    'skipped_reason': 'confirmation_email',
                    'subject': email_meta['subject'][:100]
                }
                mark_as_processed(idempotency_key, metadata)
                continue

            # GOOGLE-GRADE MATCHING: Domain first (source of truth), then name
            matched_company = None
            matched_urls = []

            # Priority 1: Domain-based matching (most reliable)
            domain_company, domain_url = match_company_by_urls(email_meta['urls'])
            if domain_company:
                matched_company = domain_company
                logger.info(f"✓ Company matched by domain (source of truth): {matched_company['ticker']} ({matched_company['name']})")
                # Domain match already provides a URL, we'll use URL construction if available
            else:
                # Priority 2: Name-based matching (fallback)
                sender_name = extract_sender_name(email_meta['from_field'])
                matched_company = match_company_by_name(sender_name) if sender_name else None
                if matched_company:
                    logger.info(f"Company matched from From field: {matched_company['ticker']} ({matched_company['name']})")

            if matched_company:
                # Matched company found (either by domain or name)

                # SPECIAL HANDLING: JavaScript-rendered companies (EPRT, etc.)
                # SOLID: Open/Closed - Add tickers to JAVASCRIPT_RENDERED_COMPANIES constant
                if matched_company['ticker'] in JAVASCRIPT_RENDERED_COMPANIES:
                    logger.info(f"🎬 JavaScript-rendered company detected: {matched_company['ticker']}")

                    # Send to Playwright queue for headless browser scraping
                    queue_for_playwright_scraping(
                        ticker=matched_company['ticker'],
                        email_subject=email_meta['subject'],
                        email_date=email_meta.get('date', ''),
                        idempotency_key=idempotency_key
                    )

                    # Mark as processed
                    metadata = {
                        'email_key': key,
                        'ticker': matched_company['ticker'],
                        'routing': 'playwright_queue',
                        'subject': email_meta['subject'][:100]
                    }
                    mark_as_processed(idempotency_key, metadata)
                    continue  # Skip normal URL construction processing

                # Use Strategy Pattern: check url_construction_method (O(1) decision!)
                construction_method = matched_company.get('url_construction_method', 'direct_url')
                logger.info(f"Using construction method: {construction_method}")

                # Track if constructed URL worked (for auto-correction)
                constructed_url_worked = False
                crafted_url = None

                if construction_method == 'gcs_hosted' or construction_method == 'gcs_custom_domain':
                    # Strategy: GCS URL Construction (hosted or custom domain)
                    crafted_url = create_gcs_url_from_subject(email_meta['subject'], matched_company['ir_domain'])
                    if crafted_url:
                        # VALIDATION: Test if constructed URL exists (not 404)
                        exists, status = validate_url_exists(crafted_url)
                        if exists:
                            matched_urls.append((crafted_url, matched_company))
                            logger.info(f"✓ Crafted GCS URL validated ({construction_method}): {matched_company['ticker']} - {crafted_url}")
                            constructed_url_worked = True
                        else:
                            logger.warning(f"✗ Crafted GCS URL failed validation (status {status}): {crafted_url}")

                elif construction_method == 'brixmor_aspx':
                    # Strategy: Brixmor ASPX URL Construction
                    crafted_url = create_brixmor_aspx_url(email_meta['subject'], matched_company['ir_domain'])
                    if crafted_url:
                        # VALIDATION: Test if constructed URL exists (not 404)
                        exists, status = validate_url_exists(crafted_url)
                        if exists:
                            matched_urls.append((crafted_url, matched_company))
                            logger.info(f"✓ Crafted Brixmor ASPX URL validated: {matched_company['ticker']} - {crafted_url}")
                            constructed_url_worked = True
                        else:
                            logger.warning(f"✗ Crafted Brixmor ASPX URL failed validation (status {status}): {crafted_url}")

                elif construction_method == 'terreno_aspx':
                    # Strategy: Terreno ASPX URL Construction (different path than Brixmor)
                    crafted_url = create_terreno_aspx_url(email_meta['subject'], matched_company['ir_domain'])
                    if crafted_url:
                        # VALIDATION: Test if constructed URL exists (not 404)
                        exists, status = validate_url_exists(crafted_url)
                        if exists:
                            matched_urls.append((crafted_url, matched_company))
                            logger.info(f"✓ Crafted Terreno ASPX URL validated: {matched_company['ticker']} - {crafted_url}")
                            constructed_url_worked = True
                        else:
                            logger.warning(f"✗ Crafted Terreno ASPX URL failed validation (status {status}): {crafted_url}")

                elif construction_method == 'gcs_9_words':
                    # Strategy: GCS URL with 9-word slug (Alexander's)
                    crafted_url = create_gcs_9_word_url(email_meta['subject'], matched_company['ir_domain'])
                    if crafted_url:
                        # VALIDATION: Test if constructed URL exists (not 404)
                        exists, status = validate_url_exists(crafted_url)
                        if exists:
                            matched_urls.append((crafted_url, matched_company))
                            logger.info(f"✓ Crafted GCS 9-word URL validated: {matched_company['ticker']} - {crafted_url}")
                            constructed_url_worked = True
                        else:
                            logger.warning(f"✗ Crafted GCS 9-word URL failed validation (status {status}): {crafted_url}")

                elif construction_method == 'eprt_scrape_list':
                    # Strategy: EPRT-specific scraper (emails don't contain PR URL)
                    # Scrape press releases list page to find matching title

                    # Verify this is a press release email (not SEC filing/activation)
                    subject_lower = email_meta['subject'].lower()
                    is_press_release = any(keyword in subject_lower for keyword in [
                        'announces', 'declares', 'reports', 'completes', 'acquires',
                        'dividend', 'earnings', 'acquisition'
                    ])

                    if not is_press_release:
                        logger.info(f"EPRT: Skipping non-press-release email: {email_meta['subject'][:60]}")
                        constructed_url_worked = False
                    else:
                        # Extract title from subject (remove "Essential Properties: " prefix if present)
                        title = email_meta['subject']
                        if ':' in title:
                            title = title.split(':', 1)[1].strip()

                        # Get press releases list page URL from company config
                        press_releases_url = matched_company.get('press_release_url') or \
                                            f"https://{matched_company['ir_domain']}/press-releases/"

                        # Scrape list page to find matching PR
                        pr_url = scrape_eprt_press_release_url(title, press_releases_url)

                        if pr_url:
                            matched_urls.append((pr_url, matched_company))
                            logger.info(f"✓ EPRT scraper found PR: {matched_company['ticker']} - {pr_url}")
                            constructed_url_worked = True
                        else:
                            logger.warning(f"✗ EPRT scraper failed to find matching PR for: {title[:60]}")
                            constructed_url_worked = False

                elif construction_method == 'direct_url':
                    # Strategy: Direct URL Matching
                    for url in email_meta['urls']:
                        if not is_press_release_url(url):
                            continue

                        # Check if URL belongs to matched company
                        try:
                            parsed = urlparse(url)
                            url_domain = parsed.netloc.lower()
                            url_path = parsed.path.lower()
                            company_domain = matched_company.get('ir_domain', '').lower()
                            ticker = matched_company.get('ticker', '').lower()
                            company_name = matched_company.get('name', '').lower()

                            # Strategy 1: Domain match (standard)
                            if company_domain and (company_domain in url_domain or url_domain in company_domain):
                                matched_urls.append((url, matched_company))
                                logger.info(f"URL matched to company: {matched_company['ticker']} - {url}")
                                continue

                            # Strategy 2: Third-party IR platform with ticker/name in path
                            # (e.g., ir.stockpr.com/copt/news/detail/552)
                            is_third_party = any(platform in url_domain for platform in THIRD_PARTY_IR_PLATFORMS)
                            if is_third_party:
                                # Check if ticker or company name appears in URL path
                                if ticker and ticker in url_path:
                                    matched_urls.append((url, matched_company))
                                    logger.info(f"Third-party IR platform match: {matched_company['ticker']} - {url}")
                                    continue
                                # Also check for company name (first word)
                                company_first_word = company_name.split()[0] if company_name else ''
                                if len(company_first_word) > 3 and company_first_word in url_path:
                                    matched_urls.append((url, matched_company))
                                    logger.info(f"Third-party IR platform match (name): {matched_company['ticker']} - {url}")
                                    continue
                        except:
                            continue

                elif construction_method == 'redirect_follow':
                    # Strategy: Follow Redirects (ONLY for notification/tracking URLs)
                    for url in email_meta['urls']:
                        # Only follow URLs that are notification/tracking redirects
                        # (e.g., notification.gcs-web.com/ls/click, ct.sendgrid.net/ls/click, ir.stockpr.com)
                        is_redirect_url = (
                            '/ls/click' in url or
                            'notification' in url or
                            'sendgrid' in url or
                            'ir.stockpr.com' in url  # StockPR redirect service
                        )
                        if not is_redirect_url:
                            continue

                        if not is_press_release_url(url):
                            continue

                        # Follow redirects to get final press release URL
                        final_url = follow_redirect_url(url, timeout=5)
                        if final_url and final_url != url:
                            # Validate final URL is actually a press release (not unsubscribe, etc.)
                            if is_press_release_url(final_url):
                                matched_urls.append((final_url, matched_company))
                                logger.info(f"Redirect followed: {matched_company['ticker']} - {url[:50]}... → {final_url}")
                                constructed_url_worked = True
                            else:
                                logger.info(f"Skipped non-PR redirect result: {final_url}")

                # SMART FALLBACK: If URL construction failed (404), try redirect_follow
                if not constructed_url_worked and construction_method not in ['direct_url', 'redirect_follow']:
                    logger.warning(f"⚠️  URL construction failed for {matched_company['ticker']}, trying redirect_follow fallback...")

                    for url in email_meta['urls']:
                        # Only follow URLs that are notification/tracking redirects
                        is_redirect_url = (
                            '/ls/click' in url or
                            'notification' in url or
                            'sendgrid' in url or
                            'ir.stockpr.com' in url  # StockPR redirect service
                        )
                        if not is_redirect_url:
                            continue

                        if not is_press_release_url(url):
                            continue

                        # Follow redirects to get final press release URL
                        final_url = follow_redirect_url(url, timeout=5)
                        if final_url and final_url != url:
                            # Validate final URL is actually a press release (not unsubscribe, etc.)
                            if is_press_release_url(final_url):
                                matched_urls.append((final_url, matched_company))
                                logger.info(f"✓ Redirect fallback succeeded: {matched_company['ticker']} - {final_url}")

                                # AUTO-CORRECT: Update database to use redirect_follow
                                update_company_construction_method(
                                    matched_company['ticker'],
                                    'redirect_follow',
                                    f"Auto-corrected from {construction_method} which returned 404"
                                )
                                break  # Found working URL, stop trying
                            else:
                                logger.info(f"Skipped non-PR redirect result in fallback: {final_url}")

            # Fallback: If no From-field match OR no URLs matched, try URL-based matching (O(1))
            if not matched_urls:
                if matched_company:
                    logger.warning(f"Company {matched_company['ticker']} matched but no URLs matched its domain. Trying URL-based matching...")
                else:
                    logger.info("No From-field match, trying URL-based matching...")
                for url in email_meta['urls']:
                    if not is_press_release_url(url):
                        continue

                    company, matched, final_url = find_company_for_url(url)
                    if matched:
                        url_to_save = final_url if final_url else url
                        matched_urls.append((url_to_save, company))
                        logger.info(f"URL-based match: {company['ticker']} - {url_to_save}")

            # Additional fallback: If company matched but still no URLs, try following redirects
            if not matched_urls and matched_company:
                logger.warning(f"Attempting redirect follow fallback for {matched_company['ticker']}")
                for url in email_meta['urls']:
                    if not is_press_release_url(url):
                        continue

                    # Follow redirects to find actual press release URL
                    final_url = follow_redirect_url(url)
                    if final_url and final_url != url:
                        # Check if final URL belongs to company domain
                        try:
                            parsed = urlparse(final_url)
                            final_domain = parsed.netloc.lower()
                            company_domain = matched_company.get('ir_domain', '').lower()

                            if company_domain and (company_domain in final_domain or final_domain in company_domain):
                                matched_urls.append((final_url, matched_company))
                                logger.info(f"Redirect fallback success: {matched_company['ticker']} - {url} → {final_url}")
                                break  # Found one, that's enough
                        except:
                            continue

            logger.info(f"Filtered to {len(matched_urls)} company press release URLs (from {len(email_meta['urls'])} total)")

            # Process each matched URL
            direct_count = 0
            newswire_count = 0

            for url, company in matched_urls:
                url_type, url = classify_url(url)

                metadata = {
                    'email_key': key,
                    'extracted_at': datetime.utcnow().isoformat(),
                    'ticker': company['ticker'],
                    'company_name': company['name']
                }

                if url_type == 'direct':
                    save_direct_link(url, metadata)
                    direct_count += 1
                elif url_type == 'newswire':
                    queue_for_scraping(url, metadata)
                    newswire_count += 1

            # Mark as processed
            mark_as_processed(idempotency_key, {
                'email_key': key,
                'from_field': email_meta['from_field'],
                'subject': email_meta['subject'],
                'urls_found': len(email_meta['urls']),
                'urls_matched': len(matched_urls),
                'direct_links': direct_count,
                'newswire_links': newswire_count
            })

            logger.info(f"Completed: {direct_count} direct, {newswire_count} newswire")

        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}")
            batch_item_failures.append({
                'itemIdentifier': message_id
            })

    # Return partial batch response
    # Failed messages will be retried, successful ones deleted
    return {
        'batchItemFailures': batch_item_failures
    }
