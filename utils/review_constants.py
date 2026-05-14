"""
Review Email System - Centralized Constants

ALL configuration values for the review email feature in one place.
Change behavior by modifying these constants, not the code.
"""

# ═══════════════════════════════════════════════════════════
# GMAIL CONFIGURATION
# ═══════════════════════════════════════════════════════════

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
GMAIL_TOKEN_FILE = 'gmail-token.pickle'
GMAIL_CREDENTIALS_FILE = 'gmail-credentials.json'

# Security: Maximum email size to process (prevents DoS attacks)
MAX_EMAIL_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

# ═══════════════════════════════════════════════════════════
# SCREENSHOT CONFIGURATION
# ═══════════════════════════════════════════════════════════

SCREENSHOT_DIR = 'static/screenshots'
SCREENSHOT_WEB_PATH_PREFIX = 'screenshots'

# Screenshot dimensions (width x height)
SCREENSHOT_WIDTH = 600
SCREENSHOT_HEIGHT = 800

# JPEG quality (0-100, lower = smaller file size)
SCREENSHOT_QUALITY = 65

# Screenshot format
SCREENSHOT_FORMAT = 'jpeg'

# Wait time for page rendering before screenshot (milliseconds)
SCREENSHOT_RENDER_TIMEOUT_MS = 500

# ═══════════════════════════════════════════════════════════
# GMAIL INBOX SCAN CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Maximum number of emails to fetch per scan
SCAN_MAX_RESULTS_ALL_TIME = 100
SCAN_MAX_RESULTS_24H = 50
SCAN_MAX_RESULTS_7D = 50

# Default max results for manual scan (gmail_to_review.py)
SCAN_DEFAULT_MAX_RESULTS = 50

# Progress polling interval for frontend (milliseconds)
SCAN_PROGRESS_POLL_INTERVAL_MS = 500

# Auto-refresh interval for processing emails (milliseconds)
SCAN_AUTO_REFRESH_INTERVAL_MS = 30000  # 30 seconds

# ═══════════════════════════════════════════════════════════
# PRESS RELEASE PROCESSING CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Number of characters to save as preview in content field
PR_CONTENT_PREVIEW_LENGTH = 1000

# Maximum words to save in full_text field
MAX_PRESS_RELEASE_WORDS = 2000

# Status check interval when processing in background (milliseconds)
PROCESSING_STATUS_CHECK_INTERVAL_MS = 3000

# Timeout before auto-reload after background processing starts (milliseconds)
PROCESSING_TIMEOUT_MS = 10000  # 10 seconds

# Delay before removing deleted row from UI (milliseconds)
DELETE_ROW_FADE_DELAY_MS = 2000  # 2 seconds

# Scraper headless mode (False = visible browser, bypasses detection)
SCRAPER_HEADLESS_MODE = False

# ═══════════════════════════════════════════════════════════
# REVIEW EMAIL STATUS VALUES
# ═══════════════════════════════════════════════════════════

class ReviewEmailStatus:
    """Valid status values for ReviewEmail model"""
    PENDING = 'pending'
    PROCESSING = 'processing'
    ADDED = 'added'
    DELETED = 'deleted'
    FAILED = 'failed'
    LANDING_PAGE = 'landing_page'  # Landing page detected (needs manual triage)
    FAILED_MATCH = 'failed_match'  # Playwright fuzzy match failed

# ═══════════════════════════════════════════════════════════
# ERROR MESSAGES
# ═══════════════════════════════════════════════════════════

class ReviewEmailErrors:
    """Standard error messages for review email operations"""
    NOT_FOUND = 'Review email not found'
    ALREADY_PROCESSING = 'Email already {status}'
    SCAN_IN_PROGRESS = 'Scan already in progress'
    NO_SCAN_IN_PROGRESS = 'No scan in progress'
    EXTRACTION_FAILED = 'Failed to extract PR URL'
    UNSAFE_URL = 'Blocked unsafe URL: {url}'
    NO_COMPANY_MATCH = 'Could not match company'
    FETCH_FAILED = 'Failed to fetch press release content'
    EMAIL_TOO_LARGE = 'Email too large ({size_mb:.1f}MB), skipping'
