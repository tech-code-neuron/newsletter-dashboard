"""
Parser - Company Index Builder
===============================
Build O(1) lookup indices for company matching

SOLID Principles:
- Single Responsibility: Only builds indices
- Performance: O(1) lookups using dictionary indices

Last Created: 2026-03-11
"""

import logging
from typing import Tuple, Dict
from .domain_extraction import extract_all_domains_from_company
from .name_normalization import normalize_company_name
from .company_filter import is_private_company

logger = logging.getLogger()


def build_company_indices(companies: list) -> Tuple[Dict[str, str], Dict[str, dict], Dict[str, dict]]:
    """
    Build O(1) lookup indices for company matching

    Single Responsibility: Only builds indices

    Creates three indices:
        - DOMAIN_TO_TICKER_INDEX: domain → ticker (O(1))
        - TICKER_TO_COMPANY_INDEX: ticker → company (O(1))
        - COMPANIES_BY_NORMALIZED_NAME: normalized_name → company (O(1))

    Args:
        companies: List of company dictionaries

    Returns:
        tuple: (domain_index, ticker_index, name_index)
    """
    domain_to_ticker = {}
    ticker_to_company = {}
    name_to_company = {}

    private_count = 0
    for company in companies:
        ticker = company.get('ticker')
        if not ticker:
            continue

        # Skip private companies (Z-prefixed or is_public=false)
        if is_private_company(company):
            private_count += 1
            continue

        # Ticker -> Company index
        ticker_to_company[ticker] = company

        # Domain → Ticker index
        domains = extract_all_domains_from_company(company)
        for domain in domains:
            if domain not in domain_to_ticker:
                domain_to_ticker[domain] = ticker
                logger.debug(f"Indexed domain: {domain} → {ticker}")

        # Normalized Name → Company index
        if company.get('company_name'):
            normalized = normalize_company_name(company['company_name'])
            if normalized and normalized not in name_to_company:
                name_to_company[normalized] = company
                logger.debug(f"Indexed name: {normalized} → {ticker}")

    logger.info(f"Built indices: {len(domain_to_ticker)} domains, {len(ticker_to_company)} tickers, {len(name_to_company)} names (skipped {private_count} private companies)")

    return domain_to_ticker, ticker_to_company, name_to_company
