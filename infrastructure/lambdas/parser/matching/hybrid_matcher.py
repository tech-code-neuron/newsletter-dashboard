"""
Parser - Hybrid Company Matching Strategy
==========================================
Selects between in-memory vs GSI matching strategies

SOLID Principles:
- Strategy Pattern: Switch between strategies without modifying callers
- Open/Closed: Can add new strategies without modifying existing code
- Single Responsibility: Only orchestrates matching strategy

Last Created: 2026-03-11
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger()


def match_company_by_urls_hybrid(companies_config_table, urls: list, use_gsi: bool = True) -> Tuple[Optional[dict], Optional[str]]:
    """
    Hybrid matching: Try GSI first, fallback to in-memory if needed

    Single Responsibility: Only orchestrates matching strategy

    Open/Closed: Can switch between strategies without modifying callers

    Use Cases:
        - use_gsi=True: GSI queries (new, no cold start overhead)
        - use_gsi=False: In-memory indices (legacy, backward compatible)

    Args:
        companies_config_table: DynamoDB table resource (required if use_gsi=True)
        urls: List of URLs from email
        use_gsi: If True, use GSI queries; if False, use in-memory

    Returns:
        tuple: (company_dict, matched_url) or (None, None)
    """
    if use_gsi and companies_config_table:
        from .gsi_matcher import match_company_by_urls_gsi
        return match_company_by_urls_gsi(companies_config_table, urls)
    else:
        # Fallback to in-memory (legacy)
        from .memory_matcher import match_company_by_urls
        return match_company_by_urls(urls)


def match_company_by_name_hybrid(companies_config_table, sender_name: str, use_gsi: bool = True) -> Optional[dict]:
    """
    Hybrid matching: Try GSI first, fallback to in-memory if needed

    Single Responsibility: Only orchestrates matching strategy

    Open/Closed: Can switch between strategies without modifying callers

    Use Cases:
        - use_gsi=True: GSI queries (new, exact match only)
        - use_gsi=False: In-memory indices (legacy, supports partial matching)

    Args:
        companies_config_table: DynamoDB table resource (required if use_gsi=True)
        sender_name: Sender name from email
        use_gsi: If True, use GSI queries; if False, use in-memory

    Returns:
        dict: Company or None
    """
    if use_gsi and companies_config_table:
        from .gsi_matcher import match_company_by_name_gsi
        return match_company_by_name_gsi(companies_config_table, sender_name)
    else:
        # Fallback to in-memory (legacy, supports partial matching)
        from .memory_matcher import match_company_by_name
        return match_company_by_name(sender_name)
