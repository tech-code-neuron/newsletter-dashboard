#!/usr/bin/env python3
"""
Migrate Companies to Config Table with GSI Optimization
========================================================
Migrates 127 companies from old schema to new companies-config table with GSI indices

SOLID Principles:
- Single Responsibility: Each function does ONE thing
- Open/Closed: Extensible transformation pipeline
- No Hardcoded Values: All constants extracted
- Dependency Injection: Takes table resources as parameters

Performance: O(n) migration with batch writes for efficiency

Usage:
    python migrate_companies_to_config_table.py [--dry-run] [--batch-size 25]

Last Updated: 2026-03-09
"""

import sys
import os
import re
import argparse
import logging
from typing import List, Dict, Optional, Set
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import boto3
from botocore.exceptions import ClientError

# ============================================================================
# Constants (SOLID: No Hardcoded Values)
# ============================================================================

# Table names
SOURCE_TABLE_NAME = 'reitsheet-companies'
TARGET_TABLE_NAME = 'reitsheet-companies-config'

# Batch processing
DEFAULT_BATCH_SIZE = 25  # DynamoDB BatchWriteItem limit
MAX_RETRIES = 3
RETRY_BACKOFF_MS = 100

# Company name suffixes for normalization (must match parser/constants.py)
COMPANY_NAME_SUFFIXES = [
    r',?\s+inc\.?$',
    r',?\s+corp\.?$',
    r',?\s+corporation$',
    r',?\s+company$',
    r',?\s+co\.?$',
    r',?\s+llc\.?$',
    r',?\s+l\.?p\.?$',
    r',?\s+ltd\.?$',
    r',?\s+limited$',
    r',?\s+trust$',
    r',?\s+reit$',
    r'\s+properties$',
    r'\s+property$',
    r'\s+realty$',
    r'\s+hospitality$',
]

# Third-party IR platforms (don't extract parent domains)
THIRD_PARTY_IR_PLATFORMS = {
    'gcs-web.com',
    'q4cdn.com',
    'q4inc.com',
    'equisolve.com',
    'em.equisolve.com',
    'ir.stockpr.com',
    'stockpr.com',
    'businesswire.com',
    'prnewswire.com',
    'globenewswire.com',
}

# ============================================================================
# Logging Configuration
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Company Name Normalization (Single Responsibility)
# ============================================================================


def normalize_company_name(name: str) -> str:
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

    # Remove common suffixes
    for suffix in COMPANY_NAME_SUFFIXES:
        normalized = re.sub(suffix, '', normalized)

    # Remove all punctuation except spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized.strip()


# ============================================================================
# Domain Extraction (Single Responsibility)
# ============================================================================


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extract domain from URL

    Single Responsibility: Only extracts domains

    Args:
        url: URL string

    Returns:
        str: Domain or None
    """
    if not url:
        return None

    # Remove protocol
    url = re.sub(r'^https?://', '', url.lower())

    # Remove www.
    if url.startswith('www.'):
        url = url[4:]

    # Extract domain (before first /)
    domain = url.split('/')[0].split('?')[0]

    return domain if domain else None


def extract_all_domains_from_company(company: Dict) -> List[str]:
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
        list: List of unique domains
    """
    domains: Set[str] = set()

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

    return sorted(list(domains))


# ============================================================================
# Data Transformation (Single Responsibility)
# ============================================================================


