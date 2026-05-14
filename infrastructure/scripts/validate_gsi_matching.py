#!/usr/bin/env python3
"""
Validate GSI Matching vs In-Memory Matching
============================================
Ensures DynamoDB GSI queries produce identical results to in-memory indices

SOLID Principles:
- Single Responsibility: Each function tests ONE matching strategy
- No Hardcoded Values: All constants extracted
- Dependency Injection: Takes table resources as parameters
- Open/Closed: Extensible test suite

Test Coverage:
    1. Domain-based matching (O(1) via domain-index GSI)
    2. Ticker-based matching (O(1) via primary key)
    3. Name-based matching (O(1) via name-index GSI)
    4. URL-based matching (O(1) via pr-url-domain-index GSI)

Success Criteria: 100% match rate between GSI and in-memory methods

Usage:
    python validate_gsi_matching.py [--sample-size 10] [--verbose]

Last Updated: 2026-03-09
"""

import sys
import os
import argparse
import logging
import random
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import boto3
from botocore.exceptions import ClientError

# ============================================================================
# Constants (SOLID: No Hardcoded Values)
# ============================================================================

# Table names
CONFIG_TABLE_NAME = 'reitsheet-companies-config'

# GSI names
DOMAIN_INDEX = 'domain-index'
NAME_INDEX = 'name-index'
PR_URL_DOMAIN_INDEX = 'pr-url-domain-index'

# Test configuration
DEFAULT_SAMPLE_SIZE = 10  # Number of random companies to test
MIN_SAMPLE_SIZE = 5
MAX_SAMPLE_SIZE = 127  # All companies

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
# In-Memory Index Builder (Baseline for Comparison)
# ============================================================================


def build_in_memory_indices(companies: List[Dict]) -> Tuple[Dict, Dict, Dict, Dict]:
    """
    Build in-memory indices (original method)

    Single Responsibility: Only builds indices

    Returns:
        tuple: (domain_to_ticker, ticker_to_company, name_to_company, pr_domain_to_ticker)
    """
    domain_to_ticker = {}
    ticker_to_company = {}
    name_to_company = {}
    pr_domain_to_ticker = {}

    for company in companies:
        ticker = company.get('ticker')
        if not ticker:
            continue

        # Ticker → Company index
        ticker_to_company[ticker] = company

        # Domain → Ticker index
        if company.get('ir_domain'):
            domain_to_ticker[company['ir_domain']] = ticker

        # Normalized Name → Company index
        if company.get('normalized_name'):
            name_to_company[company['normalized_name']] = company

        # PR URL Domain → Ticker index
        if company.get('pr_url_domain'):
            pr_domain_to_ticker[company['pr_url_domain']] = ticker

    logger.info(f"Built in-memory indices:")
    logger.info(f"  - {len(domain_to_ticker)} domains")
    logger.info(f"  - {len(ticker_to_company)} tickers")
    logger.info(f"  - {len(name_to_company)} names")
    logger.info(f"  - {len(pr_domain_to_ticker)} PR domains")

    return domain_to_ticker, ticker_to_company, name_to_company, pr_domain_to_ticker


# ============================================================================
# GSI Query Functions (New Method)
# ============================================================================


def query_by_domain_gsi(table, domain: str) -> Optional[Dict]:
    """
    Query company by domain using GSI

    Single Responsibility: Only queries by domain

    Args:
        table: DynamoDB table resource
        domain: IR domain

    Returns:
        dict: Company or None
    """
    try:
        response = table.query(
            IndexName=DOMAIN_INDEX,
            KeyConditionExpression='ir_domain = :domain',
            ExpressionAttributeValues={':domain': domain}
        )

        items = response.get('Items', [])
        return items[0] if items else None

    except ClientError as e:
        logger.error(f"GSI query failed for domain '{domain}': {e}")
        return None


def query_by_ticker_pk(table, ticker: str) -> Optional[Dict]:
    """
    Query company by ticker using primary key

    Single Responsibility: Only queries by ticker

    Args:
        table: DynamoDB table resource
        ticker: Company ticker

    Returns:
        dict: Company or None
    """
    try:
        response = table.get_item(Key={'ticker': ticker})
        return response.get('Item')

    except ClientError as e:
        logger.error(f"Primary key query failed for ticker '{ticker}': {e}")
        return None


