"""
Parser - GSI-Based Company Matching
====================================
Company matching using DynamoDB GSI queries (O(1))

SOLID Principles:
- Single Responsibility: Only matches companies using GSI
- Performance: O(1) DynamoDB GSI queries (~1-2ms latency)
- Replaces in-memory indices with database queries

Last Created: 2026-03-11
"""

import logging
from typing import Optional, Tuple

from .company_filter import filter_private_company

logger = logging.getLogger()

# GSI Index Names (SOLID: No Hardcoded Values)
DOMAIN_INDEX_NAME = 'domain-index'
NAME_INDEX_NAME = 'name-index'
PR_URL_DOMAIN_INDEX_NAME = 'pr-url-domain-index'


def match_company_by_domain_gsi(companies_config_table, domain: str) -> Optional[dict]:
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
            company = filter_private_company(items[0], 'GSI domain match')
            if company:
                logger.info(f"GSI domain match: {domain} -> {company.get('ticker')}")
                return company

        return None

    except Exception as e:
        logger.error(f"GSI domain query failed for '{domain}': {e}")
        return None


def match_company_by_ticker_gsi(companies_config_table, ticker: str) -> Optional[dict]:
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
        item = response.get('Item')

        if item:
            company = filter_private_company(item, 'GSI ticker match')
            if company:
                logger.info(f"GSI ticker match: {ticker}")
                return company

        return None

    except Exception as e:
        logger.error(f"GSI ticker query failed for '{ticker}': {e}")
        return None


def match_company_by_name_gsi(companies_config_table, sender_name: str) -> Optional[dict]:
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
    from .name_normalization import normalize_company_name

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
            company = filter_private_company(items[0], 'GSI name match')
            if company:
                logger.info(f"GSI name match: '{sender_name}' -> {company.get('ticker')}")
                return company

        # Note: Partial matching not supported with GSI (would require scan)
        # For partial matching, use in-memory fallback or implement with scan + filter

        return None

    except Exception as e:
        logger.error(f"GSI name query failed for '{sender_name}': {e}")
        return None


def match_company_by_urls_gsi(companies_config_table, urls: list) -> Tuple[Optional[dict], Optional[str]]:
    """
    Match company by domains found in URLs using GSI queries

    Single Responsibility: Only matches companies by URL

    Replaces: match_company_by_urls (in-memory version)
    Performance: O(n) GSI queries where n = number of URLs (typically 1-3)

    Priority:
        1. Direct domain match via domain-index GSI (O(1))
        2. PR URL domain match via pr-url-domain-index GSI (O(1))
        3. Parent domain match (O(1))

    Args:
        companies_config_table: DynamoDB table resource
        urls: List of URLs from email

    Returns:
        tuple: (company_dict, matched_url) or (None, None)
    """
    from url_utils import extract_domain_from_url

    if not urls or not companies_config_table:
        return None, None

    # Strategy 1: Direct domain matching via GSI - O(1) per URL
    for url in urls:
        domain = extract_domain_from_url(url)
        if not domain:
            continue

        # Check exact domain match via GSI - O(1)
        # Note: filter_private_company already called in match_company_by_domain_gsi
        company = match_company_by_domain_gsi(companies_config_table, domain)
        if company:
            return company, url

        # Check parent domain (e.g., subdomain.example.com -> example.com) - O(1)
        parts = domain.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            # Note: filter_private_company already called in match_company_by_domain_gsi
            company = match_company_by_domain_gsi(companies_config_table, parent_domain)
            if company:
                logger.info(f"GSI parent domain match: {domain} ({parent_domain}) -> {company.get('ticker')}")
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
                company = filter_private_company(items[0], 'GSI PR domain match')
                if company:
                    logger.info(f"GSI PR domain match: {domain} -> {company.get('ticker')}")
                    return company, url

        except Exception as e:
            logger.error(f"GSI PR domain query failed for '{domain}': {e}")
            continue

    # No redirect following - parser should NOT make HTTP requests
    # Notification URLs will be handled by name matching
    return None, None


def match_company_by_pr_url_fallback(companies_config_table, urls: list) -> Tuple[Optional[dict], Optional[str]]:
    """
    Fallback: Match by extracting domain from press_release_url for companies
    missing pr_url_domain field.

    SOLID: Single Responsibility - Only fallback matching for incomplete configs
    Performance: O(n) scan - use ONLY when GSI matching fails

    Args:
        companies_config_table: DynamoDB table resource
        urls: List of URLs from email

    Returns:
        tuple: (company_dict, matched_url) or (None, None)
    """
    from url_utils import extract_domain_from_url

    if not urls or not companies_config_table:
        return None, None

    # Extract domains from email URLs
    email_domains = set()
    for url in urls:
        domain = extract_domain_from_url(url)
        if domain:
            email_domains.add(domain.lower())
            parts = domain.split('.')
            if len(parts) > 2:
                email_domains.add('.'.join(parts[-2:]).lower())

    if not email_domains:
        return None, None

    try:
        # Scan for companies with press_release_url but no pr_url_domain
        response = companies_config_table.scan(
            FilterExpression='attribute_exists(press_release_url) AND attribute_not_exists(pr_url_domain)',
            ProjectionExpression='ticker, company_name, press_release_url, #active, is_public, company_rss_feed_url',
            ExpressionAttributeNames={'#active': 'active'}
        )

        for company in response.get('Items', []):
            pr_url = company.get('press_release_url', '')
            if not pr_url:
                continue

            pr_domain = extract_domain_from_url(pr_url)
            if pr_domain and pr_domain.lower() in email_domains:
                matched = filter_private_company(company, 'press_release_url fallback')
                if matched:
                    logger.info(f"Fallback: press_release_url domain match: {pr_domain} -> {matched.get('ticker')}")
                    for url in urls:
                        if pr_domain.lower() in url.lower():
                            return matched, url
                    return matched, urls[0] if urls else None

        return None, None

    except Exception as e:
        logger.warning(f"Fallback matching failed: {e}")
        return None, None
