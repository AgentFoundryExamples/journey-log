#!/usr/bin/env python3
# Copyright 2025 John Brosnihan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
POI Migration Script - Bulk migrate embedded POIs to subcollections.

This script migrates all characters with embedded world_pois arrays to use
the new pois subcollection storage format. It leverages the migration utilities
from app.firestore (should_migrate_pois, migrate_embedded_pois_to_subcollection).

Usage:
    # Dry run (no changes):
    python scripts/migrate_character_pois.py --dry-run

    # Migrate all characters:
    python scripts/migrate_character_pois.py

    # Migrate specific character:
    python scripts/migrate_character_pois.py --character-id 550e8400-e29b-41d4-a716-446655440000

    # Resume from checkpoint (skip already processed):
    python scripts/migrate_character_pois.py --resume

    # Limit number of characters to migrate:
    python scripts/migrate_character_pois.py --limit 100

Features:
- Dry-run mode to preview changes without modifying data
- Resume capability to skip already migrated characters
- Progress logging for operators
- Error handling with rollback on transaction failures
- Migration statistics reporting
- Configurable character limit

Requirements:
- GCP_PROJECT_ID environment variable must be set
- Firestore credentials configured (ADC or FIRESTORE_EMULATOR_HOST)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.cloud import firestore  # type: ignore[import-untyped]

