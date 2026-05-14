"""
Scraper Orchestrator - Strategy Pattern Router
===============================================
Orchestrates 4-layer scraping cascade with O(1) layer selection

SOLID Principles:
- Strategy Pattern: O(1) layer selection instead of if-elif cascade
- Single Responsibility: Only orchestrates scraping workflow
- Open/Closed: Add new layers by registering in LAYER_STRATEGIES dict

This replaces 67+ lines of if-elif cascade with clean Strategy Pattern

Last Created: 2026-03-11
"""

import logging
from typing import Optional, Tuple, Dict

from scraper_base import validate_page_content
from session_manager import extract_domain

# Import all layer implementations
from layer_curl_cffi import create_curl_cffi_layer
from layer_cloudscraper import create_cloudscraper_layer
from layer_undetected_chrome import create_undetected_chrome_layer
from layer_playwright import create_playwright_layer

logger = logging.getLogger()

# ============================================================================
# Layer Strategy Registry (Strategy Pattern)
# ============================================================================

# Layer strategies: O(1) lookup instead of if-elif cascade
LAYER_STRATEGIES = {
    'curl_cffi': create_curl_cffi_layer(),
    'cloudscraper': create_cloudscraper_layer(),
    'undetected_chrome': create_undetected_chrome_layer(),
    'playwright': create_playwright_layer()
}

# Layer cascade order (try in this order)
LAYER_CASCADE_ORDER = [
    'curl_cffi',        # Layer 1: TLS fingerprinting (fastest, 70-85%)
    'cloudscraper',     # Layer 2: Cloudflare solver (60-80%)
    'undetected_chrome',# Layer 3: Binary patches (85-95%)
    'playwright'        # Layer 4: Full arsenal (90%+, slowest)
]


# ============================================================================
# Adaptive Layer Selection (Advanced)
# ============================================================================

# Domain → best_layer cache (persists across Lambda warm starts)
# Populated based on historical success rates
DOMAIN_BEST_LAYER_CACHE: Dict[str, str] = {}


def get_best_layer_for_domain(domain: str) -> Optional[str]:
    """
    Get best-performing layer for domain (adaptive selection)

    Single Responsibility: Only retrieves best layer

    Uses historical success data to skip straight to best layer
    (e.g., if cloudscraper always succeeds for domain X, use it first)

    Args:
        domain: Domain name

    Returns:
        str: Best layer name or None
    """
    return DOMAIN_BEST_LAYER_CACHE.get(domain)


def record_layer_success(domain: str, layer_name: str, success: bool):
    """
    Record layer success for adaptive selection

    Single Responsibility: Only records success data

    Updates DOMAIN_BEST_LAYER_CACHE based on success patterns
    (Simple strategy: cache the first successful layer for each domain)

    Args:
        domain: Domain name
        layer_name: Layer name
        success: Whether layer succeeded
    """
    if success and domain not in DOMAIN_BEST_LAYER_CACHE:
        DOMAIN_BEST_LAYER_CACHE[domain] = layer_name
        logger.info(f"Cached best layer for {domain}: {layer_name}")


# ============================================================================
# Scraping Orchestration
# ============================================================================

def scrape_with_cascade(url: str, use_adaptive: bool = True) -> Tuple[Optional[str], Optional[str], str, bool]:
    """
    Scrape URL using 4-layer cascade with adaptive selection

    Single Responsibility: Orchestrates scraping cascade

    Strategy:
    1. Adaptive: Try best-performing layer first (if known)
    2. Standard cascade: Try all 4 layers in order
    3. Validate content after each layer
    4. Record success for future adaptive selection
    5. Return result

    Args:
        url: URL to scrape
        use_adaptive: Whether to use adaptive layer selection (default: True)

    Returns:
        tuple: (html_content, final_url, method_used, is_valid)
    """
    domain = extract_domain(url)

    # Strategy 1: Adaptive selection (skip to best layer)
    if use_adaptive and domain:
        best_layer = get_best_layer_for_domain(domain)
        if best_layer:
            logger.info(f"Adaptive: Trying {best_layer} first (historical success)")
            success, html, final_url, status = _try_layer(best_layer, url, domain)
            if success:
                return html, final_url, f'{best_layer}_adaptive', True

    # Strategy 2: Standard 4-layer cascade
    logger.info(f"Standard cascade: Trying all layers")

    for layer_name in LAYER_CASCADE_ORDER:
        logger.info(f"Trying Layer: {layer_name}")

        success, html, final_url, status = _try_layer(layer_name, url, domain)

        if success:
            logger.info(f"✅ {layer_name.upper()} VICTORY")
            return html, final_url, layer_name, True

        if status == 403:
            logger.warning(f"⚠️  {layer_name}: 403 - ESCALATING to next layer")

    # All layers failed
    logger.error(f"❌ TOTAL FAILURE - All 4 layers blocked for {url}")
    return None, None, 'all_layers_failed', False


