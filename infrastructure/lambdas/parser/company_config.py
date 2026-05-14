"""
Company Configuration - Single Source of Truth

All routing decisions query DynamoDB companies-config table.
Never hardcode company lists in constants.

This module provides a clean interface for querying company configuration
from DynamoDB, with TTL caching for performance and consistency.

Usage:
    from company_config import should_use_playwright, get_routing_decision

    if should_use_playwright(ticker):
        route_to_playwright_scraper(ticker, email)
    else:
        route_to_enricher(ticker, email)
"""

import boto3
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb')
companies_table = dynamodb.Table(
    os.environ.get('COMPANIES_TABLE', 'reitsheet-companies-config')
)

# TTL Cache configuration (5 minutes)
# This ensures config changes from Flask web interface propagate within 5 minutes
CACHE_TTL_SECONDS = int(os.environ.get('CONFIG_CACHE_TTL_SECONDS', '300'))

# Cache storage
_config_cache: Dict[str, Dict] = {}
_cache_timestamps: Dict[str, datetime] = {}


def get_company_config(ticker: str) -> Dict:
    """
    Get company configuration from DynamoDB with TTL caching

    Args:
        ticker: Company ticker symbol (e.g., 'EPRT', 'O', 'PK')

    Returns:
        Dict containing company configuration, or empty dict if not found

    Note:
        Results are cached for 5 minutes (configurable via CONFIG_CACHE_TTL_SECONDS env var)
        This ensures Flask web interface config changes propagate within 5 minutes
        Cache is cleared on Lambda cold start (natural refresh mechanism)
    """
    now = datetime.now()

    # Check if cached and still valid
    if ticker in _config_cache:
        cache_age = now - _cache_timestamps[ticker]
        if cache_age < timedelta(seconds=CACHE_TTL_SECONDS):
            logger.debug(f"Cache hit for {ticker} (age: {cache_age.total_seconds():.1f}s)")
            return _config_cache[ticker]
        else:
            logger.debug(f"Cache expired for {ticker} (age: {cache_age.total_seconds():.1f}s)")

    # Cache miss or expired - fetch from DynamoDB
    try:
        response = companies_table.get_item(Key={'ticker': ticker})
        if 'Item' not in response:
            logger.warning(f"Company {ticker} not found in DynamoDB")
            config = {}
        else:
            config = response['Item']

        # Update cache
        _config_cache[ticker] = config
        _cache_timestamps[ticker] = now
        logger.debug(f"Cached config for {ticker} (TTL: {CACHE_TTL_SECONDS}s)")

        return config

    except Exception as e:
        logger.error(f"Error getting config for {ticker}: {e}")
        # Return cached value if available, even if expired
        if ticker in _config_cache:
            logger.warning(f"Returning expired cache for {ticker} due to DynamoDB error")
            return _config_cache[ticker]
        return {}


def should_use_playwright(ticker: str) -> bool:
    """
    Check if company requires Playwright scraping

    Args:
        ticker: Company ticker symbol

    Returns:
        True if company uses playwright_scraper method, False otherwise

    Examples:
        >>> should_use_playwright('EPRT')
        True
        >>> should_use_playwright('ADC')
        False
    """
    config = get_company_config(ticker)
    method = config.get('url_construction_method', 'direct_url')
    return method == 'playwright_scraper'


def should_use_enricher(ticker: str) -> bool:
    """
    Check if company should go through enricher

    Args:
        ticker: Company ticker symbol

    Returns:
        True if company uses enricher-compatible method

    Note:
        Enricher handles: direct_url, gcs_*, redirect_follow, brixmor_aspx
        Playwright scraper bypasses enricher entirely
    """
    config = get_company_config(ticker)
    method = config.get('url_construction_method', 'direct_url')

    # Enricher handles everything EXCEPT playwright_scraper
    return method != 'playwright_scraper'


def get_routing_decision(ticker: str) -> str:
    """
    Get routing decision for ticker

    Args:
        ticker: Company ticker symbol

    Returns:
        'playwright' if uses Playwright scraper
        'enricher' if uses enricher
        'unknown' if company not found or invalid config

    Examples:
        >>> get_routing_decision('EPRT')
        'playwright'
        >>> get_routing_decision('ADC')
        'enricher'
        >>> get_routing_decision('INVALID')
        'unknown'
    """
    config = get_company_config(ticker)

    if not config:
        return 'unknown'

    if should_use_playwright(ticker):
        return 'playwright'
    elif should_use_enricher(ticker):
        return 'enricher'
    else:
        return 'unknown'


def get_url_construction_method(ticker: str) -> Optional[str]:
    """
    Get the URL construction method for a company

    Args:
        ticker: Company ticker symbol

    Returns:
        URL construction method string, or None if not found

    Examples:
        >>> get_url_construction_method('EPRT')
        'playwright_scraper'
        >>> get_url_construction_method('ADC')
        'direct_url'
        >>> get_url_construction_method('SLG')
        'gcs_9_word_slug'
    """
    config = get_company_config(ticker)
    return config.get('url_construction_method')


def get_sector_for_ticker(ticker: str) -> Optional[str]:
    """
    Get company sector from DynamoDB config (cached)

    Args:
        ticker: Company ticker symbol (e.g., 'AMT', 'O', 'EPRT')

    Returns:
        Sector string (e.g., 'Data Centers', 'Retail') or None if not found

    Examples:
        >>> get_sector_for_ticker('AMT')
        'Data Centers'
        >>> get_sector_for_ticker('O')
        'Retail'
    """
    config = get_company_config(ticker)
    return config.get('sector')


def clear_cache():
    """
    Clear the company config cache

    Useful for testing or if DynamoDB config changes during Lambda execution
    (though Lambda cold starts will naturally clear cache)
    """
    _config_cache.clear()
    _cache_timestamps.clear()
    logger.info("Company config cache cleared")


def get_cache_stats() -> Dict[str, int]:
    """
    Get cache statistics for monitoring

    Returns:
        Dict with cache size, expired entries, and oldest entry age
    """
    now = datetime.now()
    total_entries = len(_config_cache)
    expired_count = sum(
        1 for ticker in _cache_timestamps
        if (now - _cache_timestamps[ticker]) >= timedelta(seconds=CACHE_TTL_SECONDS)
    )
    oldest_age = max(
        [(now - ts).total_seconds() for ts in _cache_timestamps.values()],
        default=0
    )

    return {
        'total_entries': total_entries,
        'expired_entries': expired_count,
        'oldest_entry_age_seconds': int(oldest_age),
        'cache_ttl_seconds': CACHE_TTL_SECONDS
    }


# Backward compatibility - allow importing the table directly
# (Used by existing code that queries DynamoDB directly)
__all__ = [
    'get_company_config',
    'should_use_playwright',
    'should_use_enricher',
    'get_routing_decision',
    'get_url_construction_method',
    'get_sector_for_ticker',
    'clear_cache',
    'companies_table'
]
