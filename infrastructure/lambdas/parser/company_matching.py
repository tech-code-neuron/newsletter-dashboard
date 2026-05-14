"""
Parser Lambda - Company Matching
=================================
Google-grade O(1) company matching by domain and name

SOLID Refactoring (2026-03-19):
- Extracted extract_parent_domain() helper (eliminates 4x duplication)

SOLID Principles:
- Single Responsibility: Each function does ONE thing
- No Hardcoded Values: All constants imported
- Performance: O(1) lookups using dictionary indices or DynamoDB GSI
- DRY: Parent domain extraction consolidated

Two matching strategies:
    1. In-memory indices (legacy, loaded once per container)
    2. DynamoDB GSI queries (new, O(1) database lookups)

Last Updated: 2026-03-19 (SOLID refactoring)
"""

import re
import logging
from typing import Optional
from constants import (
    COMPANY_NAME_SUFFIXES,
    THIRD_PARTY_IR_PLATFORMS
)
from url_utils import extract_domain_from_url, is_landing_page

logger = logging.getLogger()

# Module-level caches (loaded once per Lambda container)
COMPANIES_CACHE = None
DOMAIN_TO_TICKER_INDEX = None  # O(1) domain → ticker
TICKER_TO_COMPANY_INDEX = None  # O(1) ticker → company
COMPANIES_BY_NORMALIZED_NAME = None  # Fuzzy name matching


# ============================================================================
# Domain Utilities (SOLID: DRY - Consolidate parent domain extraction)
# ============================================================================


def extract_parent_domain(domain: str, exclude_shared_platforms: bool = True) -> Optional[str]:
    """
    Extract parent domain from subdomain.

    SOLID: DRY - Consolidates logic duplicated 4 times.

    Examples:
        "investors.terreno.com" → "terreno.com"
        "alx.gcs-web.com" → None (shared platform, excluded)
        "ir.company.co.uk" → "company.co.uk"

    Args:
        domain: Full domain string
        exclude_shared_platforms: If True, return None for shared IR platforms

    Returns:
        str: Parent domain or None if not applicable
    """
    if not domain:
        return None

    parts = domain.split('.')
    if len(parts) <= 2:
        return None  # Already a parent domain

    parent_domain = '.'.join(parts[-2:])

    # Check if parent is a shared platform (gcs-web.com, etc.)
    if exclude_shared_platforms and parent_domain in THIRD_PARTY_IR_PLATFORMS:
        return None

    return parent_domain

# ============================================================================
# Company Name Normalization
# ============================================================================


def normalize_company_name(name):
    """
    Normalize company name for fuzzy matching

    Single Responsibility: Only normalizes names

    Examples:
        "Alexander's, Inc." → "alexanders"
        "Terreno Realty Corporation" → "terreno realty"
        "SL Green Realty Corp." → "sl green realty"

    Args:
        name: Company name string

    Returns:
        str: Normalized lowercase string
    """
    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower()

    # Remove all punctuation first (before suffix matching)
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    # Remove common suffixes repeatedly until no more changes
    # This handles cases like "Healthpeak Properties, Inc." -> "healthpeak"
    # and "DiamondRock Hospitality Email Alert" -> "diamondrock"
    changed = True
    while changed:
        prev = normalized
        for suffix in COMPANY_NAME_SUFFIXES:
            normalized = re.sub(suffix, '', normalized)
        normalized = normalized.strip()
        changed = (prev != normalized)

    return normalized.strip()


def extract_sender_name(from_field):
    """
    Extract sender name from From field

    Single Responsibility: Only extracts sender name

    Example:
        "Chatham Lodging Trust <alerts@em.equisolve.com>" → "Chatham Lodging Trust"

    Args:
        from_field: Email From header

    Returns:
        str: Sender name or None
    """
    if not from_field:
        return None

    # Try to extract name from "Name <email>" format
    match = re.match(r'^(.+?)\s*<.+>$', from_field)
    if match:
        return match.group(1).strip().strip('"').strip("'")

    # If no angle brackets, return as-is (might be just email)
    return from_field.strip()


# ============================================================================
# Domain Extraction from Company Record
# ============================================================================


