"""
Database Backup Utility

CRITICAL: Always backup before schema changes or major operations.
"""
import sys
import os
from pathlib import Path
from datetime import datetime
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.paths import DB_PATH

# Backup directory
BACKUP_DIR = Path(__file__).parent.parent / 'data' / 'backups'
BACKUP_DIR.mkdir(exist_ok=True)


def create_backup(reason="manual"):
    """
    Create a timestamped backup of the database

    Args:
        reason: Why the backup is being created (e.g., 'pre-migration', 'manual')

    Returns:
        Path to backup file
    """
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return None

    # Get database size
    db_size = os.path.getsize(DB_PATH)

    # Create backup filename with timestamp and reason
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"reit_newsletter_{timestamp}_{reason}.db"
    backup_path = BACKUP_DIR / backup_filename

    # Copy database
    print(f"📦 Creating backup: {backup_filename}")
    shutil.copy2(DB_PATH, backup_path)

    print(f"✅ Backup created: {backup_path}")
    print(f"   Size: {db_size:,} bytes")

    return backup_path


def list_backups():
    """List all available backups"""
    backups = sorted(BACKUP_DIR.glob("*.db"), reverse=True)

    if not backups:
        print("No backups found.")
        return []

    print(f"\n📋 Available backups ({len(backups)}):")
    print("="*80)

    for backup in backups:
        size = os.path.getsize(backup)
        mtime = datetime.fromtimestamp(backup.stat().st_mtime)
        print(f"  {backup.name}")
        print(f"    Size: {size:,} bytes | Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

    return backups


def restore_backup(backup_path):
    """
    Restore database from backup

    Args:
        backup_path: Path to backup file
    """
    if not os.path.exists(backup_path):
        print(f"❌ Backup not found: {backup_path}")
        return False

    # Create safety backup of current database
    if os.path.exists(DB_PATH):
        safety_backup = create_backup(reason="pre-restore")
        print(f"🔒 Created safety backup: {safety_backup}")

    # Restore from backup
    print(f"♻️  Restoring from: {backup_path}")
    shutil.copy2(backup_path, DB_PATH)

    print(f"✅ Database restored successfully!")
    return True


def cleanup_old_backups(keep_count=10):
    """
    Keep only the most recent N backups

    Args:
        keep_count: Number of recent backups to keep
    """
    backups = sorted(BACKUP_DIR.glob("*.db"), reverse=True)

    if len(backups) <= keep_count:
        print(f"✅ Only {len(backups)} backups exist (keeping all)")
        return

    to_delete = backups[keep_count:]
    print(f"🗑️  Removing {len(to_delete)} old backups...")

    for backup in to_delete:
        backup.unlink()
        print(f"   Deleted: {backup.name}")

    print(f"✅ Cleanup complete. {keep_count} backups retained.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Database backup utility')
    parser.add_argument('action', choices=['backup', 'list', 'restore', 'cleanup'],
                       help='Action to perform')
    parser.add_argument('--reason', default='manual',
                       help='Reason for backup (default: manual)')
    parser.add_argument('--file', help='Backup file to restore')
    parser.add_argument('--keep', type=int, default=10,
                       help='Number of backups to keep (default: 10)')

    args = parser.parse_args()

    if args.action == 'backup':
        create_backup(args.reason)

    elif args.action == 'list':
        list_backups()

    elif args.action == 'restore':
        if not args.file:
            print("❌ Must specify --file for restore")
            sys.exit(1)
        restore_backup(args.file)

    elif args.action == 'cleanup':
        cleanup_old_backups(args.keep)
