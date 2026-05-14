#!/usr/bin/env python3
"""
Fix SL Green (SLG) Configuration
================================
This script:
1. Removes incorrectly added Playwright config fields from SLG
2. Resets circuit breaker state (redirect_failure_count = 0)
3. Shows current SLG config after fix

Background:
- SLG uses url_construction_method = gcs_9_word_slug, NOT playwright_scraper
- Circuit breaker triggered (3+ failures) and routed to Playwright
- But SLG had no Playwright config, so Playwright Lambda failed
- I incorrectly added Playwright config instead of fixing the root cause

Usage:
    python3 scripts/fix_slg_config.py --dry-run   # Preview changes
    python3 scripts/fix_slg_config.py             # Apply fix
"""

import argparse
import boto3
from datetime import datetime, timezone


def get_slg_config(table):
    """Get current SLG config."""
    response = table.get_item(Key={'ticker': 'SLG'})
    return response.get('Item', {})


def remove_playwright_config(table, dry_run=False):
    """Remove incorrectly added Playwright config from SLG."""

    fields_to_remove = [
        'playwright_url',
        'playwright_selector',
        'playwright_wait_for'
    ]

    current = get_slg_config(table)

    # Check which fields exist
    fields_present = [f for f in fields_to_remove if f in current]

    if not fields_present:
        print("No Playwright config fields to remove (already clean)")
        return

    print(f"Playwright config fields to remove: {fields_present}")

    if dry_run:
        print("[DRY RUN] Would remove these fields")
        return

    # Remove fields
    remove_expr = 'REMOVE ' + ', '.join(fields_present)
    table.update_item(
        Key={'ticker': 'SLG'},
        UpdateExpression=remove_expr
    )
    print(f"Removed Playwright config fields from SLG")


def reset_circuit_breaker(table, dry_run=False):
    """Reset circuit breaker state for SLG."""

    current = get_slg_config(table)

    failure_count = current.get('redirect_failure_count', 0)
    redirect_strategy = current.get('redirect_strategy', 'redirect_first')
    last_failure_date = current.get('last_redirect_failure_date', 'N/A')

    print(f"\nCurrent circuit breaker state:")
    print(f"  redirect_failure_count: {failure_count}")
    print(f"  redirect_strategy: {redirect_strategy}")
    print(f"  last_redirect_failure_date: {last_failure_date}")

    if failure_count == 0 and redirect_strategy == 'redirect_first':
        print("Circuit breaker already reset (no action needed)")
        return

    if dry_run:
        print("[DRY RUN] Would reset circuit breaker")
        return

    # Reset circuit breaker
    table.update_item(
        Key={'ticker': 'SLG'},
        UpdateExpression="""
            SET redirect_failure_count = :zero,
                redirect_strategy = :redirect_first
            REMOVE last_redirect_attempt_date, last_redirect_failure_date
        """,
        ExpressionAttributeValues={
            ':zero': 0,
            ':redirect_first': 'redirect_first'
        }
    )
    print("Circuit breaker RESET for SLG")


def show_config(table):
    """Show current SLG config."""
    current = get_slg_config(table)

    print("\n" + "=" * 60)
    print("Current SLG Configuration:")
    print("=" * 60)

    # Key fields
    key_fields = [
        'ticker',
        'company_name',
        'url_construction_method',
        'press_release_url',
        'playwright_url',
        'playwright_selector',
        'playwright_wait_for',
        'redirect_failure_count',
        'redirect_strategy',
        'last_redirect_failure_date',
        'last_redirect_attempt_date'
    ]

    for field in key_fields:
        value = current.get(field, '(not set)')
        print(f"  {field}: {value}")


def main():
    parser = argparse.ArgumentParser(description='Fix SL Green DynamoDB config')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    args = parser.parse_args()

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('reitsheet-companies-config')

    print("=" * 60)
    print("SL Green (SLG) Configuration Fix")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")

    # Step 1: Show current config
    show_config(table)

    # Step 2: Remove Playwright config
    print("\n" + "-" * 60)
    print("Step 1: Remove incorrect Playwright config")
    print("-" * 60)
    remove_playwright_config(table, args.dry_run)

    # Step 3: Reset circuit breaker
    print("\n" + "-" * 60)
    print("Step 2: Reset circuit breaker")
    print("-" * 60)
    reset_circuit_breaker(table, args.dry_run)

    # Step 4: Show final config
    if not args.dry_run:
        show_config(table)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)

    if args.dry_run:
        print("\nTo apply changes, run without --dry-run:")
        print("  python3 scripts/fix_slg_config.py")


if __name__ == '__main__':
    main()
