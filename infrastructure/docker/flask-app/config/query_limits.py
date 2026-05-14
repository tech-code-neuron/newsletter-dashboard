"""
Query Limits Configuration

SOLID Principle: Extract all magic numbers to named constants.
Changes to pagination/limits should be made here, not scattered in code.
"""

# ============================================================================
# PAGINATION LIMITS
# ============================================================================

# Dashboard limits
DASHBOARD_RECENT_RELEASES_LIMIT = 25
DASHBOARD_RECENT_NEWSLETTERS_LIMIT = 5

# Company limits
MAX_COMPANIES_DISPLAY = 1000  # Safety limit (REITs are finite, ~200 total)
MAX_COMPANIES_AUTOCOMPLETE = 1000  # For autocomplete dropdowns

# Press release limits
MAX_PRESS_RELEASES_PER_PAGE = 500  # Main listing page
MAX_ARCHIVED_RELEASES = 200  # Archived releases tab
COMPANY_DETAIL_RELEASES_LIMIT = 50  # Company detail page
NEWSLETTERS_HISTORY_LIMIT = 30  # Newsletter list page
MANUAL_ENTRY_RECENT_LIMIT = 100  # Manual entry modal

# ============================================================================
# QUERY PERFORMANCE
# ============================================================================

# Database connection pool settings (set in models.py)
DB_POOL_SIZE = 10  # Keep 10 connections ready
DB_MAX_OVERFLOW = 20  # Allow 20 additional connections if needed

# ============================================================================
# SEARCH & AUTOCOMPLETE
# ============================================================================

MAX_AUTOCOMPLETE_RESULTS = 50  # Dropdown autocomplete results
SEARCH_RESULTS_PER_PAGE = 100  # Search results pagination

# ============================================================================
# FEED HEALTH MONITORING
# ============================================================================

STALE_FEED_DAYS = 90  # Flag feeds with no releases in 90+ days

# ============================================================================
# EMAIL PROCESSING
# ============================================================================

SCAN_DEFAULT_MAX_RESULTS = 50  # Default number of emails to scan per batch
SCAN_DEFAULT_DAYS_BACK = 7  # Default lookback period for email scanning