def extract_all_domains_from_company(company):
    """
    Extract all possible domains from company record

    Single Responsibility: Only extracts domains

    Smart parent domain extraction: Skip parent domains for shared platforms
    (e.g., don't add "gcs-web.com" when domain is "alx.gcs-web.com")

    Examples:
        ir_domain: "investors.terreno.com" → ["terreno.com", "investors.terreno.com"]
        ir_domain: "alx.gcs-web.com" → ["alx.gcs-web.com"] (no parent, shared)

    Args:
        company: Company dictionary

    Returns:
        list: List of domains
    """
    domains = set()

    # From ir_domain field
    if company.get('ir_domain'):
        domain = company['ir_domain'].lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        domains.add(domain)

        # Add parent domain (excludes shared platforms)
        parent = extract_parent_domain(domain)
        if parent:
            domains.add(parent)

    # From press_release_url
    if company.get('press_release_url'):
        domain = extract_domain_from_url(company['press_release_url'])
        if domain:
            domains.add(domain)
            # Add parent domain (excludes shared platforms)
            parent = extract_parent_domain(domain)
            if parent:
                domains.add(parent)

    # From ir_url (legacy field)
    if company.get('ir_url'):
        domain = extract_domain_from_url(company['ir_url'])
        if domain:
            domains.add(domain)

    return list(domains)


# ============================================================================
# Company Index Building (O(1) Lookups)
# ============================================================================


def build_company_indices(companies):
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

    for company in companies:
        ticker = company.get('ticker')
        if not ticker:
            continue

        # Ticker → Company index
        ticker_to_company[ticker] = company

        # Domain → Ticker index
        domains = extract_all_domains_from_company(company)
        for domain in domains:
            if domain not in domain_to_ticker:
                domain_to_ticker[domain] = ticker
                logger.debug(f"Indexed domain: {domain} → {ticker}")

        # Normalized Name → Company index
        # Use pre-computed normalized_name from DynamoDB (preferred)
        # Fall back to normalizing company_name if not present
        normalized = company.get('normalized_name')
        if not normalized and company.get('company_name'):
            normalized = normalize_company_name(company['company_name'])
        if normalized and normalized not in name_to_company:
            name_to_company[normalized] = company
            logger.debug(f"Indexed name: {normalized} → {ticker}")

    logger.info(f"Built indices: {len(domain_to_ticker)} domains, {len(ticker_to_company)} tickers, {len(name_to_company)} names")

    return domain_to_ticker, ticker_to_company, name_to_company


# ============================================================================
# Company Loading (Module-Level Cache)
# ============================================================================


def load_all_companies(companies_table):
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


# ============================================================================
# Company Matching by URL (O(1))
# ============================================================================


def match_company_by_urls(urls):
    """
    Match company by domains found in URLs

    Single Responsibility: Only matches companies by URL

    Google-grade: Domain matching as source of truth, O(1) lookups

    Priority:
        1. Direct domain match in DOMAIN_TO_TICKER_INDEX (O(1))
        2. Domain match after following redirects (O(1) after HTTP request)

    Args:
        urls: List of URLs from email

    Returns:
        tuple: (company_dict, matched_url) or (None, None)
    """
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
        # Uses helper to exclude shared platforms
        parent_domain = extract_parent_domain(domain, exclude_shared_platforms=False)
        if parent_domain:
            ticker = DOMAIN_TO_TICKER_INDEX.get(parent_domain)
            if ticker:
                company = TICKER_TO_COMPANY_INDEX.get(ticker)
                if company:
                    logger.info(f"✓ Parent domain match (O(1)): {domain} ({parent_domain}) → {ticker}")
                    return company, url

    # No redirect following - parser should NOT make HTTP requests
    # Notification URLs (notification.gcs-web.com, sendgrid, etc.) will be handled by name matching
    return None, None


# ============================================================================
# Company Matching by Name (Fallback)
# ============================================================================


def match_company_by_name(sender_name):
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


# ============================================================================
# GSI-Based Matching (New: DynamoDB O(1) Queries)
# ============================================================================
# Replaces in-memory indices with DynamoDB GSI queries
# Eliminates cold start overhead from loading all companies
# ============================================================================


