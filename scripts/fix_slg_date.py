#!/usr/bin/env python3
"""
Fix SL Green (SLG) Press Release Date
======================================
Fixes the date import error where SL Green press release was
imported with March 15 instead of March 16 date.

The email was received at 10:20 PM UTC on March 16, 2026.

Usage:
    python3 scripts/fix_slg_date.py --dry-run    # Preview changes
    python3 scripts/fix_slg_date.py              # Apply fix
"""

import argparse
import boto3
from datetime import datetime, timezone


def find_slg_march_15_prs(reit_news_table):
    """Find SLG press releases with incorrect March 15 date."""

    # Query SLG press releases for March 15
    response = reit_news_table.query(
        IndexName='ticker-date-index',
        KeyConditionExpression='ticker = :ticker AND press_release_date = :date',
        ExpressionAttributeValues={
            ':ticker': 'SLG',
            ':date': '2026-03-15'
        }
    )

    return response.get('Items', [])


def find_recent_slg_prs(reit_news_table):
    """Find recent SLG press releases (last 5)."""

    response = reit_news_table.query(
        IndexName='ticker-date-index',
        KeyConditionExpression='ticker = :ticker',
        ExpressionAttributeValues={':ticker': 'SLG'},
        ScanIndexForward=False,  # Newest first
        Limit=5
    )

    return response.get('Items', [])


def update_press_release_date(reit_news_table, url, new_date, dry_run=False):
    """Update press_release_date for a specific press release."""

    if dry_run:
        print(f"  [DRY RUN] Would update: {url[:60]}...")
        print(f"            New date: {new_date}")
        return

    reit_news_table.update_item(
        Key={'url': url},
        UpdateExpression='SET press_release_date = :date',
        ExpressionAttributeValues={':date': new_date}
    )
    print(f"  Updated: {url[:60]}...")


def main():
    parser = argparse.ArgumentParser(description='Fix SL Green press release date')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--correct-date', default='2026-03-16', help='Correct date (default: 2026-03-16)')
    args = parser.parse_args()

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    reit_news_table = dynamodb.Table('reitsheet-reit-news-v2')

    print("=" * 60)
    print("SL Green Date Fix")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")

    # Step 1: Show recent SLG press releases
    print("\nRecent SLG press releases:")
    print("-" * 60)
    recent = find_recent_slg_prs(reit_news_table)
    for pr in recent:
        url = pr.get('url', 'N/A')[:60]
        date = pr.get('press_release_date', 'N/A')
        first_seen = pr.get('first_seen_at', 'N/A')
        title = pr.get('title', 'N/A')[:50]
        print(f"  Date: {date}  |  First seen: {first_seen[:19] if first_seen != 'N/A' else 'N/A'}")
        print(f"    URL: {url}...")
        print(f"    Title: {title}...")
        print()

    # Step 2: Find March 15 press releases
    print("\n" + "-" * 60)
    print("Press releases with incorrect date (2026-03-15):")
    print("-" * 60)

    march_15_prs = find_slg_march_15_prs(reit_news_table)

    if not march_15_prs:
        print("  No SLG press releases found with date 2026-03-15")
        print("\n  Checking if any were imported with different dates...")

        # Show all recent to help debug
        print("\n  All recent SLG press releases:")
        for pr in recent:
            date = pr.get('press_release_date', 'N/A')
            first_seen = pr.get('first_seen_at', 'N/A')
            email_received = pr.get('email_received_at', 'N/A')
            print(f"    PR Date: {date}, First Seen: {first_seen}, Email: {email_received}")
        return

    print(f"\nFound {len(march_15_prs)} press release(s) to fix:")
    for pr in march_15_prs:
        print(f"\n  URL: {pr.get('url', 'N/A')[:60]}...")
        print(f"  Current date: {pr.get('press_release_date', 'N/A')}")
        print(f"  First seen: {pr.get('first_seen_at', 'N/A')}")
        print(f"  Email received: {pr.get('email_received_at', 'N/A')}")

    # Step 3: Fix dates
    print("\n" + "-" * 60)
    print(f"Fixing dates to: {args.correct_date}")
    print("-" * 60)

    for pr in march_15_prs:
        update_press_release_date(
            reit_news_table,
            pr['url'],
            args.correct_date,
            args.dry_run
        )

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)

    if args.dry_run:
        print("\nTo apply changes, run without --dry-run:")
        print("  python3 scripts/fix_slg_date.py")


if __name__ == '__main__':
    main()
