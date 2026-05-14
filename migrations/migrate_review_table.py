#!/usr/bin/env python3
"""
Create review_emails table
"""
import sqlite3
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.paths import DB_PATH

def migrate():
    """Create review_emails table if it doesn't exist"""

    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        print("Run the Flask app first to create the database.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='review_emails'
    """)

    if cursor.fetchone():
        print("✅ review_emails table already exists")
    else:
        print("Creating review_emails table...")

        cursor.execute("""
            CREATE TABLE review_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gmail_message_id VARCHAR(100) UNIQUE NOT NULL,
                subject VARCHAR(500) NOT NULL,
                from_header VARCHAR(200),
                from_email VARCHAR(200),
                from_domain VARCHAR(100),
                date DATETIME,
                raw_email TEXT,
                screenshot_path VARCHAR(500),
                classification_reason VARCHAR(500),
                status VARCHAR(20) DEFAULT 'pending',
                press_release_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME,
                FOREIGN KEY (press_release_id) REFERENCES press_releases(id)
            )
        """)

        # Create index on gmail_message_id for faster lookups
        cursor.execute("""
            CREATE INDEX idx_review_emails_gmail_id ON review_emails(gmail_message_id)
        """)

        # Create index on status for filtering
        cursor.execute("""
            CREATE INDEX idx_review_emails_status ON review_emails(status)
        """)

        conn.commit()
        print("✅ review_emails table created successfully")

    # Add screenshot_path column if it doesn't exist
    cursor.execute("PRAGMA table_info(review_emails)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'screenshot_path' not in columns:
        print("Adding screenshot_path column...")
        cursor.execute("ALTER TABLE review_emails ADD COLUMN screenshot_path VARCHAR(500)")
        conn.commit()
        print("✅ screenshot_path column added")

    # Show stats
    cursor.execute("SELECT COUNT(*) FROM review_emails")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM review_emails WHERE status = 'pending'")
    pending = cursor.fetchone()[0]

    print(f"\nReview Emails:")
    print(f"  Total: {total}")
    print(f"  Pending: {pending}")

    conn.close()


if __name__ == '__main__':
    migrate()