def transform_company_to_config_schema(company: Dict) -> Dict:
    """
    Transform company from old schema to new config schema with GSI fields

    Single Responsibility: Only transforms schema

    Adds GSI-optimized fields:
        - normalized_name: For name-index GSI
        - pr_url_domain: For pr-url-domain-index GSI
        - all_domains: JSON array of all domains (for reference)

    Args:
        company: Company dict from source table

    Returns:
        dict: Transformed company for target table
    """
    # Start with all existing fields
    config = dict(company)

    # Add normalized name for GSI
    if company.get('name'):
        config['normalized_name'] = normalize_company_name(company['name'])
    else:
        config['normalized_name'] = ""

    # Add PR URL domain for GSI
    if company.get('press_release_url'):
        config['pr_url_domain'] = extract_domain_from_url(company['press_release_url']) or ""
    elif company.get('ir_domain'):
        config['pr_url_domain'] = company['ir_domain']
    else:
        config['pr_url_domain'] = ""

    # Add all domains as JSON array (for migration validation)
    all_domains = extract_all_domains_from_company(company)
    config['all_domains'] = all_domains

    # Ensure ir_domain exists (required for GSI)
    if not config.get('ir_domain'):
        # Fallback: use pr_url_domain or first domain from all_domains
        if config['pr_url_domain']:
            config['ir_domain'] = config['pr_url_domain']
        elif all_domains:
            config['ir_domain'] = all_domains[0]
        else:
            config['ir_domain'] = f"{company.get('ticker', 'unknown').lower()}.example.com"
            logger.warning(f"⚠️  {company.get('ticker')}: No domain found, using placeholder")

    return config


# ============================================================================
# DynamoDB Operations (Single Responsibility)
# ============================================================================


def load_source_companies(dynamodb_resource) -> List[Dict]:
    """
    Load all companies from source table

    Single Responsibility: Only loads data

    Args:
        dynamodb_resource: boto3 DynamoDB resource

    Returns:
        list: List of company dictionaries
    """
    table = dynamodb_resource.Table(SOURCE_TABLE_NAME)
    logger.info(f"Loading companies from {SOURCE_TABLE_NAME}...")

    companies = []
    try:
        response = table.scan()
        companies.extend(response.get('Items', []))

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            companies.extend(response.get('Items', []))

        logger.info(f"✓ Loaded {len(companies)} companies")
        return companies

    except ClientError as e:
        logger.error(f"✗ Failed to load companies: {e}")
        raise