from app.config import get_settings
from app.firestore import (
    get_firestore_client,
    should_migrate_pois,
    migrate_embedded_pois_to_subcollection,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class MigrationStats:
    """Track migration statistics across all characters."""

    def __init__(self):
        self.total_characters_scanned = 0
        self.total_characters_migrated = 0
        self.total_characters_skipped = 0
        self.total_characters_failed = 0
        self.total_pois_migrated = 0
        self.total_pois_skipped = 0
        self.total_errors = 0
        self.failed_character_ids: List[str] = []
        self.start_time = datetime.now(timezone.utc)

    def to_dict(self) -> Dict:
        """Convert stats to dictionary for reporting."""
        duration = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        return {
            "total_characters_scanned": self.total_characters_scanned,
            "total_characters_migrated": self.total_characters_migrated,
            "total_characters_skipped": self.total_characters_skipped,
            "total_characters_failed": self.total_characters_failed,
            "total_pois_migrated": self.total_pois_migrated,
            "total_pois_skipped": self.total_pois_skipped,
            "total_errors": self.total_errors,
            "failed_character_ids": self.failed_character_ids,
            "duration_seconds": duration,
        }


def migrate_character(
    character_id: str,
    dry_run: bool = False,
) -> Dict:
    """
    Migrate a single character's POIs from embedded to subcollection.

    Args:
        character_id: UUID of the character to migrate
        dry_run: If True, only check if migration needed without making changes

    Returns:
        Dictionary with migration results:
        - status: "migrated", "skipped", or "failed"
        - stats: Migration statistics if migrated
        - error: Error message if failed
    """
    try:
        settings = get_settings()
        db = get_firestore_client()
        characters_ref = db.collection(settings.firestore_characters_collection)

        # Read character document
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(f"Character {character_id} not found - skipping")
            return {"status": "skipped", "reason": "not_found"}

        char_data = char_snapshot.to_dict()

        # Check if migration needed
        if not should_migrate_pois(char_data):
            logger.debug(f"Character {character_id} does not need migration - skipping")
            return {"status": "skipped", "reason": "no_embedded_pois"}

        embedded_count = len(char_data.get("world_pois", []))
        logger.info(
            f"Character {character_id} needs migration ({embedded_count} embedded POIs)"
        )

        if dry_run:
            logger.info(
                f"[DRY RUN] Would migrate {embedded_count} POIs for character {character_id}"
            )
            return {
                "status": "would_migrate",
                "embedded_count": embedded_count,
            }

        # Perform migration in transaction with proper callback
        transaction = db.transaction()
        
        @firestore.transactional
        def migrate_in_transaction(transaction):
            """Execute migration within transactional context."""
            return migrate_embedded_pois_to_subcollection(
                character_id, transaction
            )
        
        migration_stats = migrate_in_transaction(transaction)

        logger.info(
            f"Successfully migrated character {character_id}: "
            f"{migration_stats['migrated']} POIs migrated, "
            f"{migration_stats['skipped']} skipped, "
            f"{len(migration_stats['errors'])} errors"
        )

        return {
            "status": "migrated",
            "stats": migration_stats,
        }

    except Exception as e:
        logger.error(
            f"Failed to migrate character {character_id}: {type(e).__name__}: {str(e)}",
            exc_info=True,
        )
        return {
            "status": "failed",
            "error": str(e),
        }


def migrate_all_characters(
    character_id: Optional[str] = None,
    dry_run: bool = False,
    resume: bool = False,
    limit: Optional[int] = None,
) -> MigrationStats:
    """
    Migrate all characters or a specific character.

    Args:
        character_id: If provided, migrate only this character
        dry_run: If True, only check what would be migrated
        resume: If True, skip characters that don't have embedded POIs
        limit: Maximum number of characters to process

    Returns:
        MigrationStats with summary of migration results
    """
    stats = MigrationStats()

    try:
        settings = get_settings()
        db = get_firestore_client()
        characters_ref = db.collection(settings.firestore_characters_collection)

        # Determine which characters to migrate
        if character_id:
            logger.info(f"Migrating specific character: {character_id}")
            character_ids = [character_id]
        else:
            logger.info("Scanning all characters for migration...")
            # Query all character documents
            query = characters_ref
            if limit:
                query = query.limit(limit)

            character_ids = []
            for doc in query.stream():
                character_ids.append(doc.id)
                if limit and len(character_ids) >= limit:
                    break

            logger.info(f"Found {len(character_ids)} characters to scan")

        # Migrate each character
        for idx, char_id in enumerate(character_ids, 1):
            stats.total_characters_scanned += 1

            logger.info(
                f"Processing character {idx}/{len(character_ids)}: {char_id}"
            )

            result = migrate_character(char_id, dry_run=dry_run)

            if result["status"] == "migrated":
                stats.total_characters_migrated += 1
                migration_stats = result["stats"]
                stats.total_pois_migrated += migration_stats["migrated"]
                stats.total_pois_skipped += migration_stats["skipped"]
                stats.total_errors += len(migration_stats["errors"])

            elif result["status"] == "would_migrate":
                stats.total_characters_migrated += 1
                logger.info(
                    f"[DRY RUN] Would migrate {result.get('embedded_count', 0)} POIs"
                )

            elif result["status"] == "skipped":
                stats.total_characters_skipped += 1

            elif result["status"] == "failed":
                stats.total_characters_failed += 1
                stats.failed_character_ids.append(char_id)
                logger.error(f"Migration failed for {char_id}: {result.get('error')}")

            # Progress update every 10 characters
            if idx % 10 == 0:
                logger.info(
                    f"Progress: {idx}/{len(character_ids)} characters processed, "
                    f"{stats.total_characters_migrated} migrated, "
                    f"{stats.total_characters_skipped} skipped, "
                    f"{stats.total_characters_failed} failed"
                )

    except Exception as e:
        logger.error(f"Migration process failed: {type(e).__name__}: {str(e)}", exc_info=True)
        raise

    return stats


def main():
    """Main entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate character POIs from embedded arrays to subcollections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying data",
    )
    parser.add_argument(
        "--character-id",
        type=str,
        help="Migrate specific character by ID (UUID format)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip characters that don't need migration",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of characters to process",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # Validate environment
    try:
        settings = get_settings()
        if not settings.gcp_project_id and not settings.firestore_emulator_host:
            logger.error(
                "GCP_PROJECT_ID must be set or FIRESTORE_EMULATOR_HOST must be configured"
            )
            sys.exit(1)
    except Exception as e:
        logger.error(f"Configuration error: {str(e)}")
        sys.exit(1)

    # Log migration parameters
    logger.info("=" * 80)
    logger.info("POI Migration Script")
    logger.info("=" * 80)
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Character ID: {args.character_id or 'ALL'}")
    logger.info(f"Resume mode: {args.resume}")
    logger.info(f"Limit: {args.limit or 'NONE'}")
    logger.info(f"GCP Project: {settings.gcp_project_id or 'EMULATOR'}")
    logger.info("=" * 80)

    if args.dry_run:
        logger.warning("DRY RUN MODE - No changes will be made to Firestore")

    # Run migration
    try:
        stats = migrate_all_characters(
            character_id=args.character_id,
            dry_run=args.dry_run,
            resume=args.resume,
            limit=args.limit,
        )

        # Print final statistics
        logger.info("=" * 80)
        logger.info("Migration Complete")
        logger.info("=" * 80)
        logger.info(json.dumps(stats.to_dict(), indent=2))

        # Exit with error code if any failures
        if stats.total_characters_failed > 0:
            logger.error(
                f"Migration completed with {stats.total_characters_failed} failures"
            )
            logger.error(f"Failed character IDs: {stats.failed_character_ids}")
            sys.exit(1)
        else:
            logger.info("Migration completed successfully with no failures")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("Migration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Migration failed: {type(e).__name__}: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