def query_by_name_gsi(table, normalized_name: str) -> Optional[Dict]:
    """
    Query company by normalized name using GSI

    Single Responsibility: Only queries by name

    Args:
        table: DynamoDB table resource
        normalized_name: Normalized company name

    Returns:
        dict: Company or None
    """
    try:
        response = table.query(
            IndexName=NAME_INDEX,
            KeyConditionExpression='normalized_name = :name',
            ExpressionAttributeValues={':name': normalized_name}
        )

        items = response.get('Items', [])
        return items[0] if items else None

    except ClientError as e:
        logger.error(f"GSI query failed for name '{normalized_name}': {e}")
        return None


def query_by_pr_domain_gsi(table, pr_domain: str) -> Optional[Dict]:
    """
    Query company by PR URL domain using GSI

    Single Responsibility: Only queries by PR domain

    Args:
        table: DynamoDB table resource
        pr_domain: Press release URL domain

    Returns:
        dict: Company or None
    """
    try:
        response = table.query(
            IndexName=PR_URL_DOMAIN_INDEX,
            KeyConditionExpression='pr_url_domain = :domain',
            ExpressionAttributeValues={':domain': pr_domain}
        )

        items = response.get('Items', [])
        return items[0] if items else None

    except ClientError as e:
        logger.error(f"GSI query failed for PR domain '{pr_domain}': {e}")
        return None


# ============================================================================
# Validation Tests (Single Responsibility per Test)
# ============================================================================


def test_domain_matching(table, companies: List[Dict], domain_to_ticker: Dict, verbose: bool = False) -> Tuple[int, int, List[str]]:
    """
    Test domain-based matching: GSI vs in-memory

    Single Responsibility: Only tests domain matching

    Args:
        table: DynamoDB table resource
        companies: Sample companies to test
        domain_to_ticker: In-memory domain index
        verbose: If True, log each test

    Returns:
        tuple: (passed, failed, error_messages)
    """
    passed = 0
    failed = 0
    errors = []

    logger.info("\n[TEST 1] Domain-based matching (domain-index GSI)")

    for company in companies:
        domain = company.get('ir_domain')
        if not domain:
            continue

        ticker = company.get('ticker')

        # In-memory result
        in_memory_ticker = domain_to_ticker.get(domain)

        # GSI result
        gsi_result = query_by_domain_gsi(table, domain)
        gsi_ticker = gsi_result.get('ticker') if gsi_result else None

        # Compare
        if in_memory_ticker == gsi_ticker:
            passed += 1
            if verbose:
                logger.info(f"  ✓ {domain} → {ticker}")
        else:
            failed += 1
            error_msg = f"Domain '{domain}': in-memory={in_memory_ticker}, GSI={gsi_ticker}"
            errors.append(error_msg)
            logger.error(f"  ✗ {error_msg}")

    logger.info(f"Result: {passed} passed, {failed} failed")
    return passed, failed, errors


def test_ticker_matching(table, companies: List[Dict], ticker_to_company: Dict, verbose: bool = False) -> Tuple[int, int, List[str]]:
    """
    Test ticker-based matching: Primary key vs in-memory

    Single Responsibility: Only tests ticker matching

    Args:
        table: DynamoDB table resource
        companies: Sample companies to test
        ticker_to_company: In-memory ticker index
        verbose: If True, log each test

    Returns:
        tuple: (passed, failed, error_messages)
    """
    passed = 0
    failed = 0
    errors = []

    logger.info("\n[TEST 2] Ticker-based matching (primary key)")

    for company in companies:
        ticker = company.get('ticker')
        if not ticker:
            continue

        # In-memory result
        in_memory_company = ticker_to_company.get(ticker)
        in_memory_name = in_memory_company.get('name') if in_memory_company else None

        # Primary key result
        pk_result = query_by_ticker_pk(table, ticker)
        pk_name = pk_result.get('name') if pk_result else None

        # Compare
        if in_memory_name == pk_name:
            passed += 1
            if verbose:
                logger.info(f"  ✓ {ticker} → {in_memory_name}")
        else:
            failed += 1
            error_msg = f"Ticker '{ticker}': in-memory={in_memory_name}, PK={pk_name}"
            errors.append(error_msg)
            logger.error(f"  ✗ {error_msg}")

    logger.info(f"Result: {passed} passed, {failed} failed")
    return passed, failed, errors


