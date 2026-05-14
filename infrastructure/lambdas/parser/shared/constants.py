"""
Shared Constants
================
SOLID: Single Responsibility - Centralized constants management
NO MAGIC NUMBERS OR STRINGS - All values defined here

Used by: Parser, Scraper, and other Lambda functions
"""

import re

# ============================================================================
# Known Slug URL Construction (per-company verified patterns)
# ============================================================================
# NOTE: "GCS" is NOT a special category - these constants are for companies
# with verified domain+slug URL patterns (individually tested per-company)

KNOWN_SLUG_PATH_TEMPLATE = '/news-releases/news-release-details/'
KNOWN_SLUG_WORD_COUNT = 7
KNOWN_SLUG_WORD_COUNT_9 = 9  # For companies using 9-word slugs (SLG, SUI)

# Legacy aliases for backward compatibility (use KNOWN_SLUG_* in new code)
GCS_URL_PATH_TEMPLATE = KNOWN_SLUG_PATH_TEMPLATE
GCS_SLUG_WORD_COUNT = KNOWN_SLUG_WORD_COUNT
GCS_SLUG_WORD_COUNT_9 = KNOWN_SLUG_WORD_COUNT_9

# Third-party hosting identifiers (for redirect following, NOT URL construction)
GCS_DOMAIN_IDENTIFIER = 'gcs-web.com'
GCS_NOTIFICATION_IDENTIFIER = 'notification'

# ============================================================================
# Brixmor/Terreno ASPX URL Construction
# ============================================================================

BRIXMOR_URL_PATH_TEMPLATE = '/news-presentations/press-releases/news-details/{year}/{slug}/default.aspx'
TERRENO_URL_PATH_TEMPLATE = '/news-presentations/press-releases/press-release/{year}/{slug}/default.aspx'

# ============================================================================
# Timeouts and TTL
# ============================================================================

# Parser timeouts
REDIRECT_TIMEOUT_SECONDS = 30
IDEMPOTENCY_TTL_DAYS = 30
URL_VALIDATION_TIMEOUT = 5

# Scraper timeouts
TIMEOUT_LONG = 30        # Main requests (Cloudflare challenges)
TIMEOUT_MEDIUM = 10      # Homepage warmup
TIMEOUT_SHORT = 5        # Quick pre-fetch requests
TIMEOUT_PLAYWRIGHT = 30  # Playwright page loads

# ============================================================================
# Content Extraction
# ============================================================================

MAX_WORDS = 2000  # Extract first 2000 words for newsletter summaries

# ============================================================================
# Page Validation Thresholds (bytes)
# ============================================================================

MIN_VALID_PAGE_SIZE = 5000   # Minimum size for valid press release (5KB)
MIN_PAGE_SIZE = 1000          # Minimum size to have any content (1KB)

# ============================================================================
# Human Behavior Simulation (seconds)
# ============================================================================

HUMAN_DELAY_MIN = 2  # Minimum human-like delay
HUMAN_DELAY_MAX = 5  # Maximum human-like delay

# Network timing simulation (seconds) - mimic real browser
DNS_LOOKUP_TIME = (0.05, 0.15)     # DNS resolution
TCP_HANDSHAKE_TIME = (0.1, 0.3)    # TCP connection
TLS_HANDSHAKE_TIME = (0.15, 0.4)   # TLS handshake

# ============================================================================
# Adaptive Selection
# ============================================================================

MIN_ATTEMPTS_FOR_ADAPTIVE = 3  # Minimum attempts before using adaptive selection
ADAPTIVE_SUCCESS_THRESHOLD = 0.7  # 70%+ success rate to use adaptive selection

# ============================================================================
# Newswire Domains (Redirects that need scraping)
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
# Redirect Domains (Follow to get final URL before matching)
# ============================================================================

REDIRECT_DOMAINS = {
    'ir.stockpr.com',  # Veris Residential and others use this redirect service
    'stockpr.com'
}

# ============================================================================
# Third-Party IR Platforms
# ============================================================================

THIRD_PARTY_IR_PLATFORMS = [
    'ir.stockpr.com',     # StockPR investor relations platform
    'ir.equisolve.com',   # Equisolve platform
    'notification.gcs-web.com',  # GCS notifications
    'q4inc.com',          # Q4 platform
]

# ============================================================================
# JavaScript-Rendered Companies
# ============================================================================
# SOLID: Open/Closed - Add companies here without modifying code

JAVASCRIPT_RENDERED_COMPANIES = {
    'EPRT'  # Essential Properties - SvelteKit framework
    # Add more tickers as needed
}

# ============================================================================
# URL Patterns
# ============================================================================

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

