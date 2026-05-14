"""
Parser Lambda - Constants
==========================
Single source of truth for all configuration values

SOLID: No Magic Numbers/Strings - All constants extracted
Last Updated: 2026-03-09
"""

import sys
import os

# Import CONFIRMATION_KEYWORDS from shared
# Works in both dev (shared in parent dir) and Lambda (shared at root level)
import importlib.util

# Try Lambda deployment structure first (shared at same level as this file)
_shared_constants_path = os.path.join(os.path.dirname(__file__), 'shared', 'constants.py')
if not os.path.exists(_shared_constants_path):
    # Fall back to development structure (shared in parent directory)
    _shared_constants_path = os.path.join(os.path.dirname(__file__), '..', 'shared', 'constants.py')

spec = importlib.util.spec_from_file_location("shared_constants", _shared_constants_path)
shared_constants = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared_constants)
_SHARED_CONFIRMATION_KEYWORDS = shared_constants.CONFIRMATION_KEYWORDS
_SHARED_ACTIVATION_KEYWORDS = shared_constants.ACTIVATION_KEYWORDS

# ============================================================================
# Known Slug URL Construction (per-company verified patterns)
# ============================================================================
# NOTE: "GCS" is NOT a special category - these constants are for companies
# with verified domain+slug URL patterns (individually tested per-company)

KNOWN_SLUG_PATH_TEMPLATE = '/news-releases/news-release-details/'
KNOWN_SLUG_WORD_COUNT = 7
KNOWN_SLUG_WORD_COUNT_LONG = 9  # For companies using 9-word slugs

# Legacy aliases for backward compatibility
GCS_URL_PATH_TEMPLATE = KNOWN_SLUG_PATH_TEMPLATE
GCS_SLUG_WORD_COUNT = KNOWN_SLUG_WORD_COUNT
GCS_SLUG_WORD_COUNT_LONG = KNOWN_SLUG_WORD_COUNT_LONG

# Third-party hosting identifiers (for redirect following, NOT URL construction)
GCS_DOMAIN_IDENTIFIER = 'gcs-web.com'
GCS_NOTIFICATION_IDENTIFIER = 'notification'

# ============================================================================
# Timeouts and TTL
# ============================================================================

REDIRECT_TIMEOUT_SECONDS = 30
REDIRECT_MAX_REDIRECTS = 5
URL_VALIDATION_TIMEOUT_SECONDS = 10  # Increased from 5s for better reliability
GCS_REDIRECT_TIMEOUT_SECONDS = 60  # GCS domains need longer timeout (high latency)
SENDGRID_REDIRECT_TIMEOUT_SECONDS = 15  # SendGrid tracking URLs
REDIRECT_MAX_RETRIES = 3  # Exponential backoff retry attempts
IDEMPOTENCY_TTL_DAYS = 30

# RSS Feed Settings
RSS_FETCH_TIMEOUT_SECONDS = 10  # Timeout for fetching RSS feed
RSS_MAX_RETRIES = 2  # Retry attempts for RSS fetch
RSS_ENTRY_MAX_AGE_DAYS = 7  # Only consider entries from last 7 days

# ============================================================================
# Newswire Domains (require scraping)
# ============================================================================

NEWSWIRE_DOMAINS = {
    'globenewswire.com',
    'businesswire.com',
    'prnewswire.com',
    'accesswire.com',
    'prnews.com',
    'marketwired.com'
}

# ============================================================================
# Redirect Domains (follow to get final URL)
# ============================================================================

REDIRECT_DOMAINS = {
    'ir.stockpr.com',
    'stockpr.com',
    'notification.gcs-web.com',
    'ct.sendgrid.net'
}

# ============================================================================
# Third-Party IR Platforms (shared hosting)
# ============================================================================

THIRD_PARTY_IR_PLATFORMS = {
    'ir.stockpr.com',
    'ir.equisolve.com',
    'notification.gcs-web.com',
    'q4inc.com',
    'q4web.com',
    'gcs-web.com',
    'equisolve.com',
    'investis.com',
    'irwebpage.com',
    'vcall.com'
}

