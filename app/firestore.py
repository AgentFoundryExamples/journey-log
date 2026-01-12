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
    return (client.collection(settings.firestore_characters_collection)
            .document(character_id)
            .collection("narrative_turns"))


def write_narrative_turn(
    character_id: str,
    turn_data: dict,
    *,
    use_server_timestamp: bool = True
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
        ValueError: If turn_data is missing 'turn_id'
        
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
    
    collection = get_narrative_turns_collection(character_id)
    doc_ref = collection.document(turn_id)
    doc_ref.set(turn_data)
    
    return doc_ref


def query_narrative_turns(
    character_id: str,
    *,
    limit: Optional[int] = None,
    order_by: str = "timestamp",
    direction: str = "DESCENDING"
) -> List[dict]:
    """
    Query narrative turns for a character, ordered by timestamp.
    
    Returns turns in oldest-to-newest order (despite querying newest-first for efficiency).
    This matches the natural reading order for narrative history.
    
    Args:
        character_id: The UUID of the character
        limit: Maximum number of turns to retrieve (defaults to config default)
        order_by: Field to order by (default: "timestamp")
        direction: Sort direction - "ASCENDING" or "DESCENDING" (default: "DESCENDING")
        
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
        direction=firestore.Query.DESCENDING if direction == "DESCENDING" else firestore.Query.ASCENDING
    )
    
    if limit:
        query = query.limit(limit)
    
    # Execute query and convert to list
    turns = [doc.to_dict() for doc in query.stream()]
    
    # Reverse to oldest-first for natural reading order
    # (we query newest-first for efficiency with Firestore indexes)
    if direction == "DESCENDING":
        turns.reverse()
    
    return turns


def get_narrative_turn_by_id(
    character_id: str,
    turn_id: str
) -> Optional[dict]:
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
    
    WARNING: This is an expensive operation for large collections as it requires
    streaming all documents to count them. Firestore does not provide a native
    count operation, so this function iterates through all turns.
    
    Performance considerations:
    - For large collections (>1000 turns), this can be slow and costly
    - Consider maintaining a counter field on the character document instead
    - Future enhancement: Use Firestore's aggregation queries when available
    
    Recommended alternatives:
    - Track turn count in character document's additional_metadata
    - Increment counter on write, decrement on delete
    - Use turn_number field if sequential numbering is maintained
    
    Args:
        character_id: The UUID of the character
        
    Returns:
        Total number of narrative turns
        
    Example:
        >>> count = count_narrative_turns(character_id)
        >>> print(f"Character has {count} narrative turns")
    """
    collection = get_narrative_turns_collection(character_id)
    # Firestore doesn't have a native count operation, so we must iterate
    # This is expensive for large collections
    count = sum(1 for _ in collection.stream())
    return count
