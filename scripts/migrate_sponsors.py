#!/usr/bin/env python3
"""
Sponsor Migration Script
========================
Migrates sponsor fields to canonical names with full backup/rollback support.

Usage:
    python3 scripts/migrate_sponsors.py --dry-run          # Preview changes
    python3 scripts/migrate_sponsors.py --execute          # Run migration
    python3 scripts/migrate_sponsors.py --rollback FILE    # Rollback from backup

Safety Features:
    1. Creates timestamped backup before any changes
    2. Dry-run mode shows all changes without writing
    3. Rollback restores exact original values
    4. Atomic updates (one company at a time)
    5. Validates all mappings before starting
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add Flask app config to path
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'infrastructure', 'docker', 'flask-app'
))

from config.sponsors import get_canonical_sponsor, is_canonical_sponsor

# Constants
BACKUP_DIR = Path('data/sponsor_backups')
TABLE_NAME = os.environ.get('COMPANIES_TABLE', 'reitsheet-companies-config')
REGION = os.environ.get('AWS_REGION', 'us-east-1')


def get_dynamodb_table():
    """Get DynamoDB table resource."""
    import boto3
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    return dynamodb.Table(TABLE_NAME)


def scan_all_items(table):
    """Scan all items from table, handling pagination."""
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))

    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    return items


def create_backup(table, dry_run=False):
    """
    Create backup of all sponsor data.

    Args:
        table: DynamoDB table resource
        dry_run: If True, skip actual backup creation

    Returns:
        Path to backup file, or None if dry_run
    """
    if dry_run:
        print("[DRY-RUN] Would create backup")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = BACKUP_DIR / f'sponsors_backup_{timestamp}.json'

    # Scan all companies with sponsor data
    items = scan_all_items(table)

    backup_data = []
    for item in items:
        lead = item.get('lead_sponsor')
        second = item.get('second_sponsor')

        if lead or second:
            backup_data.append({
                'ticker': item['ticker'],
                'lead_sponsor': lead,
                'second_sponsor': second
            })

    with open(backup_file, 'w') as f:
        json.dump({
            'created_at': datetime.now().isoformat(),
            'table_name': TABLE_NAME,
            'company_count': len(backup_data),
            'companies': backup_data
        }, f, indent=2)

    print(f"Backup created: {backup_file}")
    print(f"  Companies with sponsors: {len(backup_data)}")
    return backup_file


def analyze_changes(items):
    """
    Analyze what changes would be made.

    Args:
        items: List of DynamoDB items

    Returns:
        List of change dicts with ticker, field, old_value, new_value
    """
    changes = []

    for item in items:
        ticker = item['ticker']

        for field in ['lead_sponsor', 'second_sponsor']:
            old_value = item.get(field)
            if old_value:
                new_value = get_canonical_sponsor(old_value)
                if new_value != old_value:
                    changes.append({
                        'ticker': ticker,
                        'field': field,
                        'old_value': old_value,
                        'new_value': new_value
                    })

    return changes


def print_changes(changes, verbose=True):
    """Print summary of changes."""
    if not changes:
        print("\nNo changes needed - all sponsors are already canonical.")
        return

    print(f"\n{'=' * 60}")
    print(f"CHANGES TO BE MADE: {len(changes)} field(s) across {len(set(c['ticker'] for c in changes))} company(ies)")
    print(f"{'=' * 60}\n")

    # Group by ticker
    by_ticker = {}
    for change in changes:
        ticker = change['ticker']
        if ticker not in by_ticker:
            by_ticker[ticker] = []
        by_ticker[ticker].append(change)

    for ticker in sorted(by_ticker.keys()):
        ticker_changes = by_ticker[ticker]
        print(f"{ticker}:")
        for c in ticker_changes:
            print(f"  {c['field']}: '{c['old_value']}' -> '{c['new_value']}'")
        print()


def migrate(table, dry_run=True):
    """
    Migrate sponsors to canonical names.

    Args:
        table: DynamoDB table resource
        dry_run: If True, only show what would change

    Returns:
        List of changes made (or would be made)
    """
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Scanning companies...")

    items = scan_all_items(table)
    print(f"  Total companies: {len(items)}")

    # Analyze changes
    changes = analyze_changes(items)
    print_changes(changes)

    if dry_run:
        if changes:
            print("\n[DRY-RUN] No changes written. Run with --execute to apply.")
        return changes

    # Apply changes
    if not changes:
        return changes

    print("Applying changes...")
    success_count = 0
    error_count = 0

    # Group changes by ticker for efficient updates
    by_ticker = {}
    for change in changes:
        ticker = change['ticker']
        if ticker not in by_ticker:
            by_ticker[ticker] = {}
        by_ticker[ticker][change['field']] = change['new_value']

    for ticker, updates in by_ticker.items():
        try:
            # Build update expression
            update_parts = []
            expr_values = {}

            for field, value in updates.items():
                safe_field = field.replace('_', '')  # lead_sponsor -> leadsponsor
                update_parts.append(f"{field} = :{safe_field}")
                expr_values[f":{safe_field}"] = value

            update_expr = 'SET ' + ', '.join(update_parts)

            table.update_item(
                Key={'ticker': ticker},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )
            print(f"  Updated: {ticker}")
            success_count += 1

        except Exception as e:
            print(f"  ERROR updating {ticker}: {e}")
            error_count += 1

    print(f"\nMigration complete:")
    print(f"  Success: {success_count}")
    print(f"  Errors:  {error_count}")

    return changes


def rollback(table, backup_file):
    """
    Rollback to backup state.

    Args:
        table: DynamoDB table resource
        backup_file: Path to backup JSON file
    """
    print(f"\nReading backup: {backup_file}")

    with open(backup_file) as f:
        backup_data = json.load(f)

    companies = backup_data.get('companies', [])
    print(f"  Companies to restore: {len(companies)}")

    if not companies:
        print("No companies in backup file.")
        return

    # Confirm rollback
    print("\nThis will restore the following sponsor values:")
    for item in companies[:10]:  # Show first 10
        print(f"  {item['ticker']}: lead={item.get('lead_sponsor')}, second={item.get('second_sponsor')}")
    if len(companies) > 10:
        print(f"  ... and {len(companies) - 10} more")

    response = input("\nProceed with rollback? [y/N]: ")
    if response.lower() != 'y':
        print("Rollback cancelled.")
        return

    # Apply rollback
    print("\nRestoring original values...")
    success_count = 0
    error_count = 0

    for item in companies:
        ticker = item['ticker']
        try:
            update_parts = []
            expr_values = {}
            remove_parts = []

            for field in ['lead_sponsor', 'second_sponsor']:
                value = item.get(field)
                if value:
                    safe_field = field.replace('_', '')
                    update_parts.append(f"{field} = :{safe_field}")
                    expr_values[f":{safe_field}"] = value
                else:
                    remove_parts.append(field)

            # Build expression
            expressions = []
            if update_parts:
                expressions.append('SET ' + ', '.join(update_parts))
            if remove_parts:
                expressions.append('REMOVE ' + ', '.join(remove_parts))

            if expressions:
                table.update_item(
                    Key={'ticker': ticker},
                    UpdateExpression=' '.join(expressions),
                    ExpressionAttributeValues=expr_values if expr_values else None
                )
                print(f"  Restored: {ticker}")
                success_count += 1

        except Exception as e:
            print(f"  ERROR restoring {ticker}: {e}")
            error_count += 1

    print(f"\nRollback complete:")
    print(f"  Success: {success_count}")
    print(f"  Errors:  {error_count}")


def validate_config():
    """Validate that sponsors config is properly loaded."""
    from config.sponsors import SPONSORS, SPONSOR_ALIASES

    print("Validating sponsor configuration...")
    print(f"  Canonical sponsors: {len(SPONSORS)}")
    print(f"  Alias mappings: {len(SPONSOR_ALIASES)}")

    # Check all aliases map to valid sponsors
    errors = []
    for alias, canonical in SPONSOR_ALIASES.items():
        if canonical not in SPONSORS and canonical not in ['Family-owned', 'Independent', 'Institutional', 'Management/PE-backed', 'Venture/Growth-backed']:
            errors.append(f"Alias '{alias}' maps to unknown sponsor '{canonical}'")

    if errors:
        print("\nConfiguration errors:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("  Configuration valid!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Migrate sponsor fields to canonical names',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --dry-run                              Preview changes
  %(prog)s --execute                              Apply changes (with auto-backup)
  %(prog)s --rollback data/sponsor_backups/X.json Restore from backup
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true',
                       help='Preview changes without modifying database')
    group.add_argument('--execute', action='store_true',
                       help='Apply changes (creates backup first)')
    group.add_argument('--rollback', type=str, metavar='BACKUP_FILE',
                       help='Restore sponsor values from backup file')

    parser.add_argument('--skip-validation', action='store_true',
                        help='Skip config validation (not recommended)')

    args = parser.parse_args()

    # Validate config
    if not args.skip_validation and not args.rollback:
        if not validate_config():
            print("\nFix configuration errors before proceeding.")
            sys.exit(1)

    # Get DynamoDB table
    try:
        table = get_dynamodb_table()
        # Test connection
        table.table_status
    except Exception as e:
        print(f"Error connecting to DynamoDB: {e}")
        print("Make sure AWS credentials are configured.")
        sys.exit(1)

    if args.rollback:
        if not os.path.exists(args.rollback):
            print(f"Backup file not found: {args.rollback}")
            sys.exit(1)
        rollback(table, args.rollback)
    else:
        # Create backup before migration
        if args.execute:
            backup_file = create_backup(table, dry_run=False)
            print(f"\nTo rollback: python3 {sys.argv[0]} --rollback {backup_file}\n")

        changes = migrate(table, dry_run=args.dry_run)

        if args.dry_run and changes:
            print(f"\nTo apply these changes: python3 {sys.argv[0]} --execute")


if __name__ == '__main__':
    main()
