"""
Scraper configuration constants
Centralized configuration for all scraping operations (SOLID Principle)
"""
import os

# ═══════════════════════════════════════════════════════════
# HTTP TIMEOUTS (seconds)
# ═══════════════════════════════════════════════════════════
TIMEOUT_SHORT = int(os.getenv('SCRAPER_TIMEOUT_SHORT', '5'))
TIMEOUT_MEDIUM = int(os.getenv('SCRAPER_TIMEOUT_MEDIUM', '10'))
TIMEOUT_LONG = int(os.getenv('SCRAPER_TIMEOUT_LONG', '15'))

# ═══════════════════════════════════════════════════════════
# RATE LIMITING DELAYS (seconds)
# ═══════════════════════════════════════════════════════════
RATE_LIMIT_DELAY = int(os.getenv('SCRAPER_RATE_LIMIT_DELAY', '2'))
RATE_LIMIT_DELAY_SHORT = int(os.getenv('SCRAPER_RATE_LIMIT_DELAY_SHORT', '1'))

# ═══════════════════════════════════════════════════════════
# HTTP HEADERS
# ═══════════════════════════════════════════════════════════
USER_AGENT = os.getenv(
    'SCRAPER_USER_AGENT',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

# ═══════════════════════════════════════════════════════════
# SCRAPING LIMITS
# ═══════════════════════════════════════════════════════════
MAX_CONTAINERS_TO_PARSE = int(os.getenv('SCRAPER_MAX_CONTAINERS', '20'))

# ═══════════════════════════════════════════════════════════
# THREADING CONFIGURATION
# ═══════════════════════════════════════════════════════════
DEFAULT_BROWSER_WORKERS = 10   # Max concurrent browser instances
DEFAULT_RSS_WORKERS = 20       # Max concurrent RSS feed scrapers

# ═══════════════════════════════════════════════════════════
# CONTENT ANALYSIS
# ═══════════════════════════════════════════════════════════
MAX_WORDS_FOR_COMPARISON = 1000  # Used in fuzzy content matching

# ═══════════════════════════════════════════════════════════
# URL PATH DISCOVERY
# ═══════════════════════════════════════════════════════════
# Common press release page paths (tried in order)
# Used when automatic detection fails
COMMON_PRESS_RELEASE_PATHS = [
    '/press-releases',
    '/news-releases',
    '/news',
    '/press',
    '/news-events',
    '/newsroom'
]

# ═══════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════
SEPARATOR_LINE = '='*60  # Used for log formatting