# ============================================================================
# JavaScript-Rendered Companies (use Playwright)
# ============================================================================
#
# ⚠️ DEPRECATED: This constant is being phased out in favor of DynamoDB SSOT
#
# DO NOT UPDATE THIS LIST - Update DynamoDB instead:
#   aws dynamodb update-item \
#     --table-name reitsheet-companies-config \
#     --key '{"ticker": {"S": "TICKER"}}' \
#     --update-expression "SET url_construction_method = :method" \
#     --expression-attribute-values '{":method": {"S": "playwright_scraper"}}'
#
# NEW CODE: Use company_config.should_use_playwright(ticker) instead
#
# This constant remains for backward compatibility during migration.
# Will be removed after all code migrated to company_config module.
#
JAVASCRIPT_RENDERED_COMPANIES = {
    'EPRT',  # Essential Properties - SvelteKit framework
    'O',     # Realty Income - Cloudflare protection + inconsistent URL slugs
    'PK',    # Park Hotels - Investis.com tracking links require JavaScript
    'SAFE'   # Safehold - JavaScript-rendered press releases
}

# ============================================================================
# Press Release URL Patterns
# ============================================================================

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

# ============================================================================
# Press Release Link Text Keywords (Fuzzy Logic)
# ============================================================================
# Used to identify "View Press Release" links in HTML emails
# These get highest priority (score=100) in URL extraction

PRESS_RELEASE_LINK_KEYWORDS = [
    'press release',
    'full article',
    'read more',
    'view release',
    'full release',
    'full story',
    'read full',
    'click here to view',
    'view press',
    'read press',
    'full press',
    'view article',
    'read article',
    'click to read',
    'click to view'
]

# ============================================================================
# URL Exclusion Patterns
# ============================================================================
# Based on analysis of 157 real S3 emails + March 9-10 missed PR analysis
# See: scripts/analyze_all_s3_emails.py
#
# UPDATED 2026-03-10: Relaxed filtering to reduce false negatives
# - Removed email notification patterns (they often redirect to PRs)
# - Removed /default.aspx (often used for specific PR pages)
# - Made patterns more specific to avoid catching legitimate PR URLs

EXCLUDE_PATTERNS = [
    # Image/media files (definitely not PRs)
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
    '/logo', '/icon', '/image',
    '/alerts_logos/',

    # Direct unsubscribe/manage (not redirects)
    '/unsubscribe', '/preferences', '/optout',
    '/email-pref', '/manage-subscription',
    '/email-alert-unsubscription',

    # Email marketing platforms (footer/legal links, not PRs)
    'constantcontact.com',

    # Tracking pixels (not PRs)
    '/wf/open', '/wf/click',
    '/track', '/pixel', '/beacon',

    # CDN/assets (not PRs)
    'cloudfront.net',
    '/files/design/',
    '/files/theme/',
    '/sites/g/files/',

    # Social media (not PRs)
    'facebook.com', 'twitter.com', 'linkedin.com',
    'instagram.com', 'youtube.com',

    # Events/calendar (different from PRs)
    '/calendar/', '/event/', '/webcast/', '/conference/',
    '/events-presentations/',

    # Financial pages (not PR pages)
    '/financial-information', '/sec-filings',
]

# REMOVED PATTERNS (were too aggressive):
# - '/email-alert-activation/' - These redirect to PRs!
# - '/emailnotification/' - These redirect to PRs!
# - '/email-notification/' - These redirect to PRs!
# - 'token=' - Legitimate notification URLs use tokens
# - '/default.aspx' - Often used for specific PR pages
# - '/investors/$' - Moved to LANDING_PAGE_PATTERNS
# - '/investor-relations/$' - Moved to LANDING_PAGE_PATTERNS
# - '/press-releases/$' - Moved to LANDING_PAGE_PATTERNS
# - '/news-releases/$' - Moved to LANDING_PAGE_PATTERNS

