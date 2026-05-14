"""
Enricher Constants - Single Source of Truth
============================================
All configuration constants for the enricher Lambda.
"""

# ============================================================================
# Timeouts
# ============================================================================

URL_VALIDATION_TIMEOUT = 5  # HTTP HEAD request timeout (seconds)
REDIRECT_TIMEOUT = 10  # Redirect following timeout (seconds)

# ============================================================================
# Limits
# ============================================================================

MAX_REDIRECTS = 5  # Maximum redirect chain length

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
# HTTP Status Codes
# ============================================================================

HTTP_STATUS_OK = 200
HTTP_STATUS_REDIRECT = 301
HTTP_STATUS_TEMP_REDIRECT = 302
HTTP_STATUS_FORBIDDEN = 403
HTTP_STATUS_NOT_FOUND = 404

# ============================================================================
# User Agent
# ============================================================================

USER_AGENT = 'Mozilla/5.0 (compatible; PressReleasePipeline/1.0; +https://your-domain.com)'

# ============================================================================
# URL Selection - Landing Page Detection
# ============================================================================
# MOVED to shared/landing_page_detector.py for single source of truth
# Import from there if needed:
#   from shared.landing_page_detector import GENERIC_PAGE_SEGMENTS

# ============================================================================
# URL Selection - Subject Line Noise Words
# ============================================================================

SUBJECT_NOISE_WORDS = {
    'the', 'of', 'and', 'to', 'a', 'an', 'in', 'for', 'on',
    'announces', 'reports', 'releases', 'inc', 'corp', 'corporation',
    'company', 'companies', 'press', 'release', 'news'
}

# ============================================================================
# URL Selection - Scoring Weights
# ============================================================================

SCORE_SUBJECT_MATCH = 100        # Points per subject word match
SCORE_PATH_DEPTH = 10            # Points per path segment
PENALTY_LANDING_PAGE = -500      # Penalty for landing pages
PENALTY_DB_MATCH = -800          # HEAVY penalty for exact DB press_release_url match
PENALTY_UTILITY_PAGE = -1000     # Exclusion penalty for utility pages
