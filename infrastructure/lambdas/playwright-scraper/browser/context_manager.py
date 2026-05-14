"""
Browser Context Manager - Playwright Browser Setup
====================================================
Extracted from handler.py (lines 267-298)

SOLID: Single Responsibility - Only handles browser context creation
DRY: Constants imported from centralized config.py

Last Updated: 2026-03-19 (SOLID refactoring - centralized config)
"""

import logging
from browser.config import (
    BROWSER_HEADLESS,
    BROWSER_ARGS,
    USER_AGENT,
    VIEWPORT_WIDTH,
    VIEWPORT_HEIGHT,
    LOCALE
)

logger = logging.getLogger()


# ============================================================================
# Browser Context Creation
# ============================================================================

def create_browser_context(playwright):
    """
    Create browser context with stealth configuration

    SOLID: Single Responsibility - Only handles browser setup

    Args:
        playwright: Playwright instance

    Returns:
        tuple: (browser, context, page)
    """
    logger.info("🎬 Launching headless Chrome...")

    # Launch browser with anti-detection arguments
    browser = playwright.chromium.launch(
        headless=BROWSER_HEADLESS,
        args=BROWSER_ARGS
    )

    # Create context with realistic user agent
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT},
        locale=LOCALE
    )

    # Create new page
    page = context.new_page()

    logger.info("✓ Browser ready")
    return browser, context, page
