"""
Parser - Domain Extraction from Company Records
================================================
Extract all possible domains from company configuration

SOLID Principles:
- Single Responsibility: Only extracts domains
- Smart parent domain logic: Skip shared platforms (gcs-web.com, etc.)

Last Created: 2026-03-11
"""

import logging
from typing import List
from constants import THIRD_PARTY_IR_PLATFORMS

logger = logging.getLogger()


def extract_all_domains_from_company(company: dict) -> List[str]:
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
    from url_utils import extract_domain_from_url

    domains = set()

    # From ir_domain field
    if company.get('ir_domain'):
        domain = company['ir_domain'].lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        domains.add(domain)

        # Add parent domain ONLY if not a shared platform
        parts = domain.split('.')
        if len(parts) > 2:
            parent_domain = '.'.join(parts[-2:])
            if parent_domain not in THIRD_PARTY_IR_PLATFORMS:
                domains.add(parent_domain)

    # From press_release_url
    if company.get('press_release_url'):
        domain = extract_domain_from_url(company['press_release_url'])
        if domain:
            domains.add(domain)
            # Add parent domain ONLY if not a shared platform
            parts = domain.split('.')
            if len(parts) > 2:
                parent_domain = '.'.join(parts[-2:])
                if parent_domain not in THIRD_PARTY_IR_PLATFORMS:
                    domains.add(parent_domain)

    # From ir_url (legacy field)
    if company.get('ir_url'):
        domain = extract_domain_from_url(company['ir_url'])
        if domain:
            domains.add(domain)

    return list(domains)