# ============================================================================
# Exclude Patterns
# ============================================================================
# Generated from analysis of 157 real S3 emails
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
    '/email-alert-unsubscription',

    # Email activation/verification (CRITICAL - 70 occurrences in real data)
    '/email-alert-activation/',  # 70 occurrences
    '/emailnotification/',
    '/email-activation/',
    '/alert-activation',
    '/activate',

    # Social media tracking
    '/linkedin', '/twitter', '/facebook',
    '/social', '/share',

    # Tracking pixels and analytics
    '/track/', '/pixel/', '/analytics/',
    '/beacon/', '/metrics/',

    # Company branding/boilerplate
    '/about', '/contact', '/careers',
    '/privacy', '/terms',

    # GCS notification infrastructure
    'notification.gcs-web.com/compose',  # Email composition interface
    'notification.gcs-web.com/settings', # User settings
]

# ============================================================================
# Search Engine Referrers
# ============================================================================
# Sites often whitelist these referrers

SEARCH_REFERRERS = [
    'https://www.google.com/search?q=investor+relations+press+release',
    'https://www.bing.com/search?q=corporate+news',
    'https://duckduckgo.com/?q=company+announcement'
]

# ============================================================================
# Confirmation/SEC Filing Keywords (SSOT)
# ============================================================================
# Used by: email-forwarder, parser
# Purpose: Filter out confirmation emails and SEC filings

CONFIRMATION_KEYWORDS = [
    # NOTE: Activation/verification keywords REMOVED so user can complete
    # email subscription flows (validate account, verify email, etc.)

    # ============================================================================
    # SEC Filing Filters (Block ALL SEC filings from enricher)
    # ============================================================================
    # Email forwarder forwards some to Outlook (8-K, 424, FWP)
    # But parser blocks ALL SEC filings from enricher/website
    # ONLY press releases go to enricher/website

    # Generic SEC filing announcement emails (catches all filing types)
    'published the following sec filing',  # "published the following SEC filing announcement"
    'sec filing announcement',             # Generic SEC filing alert
    'has filed',                           # "has filed a Form..."
    'filed a form',                        # Generic form filing mention (duplicate but more specific)

    # Insider ownership/beneficial ownership filings (NOT press releases)
    'form 4',                              # Insider trading statement
    'form 3',                              # Initial insider ownership
    'form 5',                              # Annual insider ownership
    'new form 4',                          # Email prefix variant
    'new form 3',
    'new form 5',
    'statement of changes in beneficial',  # Form 4 description
    'statement of beneficial ownership',   # Generic beneficial ownership
    'sc 13d',                              # Beneficial ownership filing
    'sc 13g',                              # Passive investor filing
    'schedule 13d',                        # Full name variant
    'schedule 13g',                        # Full name variant
    'amended statement of beneficial',     # SC 13D/A description

    # Quarterly/Annual reports (NOT press releases about events)
    'form 10-k',                           # Annual report
    'form 10-q',                           # Quarterly report
    'new form 10-k',
    'new form 10-q',
    '10-k (annual report)',                # Description variant
    '10-q (quarterly report)',             # Description variant

    # Proxy statements (NOT press releases)
    'def 14a',                             # Definitive proxy statement
    'defa14a',                             # Definitive additional proxy
    'dfan14a',                             # Definitive additional proxy solicitation
    'pre 14a',                             # Preliminary proxy statement
    'proxy statement (definitive)',        # Description variant
    'proxy statement (preliminary)',       # Description variant

    # Annual reports to shareholders (NOT press releases)
    'ars (annual report to security',     # ARS description
    'annual report to security holders',
    'form ars',                            # Form ARS (annual report to shareholders)
    'new form ars',                        # Email prefix variant

    # Form 144 - Pre-sale notice (insider trading intent)
    'form 144',                            # Beneficial ownership declaration
    'new form 144',                        # Email prefix variant

    # Material event reports (forwarded to email, but NOT enricher/website)
    'form 8-k',                            # Current report (material events)
    'new form 8-k',
    '8-k (current report',                 # Description variant
    'form 424',                            # Prospectus supplement (FIXED: was '424' - too broad)
    '424b',                                # 424B prospectus variants
    'fwp (',                               # Free writing prospectus (FIXED: require paren to avoid false positives)

    # Other non-press-release SEC filings
    'form s-3',                            # Registration statement (FIXED: was 's-3' - too broad)
    's-3 registration',                    # S-3 description
    'form s-8',                            # Employee stock plan registration (FIXED: was 's-8')
    's-8 registration',                    # S-8 description
    'filed with sec',                      # Generic SEC filing mention
    'sec filing',                          # Generic SEC filing mention
    'filed a form',                        # Generic form filing mention
]

# ============================================================================
# Logging Configuration
# ============================================================================

LOG_LEVEL_DEFAULT = 'INFO'
