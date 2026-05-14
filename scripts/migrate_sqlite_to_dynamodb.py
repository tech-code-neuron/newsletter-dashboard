#!/usr/bin/env python3
"""
SQLite to DynamoDB Migration Script

Migrates data from local SQLite tables to AWS DynamoDB:
- newsletters -> reitsheet-newsletters
- review_emails -> reitsheet-review-emails
- relevance_decisions -> reitsheet-relevance-decisions

Note: companies and press_releases already exist in DynamoDB
(reitsheet-companies-config and reitsheet-reit-news-v2)

Usage:
    # Dry run (shows what would be migrated)
    python3 scripts/migrate_sqlite_to_dynamodb.py --dry-run

    # Migrate all tables
    python3 scripts/migrate_sqlite_to_dynamodb.py

    # Migrate specific table
    python3 scripts/migrate_sqlite_to_dynamodb.py --table newsletters

    # Verify migration
    python3 scripts/migrate_sqlite_to_dynamodb.py --verify
"""
import os
import sys
import argparse
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import get_session, Newsletter, ReviewEmail, RelevanceDecision
from core.dynamodb_models import (
    DynamoDBSession,
    Newsletter as DDBNewsletter,
    ReviewEmail as DDBReviewEmail,
    RelevanceDecision as DDBRelevanceDecision
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_newsletters(dry_run: bool = False) -> dict:
    """Migrate newsletters table from SQLite to DynamoDB."""
    logger.info("Migrating newsletters...")

    sqlite_session = get_session()
    results = {'migrated': 0, 'skipped': 0, 'errors': 0}

    try:
        newsletters = sqlite_session.query(Newsletter).all()
        logger.info(f"Found {len(newsletters)} newsletters in SQLite")

        if dry_run:
            results['migrated'] = len(newsletters)
            return results

        with DynamoDBSession() as ddb:
            for nl in newsletters:
                try:
                    # Check if already exists in DynamoDB
                    existing = ddb.query(DDBNewsletter).filter_by(
                        newsletter_id=str(nl.id)
                    ).first()

                    if existing:
                        logger.debug(f"Newsletter {nl.id} already exists, skipping")
                        results['skipped'] += 1
                        continue

                    # Create DynamoDB record
                    ddb_newsletter = DDBNewsletter(
                        newsletter_id=str(nl.id),
                        date=nl.date.strftime('%Y-%m-%d') if nl.date else '',
                        newsletter_type=nl.newsletter_type or 'daily',
                        status=nl.status or 'draft',
                        subject_line=nl.subject_line,
                        html_content=nl.html_content,
                        recipient_count=nl.recipient_count or 0,
                        created_at=nl.created_at.isoformat() if nl.created_at else datetime.utcnow().isoformat(),
                        sent_at=nl.sent_at.isoformat() if nl.sent_at else None
                    )
                    ddb.add(ddb_newsletter)
                    results['migrated'] += 1

                except Exception as e:
                    logger.error(f"Error migrating newsletter {nl.id}: {e}")
                    results['errors'] += 1

    finally:
        sqlite_session.close()

    return results


def migrate_review_emails(dry_run: bool = False) -> dict:
    """Migrate review_emails table from SQLite to DynamoDB."""
    logger.info("Migrating review_emails...")

    sqlite_session = get_session()
    results = {'migrated': 0, 'skipped': 0, 'errors': 0}

    try:
        emails = sqlite_session.query(ReviewEmail).all()
        logger.info(f"Found {len(emails)} review emails in SQLite")

        if dry_run:
            results['migrated'] = len(emails)
            return results

        with DynamoDBSession() as ddb:
            for email in emails:
                try:
                    # Check if already exists in DynamoDB
                    existing = ddb.query(DDBReviewEmail).filter_by(
                        gmail_message_id=email.gmail_message_id
                    ).first()

                    if existing:
                        logger.debug(f"Review email {email.gmail_message_id} already exists, skipping")
                        results['skipped'] += 1
                        continue

                    # Create DynamoDB record
                    ddb_email = DDBReviewEmail(
                        gmail_message_id=email.gmail_message_id,
                        subject=email.subject or '',
                        from_header=email.from_header,
                        from_email=email.from_email,
                        from_domain=email.from_domain,
                        date=email.date.isoformat() if email.date else None,
                        raw_email=email.raw_email,
                        screenshot_path=email.screenshot_path,
                        classification_reason=email.classification_reason,
                        status=email.status or 'pending',
                        press_release_url=None,  # Link by URL if press_release exists
                        created_at=email.created_at.isoformat() if email.created_at else datetime.utcnow().isoformat(),
                        processed_at=email.processed_at.isoformat() if email.processed_at else None
                    )
                    ddb.add(ddb_email)
                    results['migrated'] += 1

                except Exception as e:
                    logger.error(f"Error migrating review email {email.gmail_message_id}: {e}")
                    results['errors'] += 1

    finally:
        sqlite_session.close()

    return results


def migrate_relevance_decisions(dry_run: bool = False) -> dict:
    """Migrate relevance_decisions table from SQLite to DynamoDB."""
    logger.info("Migrating relevance_decisions...")

    sqlite_session = get_session()
    results = {'migrated': 0, 'skipped': 0, 'errors': 0}

    try:
        decisions = sqlite_session.query(RelevanceDecision).all()
        logger.info(f"Found {len(decisions)} relevance decisions in SQLite")

        if dry_run:
            results['migrated'] = len(decisions)
            return results

        with DynamoDBSession() as ddb:
            for decision in decisions:
                try:
                    decision_id = str(decision.id)

                    # Check if already exists in DynamoDB
                    existing = ddb.query(DDBRelevanceDecision).filter_by(
                        decision_id=decision_id
                    ).first()

                    if existing:
                        logger.debug(f"Relevance decision {decision_id} already exists, skipping")
                        results['skipped'] += 1
                        continue

                    # Get press release URL for the decision
                    pr = decision.press_release
                    pr_url = pr.url if pr else f"unknown-pr-{decision.press_release_id}"
                    ticker = pr.company.ticker if pr and pr.company else 'UNKNOWN'

                    # Create DynamoDB record
                    ddb_decision = DDBRelevanceDecision(
                        decision_id=decision_id,
                        press_release_url=pr_url,
                        ticker=ticker,
                        decision=decision.decision,
                        decided_by=decision.decided_by or 'user',
                        decided_at=decision.decided_at.isoformat() if decision.decided_at else datetime.utcnow().isoformat()
                    )
                    ddb.add(ddb_decision)
                    results['migrated'] += 1

                except Exception as e:
                    logger.error(f"Error migrating relevance decision {decision.id}: {e}")
                    results['errors'] += 1

    finally:
        sqlite_session.close()

    return results


def verify_migration() -> dict:
    """Verify migration by comparing counts."""
    logger.info("Verifying migration...")

    sqlite_session = get_session()
    results = {}

    try:
        # Count SQLite records
        sqlite_counts = {
            'newsletters': sqlite_session.query(Newsletter).count(),
            'review_emails': sqlite_session.query(ReviewEmail).count(),
            'relevance_decisions': sqlite_session.query(RelevanceDecision).count()
        }

        # Count DynamoDB records
        with DynamoDBSession() as ddb:
            ddb_counts = {
                'newsletters': ddb.query(DDBNewsletter).count(),
                'review_emails': ddb.query(DDBReviewEmail).count(),
                'relevance_decisions': ddb.query(DDBRelevanceDecision).count()
            }

        # Compare
        for table in ['newsletters', 'review_emails', 'relevance_decisions']:
            sqlite_count = sqlite_counts[table]
            ddb_count = ddb_counts[table]
            match = sqlite_count == ddb_count
            results[table] = {
                'sqlite': sqlite_count,
                'dynamodb': ddb_count,
                'match': match
            }
            status = "MATCH" if match else "MISMATCH"
            logger.info(f"  {table}: SQLite={sqlite_count}, DynamoDB={ddb_count} - {status}")

    finally:
        sqlite_session.close()

    return results


def main():
    parser = argparse.ArgumentParser(description='Migrate SQLite tables to DynamoDB')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without making changes')
    parser.add_argument('--table', choices=['newsletters', 'review_emails', 'relevance_decisions', 'all'],
                       default='all', help='Table to migrate (default: all)')
    parser.add_argument('--verify', action='store_true', help='Verify migration counts')

    args = parser.parse_args()

    if args.verify:
        results = verify_migration()
        all_match = all(r['match'] for r in results.values())
        sys.exit(0 if all_match else 1)

    if args.dry_run:
        logger.info("=== DRY RUN MODE - No changes will be made ===")

    tables_to_migrate = ['newsletters', 'review_emails', 'relevance_decisions'] if args.table == 'all' else [args.table]
    total_results = {'migrated': 0, 'skipped': 0, 'errors': 0}

    for table in tables_to_migrate:
        if table == 'newsletters':
            results = migrate_newsletters(args.dry_run)
        elif table == 'review_emails':
            results = migrate_review_emails(args.dry_run)
        elif table == 'relevance_decisions':
            results = migrate_relevance_decisions(args.dry_run)

        logger.info(f"  {table}: migrated={results['migrated']}, skipped={results['skipped']}, errors={results['errors']}")

        for key in total_results:
            total_results[key] += results[key]

    logger.info("=" * 50)
    logger.info(f"TOTAL: migrated={total_results['migrated']}, skipped={total_results['skipped']}, errors={total_results['errors']}")

    if total_results['errors'] > 0:
        logger.warning("Some records failed to migrate. Check logs above for details.")
        sys.exit(1)

    if not args.dry_run:
        logger.info("Migration complete! Run with --verify to confirm counts match.")


if __name__ == '__main__':
    main()