def _try_layer(layer_name: str, url: str, domain: str) -> Tuple[bool, Optional[str], Optional[str], Optional[int]]:
    """
    Try scraping with one layer

    Single Responsibility: Only tries one layer

    Args:
        layer_name: Layer name
        url: URL to scrape
        domain: Domain name

    Returns:
        tuple: (success, html_content, final_url, status_code)
    """
    # Get layer strategy - O(1) lookup
    layer = LAYER_STRATEGIES.get(layer_name)

    if not layer:
        logger.error(f"Unknown layer: {layer_name}")
        return False, None, None, None

    # Execute layer scraping
    html, final_url, status = layer.scrape(url, domain)

    # Validate content
    if html and status == 200:
        is_valid, page_size, has_content = validate_page_content(html)
        if is_valid:
            # Record success for adaptive selection
            record_layer_success(domain, layer_name, True)
            logger.info(f"Page size: {page_size} bytes, valid: {is_valid}")
            return True, html, final_url, status

    # Record failure
    record_layer_success(domain, layer_name, False)
    return False, None, final_url, status


# ============================================================================
# Backwards Compatibility (Legacy Interface)
# ============================================================================

def scrape_press_release(url: str) -> Tuple[Optional[str], Optional[str], str, bool]:
    """
    Legacy interface for scraping press releases

    Single Responsibility: Provides backwards compatibility

    This maintains the same interface as the old handler.py function
    while using the new Strategy Pattern implementation

    Args:
        url: URL to scrape

    Returns:
        tuple: (html_content, final_url, method_used, is_valid)
    """
    return scrape_with_cascade(url, use_adaptive=True)


# ============================================================================
# Layer Registration (Open/Closed Principle)
# ============================================================================

def register_layer(layer_name: str, layer_instance, position: Optional[int] = None):
    """
    Register new scraper layer (Open/Closed Principle)

    Single Responsibility: Only registers layers

    Allows adding new layers without modifying existing code:
    - Add layer to LAYER_STRATEGIES dict
    - Optionally insert at specific position in cascade

    Example:
        new_layer = MyCustomLayer()
        register_layer('my_layer', new_layer, position=2)

    Args:
        layer_name: Layer name
        layer_instance: Layer instance
        position: Optional position in cascade (None = append)
    """
    # Register in strategy dict
    LAYER_STRATEGIES[layer_name] = layer_instance

    # Add to cascade order
    if position is not None and 0 <= position <= len(LAYER_CASCADE_ORDER):
        LAYER_CASCADE_ORDER.insert(position, layer_name)
    else:
        LAYER_CASCADE_ORDER.append(layer_name)

    logger.info(f"Registered layer: {layer_name} at position {position if position else 'end'}")


def unregister_layer(layer_name: str):
    """
    Unregister scraper layer

    Single Responsibility: Only unregisters layers

    Args:
        layer_name: Layer name to remove
    """
    if layer_name in LAYER_STRATEGIES:
        del LAYER_STRATEGIES[layer_name]

    if layer_name in LAYER_CASCADE_ORDER:
        LAYER_CASCADE_ORDER.remove(layer_name)

    logger.info(f"Unregistered layer: {layer_name}")
