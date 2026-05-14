"""
Parser - In-Memory Company Matching
====================================
Company matching using in-memory indices (legacy)

SOLID Principles:
- Single Responsibility: Only matches companies using in-memory indices
- O(1) Lookups: Domain/name matching via dictionary indices

Last Created: 2026-03-11
"""

import logging
from typing import Tuple, Optional
from .index_builder import build_company_indices
from .name_normalization import normalize_company_name

logger = logging.getLogger()

# ============================================================================
# Module-Level Caches (Loaded Once Per Lambda Container)
# ============================================================================

COMPANIES_CACHE = None
DOMAIN_TO_TICKER_INDEX = None  # O(1) domain → ticker
TICKER_TO_COMPANY_INDEX = None  # O(1) ticker → company
COMPANIES_BY_NORMALIZED_NAME = None  # Fuzzy name matching


def load_all_companies(companies_table) -> Tuple[list, dict, dict, dict]:
    """
    Load all companies from DynamoDB and build indices

    Single Responsibility: Only loads and caches companies

    Uses module-level cache (loaded once per Lambda container)

    Args:
        companies_table: DynamoDB table resource

    Returns:
        tuple: (companies_list, domain_index, ticker_index, name_index)
    """
    global COMPANIES_CACHE, DOMAIN_TO_TICKER_INDEX, TICKER_TO_COMPANY_INDEX, COMPANIES_BY_NORMALIZED_NAME

    # Return cached if available
    if COMPANIES_CACHE is not None:
        return COMPANIES_CACHE, DOMAIN_TO_TICKER_INDEX, TICKER_TO_COMPANY_INDEX, COMPANIES_BY_NORMALIZED_NAME

    logger.info("Loading companies from DynamoDB (first time)...")

    # Scan all companies
    response = companies_table.scan()
    companies = response.get('Items', [])

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = companies_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        companies.extend(response.get('Items', []))

    # Build indices
    domain_index, ticker_index, name_index = build_company_indices(companies)

    # Cache everything
    COMPANIES_CACHE = companies
    DOMAIN_TO_TICKER_INDEX = domain_index
    TICKER_TO_COMPANY_INDEX = ticker_index
    COMPANIES_BY_NORMALIZED_NAME = name_index

    logger.info(f"Loaded {len(companies)} companies")

    return companies, domain_index, ticker_index, name_index


def match_company_by_urls(urls: list) -> Tuple[Optional[dict], Optional[str]]:
    """
    Match company by domains found in URLs

    Single Responsibility: Only matches companies by URL

    Google-grade: Domain matching as source of truth, O(1) lookups

    Priority:
        1. Direct domain match in DOMAIN_TO_TICKER_INDEX (O(1))
        2. Parent domain match (O(1))

    Args:
        urls: List of URLs from email

    Returns:
        tuple: (company_dict, matched_url) or (None, None)
    """
    from url_utils import extract_domain_from_url

    if not urls or not DOMAIN_TO_TICKER_INDEX or not TICKER_TO_COMPANY_INDEX:
        return None, None

    # Strategy 1: Direct domain matching (no redirects) - O(1)
    for url in urls:
        domain = extract_domain_from_url(url)
        if not domain:
            continue

        # Check exact domain match - O(1)
        ticker = DOMAIN_TO_TICKER_INDEX.get(domain)
        if ticker:
            company = TICKER_TO_COMPANY_INDEX.get(ticker)
            if company:
                logger.info(f"✓ Domain match (O(1)): {domain} → {ticker}")
                return company, url

        # Check parent domain (e.g., subdomain.example.com → example.com) - O(1)
        parts = domain.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            ticker = DOMAIN_TO_TICKER_INDEX.get(parent_domain)
            if ticker:
                company = TICKER_TO_COMPANY_INDEX.get(ticker)
                if company:
                    logger.info(f"✓ Parent domain match (O(1)): {domain} ({parent_domain}) → {ticker}")
                    return company, url

    # No redirect following - parser should NOT make HTTP requests
    # Notification URLs will be handled by name matching
    return None, None


def match_company_by_name(sender_name: str) -> Optional[dict]:
    """
    Match company by sender name (fallback when domain matching fails)

    Single Responsibility: Only matches by name

    Uses normalized name matching (punctuation-agnostic)

    Args:
        sender_name: Sender name from email

    Returns:
        dict: Company dict or None
    """
    if not sender_name or not COMPANIES_BY_NORMALIZED_NAME:
        return None

    # Normalize sender name
    normalized = normalize_company_name(sender_name)
    if not normalized:
        return None

    # Try exact normalized match
    company = COMPANIES_BY_NORMALIZED_NAME.get(normalized)
    if company:
        logger.info(f"✓ Name match (normalized): '{sender_name}' → {company.get('ticker')}")
        return company

    # Try partial match (sender contains company name)
    for name, comp in COMPANIES_BY_NORMALIZED_NAME.items():
        if name in normalized or normalized in name:
            logger.info(f"✓ Name match (partial): '{sender_name}' → {comp.get('ticker')}")
            return comp

    return None
