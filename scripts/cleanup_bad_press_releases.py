"""
Cleanup Script: Remove Email Signup Links Misidentified as Press Releases
===========================================================================

Problem: Email activation/confirmation links were incorrectly saved as press releases
Fix: Remove these bad entries from database

Patterns to remove:
- /email-alert-activation/
- /EmailNotification/
- /email-activation/
- /contact-ir/EmailNotification
- URLs with token= parameter (email verification)
- /verify-email, /confirm-subscription
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime

def find_bad_press_releases(conn):
    """Find all press releases that are actually email signup/activation links."""
    cursor = conn.cursor()

    patterns = [
        '%/email-alert-activation/%',
        '%/EmailNotification/%',
        '%/email-activation/%',
        '%/email-verification/%',
        '%/email-confirm/%',
        '%/activate-alert%',
        '%/confirm-subscription%',
        '%/verify-email%',
        '%token=%',  # Email verification tokens
        '%/contact-ir/emailnotification%'
    ]

    # Build WHERE clause
    where_clauses = ' OR '.join(['url LIKE ?' for _ in patterns])

    query = f"""
        SELECT id, company_id, title, url, published_date, scraped_date
        FROM press_releases
        WHERE {where_clauses}
    """

    cursor.execute(query, patterns)
    return cursor.fetchall()


def delete_bad_press_releases(conn, press_release_ids):
    """Delete bad press releases from database."""
    cursor = conn.cursor()

    placeholders = ','.join(['?' for _ in press_release_ids])
    query = f"DELETE FROM press_releases WHERE id IN ({placeholders})"

    cursor.execute(query, press_release_ids)
    conn.commit()

    return cursor.rowcount


def main():
    """Main cleanup function."""
    db_path = 'data/press_releases.db'

    print("=" * 70)
    print("Email Signup Link Cleanup")
    print("=" * 70)
    print()

    # Connect to database
    conn = sqlite3.connect(db_path)

    # Find bad press releases
    print("🔍 Searching for bad press releases...")
    bad_prs = find_bad_press_releases(conn)

    if not bad_prs:
        print("✅ No bad press releases found!")
        conn.close()
        return

    print(f"\n❌ Found {len(bad_prs)} bad press releases:")
    print()

    for pr_id, company_id, title, url, published_date, scraped_date in bad_prs:
        print(f"ID {pr_id}:")
        print(f"  Title: {title or 'No Subject'}")
        print(f"  URL: {url[:100]}{'...' if len(url) > 100 else ''}")
        print(f"  Published: {published_date}")
        print(f"  Scraped: {scraped_date}")
        print()

    # Ask for confirmation
    response = input(f"Delete these {len(bad_prs)} press releases? (yes/no): ").strip().lower()

    if response != 'yes':
        print("Cancelled.")
        conn.close()
        return

    # Delete bad press releases
    print("\n🗑️  Deleting bad press releases...")
    press_release_ids = [pr[0] for pr in bad_prs]
    deleted_count = delete_bad_press_releases(conn, press_release_ids)

    print(f"✅ Deleted {deleted_count} bad press releases")

    # Close connection
    conn.close()

    print()
    print("=" * 70)
    print("Cleanup Complete!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Redeploy parser Lambda with updated EXCLUDE_PATTERNS")
    print("2. Monitor future emails to ensure no more bad PRs saved")


if __name__ == '__main__':
    main()
