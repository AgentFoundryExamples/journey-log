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
Cleanup script to remove legacy numeric health fields from Firestore character documents.

This script scans character documents and removes deprecated numeric health/stat fields
such as level, experience, stats, current_hp, max_hp, current_health, max_health, and health.

Features:
- Dry-run mode to preview changes without modifying data
- Batch processing with configurable delays
- Atomic per-document updates
- Progress logging and audit trail
- Graceful error handling
- Idempotent (safe to run multiple times)

Usage:
    # Preview changes without modifying data (recommended first)
    python scripts/remove_numeric_health.py --dry-run

    # Apply changes to all documents
    python scripts/remove_numeric_health.py

    # Clean specific documents
    python scripts/remove_numeric_health.py --character-ids char_001 char_002

    # Process with custom batch settings
    python scripts/remove_numeric_health.py --batch-size 50 --batch-delay 0.1

Environment Variables:
    GCP_PROJECT_ID: Required - GCP project ID
    FIRESTORE_CHARACTERS_COLLECTION: Optional - Collection name (default: "characters")
    FIRESTORE_EMULATOR_HOST: Optional - Emulator host for local testing
"""

import argparse
import os
import sys
import time
from typing import List, Optional, Set

from google.cloud import firestore  # type: ignore[import-untyped]
from google.cloud.firestore_v1 import FieldFilter  # type: ignore[import-untyped]


# Deprecated fields to remove from player_state
DEPRECATED_FIELDS = [
    "level",
    "experience",
    "stats",
    "current_hp",
    "max_hp",
    "current_health",
    "max_health",
    "health",
]


def get_firestore_client(project_id: str) -> firestore.Client:
    """
    Initialize and return a Firestore client.

    Args:
        project_id: GCP project ID

    Returns:
        Firestore client instance
    """
    # Check for emulator
    emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
    if emulator_host:
        os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
        print(f"INFO: Using Firestore emulator at {emulator_host}")

    return firestore.Client(project=project_id)


def get_documents_to_process(
    db: firestore.Client,
    collection_name: str,
    character_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[firestore.DocumentSnapshot]:
    """
    Get character documents to process.

    Args:
        db: Firestore client
        collection_name: Collection name
        character_ids: Optional list of specific character IDs to process
        limit: Optional limit on number of documents to process

    Returns:
        List of document snapshots
    """
    characters_ref = db.collection(collection_name)

    if character_ids:
        # Fetch specific documents
        documents = []
        for char_id in character_ids:
            doc = characters_ref.document(char_id).get()
            if doc.exists:
                documents.append(doc)
            else:
                print(f"WARNING: Character {char_id} not found")
        return documents
    else:
        # Fetch all documents
        query = characters_ref
        if limit:
            query = query.limit(limit)
        return list(query.stream())


def find_legacy_fields(player_state: dict) -> List[str]:
    """
    Find deprecated fields in player_state.

    Args:
        player_state: Player state dictionary

    Returns:
        List of deprecated field names found
    """
    return [field for field in DEPRECATED_FIELDS if field in player_state]


def remove_legacy_fields_from_document(
    db: firestore.Client,
    doc_ref: firestore.DocumentReference,
    dry_run: bool = False,
) -> tuple[bool, List[str]]:
    """
    Remove legacy numeric health fields from a single character document.

    Args:
        db: Firestore client
        doc_ref: Document reference
        dry_run: If True, only log what would be done without modifying

    Returns:
        Tuple of (modified, fields_removed)
        - modified: True if document had legacy fields (or would have been modified)
        - fields_removed: List of field names that were (or would be) removed
    """
    doc = doc_ref.get()
    if not doc.exists:
        return False, []

    data = doc.to_dict()
    player_state = data.get("player_state")

    if not player_state or not isinstance(player_state, dict):
        return False, []

    # Find legacy fields
    legacy_fields = find_legacy_fields(player_state)

    if not legacy_fields:
        return False, []

    # Check if status field exists (log warning if missing but don't fail)
    if "status" not in player_state:
        print(
            f"WARNING: Document {doc_ref.id} has legacy fields but missing 'status' field - skipping"
        )
        return False, []

    # Remove legacy fields
    if not dry_run:
        # Build update dict with field deletes
        updates = {
            f"player_state.{field}": firestore.DELETE_FIELD for field in legacy_fields
        }
        try:
            doc_ref.update(updates)
        except Exception as e:
            print(f"ERROR: Failed to update document {doc_ref.id}: {e}")
            return False, []

    return True, legacy_fields


def process_documents(
    db: firestore.Client,
    collection_name: str,
    character_ids: Optional[List[str]] = None,
    limit: Optional[int] = None,
    batch_size: int = 10,
    batch_delay: float = 0.5,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Process character documents and remove legacy fields.

    Args:
        db: Firestore client
        collection_name: Collection name
        character_ids: Optional list of specific character IDs
        limit: Optional limit on documents to process
        batch_size: Number of documents to process before delay
        batch_delay: Seconds to wait between batches
        dry_run: If True, preview changes without modifying

    Returns:
        Tuple of (total_processed, documents_cleaned)
    """
    print(f"INFO: Scanning character documents in collection '{collection_name}'...")

    documents = get_documents_to_process(db, collection_name, character_ids, limit)
    total_docs = len(documents)

    if total_docs == 0:
        print("INFO: No documents found to process")
        return 0, 0

    print(f"INFO: Found {total_docs} document(s) to scan")

    documents_cleaned = 0
    total_processed = 0
    all_removed_fields: Set[str] = set()

    for i, doc in enumerate(documents):
        total_processed += 1
        doc_ref = db.collection(collection_name).document(doc.id)

        modified, fields_removed = remove_legacy_fields_from_document(
            db, doc_ref, dry_run=dry_run
        )

        if modified:
            documents_cleaned += 1
            all_removed_fields.update(fields_removed)
            action = "Would remove" if dry_run else "Removed"
            print(
                f"{action} legacy fields from {doc.id}: {', '.join(fields_removed)}"
            )

        # Progress logging every 10 documents
        if (i + 1) % 10 == 0:
            print(f"INFO: Processed {i + 1}/{total_docs} documents...")

        # Batch delay
        if (i + 1) % batch_size == 0 and (i + 1) < total_docs:
            time.sleep(batch_delay)

    print(f"\nINFO: Processed {total_processed} document(s)")
    print(f"INFO: Documents with legacy fields: {documents_cleaned}")
    if all_removed_fields:
        print(f"INFO: Legacy fields found: {', '.join(sorted(all_removed_fields))}")

    return total_processed, documents_cleaned


