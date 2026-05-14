"""
File Utilities for Review Email System

Centralized file path construction and management.
"""
import os
from utils.review_constants import SCREENSHOT_DIR, SCREENSHOT_WEB_PATH_PREFIX


def ensure_screenshot_directory():
    """Create screenshots directory if it doesn't exist"""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def get_screenshot_filename(gmail_message_id):
    """
    Generate screenshot filename from Gmail message ID.

    Args:
        gmail_message_id (str): Gmail message ID

    Returns:
        str: Screenshot filename (e.g., 'email_abc123.jpg')
    """
    return f"email_{gmail_message_id}.jpg"


def get_screenshot_full_path(gmail_message_id):
    """
    Get absolute filesystem path for screenshot.

    Args:
        gmail_message_id (str): Gmail message ID

    Returns:
        str: Absolute path (e.g., 'static/screenshots/email_abc123.jpg')
    """
    filename = get_screenshot_filename(gmail_message_id)
    return os.path.join(SCREENSHOT_DIR, filename)


def get_screenshot_web_path(gmail_message_id):
    """
    Get web-accessible path for screenshot (for HTML src attribute).

    Args:
        gmail_message_id (str): Gmail message ID

    Returns:
        str: Web path (e.g., 'screenshots/email_abc123.jpg')
    """
    filename = get_screenshot_filename(gmail_message_id)
    return f"{SCREENSHOT_WEB_PATH_PREFIX}/{filename}"


def delete_screenshot(screenshot_path):
    """
    Delete screenshot file if it exists.

    Args:
        screenshot_path (str): Web path or full path to screenshot

    Returns:
        bool: True if deleted, False if file didn't exist or error
    """
    if not screenshot_path:
        return False

    # Handle both web paths and full paths
    if screenshot_path.startswith(SCREENSHOT_WEB_PATH_PREFIX):
        # Convert web path to full path
        full_path = os.path.join('static', screenshot_path)
    else:
        full_path = screenshot_path

    if os.path.exists(full_path):
        try:
            os.remove(full_path)
            return True
        except Exception:
            return False

    return False