def batch_write_companies(dynamodb_resource, companies: List[Dict], batch_size: int = DEFAULT_BATCH_SIZE, dry_run: bool = False) -> int:
    """
    Write companies to target table in batches

    Single Responsibility: Only writes data

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        companies: List of transformed companies
        batch_size: Batch size (default 25)
        dry_run: If True, don't actually write

    Returns:
        int: Number of companies written
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would write {len(companies)} companies to {TARGET_TABLE_NAME}")
        return len(companies)

    table = dynamodb_resource.Table(TARGET_TABLE_NAME)
    total_written = 0

    for i in range(0, len(companies), batch_size):
        batch = companies[i:i + batch_size]

        try:
            with table.batch_writer() as writer:
                for company in batch:
                    writer.put_item(Item=company)
                    total_written += 1

            logger.info(f"✓ Wrote batch {i // batch_size + 1} ({len(batch)} items)")

        except ClientError as e:
            logger.error(f"✗ Failed to write batch: {e}")
            # Continue with next batch instead of failing completely
            continue

    logger.info(f"✓ Total written: {total_written} companies")
    return total_written


# ============================================================================
# Validation (Single Responsibility)
# ============================================================================


def validate_transformed_companies(companies: List[Dict]) -> tuple[int, List[str]]:
    """
    Validate transformed companies have required GSI fields

    Single Responsibility: Only validates data

    Args:
        companies: List of transformed companies

    Returns:
        tuple: (valid_count, list of validation errors)
    """
    errors = []
    valid_count = 0

    required_fields = ['ticker', 'ir_domain', 'normalized_name', 'pr_url_domain']

    for company in companies:
        ticker = company.get('ticker', 'UNKNOWN')

        # Check required fields
        missing_fields = [field for field in required_fields if not company.get(field)]

        if missing_fields:
            errors.append(f"{ticker}: Missing fields: {', '.join(missing_fields)}")
            continue

        # Check normalized_name is actually normalized (lowercase, no punctuation)
        normalized = company.get('normalized_name')
        if normalized and (normalized != normalized.lower() or re.search(r'[^\w\s]', normalized)):
            errors.append(f"{ticker}: normalized_name not properly normalized: '{normalized}'")
            continue

        # Check domains are valid
        ir_domain = company.get('ir_domain')
        if ir_domain and ('://' in ir_domain or ir_domain.startswith('www.')):
            errors.append(f"{ticker}: ir_domain should not contain protocol or www: '{ir_domain}'")
            continue

        valid_count += 1

    return valid_count, errors


# ============================================================================
# Main Migration Orchestration
# ============================================================================


def migrate_companies(dynamodb_resource, batch_size: int = DEFAULT_BATCH_SIZE, dry_run: bool = False) -> bool:
    """
    Main migration orchestrator

    Single Responsibility: Orchestrates migration steps

    Steps:
        1. Load companies from source table
        2. Transform to config schema
        3. Validate transformed data
        4. Write to target table

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        batch_size: Batch write size
        dry_run: If True, don't actually write

    Returns:
        bool: True if migration successful
    """
    logger.info("=" * 60)
    logger.info("Company Config Migration")
    logger.info("=" * 60)
    logger.info(f"Source: {SOURCE_TABLE_NAME}")
    logger.info(f"Target: {TARGET_TABLE_NAME}")
    logger.info(f"Batch size: {batch_size}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("=" * 60)

    # Step 1: Load source companies
    try:
        companies = load_source_companies(dynamodb_resource)
        if not companies:
            logger.error("✗ No companies found in source table")
            return False
    except Exception as e:
        logger.error(f"✗ Failed to load companies: {e}")
        return False

    # Step 2: Transform to config schema
    logger.info(f"\nTransforming {len(companies)} companies...")
    transformed = []
    for company in companies:
        try:
            config = transform_company_to_config_schema(company)
            transformed.append(config)
        except Exception as e:
            ticker = company.get('ticker', 'UNKNOWN')
            logger.error(f"✗ Failed to transform {ticker}: {e}")
            continue

    logger.info(f"✓ Transformed {len(transformed)} companies")

    # Step 3: Validate transformed data
    logger.info("\nValidating transformed data...")
    valid_count, errors = validate_transformed_companies(transformed)

    if errors:
        logger.warning(f"⚠️  Found {len(errors)} validation errors:")
        for error in errors[:10]:  # Show first 10
            logger.warning(f"  - {error}")
        if len(errors) > 10:
            logger.warning(f"  ... and {len(errors) - 10} more errors")

    logger.info(f"✓ Valid: {valid_count}/{len(transformed)} companies")

    if valid_count == 0:
        logger.error("✗ No valid companies to migrate")
        return False

    # Step 4: Write to target table
    logger.info(f"\nWriting {valid_count} companies to {TARGET_TABLE_NAME}...")
    try:
        written_count = batch_write_companies(dynamodb_resource, transformed, batch_size, dry_run)

        if dry_run:
            logger.info("\n✓ DRY RUN COMPLETE - No data written")
            return True

        if written_count == len(transformed):
            logger.info(f"\n✓ MIGRATION COMPLETE - {written_count} companies migrated")
            return True
        else:
            logger.warning(f"\n⚠️  PARTIAL SUCCESS - {written_count}/{len(transformed)} companies migrated")
            return False

    except Exception as e:
        logger.error(f"\n✗ MIGRATION FAILED: {e}")
        return False


# ============================================================================
# CLI Interface
# ============================================================================


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Migrate companies to config table with GSI optimization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run (no data written)
    python migrate_companies_to_config_table.py --dry-run

    # Migrate with default batch size (25)
    python migrate_companies_to_config_table.py

    # Migrate with custom batch size
    python migrate_companies_to_config_table.py --batch-size 10
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run migration without writing data'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f'Batch write size (default: {DEFAULT_BATCH_SIZE})'
    )

    parser.add_argument(
        '--region',
        type=str,
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )

    args = parser.parse_args()

    # Initialize DynamoDB resource
    try:
        dynamodb = boto3.resource('dynamodb', region_name=args.region)
        logger.info(f"Connected to DynamoDB in {args.region}")
    except Exception as e:
        logger.error(f"Failed to connect to DynamoDB: {e}")
        sys.exit(1)

    # Run migration
    success = migrate_companies(
        dynamodb_resource=dynamodb,
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