def main():
    """Main entry point for the cleanup script."""
    parser = argparse.ArgumentParser(
        description="Remove legacy numeric health fields from Firestore character documents"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying documents",
    )
    parser.add_argument(
        "--character-ids",
        nargs="+",
        help="Process only specific character IDs (space-separated)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process at most N documents (for testing)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of documents to process before delay (default: 10)",
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=0.5,
        help="Seconds to wait between batches (default: 0.5)",
    )

    args = parser.parse_args()

    # Get configuration from environment
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        print("ERROR: GCP_PROJECT_ID environment variable is required")
        sys.exit(1)

    collection_name = os.getenv("FIRESTORE_CHARACTERS_COLLECTION", "characters")

    # Print configuration
    print("=" * 80)
    print("Numeric Health Field Cleanup Script")
    print("=" * 80)
    print(f"Project ID: {project_id}")
    print(f"Collection: {collection_name}")
    print(f"Dry Run: {args.dry_run}")
    if args.character_ids:
        print(f"Specific Characters: {', '.join(args.character_ids)}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print(f"Batch Size: {args.batch_size}")
    print(f"Batch Delay: {args.batch_delay}s")
    print("=" * 80)

    if args.dry_run:
        print("INFO: Dry run mode enabled - no changes will be made")
    else:
        print("WARNING: This will modify documents in Firestore!")
        response = input("Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted by user")
            sys.exit(0)

    # Initialize Firestore client
    try:
        db = get_firestore_client(project_id)
    except Exception as e:
        print(f"ERROR: Failed to initialize Firestore client: {e}")
        sys.exit(1)

    # Process documents
    try:
        total_processed, documents_cleaned = process_documents(
            db=db,
            collection_name=collection_name,
            character_ids=args.character_ids,
            limit=args.limit,
            batch_size=args.batch_size,
            batch_delay=args.batch_delay,
            dry_run=args.dry_run,
        )

        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Total documents processed: {total_processed}")
        print(
            f"Documents cleaned: {documents_cleaned} {'(dry run)' if args.dry_run else ''}"
        )

        if args.dry_run and documents_cleaned > 0:
            print("\nTo apply these changes, run the script without --dry-run")

    except Exception as e:
        print(f"ERROR: Script failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
