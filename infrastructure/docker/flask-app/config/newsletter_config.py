"""
Newsletter configuration constants.
Centralizes newsletter-related settings (Single Source of Truth).
"""

# ------------------------------------------------------------------
# NEWSLETTER TYPES
# ------------------------------------------------------------------

NEWSLETTER_TYPE_MORNING = 'morning'
NEWSLETTER_TYPE_BREAKING = 'breaking'

# All valid newsletter types (Open/Closed: add new types here)
NEWSLETTER_TYPES = [
    NEWSLETTER_TYPE_MORNING,
    NEWSLETTER_TYPE_BREAKING
]


# ------------------------------------------------------------------
# TIME WINDOWS (Eastern Time)
# ------------------------------------------------------------------

# Morning newsletter: yesterday 12:01 AM - today 11:59:59 PM
MORNING_NEWSLETTER_START_HOUR = 0
MORNING_NEWSLETTER_START_MINUTE = 1
MORNING_NEWSLETTER_LOOKBACK_DAYS = 1

# Breaking newsletter: today 12:01 AM - today 8:00 AM
BREAKING_NEWSLETTER_START_HOUR = 0
BREAKING_NEWSLETTER_START_MINUTE = 1
BREAKING_NEWSLETTER_END_HOUR = 8
BREAKING_NEWSLETTER_END_MINUTE = 0


# ------------------------------------------------------------------
# MARKET HOURS (Eastern Time)
# ------------------------------------------------------------------

# Pre-market hours
TIME_BEFORE_MARKET_OPEN_HOUR = 9
TIME_BEFORE_MARKET_OPEN_MINUTE = 0

# After-market hours
TIME_AFTER_MARKET_CLOSE_HOUR = 16
TIME_AFTER_MARKET_CLOSE_MINUTE = 5


# ------------------------------------------------------------------
# PRESS RELEASE CONSTRAINTS
# ------------------------------------------------------------------

PRESS_RELEASE_TITLE_MAX_LENGTH = 500
PRESS_RELEASE_MAX_WORDS = 2000


# ------------------------------------------------------------------
# MANUAL ENTRY MESSAGES
# ------------------------------------------------------------------

MANUAL_ENTRY_NOTE = 'Manually entered (Cloudflare-blocked)'

# Duplicate warning template (used in flash messages)
DUPLICATE_WARNING_TEMPLATE = (
    '<strong>Duplicate Warning:</strong> This press release already exists. '
    '({match_type})<br>'
    '<a href="{edit_url}" style="color: #0066cc;">View existing release →</a>'
)