# ============================================================================
# Landing Page Patterns
# ============================================================================
# Generic pages (not specific articles) - must end EXACTLY with these paths
# These are filtered BEFORE reaching Enricher (fixes 47% landing page issue)
#
# UPDATED 2026-03-10: Use regex to match ONLY homepage-level pages
# - Patterns now use regex $ anchor to match end of path ONLY
# - Will NOT match /news/article-123 or /press-releases/2026/01/
# - Removed /default.aspx (often used for specific PR pages)

LANDING_PAGE_PATTERNS = [
    r'/news/?$',                    # /news or /news/ but NOT /news/article-123
    r'/news-releases/?$',           # /news-releases/ but NOT /news-releases/2026/
    r'/press-releases/?$',          # /press-releases/ but NOT /press-releases/detail/
    r'/investor-relations/?$',      # /investor-relations/ but NOT /investor-relations/press/
    r'/investors/?$',               # /investors/ but NOT /investors/news/
    r'/newsroom/?$',                # /newsroom/ but NOT /newsroom/123
    r'/media/?$',                   # /media/ but NOT /media/release-456
    r'/news-events/?$',             # /news-events/ but NOT /news-events/2026/
]

# REMOVED: /default.aspx$ - This is often a specific press release page

# ============================================================================
# Email Confirmation Keywords (skip these emails)
# ============================================================================

# Re-export CONFIRMATION_KEYWORDS from shared/constants.py (SSOT)
# For backward compatibility with existing code
CONFIRMATION_KEYWORDS = _SHARED_CONFIRMATION_KEYWORDS

# Re-export ACTIVATION_KEYWORDS from shared/constants.py (SSOT)
# For filtering subscription activation/verification emails
ACTIVATION_KEYWORDS = _SHARED_ACTIVATION_KEYWORDS

# ============================================================================
# Company Name Normalization
# ============================================================================

COMPANY_NAME_SUFFIXES = [
    # Email alert suffixes (common in sender names like "DiamondRock Email Alert")
    r'\s+email\s+alerts?$',
    r'\s+alerts?$',
    r'\s+investor\s+relations$',
    r'\s+ir$',
    # Corporate suffixes
    r'\s+inc\.?$',
    r'\s+corp\.?$',
    r'\s+corporation$',
    r'\s+llc\.?$',
    r'\s+l\.p\.?$',
    r'\s+lp\.?$',
    r'\s+ltd\.?$',
    r'\s+limited$',
    r'\s+plc\.?$',
    r'\s+trust$',
    r'\s+reit$',
    # Property/real estate suffixes
    r'\s+properties$',
    r'\s+property$',
    r'\s+realty$',
    r'\s+hospitality$',
]

# ============================================================================
# URL Construction Methods
# ============================================================================
# Maps URL construction strategies to descriptions
#
# IMPORTANT: There is NO "GCS category" - each company with domain+slug
# construction is individually verified. Use known_slug_construction* names.

URL_CONSTRUCTION_METHODS = {
    'known_slug_construction': 'Domain + 7-word slug (verified per-company)',
    'known_slug_construction_9': 'Domain + 9-word slug (verified per-company)',
    'brixmor_aspx': 'Brixmor ASPX (Slug/default.aspx, case-sensitive)',
    'redirect_follow': 'Follow redirect to final URL',
    'playwright_scraper': 'JS-rendered, requires Playwright browser',
    'direct_url': 'Extract from email body (DEFAULT - safest)',
    # Legacy aliases (use new names in new configs)
    'gcs_hosted': 'Domain + 7-word slug (legacy alias)',
    'gcs_custom_domain': 'Domain + 7-word slug (legacy alias)',
    'gcs_9_word_slug': 'Domain + 9-word slug (legacy alias)',
}

# ============================================================================
# User Agents
# ============================================================================

# Full browser User-Agent for anti-bot protection (SendGrid, Cloudflare)
USER_AGENT_FULL = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# ============================================================================
# Logging
# ============================================================================

LOG_LEVEL_DEFAULT = 'INFO'
