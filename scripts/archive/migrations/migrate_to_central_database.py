#!/usr/bin/env python3
"""
Database Consolidation Migration Script

This script handles the production migration to the central database.
It safely backs up and deprecates old database files.

Usage:
    python scripts/migrate_to_central_database.py [--dry-run]

What it does:
1. Validates central database exists and has all required tables
2. Backs up old database files with timestamp
3. Archives old databases to data/archived_dbs/
4. Creates .deprecated marker files to prevent accidental use
5. Generates migration report

Safety features:
- Dry-run mode for testing
- Automatic backups before any destructive operations
- Validation checks at each step
- Detailed logging of all actions
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DatabaseMigration:
    """Handles migration to central database"""

    # Old database files to deprecate
    OLD_DATABASES = [
        "data/mailq_tracking.db",
        "mailq/digest_rules.db",
        "data/digest_feedback.db",
        "mailq/data/digest_feedback.db",
    ]

    # Required tables in central database
    REQUIRED_TABLES = [
        "email_threads",  # From mailq_tracking.db
        "digest_rules",  # From digest_rules.db
        "digest_feedback",  # From digest_feedback.db
        "digest_patterns",  # From digest_feedback.db
    ]

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.project_root = Path(__file__).parent.parent
        # Get central database path (check environment variable, fallback to default)
        db_path_env = os.getenv("MAILQ_DB_PATH")
        if db_path_env:
            self.central_db_path = Path(db_path_env)
        else:
            self.central_db_path = self.project_root / "mailq" / "data" / "mailq.db"
        self.archive_dir = self.project_root / "data" / "archived_dbs"
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info("=" * 80)
        logger.info("DATABASE CONSOLIDATION MIGRATION")
        logger.info("=" * 80)
        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No changes will be made")
        logger.info(f"Central database: {self.central_db_path}")
        logger.info(f"Archive directory: {self.archive_dir}")
        logger.info("")

    def validate_central_database(self) -> bool:
        """Validate central database exists and has required tables"""
        logger.info("📋 Step 1: Validating central database...")

        if not self.central_db_path.exists():
            logger.error(f"❌ Central database not found: {self.central_db_path}")
            logger.error("   Run: python -m mailq.config.database init_database()")
            return False

        # Check for required tables
        with sqlite3.connect(self.central_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            existing_tables = {row[0] for row in cursor.fetchall()}

        missing_tables = set(self.REQUIRED_TABLES) - existing_tables
        if missing_tables:
            logger.error(f"❌ Central database missing tables: {missing_tables}")
            logger.error("   Run: python -m mailq.config.database init_database()")
            return False

        logger.info(f"✅ Central database valid ({len(existing_tables)} tables)")
        for table in sorted(self.REQUIRED_TABLES):
            logger.info(f"   ✓ {table}")

        return True

    def find_old_databases(self) -> list[Path]:
        """Find old database files that exist"""
        found = []
        for db_path_str in self.OLD_DATABASES:
            db_path = self.project_root / db_path_str
            if db_path.exists():
                found.append(db_path)
                logger.info(f"   📦 Found: {db_path.relative_to(self.project_root)}")

        return found

    def backup_database(self, db_path: Path) -> Path | None:
        """Create timestamped backup of database file"""
        if not db_path.exists():
            return None

        # Create backup with timestamp
        backup_name = f"{db_path.stem}_backup_{self.timestamp}{db_path.suffix}"
        backup_path = db_path.parent / backup_name

        if self.dry_run:
            logger.info(f"   [DRY RUN] Would backup: {db_path.name} → {backup_name}")
            return backup_path

        shutil.copy2(db_path, backup_path)
        logger.info(f"   ✅ Backed up: {backup_name}")
        return backup_path

    def archive_database(self, db_path: Path) -> Path | None:
        """Move database to archive directory"""
        if not db_path.exists():
            return None

        # Create archive directory
        if not self.dry_run:
            self.archive_dir.mkdir(parents=True, exist_ok=True)

        archive_path = self.archive_dir / db_path.name

        if self.dry_run:
            logger.info(f"   [DRY RUN] Would archive: {db_path.name} → archived_dbs/{db_path.name}")
            return archive_path

        # If file already exists in archive, rename with timestamp
        if archive_path.exists():
            archive_path = self.archive_dir / f"{db_path.stem}_{self.timestamp}{db_path.suffix}"

        shutil.move(str(db_path), str(archive_path))
        logger.info(f"   ✅ Archived: {archive_path.name}")
        return archive_path

    def create_deprecated_marker(self, original_path: Path):
        """Create .deprecated marker file to prevent accidental use"""
        marker_path = original_path.with_suffix(".db.deprecated")

        marker_content = f"""
This database file has been deprecated and consolidated into the central database.

Original file: {original_path.name}
Deprecated on: {datetime.now().isoformat()}
Archived to: data/archived_dbs/{original_path.name}
Central database: {self.central_db_path.relative_to(self.project_root)}

DO NOT create new database files. Use get_db_connection() from mailq.shared.database.

Migration commit: See git log for database consolidation commits
"""

        if self.dry_run:
            logger.info(f"   [DRY RUN] Would create marker: {marker_path.name}")
            return

        marker_path.write_text(marker_content.strip())
        logger.info(f"   ✅ Created marker: {marker_path.name}")

    def migrate(self) -> bool:
        """Run complete migration"""
        try:
            # Step 1: Validate central database
            if not self.validate_central_database():
                return False

            logger.info("")
            logger.info("📋 Step 2: Finding old database files...")
            old_dbs = self.find_old_databases()

            if not old_dbs:
                logger.info("✅ No old database files found - migration already complete!")
                return True

            logger.info(f"   Found {len(old_dbs)} old database file(s)")
            logger.info("")

            # Step 3: Backup and archive each old database
            logger.info("📋 Step 3: Backing up and archiving old databases...")
            for db_path in old_dbs:
                logger.info(f"\n   Processing: {db_path.relative_to(self.project_root)}")

                # Check file size
                size_kb = db_path.stat().st_size / 1024
                logger.info(f"   Size: {size_kb:.1f} KB")

                # Backup
                self.backup_database(db_path)

                # Archive
                archive_path = self.archive_database(db_path)

                # Create deprecated marker
                if archive_path:
                    self.create_deprecated_marker(db_path)

            logger.info("")
            logger.info("=" * 80)
            logger.info("✅ MIGRATION COMPLETE")
            logger.info("=" * 80)
            logger.info("")
            logger.info("Summary:")
            logger.info(f"  • Central database: {self.central_db_path}")
            logger.info(f"  • Old databases archived: {len(old_dbs)}")
            logger.info(f"  • Archive location: {self.archive_dir}")
            logger.info("")
            logger.info("Next steps:")
            logger.info("  1. Verify application still works correctly")
            logger.info("  2. Check API endpoints: /api/tracking/sessions")
            logger.info("  3. Test digest generation")
            logger.info("  4. After 30 days, you can safely delete archived_dbs/")
            logger.info("")

            if self.dry_run:
                logger.info("⚠️  This was a DRY RUN - no changes were made")
                logger.info("   Run without --dry-run to execute migration")

            return True

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            import traceback

            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(
        description="Migrate to central database and deprecate old database files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    migration = DatabaseMigration(dry_run=args.dry_run)
    success = migration.migrate()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
