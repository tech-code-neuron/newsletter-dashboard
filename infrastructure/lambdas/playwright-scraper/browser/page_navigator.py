"""
Page Navigator - Playwright Page Navigation & Scraping
========================================================
Extracted from handler.py (lines 301-356)

SOLID: Single Responsibility - Only handles page navigation and content extraction
DRY: Constants imported from centralized config.py

Last Updated: 2026-03-19 (SOLID refactoring - centralized config)
"""

import logging
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from browser.config import (
    BROWSER_TIMEOUT_MS,
    SELECTOR_TIMEOUT_MS,
    MAX_PRESS_RELEASES,
    MIN_TITLE_LENGTH
)

logger = logging.getLogger()


# ============================================================================
# Page Navigation & Scraping
# ============================================================================

def scrape_press_releases(page, config):
    """
    Scrape press releases from JavaScript-rendered page

    SOLID: Single Responsibility - Only handles scraping logic

    UPDATED 2026-03-17: Supports generic scraping mode for companies without
    specific Playwright config. When use_generic_scraping=True, extracts all
    links from the page and lets fuzzy matching find the right one.

    Args:
        page: Playwright page object
        config: Company-specific configuration dict
            - url: Page URL to scrape
            - selector: CSS selector for press release links
            - wait_for: Selector to wait for before scraping
            - wait_network_idle: Whether to wait for network idle (optional)
            - title_cleanup: Optional title cleanup function name
            - use_generic_scraping: Use generic link extraction (fallback mode)

    Returns:
        list: Press releases [{title, url}, ...]
    """
    logger.info(f"🌐 Loading {config['url']}...")

    # Navigate to page with timeout fallback
    # Try networkidle first (best for JS-heavy sites), fallback to domcontentloaded if it hangs
    wait_until = 'networkidle' if config.get('wait_network_idle') else 'load'

    if wait_until == 'networkidle':
        try:
            page.goto(config['url'], wait_until='networkidle', timeout=BROWSER_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            # Fallback: networkidle hung (page keeps making requests), try domcontentloaded + wait
            logger.warning(f"⚠️ networkidle timed out for {config['url']}, falling back to domcontentloaded")
            page.goto(config['url'], wait_until='domcontentloaded', timeout=BROWSER_TIMEOUT_MS)
            page.wait_for_timeout(3000)  # Let JS render for 3 seconds
    else:
        page.goto(config['url'], wait_until=wait_until, timeout=BROWSER_TIMEOUT_MS)

    # Wait for content to load
    logger.info(f"⏳ Waiting for selector: {config['wait_for']}")
    page.wait_for_selector(config['wait_for'], timeout=SELECTOR_TIMEOUT_MS)

    # Extract press releases
    press_releases = []

    # Generic scraping mode: Extract ALL links from the page
    if config.get('use_generic_scraping'):
        logger.info(f"⚡ Using GENERIC scraping mode (no specific selector)")
        # Extract all links with href and text content
        links = page.query_selector_all('a[href]')
        logger.info(f"📄 Found {len(links)} total links on page")

        # Filter to likely press release links
        for link in links[:MAX_PRESS_RELEASES * 3]:  # Check more links in generic mode
            try:
                href = link.get_attribute('href')
                title = link.text_content().strip()

                # Skip empty/short titles
                if len(title) < MIN_TITLE_LENGTH:
                    continue

                # Skip navigation/utility links
                skip_patterns = ['login', 'sign up', 'contact', 'about', 'search',
                               'privacy', 'terms', 'cookie', 'subscribe', 'email alert',
                               'rss', 'sitemap', 'careers', 'home', 'back to']
                if any(p in title.lower() for p in skip_patterns):
                    continue

                # Skip non-PR URLs
                skip_url_patterns = ['/careers', '/contact', '/about-us', '/login',
                                   '/privacy', '/terms', '#', 'javascript:', 'mailto:']
                if any(p in href.lower() for p in skip_url_patterns):
                    continue

                # Build full URL if relative
                if href.startswith('/'):
                    url = f"https://{page.url.split('/')[2]}{href}"
                elif href.startswith('http'):
                    url = href
                else:
                    continue  # Skip relative paths like "../"

                press_releases.append({
                    'title': title,
                    'url': url
                })

            except Exception as e:
                logger.warning(f"⚠️  Error extracting link: {e}")
                continue

        logger.info(f"📄 Filtered to {len(press_releases)} likely PR links")

    else:
        # Company-specific selector mode (original behavior)
        links = page.query_selector_all(config['selector'])
        logger.info(f"📄 Found {len(links)} press release links")

        for link in links[:MAX_PRESS_RELEASES]:
            try:
                href = link.get_attribute('href')
                title = link.text_content().strip()

                # Skip if title too short (likely navigation link)
                if len(title) < MIN_TITLE_LENGTH:
                    continue

                # Build full URL if relative
                if href and href.startswith('/'):
                    url = f"https://{page.url.split('/')[2]}{href}"
                else:
                    url = href

                press_releases.append({
                    'title': title,
                    'url': url
                })

                logger.info(f"✓ Extracted: {title[:60]}...")

            except Exception as e:
                logger.warning(f"⚠️  Error extracting link: {e}")
                continue

    return press_releases