def test_name_matching(table, companies: List[Dict], name_to_company: Dict, verbose: bool = False) -> Tuple[int, int, List[str]]:
    """
    Test name-based matching: GSI vs in-memory

    Single Responsibility: Only tests name matching

    Args:
        table: DynamoDB table resource
        companies: Sample companies to test
        name_to_company: In-memory name index
        verbose: If True, log each test

    Returns:
        tuple: (passed, failed, error_messages)
    """
    passed = 0
    failed = 0
    errors = []

    logger.info("\n[TEST 3] Name-based matching (name-index GSI)")

    for company in companies:
        normalized_name = company.get('normalized_name')
        if not normalized_name:
            continue

        ticker = company.get('ticker')

        # In-memory result
        in_memory_company = name_to_company.get(normalized_name)
        in_memory_ticker = in_memory_company.get('ticker') if in_memory_company else None

        # GSI result
        gsi_result = query_by_name_gsi(table, normalized_name)
        gsi_ticker = gsi_result.get('ticker') if gsi_result else None

        # Compare
        if in_memory_ticker == gsi_ticker:
            passed += 1
            if verbose:
                logger.info(f"  ✓ '{normalized_name}' → {ticker}")
        else:
            failed += 1
            error_msg = f"Name '{normalized_name}': in-memory={in_memory_ticker}, GSI={gsi_ticker}"
            errors.append(error_msg)
            logger.error(f"  ✗ {error_msg}")

    logger.info(f"Result: {passed} passed, {failed} failed")
    return passed, failed, errors


def test_pr_domain_matching(table, companies: List[Dict], pr_domain_to_ticker: Dict, verbose: bool = False) -> Tuple[int, int, List[str]]:
    """
    Test PR domain matching: GSI vs in-memory

    Single Responsibility: Only tests PR domain matching

    Args:
        table: DynamoDB table resource
        companies: Sample companies to test
        pr_domain_to_ticker: In-memory PR domain index
        verbose: If True, log each test

    Returns:
        tuple: (passed, failed, error_messages)
    """
    passed = 0
    failed = 0
    errors = []

    logger.info("\n[TEST 4] PR domain matching (pr-url-domain-index GSI)")

    for company in companies:
        pr_domain = company.get('pr_url_domain')
        if not pr_domain:
            continue

        ticker = company.get('ticker')

        # In-memory result
        in_memory_ticker = pr_domain_to_ticker.get(pr_domain)

        # GSI result
        gsi_result = query_by_pr_domain_gsi(table, pr_domain)
        gsi_ticker = gsi_result.get('ticker') if gsi_result else None

        # Compare
        if in_memory_ticker == gsi_ticker:
            passed += 1
            if verbose:
                logger.info(f"  ✓ {pr_domain} → {ticker}")
        else:
            failed += 1
            error_msg = f"PR domain '{pr_domain}': in-memory={in_memory_ticker}, GSI={gsi_ticker}"
            errors.append(error_msg)
            logger.error(f"  ✗ {error_msg}")

    logger.info(f"Result: {passed} passed, {failed} failed")
    return passed, failed, errors


# ============================================================================
# Main Validation Orchestration
# ============================================================================


