"""
Database Migrations Utility

SOLID: Single Responsibility - Handle database schema migrations only
Open/Closed: Data-driven migration system - add migrations without modifying code

Extracted from models.py for clean separation of concerns
"""
from sqlalchemy import inspect, text


# ============================================================================
# MIGRATION DEFINITIONS - Data-driven approach (SOLID: Open/Closed)
# ============================================================================

MIGRATIONS = [
    # Press Release Table Migrations
    {'table': 'press_releases', 'column': 'deleted_at', 'type': 'DATETIME', 'description': 'Soft delete timestamp'},
    {'table': 'press_releases', 'column': 'full_text', 'type': 'TEXT', 'description': 'First 2000 words'},
    {'table': 'press_releases', 'column': 'unique_id', 'type': 'VARCHAR(8)', 'description': '8-digit unique ID'},
    {'table': 'press_releases', 'column': 'slug', 'type': 'VARCHAR(200)', 'description': 'URL-friendly slug'},

    # Company Table Migrations
    {'table': 'companies', 'column': 'scraping_status', 'type': 'VARCHAR(20)', 'description': 'RSS/Scraped/Manual'},
    {'table': 'companies', 'column': 'scraper_variant', 'type': 'VARCHAR(50)', 'description': 'Platform variant'},
    {'table': 'companies', 'column': 'emails_activated', 'type': 'BOOLEAN', 'default': '0', 'description': 'Email signup status'},
    {'table': 'companies', 'column': 'company_rss_feed_url', 'type': 'VARCHAR(500)', 'description': 'Company-specific RSS feed'},
    {'table': 'companies', 'column': 'ignore_company_rss', 'type': 'BOOLEAN', 'default': '0', 'description': 'Ignore company RSS feed'},

    # Binary Categorization System (MVP)
    {'table': 'press_releases', 'column': 'relevance', 'type': 'VARCHAR(20)', 'description': 'Binary relevance: relevant/not_relevant/NULL'},

    # Newsletter Publisher System
    {'table': 'press_releases', 'column': 'newsletter_status', 'type': 'VARCHAR(20)', 'default': "'ready'", 'description': 'Publisher status: ready/needs_review/published/excluded'},

    # Newsletter section override (headline vs other)
    {'table': 'press_releases', 'column': 'newsletter_section', 'type': 'VARCHAR(20)', 'description': 'Manual section override: headline/other/NULL(auto)'},

    # Add new migrations here - no code changes needed!
    # {'table': 'table_name', 'column': 'column_name', 'type': 'TYPE', 'description': 'What it does'},
]


def check_column_exists(inspector, table_name, column_name):
    """
    SOLID: Single Responsibility - Check if column exists

    Args:
        inspector: SQLAlchemy inspector
        table_name: Name of table
        column_name: Name of column

    Returns:
        bool: True if column exists
    """
    try:
        columns = [c['name'] for c in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def apply_single_migration(conn, migration):
    """
    SOLID: Single Responsibility - Apply one migration

    Args:
        conn: SQLAlchemy connection
        migration: Migration dictionary

    Returns:
        bool: True if migration was applied
    """
    table = migration['table']
    column = migration['column']
    col_type = migration['type']
    default = migration.get('default', None)

    try:
        # Build ALTER TABLE statement
        sql = f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'
        if default is not None:
            sql += f' DEFAULT {default}'

        conn.execute(text(sql))
        conn.commit()
        return True
    except Exception as e:
        print(f"⚠️  Migration failed for {table}.{column}: {e}")
        conn.rollback()
        return False


def run_migrations(engine, verbose=True):
    """
    SOLID: Open/Closed - Run all pending migrations from MIGRATIONS list

    Add new migrations to MIGRATIONS list above - no code changes needed!

    Args:
        engine: SQLAlchemy engine
        verbose: Print migration messages (default: True)

    Returns:
        dict: Summary {'applied': int, 'skipped': int, 'failed': int}
    """
    inspector = inspect(engine)
    summary = {'applied': 0, 'skipped': 0, 'failed': 0}

    for migration in MIGRATIONS:
        table = migration['table']
        column = migration['column']
        description = migration.get('description', '')

        # Check if column already exists
        if check_column_exists(inspector, table, column):
            summary['skipped'] += 1
            continue

        # Apply migration
        if verbose:
            print(f"🔧 Migrating: {table}.{column} - {description}")

        with engine.connect() as conn:
            if apply_single_migration(conn, migration):
                summary['applied'] += 1
                if verbose:
                    print(f"   ✅ Applied: {table}.{column}")
            else:
                summary['failed'] += 1

    # Print summary if any migrations ran
    if verbose and (summary['applied'] > 0 or summary['failed'] > 0):
        print(f"\n📊 Migration Summary:")
        print(f"   ✅ Applied: {summary['applied']}")
        print(f"   ⏭️  Skipped: {summary['skipped']} (already exist)")
        if summary['failed'] > 0:
            print(f"   ❌ Failed:  {summary['failed']}")

    return summary


def list_pending_migrations(engine):
    """
    SOLID: Single Responsibility - List migrations that haven't been applied yet

    Args:
        engine: SQLAlchemy engine

    Returns:
        list: Pending migrations
    """
    inspector = inspect(engine)
    pending = []

    for migration in MIGRATIONS:
        table = migration['table']
        column = migration['column']

        if not check_column_exists(inspector, table, column):
            pending.append(migration)

    return pending


if __name__ == "__main__":
    """Test/demo the migration system"""
    import sys
    import os

    # Add parent directory to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from core.models import get_engine

    print("="*60)
    print("DATABASE MIGRATION UTILITY")
    print("="*60)

    engine = get_engine()

    # List pending migrations
    pending = list_pending_migrations(engine)

    if pending:
        print(f"\n⏳ Found {len(pending)} pending migrations:")
        for mig in pending:
            print(f"   • {mig['table']}.{mig['column']} - {mig.get('description', '')}")

        response = input("\n▶️  Apply migrations? (y/n): ")
        if response.lower() == 'y':
            summary = run_migrations(engine, verbose=True)
            print(f"\n✅ Migration complete!")
    else:
        print("\n✅ No pending migrations - database is up to date!")