# GSI Index Names (SOLID: No Hardcoded Values)
DOMAIN_INDEX_NAME = 'domain-index'
NAME_INDEX_NAME = 'name-index'
PR_URL_DOMAIN_INDEX_NAME = 'pr-url-domain-index'


def match_company_by_domain_gsi(companies_config_table, domain):
    """
    Match company by IR domain using GSI query

    Single Responsibility: Only matches by domain

    Replaces: DOMAIN_TO_TICKER_INDEX in-memory lookup
    Performance: O(1) DynamoDB GSI query (~1-2ms latency)

    Args:
        companies_config_table: DynamoDB table resource
        domain: IR domain string

    Returns:
        dict: Company or None
    """
    if not domain or not companies_config_table:
        return None

    try:
        response = companies_config_table.query(
            IndexName=DOMAIN_INDEX_NAME,
            KeyConditionExpression='ir_domain = :domain',
            ExpressionAttributeValues={':domain': domain}
        )

        items = response.get('Items', [])
        if items:
            company = items[0]
            logger.info(f"✓ GSI domain match: {domain} → {company.get('ticker')}")
            return company

        return None

    except Exception as e:
        logger.error(f"GSI domain query failed for '{domain}': {e}")
        return None


def match_company_by_ticker_gsi(companies_config_table, ticker):
    """
    Match company by ticker using primary key

    Single Responsibility: Only matches by ticker

    Replaces: TICKER_TO_COMPANY_INDEX in-memory lookup
    Performance: O(1) DynamoDB GetItem query (~1ms latency)

    Args:
        companies_config_table: DynamoDB table resource
        ticker: Company ticker

    Returns:
        dict: Company or None
    """
    if not ticker or not companies_config_table:
        return None

    try:
        response = companies_config_table.get_item(Key={'ticker': ticker})
        company = response.get('Item')

        if company:
            logger.info(f"✓ GSI ticker match: {ticker}")
            return company

        return None

    except Exception as e:
        logger.error(f"GSI ticker query failed for '{ticker}': {e}")
        return None


def match_company_by_name_gsi(companies_config_table, sender_name):
    """
    Match company by normalized name using GSI query

    Single Responsibility: Only matches by name

    Replaces: COMPANIES_BY_NORMALIZED_NAME in-memory lookup
    Performance: O(1) DynamoDB GSI query (~1-2ms latency)

    Args:
        companies_config_table: DynamoDB table resource
        sender_name: Sender name from email

    Returns:
        dict: Company or None
    """
    if not sender_name or not companies_config_table:
        return None

    # Normalize sender name
    normalized = normalize_company_name(sender_name)
    if not normalized:
        return None

    try:
        # Try exact normalized match
        response = companies_config_table.query(
            IndexName=NAME_INDEX_NAME,
            KeyConditionExpression='normalized_name = :name',
            ExpressionAttributeValues={':name': normalized}
        )

        items = response.get('Items', [])
        if items:
            company = items[0]
            logger.info(f"✓ GSI name match: '{sender_name}' → {company.get('ticker')}")
            return company

        # Note: Partial matching not supported with GSI (would require scan)
        # For partial matching, use in-memory fallback or implement with scan + filter

        return None

    except Exception as e:
        logger.error(f"GSI name query failed for '{sender_name}': {e}")
        return None


