#!/usr/bin/env python3
"""
Migration: Add newswire fields to Company model
- newswire_provider (GlobeNewswire, Business Wire, PR Newswire, Other)
- newswire_id (org ID like 34254 for AAT)
"""

import sqlite3
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.paths import DB_PATH

def add_newswire_fields():
    """Add newswire_provider and newswire_id columns to Company table"""
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(companies)")
        columns = [row[1] for row in cursor.fetchall()]
        
        changes_made = False
        
        if 'newswire_provider' not in columns:
            print("Adding 'newswire_provider' column...")
            cursor.execute("ALTER TABLE companies ADD COLUMN newswire_provider VARCHAR")
            changes_made = True
            print("✓ Added newswire_provider")
        else:
            print("✓ newswire_provider already exists")
        
        if 'newswire_id' not in columns:
            print("Adding 'newswire_id' column...")
            cursor.execute("ALTER TABLE companies ADD COLUMN newswire_id VARCHAR")
            changes_made = True
            print("✓ Added newswire_id")
        else:
            print("✓ newswire_id already exists")
        
        if changes_made:
            conn.commit()
            print("\n✓ Migration completed successfully")
        else:
            print("\n✓ No changes needed - columns already exist")
        
        # Show updated schema
        print("\nCurrent Company table schema:")
        print("-" * 60)
        cursor.execute("PRAGMA table_info(companies)")
        for row in cursor.fetchall():
            col_id, name, type_, notnull, default, pk = row
            print(f"  {name:25} {type_:15} {'NOT NULL' if notnull else ''}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("Migration: Add newswire fields to Company")
    print("=" * 60)
    print()
    
    success = add_newswire_fields()
    
    if not success:
        print("\n" + "=" * 60)
        print("Migration failed!")
        print("=" * 60)
