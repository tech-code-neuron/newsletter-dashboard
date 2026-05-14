#!/usr/bin/env python3
"""
Fix WWW Domains in Companies Config Table
==========================================
Removes 'www.' prefix from ir_domain and pr_url_domain fields

Run:
    python3 scripts/fix_www_domains.py
"""

import boto3
import logging
from botocore.exceptions import ClientError

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('reitsheet-companies-config')

def clean_domain(domain):
    """
    Remove www. prefix from domain

    Examples:
        'www.omegahealthcare.com' -> 'omegahealthcare.com'
        'investors.americantower.com' -> 'investors.americantower.com' (unchanged)
    """
    if not domain:
        return domain

    # Remove www. prefix
    if domain.startswith('www.'):
        return domain[4:]

    return domain


def fix_company_domains():
    """Scan all companies and fix any with www. in domains"""

    logger.info("Scanning companies-config table for www. domains...")

    # Scan table
    response = table.scan()
    companies = response.get('Items', [])

    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        companies.extend(response.get('Items', []))

    logger.info(f"✓ Found {len(companies)} companies")

    # Find companies with www. domains
    companies_to_fix = []

    for company in companies:
        ticker = company.get('ticker')
        ir_domain = company.get('ir_domain', '')
        pr_url_domain = company.get('pr_url_domain', '')

        needs_fix = False
        updates = {}

        # Check ir_domain
        if ir_domain.startswith('www.'):
            clean_ir = clean_domain(ir_domain)
            updates['ir_domain'] = clean_ir
            needs_fix = True

        # Check pr_url_domain
        if pr_url_domain.startswith('www.'):
            clean_pr = clean_domain(pr_url_domain)
            updates['pr_url_domain'] = clean_pr
            needs_fix = True

        if needs_fix:
            companies_to_fix.append({
                'ticker': ticker,
                'updates': updates,
                'old_ir_domain': ir_domain,
                'old_pr_url_domain': pr_url_domain
            })

    logger.info(f"Found {len(companies_to_fix)} companies with www. domains\n")

    if not companies_to_fix:
        logger.info("✓ No companies need fixing")
        return

    # Show what will be fixed
    logger.info("Companies to be fixed:")
    for item in companies_to_fix:
        logger.info(f"  {item['ticker']:6s}: {item['old_ir_domain']:40s} -> {item['updates'].get('ir_domain', item['old_ir_domain'])}")

    # Confirm
    logger.info(f"\nReady to update {len(companies_to_fix)} companies")

    # Apply fixes
    fixed_count = 0
    for item in companies_to_fix:
        ticker = item['ticker']
        updates = item['updates']

        try:
            # Build update expression
            update_parts = []
            attr_values = {}

            for field, value in updates.items():
                update_parts.append(f"{field} = :{field}")
                attr_values[f":{field}"] = value

            update_expression = "SET " + ", ".join(update_parts)

            # Update item
            table.update_item(
                Key={'ticker': ticker},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=attr_values
            )

            fixed_count += 1
            logger.info(f"✓ Fixed {ticker}")

        except ClientError as e:
            logger.error(f"✗ Failed to fix {ticker}: {e}")

    logger.info(f"\n✅ Fixed {fixed_count}/{len(companies_to_fix)} companies")


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("Fix WWW Domains")
    logger.info("=" * 60)

    fix_company_domains()

    logger.info("\n✓ COMPLETE")