def validate_gsi_matching(dynamodb_resource, sample_size: int = DEFAULT_SAMPLE_SIZE, verbose: bool = False) -> bool:
    """
    Main validation orchestrator

    Single Responsibility: Orchestrates validation tests

    Steps:
        1. Load all companies from config table
        2. Build in-memory indices (baseline)
        3. Select random sample
        4. Run 4 validation tests
        5. Report results

    Args:
        dynamodb_resource: boto3 DynamoDB resource
        sample_size: Number of companies to test
        verbose: If True, log each test case

    Returns:
        bool: True if all tests pass
    """
    logger.info("=" * 60)
    logger.info("GSI Matching Validation")
    logger.info("=" * 60)
    logger.info(f"Table: {CONFIG_TABLE_NAME}")
    logger.info(f"Sample size: {sample_size}")
    logger.info(f"Verbose: {verbose}")
    logger.info("=" * 60)

    table = dynamodb_resource.Table(CONFIG_TABLE_NAME)

    # Step 1: Load all companies
    logger.info("\nLoading companies...")
    try:
        response = table.scan()
        companies = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            companies.extend(response.get('Items', []))

        logger.info(f"✓ Loaded {len(companies)} companies")

    except ClientError as e:
        logger.error(f"✗ Failed to load companies: {e}")
        return False

    if not companies:
        logger.error("✗ No companies found in table")
        return False

    # Step 2: Build in-memory indices (baseline)
    logger.info("\nBuilding in-memory indices (baseline)...")
    domain_to_ticker, ticker_to_company, name_to_company, pr_domain_to_ticker = build_in_memory_indices(companies)

    # Step 3: Select random sample
    if sample_size > len(companies):
        sample_size = len(companies)

    sample = random.sample(companies, sample_size) if sample_size < len(companies) else companies
    logger.info(f"\nSelected {len(sample)} companies for testing")

    # Step 4: Run validation tests
    total_passed = 0
    total_failed = 0
    all_errors = []

    # Test 1: Domain matching
    passed, failed, errors = test_domain_matching(table, sample, domain_to_ticker, verbose)
    total_passed += passed
    total_failed += failed
    all_errors.extend(errors)

    # Test 2: Ticker matching
    passed, failed, errors = test_ticker_matching(table, sample, ticker_to_company, verbose)
    total_passed += passed
    total_failed += failed
    all_errors.extend(errors)

    # Test 3: Name matching
    passed, failed, errors = test_name_matching(table, sample, name_to_company, verbose)
    total_passed += passed
    total_failed += failed
    all_errors.extend(errors)

    # Test 4: PR domain matching
    passed, failed, errors = test_pr_domain_matching(table, sample, pr_domain_to_ticker, verbose)
    total_passed += passed
    total_failed += failed
    all_errors.extend(errors)

    # Step 5: Report results
    logger.info("\n" + "=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total tests: {total_passed + total_failed}")
    logger.info(f"Passed: {total_passed}")
    logger.info(f"Failed: {total_failed}")

    if total_failed == 0:
        logger.info("\n✓ SUCCESS: All GSI queries match in-memory indices")
        logger.info("✓ GSI optimization is functionally equivalent")
        return True
    else:
        logger.error(f"\n✗ FAILURE: {total_failed} mismatches found")
        logger.error("\nError details:")
        for error in all_errors:
            logger.error(f"  - {error}")
        return False


# ============================================================================
# CLI Interface
# ============================================================================


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Validate GSI matching vs in-memory matching',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test 10 random companies (default)
    python validate_gsi_matching.py

    # Test all 127 companies
    python validate_gsi_matching.py --sample-size 127

    # Verbose mode (log each test case)
    python validate_gsi_matching.py --sample-size 20 --verbose
        """
    )

    parser.add_argument(
        '--sample-size',
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f'Number of companies to test (default: {DEFAULT_SAMPLE_SIZE}, max: {MAX_SAMPLE_SIZE})'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Log each test case (verbose mode)'
    )

    parser.add_argument(
        '--region',
        type=str,
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )

    args = parser.parse_args()

    # Validate sample size
    if args.sample_size < MIN_SAMPLE_SIZE:
        logger.error(f"Sample size must be at least {MIN_SAMPLE_SIZE}")
        sys.exit(1)

    if args.sample_size > MAX_SAMPLE_SIZE:
        logger.warning(f"Sample size capped at {MAX_SAMPLE_SIZE} (all companies)")
        args.sample_size = MAX_SAMPLE_SIZE

    # Initialize DynamoDB resource
    try:
        dynamodb = boto3.resource('dynamodb', region_name=args.region)
        logger.info(f"Connected to DynamoDB in {args.region}")
    except Exception as e:
        logger.error(f"Failed to connect to DynamoDB: {e}")
        sys.exit(1)

    # Run validation
    success = validate_gsi_matching(
        dynamodb_resource=dynamodb,
        sample_size=args.sample_size,
        verbose=args.verbose
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
