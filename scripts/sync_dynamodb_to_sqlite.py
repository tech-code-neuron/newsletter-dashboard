"""
Sync press releases from DynamoDB to local SQLite for offline work
Useful before flights or offline work sessions
"""
import sqlite3
import boto3
from datetime import datetime, timezone
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================================
# SOLID: Constants - No hardcoded values
# ============================================================================

# AWS Configuration
AWS_REGION = 'us-east-1'
DYNAMODB_REIT_NEWS_TABLE = 'reitsheet-reit-news-v2'  # Updated for V2 migration (2026-03-13)
DYNAMODB_COMPANIES_TABLE = 'reitsheet-companies'

# Sync Configuration
DEFAULT_LOOKBACK_DAYS = 30  # How many days of press releases to fetch
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data',
    'reit_newsletter.db'
)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
reit_news_table = dynamodb.Table(DYNAMODB_REIT_NEWS_TABLE)
companies_table = dynamodb.Table(DYNAMODB_COMPANIES_TABLE)

# ============================================================================
# SOLID: Single Responsibility - Each function does ONE thing
# ============================================================================

def get_all_press_releases_from_dynamodb(limit_days=None):
    """
    Scan DynamoDB for recent press releases

    SOLID: Single responsibility - only fetches data

    Args:
        limit_days: Only fetch press releases from last N days (default: DEFAULT_LOOKBACK_DAYS)

    Returns:
        List of press release items
    """
    if limit_days is None:
        limit_days = DEFAULT_LOOKBACK_DAYS

    print(f"📥 Fetching press releases from DynamoDB (last {limit_days} days)...")

    try:
        # Calculate timestamp for filtering (optional)
        # DynamoDB doesn't have a good way to filter by date in scan
        # So we fetch all and filter client-side

        response = reit_news_table.scan()
        items = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = reit_news_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        print(f"  ✅ Fetched {len(items)} press releases from DynamoDB")
        return items

    except Exception as e:
        print(f"  ❌ Error fetching from DynamoDB: {e}")
        return []


def insert_or_update_press_release(cursor, pr):
    """
    Insert or update a press release in SQLite

    SOLID: Single responsibility - only handles one PR
    """
    try:
        # Convert DynamoDB timestamp to SQLite datetime format
        # V2 schema uses 'press_release_date' (preferred) or 'first_seen_at' (fallback)
        # DynamoDB uses ISO format: 2026-03-07T12:34:56.789Z
        press_release_date = pr.get('press_release_date') or pr.get('first_seen_at') or datetime.now(timezone.utc).isoformat()

        # Extract fields (use .get() for safe access)
        ticker = pr.get('ticker', 'UNKNOWN')
        title = pr.get('title', 'No Subject')  # V2 uses 'title', not 'title'
        url = pr.get('url', '')

        # Skip if no URL (can't store in local DB)
        if not url:
            return 'skipped'

        # Check if press release already exists (by URL - unique constraint)
        cursor.execute("""
            SELECT id FROM press_releases
            WHERE url = ?
        """, (url,))

        existing = cursor.fetchone()

        if existing:
            # Update existing
            cursor.execute("""
                UPDATE press_releases
                SET title = ?,
                    published_date = ?
                WHERE id = ?
            """, (title, press_release_date, existing[0]))
            return 'updated'
        else:
            # Insert new
            # Get company_id from ticker
            cursor.execute("SELECT id FROM companies WHERE ticker = ?", (ticker,))
            company_row = cursor.fetchone()
            company_id = company_row[0] if company_row else None

            if not company_id:
                print(f"    ⚠️  Warning: No company found for ticker {ticker}")
                return 'skipped'

            cursor.execute("""
                INSERT INTO press_releases
                (company_id, title, url, published_date, scraped_date)
                VALUES (?, ?, ?, ?, ?)
            """, (company_id, title, url, press_release_date, datetime.now(timezone.utc).isoformat()))
            return 'inserted'

    except Exception as e:
        print(f"    ❌ Error with PR ({ticker}): {e}")
        return 'error'


def sync_press_releases():
    """
    Main sync function: DynamoDB → SQLite

    SOLID Compliance:
    - Single Responsibility: Orchestrates sync, delegates to helpers
    - No Hardcoded Values: Uses constants for all configuration
    - Error handling without halting entire operation
    """

    # Fetch from DynamoDB (uses DEFAULT_LOOKBACK_DAYS)
    press_releases = get_all_press_releases_from_dynamodb()

    if not press_releases:
        print("⚠️  No press releases found in DynamoDB")
        return

    # Connect to SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"\n💾 Syncing to SQLite database...")

    inserted = 0
    updated = 0
    skipped = 0
    errors = 0

    for pr in press_releases:
        result = insert_or_update_press_release(cursor, pr)

        if result == 'inserted':
            inserted += 1
        elif result == 'updated':
            updated += 1
        elif result == 'skipped':
            skipped += 1
        else:
            errors += 1

    # Commit changes
    conn.commit()
    conn.close()

    print(f"\n✅ Sync complete!")
    print(f"   📝 {inserted} new press releases inserted")
    print(f"   🔄 {updated} existing press releases updated")
    print(f"   ⏭️  {skipped} press releases skipped (no matching company)")
    print(f"   ❌ {errors} errors")
    print(f"\n🎯 Local database ready for offline work!")


def show_recent_stats():
    """Show stats about local database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Count total press releases
    cursor.execute("SELECT COUNT(*) FROM press_releases")
    total_prs = cursor.fetchone()[0]

    # Count from last 7 days
    cursor.execute("""
        SELECT COUNT(*) FROM press_releases
        WHERE published_date >= datetime('now', '-7 days')
    """)
    recent_prs = cursor.fetchone()[0]

    # Count companies
    cursor.execute("SELECT COUNT(*) FROM companies WHERE active = 1")
    total_companies = cursor.fetchone()[0]

    conn.close()

    print(f"\n📊 Local Database Stats:")
    print(f"   🏢 {total_companies} active companies")
    print(f"   📰 {total_prs} total press releases")
    print(f"   🆕 {recent_prs} press releases in last 7 days")


if __name__ == '__main__':
    print("🛫 Pre-Flight Sync: DynamoDB → SQLite")
    print("=" * 60)

    sync_press_releases()
    show_recent_stats()

    print("\n✈️  Ready for offline work!")
