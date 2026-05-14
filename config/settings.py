"""
Configuration settings for Press Release Pipeline
"""
from config.paths import DB_PATH as _DB_PATH

# Scraper Settings
SCRAPER_TIMEOUTS = {
    'page_load': 30000,  # Playwright page load timeout (ms)
    'http_request': 30,  # HTTP request timeout (seconds)
    'pdf_download': 20,  # PDF download timeout (seconds)
    'browser_launch': 60000,  # Browser launch timeout (ms)
}

SCRAPER_DEFAULTS = {
    'lookback_days': 14,  # Default days to look back for press releases
    'headless_browser': False,  # Use headless browser (set False for debugging)
    'max_pdf_pages': 5,  # Max pages to extract from PDF
    'max_pdf_words': 2000,  # Max words to extract from PDF
}

SCRAPER_PARALLELISM = {
    'max_browser_workers': 10,  # Max concurrent browser instances
    'max_rss_workers': 20,  # Max concurrent RSS scrapers
}

# Cookie Banner Settings
COOKIE_WAIT_TIME = 2000  # Wait time for dynamic cookie banners (ms)
SCROLL_WAIT_TIME = 3000  # Wait time after scrolling (ms)

# Database Settings
DB_PATH = _DB_PATH  # Imported from config.paths

# Flask Settings
FLASK_PORT = 5001  # Port 5000 conflicts with ControlCenter on macOS
FLASK_SECRET_KEY = 'dev-secret-key-change-in-production'  # Override with env var in production

# Logging
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
