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
Firestore client module with lazy initialization.

Provides a singleton Firestore client instance that is lazily initialized
on first use. Supports both production (Application Default Credentials)
and local development (Firestore emulator) configurations.

Also provides helper functions for working with narrative turns subcollection.
"""

import os
import threading
from typing import Optional, List
from google.cloud import firestore  # type: ignore[import-untyped]

from app.config import get_settings

# Module-level singleton client and lock for thread safety
_firestore_client: Optional[firestore.Client] = None
_firestore_lock = threading.Lock()


def get_firestore_client() -> firestore.Client:
    """
    Get or create a Firestore client instance with thread-safe lazy initialization.

    This function implements lazy initialization of the Firestore client,
    creating it only on first use and reusing the same instance for
    subsequent calls (singleton pattern per process). Uses a lock to
    ensure thread safety in concurrent environments.

    Configuration:
    - Uses GCP_PROJECT_ID from settings for production
    - Supports Firestore emulator via FIRESTORE_EMULATOR_HOST env var
    - Uses Application Default Credentials (ADC) in production

    Returns:
        firestore.Client: The initialized Firestore client

    Raises:
        ValueError: If GCP_PROJECT_ID is not set in non-dev environments

    Example:
        >>> client = get_firestore_client()
        >>> doc_ref = client.collection('test').document('doc1')
    """
    global _firestore_client

    # Double-checked locking pattern for thread-safe lazy initialization
    if _firestore_client is None:
        with _firestore_lock:
            # Check again inside the lock to avoid race conditions
            if _firestore_client is None:
                settings = get_settings()

                # Check if using emulator
                emulator_host = settings.firestore_emulator_host
                if emulator_host:
                    # Set environment variable for Firestore emulator
                    os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
                    # For emulator, project_id can be any non-empty string
                    project_id = settings.gcp_project_id or "demo-project"
                else:
                    # Production mode - project_id is required
                    project_id = settings.gcp_project_id
                    if not project_id:
                        raise ValueError(
                            "GCP_PROJECT_ID must be set when not using Firestore emulator. "
                            "Set FIRESTORE_EMULATOR_HOST for local development."
                        )

                # Initialize the Firestore client
                _firestore_client = firestore.Client(project=project_id)

    return _firestore_client


def reset_firestore_client() -> None:
    """
    Reset the Firestore client singleton in a thread-safe manner.

    This function is primarily used for testing to ensure a fresh
    client instance is created with new settings.

    Warning:
        This should not be called in production code as it may cause
        connection issues with ongoing operations.
    """
    global _firestore_client
    with _firestore_lock:
        _firestore_client = None


# ==============================================================================
# Narrative Turns Subcollection Helpers
# ==============================================================================


def get_narrative_turns_collection(character_id: str) -> firestore.CollectionReference:
    """
    Get a reference to the narrative_turns subcollection for a character.

    Args:
        character_id: The UUID of the character

    Returns:
        CollectionReference to the narrative_turns subcollection

    Example:
        >>> collection = get_narrative_turns_collection("550e8400-e29b-41d4-a716-446655440000")
        >>> turns = collection.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
    """
    client = get_firestore_client()
    settings = get_settings()
    return (
        client.collection(settings.firestore_characters_collection)
        .document(character_id)
        .collection("narrative_turns")
    )


def write_narrative_turn(
    character_id: str, turn_data: dict, *, use_server_timestamp: bool = True
) -> firestore.DocumentReference:
    """
    Write a narrative turn to a character's narrative_turns subcollection.

    The turn is written to: characters/{character_id}/narrative_turns/{turn_id}

    Args:
        character_id: The UUID of the character
        turn_data: Dictionary containing turn data (must include 'turn_id')
        use_server_timestamp: If True, replace timestamp with SERVER_TIMESTAMP (default: True)

    Returns:
        DocumentReference to the written turn document

    Raises:
        ValueError: If turn_data is missing 'turn_id' or 'timestamp' (when use_server_timestamp=False)

    Example:
        >>> from app.models import narrative_turn_to_firestore, NarrativeTurn
        >>> turn = NarrativeTurn(...)
        >>> turn_data = narrative_turn_to_firestore(turn)
        >>> doc_ref = write_narrative_turn(character_id, turn_data)
    """
    if "turn_id" not in turn_data:
        raise ValueError("turn_data must include 'turn_id' field")

    turn_id = turn_data["turn_id"]

    # Optionally use server timestamp
    if use_server_timestamp:
        turn_data = dict(turn_data)  # Make a copy to avoid mutating input
        turn_data["timestamp"] = firestore.SERVER_TIMESTAMP
    else:
        # When not using server timestamp, validate that timestamp exists
        if "timestamp" not in turn_data:
            raise ValueError(
                "turn_data must include 'timestamp' field when use_server_timestamp=False"
            )

    collection = get_narrative_turns_collection(character_id)
    doc_ref = collection.document(turn_id)
    doc_ref.set(turn_data)

    return doc_ref


def query_narrative_turns(
    character_id: str,
    *,
    limit: Optional[int] = None,
    order_by: str = "timestamp",
    direction: str = "DESCENDING",
) -> List[dict]:
    """
    Query narrative turns for a character, ordered by timestamp.

    Always returns turns in oldest-to-newest order (chronological reading order),
    regardless of the query direction. When direction="DESCENDING" (default), the
    function queries newest-first for Firestore index efficiency and then reverses
    the results. When direction="ASCENDING", results are already in chronological order.

    Args:
        character_id: The UUID of the character
        limit: Maximum number of turns to retrieve (defaults to config default)
        order_by: Field to order by (default: "timestamp")
        direction: Sort direction - "ASCENDING" or "DESCENDING" (default: "DESCENDING")
            Note: Results are always returned oldest-to-newest regardless of this parameter

    Returns:
        List of turn dictionaries in oldest-to-newest order

    Example:
        >>> turns = query_narrative_turns(character_id, limit=10)
        >>> # Returns last 10 turns in chronological order (oldest first)
    """
    settings = get_settings()

    # Use default limit from config if not specified
    if limit is None:
        limit = settings.narrative_turns_default_query_size

    # Enforce max limit from config
    max_limit = settings.narrative_turns_max_query_size
    if limit > max_limit:
        limit = max_limit

    # Build query
    collection = get_narrative_turns_collection(character_id)
    query = collection.order_by(
        order_by,
        direction=firestore.Query.DESCENDING
        if direction == "DESCENDING"
        else firestore.Query.ASCENDING,
    )

    if limit:
        query = query.limit(limit)

    # Execute query and convert to list
    turns = [doc.to_dict() for doc in query.stream()]

    # Always return in oldest-to-newest order (chronological reading order)
    # If we queried DESCENDING (newest-first), reverse to get oldest-first
    if direction == "DESCENDING":
        turns.reverse()

    return turns


def get_narrative_turn_by_id(character_id: str, turn_id: str) -> Optional[dict]:
    """
    Get a specific narrative turn by ID.

    Args:
        character_id: The UUID of the character
        turn_id: The UUID of the turn

    Returns:
        Turn dictionary or None if not found

    Example:
        >>> turn = get_narrative_turn_by_id(character_id, turn_id)
        >>> if turn:
        ...     print(turn['player_action'])
    """
    collection = get_narrative_turns_collection(character_id)
    doc = collection.document(turn_id).get()

    if doc.exists:
        return doc.to_dict()
    return None


def count_narrative_turns(character_id: str) -> int:
    """
    Count the total number of narrative turns for a character.

    This function uses Firestore's count() aggregation, which is efficient
    and incurs the cost of a single document read.

    Args:
        character_id: The UUID of the character

    Returns:
        Total number of narrative turns

    Example:
        >>> count = count_narrative_turns(character_id)
        >>> print(f"Character has {count} narrative turns")
    """
    collection = get_narrative_turns_collection(character_id)
    # Use the efficient count() aggregation query
    count_query = collection.count()
    result = count_query.get()
    # The result is an AggregationResult with a value attribute
    return result[0][0].value


# ==============================================================================
# POI Subcollection Helpers
# ==============================================================================


def get_pois_collection(character_id: str) -> firestore.CollectionReference:
    """
    Get a reference to the pois subcollection for a character.

    The authoritative POI storage location is:
    characters/{character_id}/pois/{poi_id}

    Args:
        character_id: The UUID of the character

    Returns:
        CollectionReference to the pois subcollection

    Example:
        >>> collection = get_pois_collection("550e8400-e29b-41d4-a716-446655440000")
        >>> pois = collection.order_by("timestamp_discovered", direction=firestore.Query.DESCENDING).limit(10).stream()
    """
    client = get_firestore_client()
    settings = get_settings()
    return (
        client.collection(settings.firestore_characters_collection)
        .document(character_id)
        .collection("pois")
    )


def create_poi(
    character_id: str,
    poi_data: dict,
    *,
    transaction: Optional[firestore.Transaction] = None,
) -> firestore.DocumentReference:
    """
    Create a POI in the character's pois subcollection.

    The POI is written to: characters/{character_id}/pois/{poi_id}

    Args:
        character_id: The UUID of the character
        poi_data: Dictionary containing POI data (must include 'poi_id')
        transaction: Optional Firestore transaction for atomic operations

    Returns:
        DocumentReference to the created POI document

    Raises:
        ValueError: If poi_data is missing 'poi_id' field

    Example:
        >>> from app.models import PointOfInterestSubcollection, poi_subcollection_to_firestore
        >>> poi = PointOfInterestSubcollection(poi_id="poi_123", name="Temple", description="Ancient temple")
        >>> poi_data = poi_subcollection_to_firestore(poi)
        >>> doc_ref = create_poi(character_id, poi_data)
    """
    if "poi_id" not in poi_data:
        raise ValueError("poi_data must include 'poi_id' field")

    poi_id = poi_data["poi_id"]
    collection = get_pois_collection(character_id)
    doc_ref = collection.document(poi_id)

    if transaction:
        transaction.set(doc_ref, poi_data)
    else:
        doc_ref.set(poi_data)

    return doc_ref


def get_poi(character_id: str, poi_id: str) -> Optional[dict]:
    """
    Get a specific POI by ID from the subcollection.

    Args:
        character_id: The UUID of the character
        poi_id: The UUID of the POI

    Returns:
        POI dictionary or None if not found

    Example:
        >>> poi = get_poi(character_id, poi_id)
        >>> if poi:
        ...     print(poi['name'])
    """
    collection = get_pois_collection(character_id)
    doc = collection.document(poi_id).get()

    if doc.exists:
        return doc.to_dict()
    return None


def query_pois(
    character_id: str,
    *,
    limit: Optional[int] = None,
    order_by: str = "timestamp_discovered",
    direction: str = "DESCENDING",
    cursor_start_after: Optional[dict] = None,
) -> List[dict]:
    """
    Query POIs from the subcollection with pagination support.

    Args:
        character_id: The UUID of the character
        limit: Maximum number of POIs to retrieve (None for unlimited)
        order_by: Field to order by (default: "timestamp_discovered")
        direction: Sort direction - "ASCENDING" or "DESCENDING" (default: "DESCENDING")
        cursor_start_after: Document snapshot to start after for pagination

    Returns:
        List of POI dictionaries ordered by the specified field

    Example:
        >>> pois = query_pois(character_id, limit=10)
        >>> # Returns up to 10 POIs sorted by discovery time (newest first)
    """
    collection = get_pois_collection(character_id)

    # Build query with ordering
    query = collection.order_by(
        order_by,
        direction=firestore.Query.DESCENDING
        if direction == "DESCENDING"
        else firestore.Query.ASCENDING,
    )

    # Apply cursor for pagination if provided
    if cursor_start_after:
        query = query.start_after(cursor_start_after)

    # Apply limit if specified
    if limit:
        query = query.limit(limit)

    # Execute query and return results
    return [doc.to_dict() for doc in query.stream()]


def update_poi(
    character_id: str,
    poi_id: str,
    poi_data: dict,
    *,
    transaction: Optional[firestore.Transaction] = None,
) -> firestore.DocumentReference:
    """
    Update a POI in the character's pois subcollection.

    Args:
        character_id: The UUID of the character
        poi_id: The UUID of the POI
        poi_data: Dictionary containing POI data to update
        transaction: Optional Firestore transaction for atomic operations

    Returns:
        DocumentReference to the updated POI document

    Example:
        >>> poi_data = {"visited": True, "last_visited": datetime.now(timezone.utc)}
        >>> doc_ref = update_poi(character_id, poi_id, poi_data)
    """
    collection = get_pois_collection(character_id)
    doc_ref = collection.document(poi_id)

    if transaction:
        transaction.update(doc_ref, poi_data)
    else:
        doc_ref.update(poi_data)

    return doc_ref


def delete_poi(
    character_id: str,
    poi_id: str,
    *,
    transaction: Optional[firestore.Transaction] = None,
) -> None:
    """
    Delete a POI from the character's pois subcollection.

    Args:
        character_id: The UUID of the character
        poi_id: The UUID of the POI
        transaction: Optional Firestore transaction for atomic operations

    Example:
        >>> delete_poi(character_id, poi_id)
    """
    collection = get_pois_collection(character_id)
    doc_ref = collection.document(poi_id)

    if transaction:
        transaction.delete(doc_ref)
    else:
        doc_ref.delete()


def count_pois(character_id: str) -> int:
    """
    Count the total number of POIs for a character in the subcollection.

    This function uses Firestore's count() aggregation, which is efficient
    and incurs the cost of a single document read.

    Args:
        character_id: The UUID of the character

    Returns:
        Total number of POIs in the subcollection

    Example:
        >>> count = count_pois(character_id)
        >>> print(f"Character has {count} POIs")
    """
    collection = get_pois_collection(character_id)
    count_query = collection.count()
    result = count_query.get()
    return result[0][0].value


def resolve_world_pois_reference(reference: str) -> str:
    """
    Resolve and validate a world_pois_reference format.

    Supported formats:
    1. Firestore collection path: "characters/{character_id}/pois" or "worlds/{world_id}/pois"
    2. Configuration key: "world-v1", "middle-earth-pois", etc.

    Args:
        reference: The world_pois_reference string to validate

    Returns:
        The validated reference string

    Raises:
        ValueError: If reference format is invalid or empty

    Example:
        >>> ref = resolve_world_pois_reference("characters/char_123/pois")
        >>> # Returns: "characters/char_123/pois"
        >>> ref = resolve_world_pois_reference("world-v1")
        >>> # Returns: "world-v1"
    """
    if not reference or not reference.strip():
        raise ValueError("world_pois_reference cannot be empty or only whitespace")

    reference = reference.strip()

    # Validate Firestore collection path format (contains slashes)
    if "/" in reference:
        # Must be a valid collection path (odd number of segments)
        segments = reference.split("/")
        if len(segments) % 2 == 0:
            raise ValueError(
                f"Invalid Firestore collection path '{reference}': "
                "collection paths must have an odd number of segments (e.g., 'col/doc/subcol')"
            )
        return reference

    # Otherwise treat as a configuration key (no slashes allowed in keys)
    # Configuration keys should be alphanumeric with hyphens/underscores
    if not reference.replace("-", "").replace("_", "").isalnum():
        raise ValueError(
            f"Invalid configuration key '{reference}': "
            "must contain only alphanumeric characters, hyphens, and underscores"
        )

    return reference


# ==============================================================================
# POI Migration Utilities
# ==============================================================================


def should_migrate_pois(char_data: dict) -> bool:
    """
    Check if a character needs POI migration from embedded array to subcollection.

    A character needs migration if it has POIs in the embedded world_pois array.

    Args:
        char_data: Character document dictionary from Firestore

    Returns:
        True if migration is needed (has embedded POIs), False otherwise

    Example:
        >>> char_data = character_ref.get().to_dict()
        >>> if should_migrate_pois(char_data):
        ...     migrate_embedded_pois_to_subcollection(character_id)
    """
    world_pois = char_data.get("world_pois", [])
    return len(world_pois) > 0


def migrate_embedded_pois_to_subcollection(
    character_id: str,
    transaction: firestore.Transaction,
) -> dict:
    """
    Migrate embedded POIs from world_pois array to pois subcollection.

    This function:
    1. Reads embedded POIs from world_pois array
    2. Checks for existing POIs in subcollection to avoid duplicates
    3. Copies unique embedded POIs to subcollection
    4. Removes the world_pois field from the character document
    5. Returns migration statistics

    The migration runs inside a transaction to ensure atomicity.

    Args:
        character_id: The UUID of the character
        transaction: Firestore transaction for atomic migration

    Returns:
        Dictionary with migration statistics:
        - total_embedded: Number of POIs in embedded array
        - migrated: Number of POIs copied to subcollection
        - skipped: Number of POIs skipped (already in subcollection)
        - errors: List of error messages for failed POIs

    Raises:
        ValueError: If character document does not exist

    Example:
        >>> db = firestore.Client()
        >>> transaction = db.transaction()
        >>> stats = migrate_embedded_pois_to_subcollection(character_id, transaction)
        >>> print(f"Migrated {stats['migrated']} POIs, skipped {stats['skipped']} duplicates")
    """
    from app.logging import get_logger

    logger = get_logger(__name__)

    client = get_firestore_client()
    settings = get_settings()

    # Get character document reference
    char_ref = client.collection(settings.firestore_characters_collection).document(
        character_id
    )

    # Read character within transaction
    char_snapshot = char_ref.get(transaction=transaction)

    if not char_snapshot.exists:
        raise ValueError(f"Character document does not exist: {character_id}")

    char_data = char_snapshot.to_dict()
    embedded_pois = char_data.get("world_pois", [])

    # Initialize stats
    stats = {
        "total_embedded": len(embedded_pois),
        "migrated": 0,
        "skipped": 0,
        "errors": [],
    }

    if not embedded_pois:
        logger.info(
            "No embedded POIs to migrate",
            character_id=character_id,
        )
        return stats

    # Get existing POI IDs in subcollection to detect duplicates
    # Only fetch document IDs for efficiency (no need to read full documents)
    pois_collection = get_pois_collection(character_id)
    existing_poi_ids = set()
    # Use select() to only fetch document IDs, not full content
    for doc in pois_collection.select([]).stream():
        existing_poi_ids.add(doc.id)

    logger.info(
        "Starting POI migration",
        character_id=character_id,
        embedded_count=len(embedded_pois),
        existing_subcollection_count=len(existing_poi_ids),
    )

    # Migrate each embedded POI
    for embedded_poi in embedded_pois:
        try:
            poi_id = embedded_poi.get("id")

            if not poi_id:
                stats["errors"].append("Embedded POI missing 'id' field")
                continue

            # Skip if already in subcollection (deduplication)
            if poi_id in existing_poi_ids:
                stats["skipped"] += 1
                logger.debug(
                    "Skipping duplicate POI",
                    character_id=character_id,
                    poi_id=poi_id,
                )
                continue

            # Convert embedded POI to subcollection format
            # Map 'id' to 'poi_id' and 'created_at' to 'timestamp_discovered'
            subcollection_poi = {
                "poi_id": poi_id,
                "name": embedded_poi.get("name", ""),
                "description": embedded_poi.get("description", ""),
                "timestamp_discovered": embedded_poi.get("created_at"),
                "tags": embedded_poi.get("tags"),
                "visited": False,  # Default for migrated POIs
            }

            # Create POI in subcollection within transaction
            poi_ref = pois_collection.document(poi_id)
            transaction.set(poi_ref, subcollection_poi)

            stats["migrated"] += 1
            logger.debug(
                "Migrated POI to subcollection",
                character_id=character_id,
                poi_id=poi_id,
            )

        except Exception as e:
            error_msg = f"Failed to migrate POI {embedded_poi.get('id', 'unknown')}: {str(e)}"
            stats["errors"].append(error_msg)
            logger.error(
                "POI migration error",
                character_id=character_id,
                poi_id=embedded_poi.get("id", "unknown"),
                error=str(e),
            )

    # Remove world_pois field from character document
    transaction.update(
        char_ref,
        {
            "world_pois": firestore.DELETE_FIELD,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
    )

    logger.info(
        "POI migration completed",
        character_id=character_id,
        **stats,
    )

    return stats
