"""
Parser - Private Company Filter
================================
Filter private companies from matching results.

Private companies are identified by:
1. is_public: false attribute in DynamoDB
2. Z-prefixed tickers (convention for non-public companies)

SOLID: Single Responsibility - Only filters private companies
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def is_private_company(company: dict) -> bool:
    """
    Check if company is private (should be excluded from matching).

    Private companies identified by:
    1. is_public: false attribute
    2. Z-prefixed tickers

    Args:
        company: Company dict from DynamoDB

    Returns:
        bool: True if company is private (should be excluded)
    """
    if not company:
        return False

    # Check is_public attribute (explicit flag)
    if company.get('is_public') is False:
        return True

    # Check Z-prefix ticker (convention for private companies)
    ticker = company.get('ticker', '')
    if ticker and ticker.upper().startswith('Z'):
        return True

    return False


def filter_private_company(company: dict, context: str = '') -> Optional[dict]:
    """
    Filter out private company from match result.

    Args:
        company: Company dict (or None)
        context: Logging context (e.g., "GSI domain match")

    Returns:
        dict: Same company if public, None if private
    """
    if not company:
        return None

    if is_private_company(company):
        ticker = company.get('ticker', 'UNKNOWN')
        logger.info(f"Filtered private company: {ticker} ({context})")
        return None

    return company
