"""
Centralized path configuration for all directories and files.
Follows SOLID principles - single source of truth for all paths.

This module provides constants for all file paths used throughout the application.
Import these constants instead of hardcoding paths in your modules.

Example:
    from config.paths import DB_PATH, SCREENSHOT_DIR

    def save_to_database():
        engine = create_engine(f'sqlite:///{DB_PATH}')
"""
import os

# Base directory (project root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# DATA DIRECTORIES
# ============================================================================

DATA_DIR = os.path.join(BASE_DIR, 'data')
NEWSLETTERS_DIR = os.path.join(DATA_DIR, 'newsletters')

# Database
DB_PATH = os.path.join(DATA_DIR, 'reit_newsletter.db')
DB_URL = f'sqlite:///{DB_PATH}'

# ============================================================================
# STATIC DIRECTORIES (Web-accessible files)
# ============================================================================

STATIC_DIR = os.path.join(BASE_DIR, 'static')
SCREENSHOT_DIR = os.path.join(STATIC_DIR, 'screenshots')

# Web paths (for HTML templates)
SCREENSHOT_WEB_PATH = '/static/screenshots'

# ============================================================================
# TEMPLATE DIRECTORIES
# ============================================================================

TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

# ============================================================================
# LOG DIRECTORIES
# ============================================================================

LOGS_DIR = os.path.join(BASE_DIR, 'logs')
DISCOVERY_LOG_PATH = os.path.join(LOGS_DIR, 'discovery.log')

# ============================================================================
# CONFIG DIRECTORIES
# ============================================================================

CONFIG_DIR = os.path.join(BASE_DIR, 'config')
PLATFORM_CONFIG_PATH = os.path.join(CONFIG_DIR, 'platform_config.py')

# ============================================================================
# GMAIL CREDENTIALS
# ============================================================================

GMAIL_CREDENTIALS_PATH = os.path.join(BASE_DIR, 'gmail-credentials.json')
GMAIL_TOKEN_PATH = os.path.join(BASE_DIR, 'gmail-token.pickle')

# ============================================================================
# ENSURE REQUIRED DIRECTORIES EXIST
# ============================================================================

# Create directories if they don't exist
_REQUIRED_DIRS = [
    DATA_DIR,
    NEWSLETTERS_DIR,
    STATIC_DIR,
    SCREENSHOT_DIR,
    LOGS_DIR,
]

for directory in _REQUIRED_DIRS:
    os.makedirs(directory, exist_ok=True)