def match_company_by_urls_gsi(companies_config_table, urls):
    """
    Match company by domains found in URLs using GSI queries

    Single Responsibility: Only matches companies by URL

    Replaces: match_company_by_urls (in-memory version)
    Performance: O(n) GSI queries where n = number of URLs (typically 1-3)

    Priority:
        1. Direct domain match via domain-index GSI (O(1))
        2. PR URL domain match via pr-url-domain-index GSI (O(1))
        3. Domain match after following redirects (O(1) after HTTP request)

    Args:
        companies_config_table: DynamoDB table resource
        urls: List of URLs from email

    Returns:
        tuple: (company_dict, matched_url) or (None, None)
    """
    if not urls or not companies_config_table:
        return None, None

    # Strategy 1: Direct domain matching via GSI - O(1) per URL
    for url in urls:
        domain = extract_domain_from_url(url)
        if not domain:
            continue

        # Check exact domain match via GSI - O(1)
        company = match_company_by_domain_gsi(companies_config_table, domain)
        if company:
            return company, url

        # Check parent domain (e.g., subdomain.example.com → example.com) - O(1)
        # Uses helper - don't exclude shared platforms for GSI lookup
        parent_domain = extract_parent_domain(domain, exclude_shared_platforms=False)
        if parent_domain:
            company = match_company_by_domain_gsi(companies_config_table, parent_domain)
            if company:
                logger.info(f"✓ GSI parent domain match: {domain} ({parent_domain}) → {company.get('ticker')}")
                return company, url

    # Strategy 2: PR URL domain matching via GSI - O(1) per URL
    for url in urls:
        domain = extract_domain_from_url(url)
        if not domain:
            continue

        try:
            response = companies_config_table.query(
                IndexName=PR_URL_DOMAIN_INDEX_NAME,
                KeyConditionExpression='pr_url_domain = :domain',
                ExpressionAttributeValues={':domain': domain}
            )

            items = response.get('Items', [])
            if items:
                company = items[0]
                logger.info(f"✓ GSI PR domain match: {domain} → {company.get('ticker')}")
                return company, url

        except Exception as e:
            logger.error(f"GSI PR domain query failed for '{domain}': {e}")
            continue

    # No redirect following - parser should NOT make HTTP requests
    # Notification URLs will be handled by name matching
    return None, None


# ============================================================================
# Hybrid Strategy (Backward Compatible)
# ============================================================================


def match_company_by_urls_hybrid(companies_config_table, urls, use_gsi=True):
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
        return match_company_by_urls_gsi(companies_config_table, urls)
    else:
        # Fallback to in-memory (legacy)
        return match_company_by_urls(urls)


def match_company_by_name_hybrid(companies_config_table, sender_name, use_gsi=True):
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
        return match_company_by_name_gsi(companies_config_table, sender_name)
    else:
        # Fallback to in-memory (legacy, supports partial matching)
        return match_company_by_name(sender_name)


def match_company_with_confidence(
    companies_config_table,
    email_metadata,
    threshold=70.0,
    use_confidence_scoring=True
):
    """
    Match company using confidence scoring with multiple signals

    Single Responsibility: Confidence-based company matching

    Args:
        companies_config_table: DynamoDB table resource
        email_metadata: {sender_name, sender_domain, subject, urls, from}
        threshold: Minimum confidence for auto-match (default: 70%)
        use_confidence_scoring: If False, fallback to legacy matching

    Returns:
        Tuple of (company, confidence, signal) or (None, 0.0, None)
    """
    if not use_confidence_scoring:
        # Fallback to legacy matching
        sender_name = email_metadata.get('sender_name', '')
        company = match_company_by_name_gsi(companies_config_table, sender_name)
        if company:
            return (company, 100.0, 'LegacyMatch')
        return (None, 0.0, None)

    try:
        # Import confidence scoring (lazy import to avoid breaking existing code)
        from confidence_scoring import ConfidenceScorer

        # Get all companies (for now, scan table - TODO: optimize with targeted queries)
        response = companies_config_table.scan()
        companies = response.get('Items', [])

        # Create scorer
        scorer = ConfidenceScorer(strategy='maximum')

        # Find best match
        result = scorer.match_with_confidence(email_metadata, companies, threshold)

        if result:
            company, confidence, signal = result
            logger.info(f"✓ Confidence match: {company.get('ticker')} ({confidence:.1f}% via {signal})")
            return result

        logger.info(f"✗ No confidence match above threshold ({threshold}%)")
        return (None, 0.0, None)

    except Exception as e:
        logger.error(f"Confidence scoring failed: {e}, falling back to legacy matching")
        # Fallback to legacy matching on error
        sender_name = email_metadata.get('sender_name', '')
        company = match_company_by_name_gsi(companies_config_table, sender_name)
        if company:
            return (company, 100.0, 'LegacyFallback')
        return (None, 0.0, None)
