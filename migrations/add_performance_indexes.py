"""
Performance Optimization Migration

Adds missing database indexes to speed up common queries.
This migration is safe to run multiple times (idempotent).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from config.paths import DB_PATH

def add_performance_indexes():
    """Add indexes to improve query performance"""
    engine = create_engine(f'sqlite:///{DB_PATH}')
    inspector = inspect(engine)

    print("🔧 Adding performance indexes...")

    # Get existing indexes
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('companies')}
    existing_pr_indexes = {idx['name'] for idx in inspector.get_indexes('press_releases')}
    existing_review_indexes = {idx['name'] for idx in inspector.get_indexes('review_emails')}

    with engine.connect() as conn:
        # Companies indexes
        if 'ix_companies_active' not in existing_indexes:
            conn.execute(text('CREATE INDEX ix_companies_active ON companies (active)'))
            conn.commit()
            print("✅ Added index: companies.active")

        if 'ix_companies_sector' not in existing_indexes:
            conn.execute(text('CREATE INDEX ix_companies_sector ON companies (sector)'))
            conn.commit()
            print("✅ Added index: companies.sector")

        # Press releases indexes
        if 'ix_press_releases_deleted_at' not in existing_pr_indexes:
            conn.execute(text('CREATE INDEX ix_press_releases_deleted_at ON press_releases (deleted_at)'))
            conn.commit()
            print("✅ Added index: press_releases.deleted_at")

        # Review emails indexes
        if 'ix_review_emails_status' not in existing_review_indexes:
            conn.execute(text('CREATE INDEX ix_review_emails_status ON review_emails (status)'))
            conn.commit()
            print("✅ Added index: review_emails.status")

        # Composite indexes for common query patterns
        if 'ix_press_releases_company_date' not in existing_pr_indexes:
            conn.execute(text('''
                CREATE INDEX ix_press_releases_company_date
                ON press_releases (company_id, published_date DESC)
            '''))
            conn.commit()
            print("✅ Added composite index: press_releases (company_id, published_date)")

        if 'ix_press_releases_active' not in existing_pr_indexes:
            conn.execute(text('''
                CREATE INDEX ix_press_releases_active
                ON press_releases (deleted_at, published_date DESC)
            '''))
            conn.commit()
            print("✅ Added composite index: press_releases (deleted_at, published_date)")

    print("✅ Performance indexes migration complete!")

if __name__ == '__main__':
    add_performance_indexes()
