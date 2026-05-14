"""
Sector Lookup Utility
=====================
Provides sector lookup for the social media pipeline.
Uses in-memory caching for efficiency.

Usage:
    from shared.sector_utils import get_sector_for_ticker
    sector = get_sector_for_ticker('AMT')  # Returns 'Data Centers'
"""

import boto3
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

dynamodb = boto3.resource('dynamodb')
_companies_table = None
_sector_cache = {}


def _get_table():
    """Lazy-load companies config table."""
    global _companies_table
    if _companies_table is None:
        table_name = os.environ.get('COMPANIES_TABLE', 'reitsheet-companies-config')
        _companies_table = dynamodb.Table(table_name)
    return _companies_table


def get_sector_for_ticker(ticker: str) -> Optional[str]:
    """
    Get sector for ticker from DynamoDB config.

    Results are cached in-memory for Lambda lifecycle.

    Args:
        ticker: Company ticker symbol (e.g., 'AMT', 'O', 'EPRT')

    Returns:
        Sector string (e.g., 'Data Centers', 'Retail') or None if not found
    """
    if not ticker:
        return None

    ticker = ticker.upper()

    if ticker in _sector_cache:
        return _sector_cache[ticker]

    try:
        response = _get_table().get_item(Key={'ticker': ticker})
        sector = response.get('Item', {}).get('sector')
        _sector_cache[ticker] = sector
        return sector
    except Exception as e:
        logger.warning(f"Failed to get sector for {ticker}: {e}")
        return None


def clear_cache():
    """Clear sector cache (useful for testing)."""
    global _sector_cache
    _sector_cache = {}
