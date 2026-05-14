"""
Setup Binary Relevance System
==============================
Creates relevance_decisions table and adds relevance column to press_releases
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import get_engine
from utils.db_migrations import run_migrations
from sqlalchemy import text

def setup_relevance_system():
    """Setup binary relevance tracking system."""
    print("=" * 70)
    print("BINARY RELEVANCE SYSTEM SETUP")
    print("=" * 70)
    print()

    # Run migrations (adds relevance column)
    print("1. Running migrations...")
    engine = get_engine()
    run_migrations(engine, verbose=True)
    print()

    # Create relevance_decisions table
    print("2. Creating relevance_decisions table...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS relevance_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                press_release_id INTEGER NOT NULL,
                decision TEXT NOT NULL,
                decided_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                decided_by TEXT DEFAULT 'user',
                FOREIGN KEY (press_release_id) REFERENCES press_releases(id)
            )
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_relevance_decisions_pr_id
            ON relevance_decisions(press_release_id)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_press_releases_relevance
            ON press_releases(relevance)
        """))

        conn.commit()

    print("✅ relevance_decisions table created")
    print()

    # Check counts
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM press_releases WHERE deleted_at IS NULL")).fetchone()[0]
        relevant = conn.execute(text("SELECT COUNT(*) FROM press_releases WHERE relevance = 'relevant'")).fetchone()[0]
        not_relevant = conn.execute(text("SELECT COUNT(*) FROM press_releases WHERE relevance = 'not_relevant'")).fetchone()[0]
        uncategorized = total - relevant - not_relevant

    print("=" * 70)
    print("PRESS RELEASE SUMMARY")
    print("=" * 70)
    print(f"Total press releases: {total}")
    print(f"  ✅ Relevant: {relevant}")
    print(f"  ❌ Not Relevant: {not_relevant}")
    print(f"  ⏳ Uncategorized: {uncategorized}")
    print()

    print("=" * 70)
    print("SETUP COMPLETE!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Start Flask app: python app.py")
    print("2. Go to /review page")
    print("3. Categorize press releases as relevant/not relevant")
    print()

if __name__ == '__main__':
    setup_relevance_system()
