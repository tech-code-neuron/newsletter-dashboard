"""
Enricher - Company Lookup
==========================
Retrieve company configuration from DynamoDB

SOLID Principles:
- Single Responsibility: Only retrieves company config
- Dependency Injection: Table can be injected for testing

Last Created: 2026-03-11
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger()

# Module-level table reference (set by initialize_tables)
COMPANIES_TABLE = None


def initialize_tables(companies_table):
    """
    Initialize companies table

    Single Responsibility: Only initializes table

    Args:
        companies_table: DynamoDB Table resource
    """
    global COMPANIES_TABLE
    COMPANIES_TABLE = companies_table
    logger.info("Companies table initialized")


def get_company_config(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get company configuration from DynamoDB

    Single Responsibility: Only retrieves company config

    Args:
        ticker: Company ticker symbol

    Returns:
        dict: Company configuration or None
    """
    if not COMPANIES_TABLE:
        logger.error("COMPANIES_TABLE not initialized")
        return None

    try:
        response = COMPANIES_TABLE.get_item(Key={'ticker': ticker})

        if 'Item' not in response:
            logger.warning(f"No company config found for {ticker}")
            return None

        return response['Item']

    except Exception as e:
        logger.error(f"Error fetching company config: {e}")
        return None
