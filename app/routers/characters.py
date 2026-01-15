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
Character management router.

Provides endpoints for creating and managing character documents.
"""

import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query, status
from google.cloud import firestore  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, model_validator

from app.config import (
    get_settings,
    DEFAULT_LOCATION_ID,
    DEFAULT_LOCATION_DISPLAY_NAME,
)
from app.dependencies import FirestoreClient
from app.logging import get_logger
from app.models import (
    CharacterDocument,
    CharacterIdentity,
    CharacterContextResponse,
    CombatEnvelope,
    CombatState,
    ContextCapsMetadata,
    ContextCombatState,
    Location,
    NarrativeContext,
    NarrativeContextMetadata,
    NarrativeTurn,
    PlayerState,
    PointOfInterest,
    PointOfInterestSubcollection,
    Quest,
    Status,
    WorldContextState,
    character_to_firestore,
    character_from_firestore,
    datetime_from_firestore,
    datetime_to_firestore,
    narrative_turn_from_firestore,
    poi_subcollection_to_firestore,
)
from app.firestore import (
    should_migrate_pois,
    migrate_embedded_pois_to_subcollection,
)

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(
    prefix="/characters",
    tags=["characters"],
)


class CreateCharacterRequest(BaseModel):
    """
    Request model for creating a new character.

    Required fields:
    - name: Character name (1-64 characters)
    - race: Character race (1-64 characters)
    - class: Character class (1-64 characters)
    - adventure_prompt: Initial adventure prompt or backstory (non-empty)

    Optional fields:
    - location_id: Override default starting location (default: origin:nexus)
    - location_display_name: Display name for location override
    """

    model_config = {"extra": "forbid"}

    name: str = Field(
        min_length=1, max_length=64, description="Character name (1-64 characters)"
    )
    race: str = Field(
        min_length=1, max_length=64, description="Character race (1-64 characters)"
    )
    character_class: str = Field(
        min_length=1,
        max_length=64,
        alias="class",
        description="Character class (1-64 characters)",
    )
    adventure_prompt: str = Field(
        min_length=1, description="Initial adventure prompt or backstory"
    )
    location_id: Optional[str] = Field(
        default=None,
        description="Optional location ID override (default: origin:nexus)",
    )
    location_display_name: Optional[str] = Field(
        default=None, description="Display name for location override"
    )

    @model_validator(mode="after")
    def validate_location_override(self) -> "CreateCharacterRequest":
        """Validate that if one location field is provided, both must be provided."""
        location_id = self.location_id
        location_display_name = self.location_display_name

        # Both must be provided or both must be None
        if (location_id is None) != (location_display_name is None):
            if location_id is not None:
                raise ValueError(
                    "location_display_name is required when location_id is provided"
                )
            else:
                raise ValueError(
                    "location_id is required when location_display_name is provided"
                )

        return self


class CreateCharacterResponse(BaseModel):
    """Response model for character creation."""

    character: CharacterDocument = Field(description="The created character document")


class GetCharacterResponse(BaseModel):
    """Response model for character retrieval."""

    character: CharacterDocument = Field(description="The character document")


class CharacterMetadata(BaseModel):
    """
    Lightweight character metadata for list responses.

    Contains essential character information without full state details.
    """

    model_config = {"extra": "forbid"}

    character_id: str = Field(description="UUID character identifier")
    name: str = Field(description="Character name")
    race: str = Field(description="Character race")
    character_class: str = Field(
        alias="class", serialization_alias="class", description="Character class"
    )
    status: Status = Field(description="Character health status")
    created_at: datetime = Field(description="When the character was created")
    updated_at: datetime = Field(description="Last update timestamp")


class ListCharactersResponse(BaseModel):
    """Response model for character list retrieval."""

    characters: list[CharacterMetadata] = Field(
        description="List of character metadata objects"
    )
    count: int = Field(
        description="Number of characters returned in this response (after pagination)"
    )


@router.get(
    "",
    response_model=ListCharactersResponse,
    status_code=status.HTTP_200_OK,
    summary="List all characters for a user",
    description=(
        "Retrieve all character saves for a user_id to drive save-slot UIs.\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (for ownership and access control)\n\n"
        "**Optional Query Parameters:**\n"
        "- `limit`: Maximum number of characters to return (default: unlimited)\n"
        "- `offset`: Number of characters to skip for pagination (default: 0)\n\n"
        "**Response:**\n"
        "- Returns an array of character metadata objects\n"
        "- Each object contains: character_id, name, race, class, status, created_at, updated_at\n"
        "- Results are sorted by updated_at descending (most recently updated first)\n"
        "- Empty list returned if user has no characters\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or empty X-User-Id header\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def list_characters(
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
    limit: Optional[int] = None,
    offset: int = 0,
) -> ListCharactersResponse:
    """
    List all characters owned by a user.

    This endpoint:
    1. Validates required X-User-Id header
    2. Queries Firestore for all characters owned by the user
    3. Projects lightweight metadata (character_id, name, race, class, status, timestamps)
    4. Sorts by updated_at descending
    5. Supports optional pagination via limit/offset

    Args:
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header
        limit: Optional maximum number of results to return
        offset: Number of results to skip (for pagination)

    Returns:
        ListCharactersResponse with array of character metadata

    Raises:
        HTTPException:
            - 400: Missing or invalid X-User-Id
            - 500: Firestore error
    """
    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("list_characters_missing_user_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Log list attempt
    logger.info(
        "list_characters_attempt",
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    try:
        # Query Firestore for characters owned by user
        characters_ref = db.collection(settings.firestore_characters_collection)
        query = characters_ref.where("owner_user_id", "==", user_id)

        # Order by updated_at descending
        query = query.order_by("updated_at", direction=firestore.Query.DESCENDING)

        # Apply offset if specified
        if offset > 0:
            query = query.offset(offset)

        # Apply limit if specified
        if limit is not None and limit > 0:
            query = query.limit(limit)

        # Execute query
        docs = query.stream()

        # Project to metadata
        characters = []
        for doc in docs:
            data = doc.to_dict()
            character_id = doc.id

            # Extract fields from nested player_state
            player_state = data.get("player_state", {})
            identity = player_state.get("identity", {})

            # Default status to Healthy if missing (as per edge case requirements)
            status_value = player_state.get("status", "Healthy")

            # Extract required identity fields
            # Note: These fields are required by the CharacterDocument schema,
            # but we use fallback values for robustness in case of data corruption
            name = identity.get("name", "Unknown")
            race = identity.get("race", "Unknown")
            character_class = identity.get("class", "Unknown")

            # Create metadata object
            metadata = CharacterMetadata(
                character_id=character_id,
                name=name,
                race=race,
                **{"class": character_class},
                status=Status(status_value),
                created_at=datetime_from_firestore(data.get("created_at")),
                updated_at=datetime_from_firestore(data.get("updated_at")),
            )
            characters.append(metadata)

        logger.info(
            "list_characters_success",
            user_id=user_id,
            count=len(characters),
        )

        # Note: 'count' represents the number of characters returned in this response
        # after pagination is applied, not the total number of characters the user owns
        return ListCharactersResponse(
            characters=characters,
            count=len(characters),
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "list_characters_error",
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list characters due to an internal error",
        )


@router.post(
    "",
    response_model=CreateCharacterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new character",
    description=(
        "Initialize a new character with defaults and persist to Firestore.\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (for ownership and access control)\n\n"
        "**Default Values Applied:**\n"
        "- `status`: Healthy\n"
        "- `equipment`: Empty list (no weapons)\n"
        "- `inventory`: Empty list (no items)\n"
        "- `location`: origin:nexus/The Nexus (unless overridden)\n"
        "- `world_state`: null\n"
        "- `active_quest`: null\n"
        "- `combat_state`: null\n"
        "- `schema_version`: 1.0.0\n"
        "- `created_at`, `updated_at`: Current server timestamp\n\n"
        "**Uniqueness Constraint:**\n"
        "The combination of (user_id, name, race, class) must be unique. "
        "Attempting to create a duplicate will return 409 Conflict.\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header\n"
        "- `409`: Duplicate character (user_id, name, race, class) already exists\n"
        "- `422`: Validation error (missing required fields or invalid values)\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def create_character(
    request: CreateCharacterRequest,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
) -> CreateCharacterResponse:
    """
    Create a new character with default values and persist to Firestore.

    This endpoint:
    1. Validates required fields and X-User-Id header
    2. Checks uniqueness of (user_id, name, race, class) tuple
    3. Generates a UUID character_id
    4. Applies default values for new characters
    5. Persists to Firestore
    6. Returns the complete character document

    Args:
        request: Character creation request data
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        CreateCharacterResponse with the created character document

    Raises:
        HTTPException:
            - 400: Missing or invalid X-User-Id
            - 409: Duplicate character exists
            - 422: Validation error
            - 500: Firestore error
    """
    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("create_character_missing_user_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Log character creation attempt
    logger.info(
        "create_character_attempt",
        user_id=user_id,
        name=request.name,
        race=request.race,
        character_class=request.character_class,
    )

    try:
        # Use a transaction to atomically check for duplicates and create the character
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        # Generate character ID (lowercase UUIDv4)
        character_id = str(uuid.uuid4()).lower()

        @firestore.transactional
        def create_in_transaction(transaction, character_data, character_id):
            # Query for existing character with same tuple
            # Note: Firestore queries are case-sensitive
            query = (
                characters_ref.where("owner_user_id", "==", user_id)
                .where("player_state.identity.name", "==", request.name)
                .where("player_state.identity.race", "==", request.race)
                .where("player_state.identity.class", "==", request.character_class)
                .limit(1)
            )

            # Run query within the transaction
            existing = list(query.stream(transaction=transaction))
            if existing:
                # Abort transaction by raising an exception
                logger.warning(
                    "create_character_duplicate",
                    user_id=user_id,
                    name=request.name,
                    race=request.race,
                    character_class=request.character_class,
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Character with name '{request.name}', race '{request.race}', and class '{request.character_class}' already exists for this user",
                )

            # Persist to Firestore within the transaction
            doc_ref = characters_ref.document(character_id)
            transaction.set(doc_ref, character_data)
            return doc_ref

        character_id = str(uuid.uuid4()).lower()

        # Determine location
        if request.location_id and request.location_display_name:
            location = Location(
                id=request.location_id,
                display_name=request.location_display_name,
            )
        else:
            location = Location(
                id=DEFAULT_LOCATION_ID,
                display_name=DEFAULT_LOCATION_DISPLAY_NAME,
            )

        # Create character identity
        identity = CharacterIdentity(
            name=request.name, race=request.race, **{"class": request.character_class}
        )

        # Create player state with defaults
        player_state = PlayerState(
            identity=identity,
            status=Status.HEALTHY,
            equipment=[],
            inventory=[],
            location=location,
            additional_fields={},
        )

        # Create character document
        # Use epoch time as placeholder - will be replaced by SERVER_TIMESTAMP
        character = CharacterDocument(
            character_id=character_id,
            owner_user_id=user_id,
            adventure_prompt=request.adventure_prompt,
            player_state=player_state,
            world_pois_reference=f"characters/{character_id}/pois",
            narrative_turns_reference=f"characters/{character_id}/narrative_turns",
            schema_version="1.0.0",
            created_at=datetime.fromtimestamp(0, timezone.utc),
            updated_at=datetime.fromtimestamp(0, timezone.utc),
            world_state=None,
            active_quest=None,
            combat_state=None,
            additional_metadata={},
        )

        # Serialize to Firestore format with server timestamps
        character_data = character_to_firestore(character, use_server_timestamp=True)

        # Execute transaction
        doc_ref = create_in_transaction(transaction, character_data, character_id)

        # Read back the document to get server timestamps
        created_doc = doc_ref.get()
        if not created_doc.exists:
            logger.error(
                "create_character_not_found_after_creation",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Character was created but could not be retrieved",
            )

        # Deserialize back to CharacterDocument
        created_character = character_from_firestore(
            created_doc.to_dict(),
            character_id=character_id,
        )

        logger.info(
            "create_character_success",
            character_id=character_id,
            user_id=user_id,
            name=request.name,
        )

        return CreateCharacterResponse(character=created_character)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "create_character_error",
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create character: {str(e)}",
        )


@router.get(
    "/{character_id}",
    response_model=GetCharacterResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a character by ID",
    description=(
        "Retrieve a complete character document by its character_id.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier (if provided, must match the character's owner_user_id)\n"
        "  - If header is provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n\n"
        "**Response:**\n"
        "- Returns the complete CharacterDocument with all fields\n"
        "- Includes player state, quests, combat state, and metadata\n"
        "- Timestamps are returned as ISO 8601 strings\n\n"
        "**Error Responses:**\n"
        "- `400`: X-User-Id header provided but empty/whitespace-only\n"
        "- `404`: Character not found\n"
        "- `403`: X-User-Id header provided but does not match character owner\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def get_character(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
) -> GetCharacterResponse:
    """
    Retrieve a character document by character_id.

    This endpoint:
    1. Validates character_id as UUID format
    2. Fetches the document from Firestore
    3. Optionally verifies X-User-Id matches owner_user_id
    4. Deserializes and returns the complete CharacterDocument

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control

    Returns:
        GetCharacterResponse with the character document

    Raises:
        HTTPException:
            - 404: Character not found
            - 403: User ID mismatch (access denied)
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format to canonical representation
    try:
        # This creates a canonical string representation (lowercase, with hyphens)
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_character_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Log retrieval attempt
    logger.info(
        "get_character_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
    )

    try:
        # Fetch document from Firestore
        characters_ref = db.collection(settings.firestore_characters_collection)
        doc_ref = characters_ref.document(character_id)
        doc = doc_ref.get()

        # Check if document exists
        if not doc.exists:
            logger.warning(
                "get_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # Deserialize document
        character = character_from_firestore(
            doc.to_dict(),
            character_id=character_id,
        )

        # Verify user_id if provided
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_character_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )
            if stripped_user_id != character.owner_user_id:
                logger.warning(
                    "get_character_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=character.owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        logger.info(
            "get_character_success",
            character_id=character_id,
            owner_user_id=character.owner_user_id,
        )

        return GetCharacterResponse(character=character)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_character_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve character due to an internal error",
        )


class AppendNarrativeRequest(BaseModel):
    """
    Request model for appending a narrative turn to a character.

    Required fields:
    - user_action: Player's action or input (1-8000 characters)
    - ai_response: Game master's/AI's response (1-32000 characters)

    Optional fields:
    - timestamp: When the turn occurred (ISO 8601 string). Defaults to server UTC now if omitted.

    Validation:
    - user_action: max 8000 characters
    - ai_response: max 32000 characters
    - Combined length: max 40000 characters
    """

    model_config = {"extra": "forbid"}

    user_action: str = Field(
        min_length=1,
        max_length=8000,
        description="Player's action or input (max 8000 characters)",
    )
    ai_response: str = Field(
        min_length=1,
        max_length=32000,
        description="Game master's/AI's response (max 32000 characters)",
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Optional ISO 8601 timestamp. Defaults to server UTC now if omitted.",
    )

    @model_validator(mode="after")
    def validate_combined_length(self) -> "AppendNarrativeRequest":
        """Validate that combined length does not exceed 40000 characters."""
        combined_length = len(self.user_action) + len(self.ai_response)
        if combined_length > 40000:
            raise ValueError(
                f"Combined length of user_action and ai_response ({combined_length}) "
                f"exceeds maximum of 40000 characters"
            )
        return self


class AppendNarrativeResponse(BaseModel):
    """Response model for narrative turn append."""

    turn: NarrativeTurn = Field(description="The stored narrative turn")
    total_turns: int = Field(
        description="Total number of narrative turns for this character"
    )


class NarrativeMetadata(BaseModel):
    """Metadata for narrative retrieval response."""

    model_config = {"extra": "forbid"}

    requested_n: int = Field(description="Number of turns requested (n parameter)")
    returned_count: int = Field(description="Number of turns actually returned")
    total_available: int = Field(
        description="Total number of turns available for this character"
    )


class GetNarrativeResponse(BaseModel):
    """Response model for GET narrative endpoint."""

    turns: list[NarrativeTurn] = Field(
        description="List of narrative turns ordered oldest-to-newest"
    )
    metadata: NarrativeMetadata = Field(description="Metadata about the query results")


@router.post(
    "/{character_id}/narrative",
    response_model=AppendNarrativeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append a narrative turn to a character",
    description=(
        "Append a validated narrative turn with concurrency safety.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (must match character owner for access control)\n\n"
        "**Request Body:**\n"
        "- `user_action`: Player's action (1-8000 characters)\n"
        "- `ai_response`: AI/GM response (1-32000 characters)\n"
        "- `timestamp`: Optional ISO 8601 timestamp (defaults to server UTC now)\n\n"
        "**Validation:**\n"
        "- user_action: max 8000 characters\n"
        "- ai_response: max 32000 characters\n"
        "- Combined length: max 40000 characters\n"
        "- Timestamp format: ISO 8601 (if provided)\n\n"
        "**Atomicity:**\n"
        "Uses Firestore transaction to atomically:\n"
        "1. Add document to characters/{character_id}/narrative_turns subcollection\n"
        "2. Update parent character.updated_at timestamp\n\n"
        "**Response:**\n"
        "- Returns the stored NarrativeTurn (with server-generated timestamp if not provided)\n"
        "- Includes total_turns count for confirmation\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header\n"
        "- `403`: X-User-Id does not match character owner\n"
        "- `404`: Character not found\n"
        "- `413`: Request entity too large (combined payload > 40000 characters)\n"
        "- `422`: Validation error (invalid field values, oversized fields, invalid timestamp format)\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def append_narrative_turn(
    character_id: str,
    request: AppendNarrativeRequest,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
) -> AppendNarrativeResponse:
    """
    Append a narrative turn to a character's history with atomic transaction.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates X-User-Id matches character owner
    3. Validates payload sizes (user_action, ai_response, combined)
    4. Validates timestamp format (if provided)
    5. Uses Firestore transaction to atomically:
       - Add narrative turn to subcollection with server timestamp if absent
       - Update character.updated_at
    6. Returns stored turn with count metadata

    Args:
        character_id: UUID-formatted character identifier
        request: Narrative turn append request data
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        AppendNarrativeResponse with stored turn and total count

    Raises:
        HTTPException:
            - 400: Invalid X-User-Id
            - 403: Access denied (user not owner)
            - 404: Character not found
            - 413: Payload too large
            - 422: Validation error
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "append_narrative_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("append_narrative_missing_user_id", character_id=character_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Log oversized attempts for metrics (Pydantic validation already enforces limits)
    combined_length = len(request.user_action) + len(request.ai_response)
    if len(request.user_action) > 7000 or len(request.ai_response) > 30000:
        logger.info(
            "append_narrative_large_payload",
            character_id=character_id,
            user_id=user_id,
            user_action_length=len(request.user_action),
            ai_response_length=len(request.ai_response),
            combined_length=combined_length,
        )

    # Parse and validate timestamp if provided
    turn_timestamp: Optional[datetime] = None
    if request.timestamp:
        try:
            turn_timestamp = datetime_to_firestore(request.timestamp)
        except ValueError as e:
            logger.warning(
                "append_narrative_invalid_timestamp",
                character_id=character_id,
                timestamp=request.timestamp,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid timestamp format: {str(e)}",
            )

    # Log append attempt
    logger.info(
        "append_narrative_attempt",
        character_id=character_id,
        user_id=user_id,
        user_action_length=len(request.user_action),
        ai_response_length=len(request.ai_response),
        has_timestamp=turn_timestamp is not None,
    )

    try:
        # Create transaction
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        @firestore.transactional
        def append_in_transaction(transaction):
            """Atomically append turn and update character."""
            # Generate turn ID inside transaction to avoid race condition on retry
            turn_id = str(uuid.uuid4()).lower()

            # 1. Fetch character document to verify existence and ownership
            char_ref = characters_ref.document(character_id)
            char_snapshot = char_ref.get(transaction=transaction)

            if not char_snapshot.exists:
                logger.warning(
                    "append_narrative_character_not_found",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Character with ID '{character_id}' not found",
                )

            # 2. Verify ownership
            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if owner_user_id != user_id:
                logger.warning(
                    "append_narrative_access_denied",
                    character_id=character_id,
                    requested_user_id=user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

            # 3. Create narrative turn document
            # Use server timestamp if not provided by client
            turn_data = {
                "turn_id": turn_id,
                "player_action": request.user_action,
                "gm_response": request.ai_response,
                "timestamp": turn_timestamp
                if turn_timestamp
                else firestore.SERVER_TIMESTAMP,
            }

            # 4. Write turn to subcollection
            turn_ref = char_ref.collection("narrative_turns").document(turn_id)
            transaction.set(turn_ref, turn_data)

            # 5. Update character.updated_at
            transaction.update(char_ref, {"updated_at": firestore.SERVER_TIMESTAMP})

            # 6. Count turns atomically within transaction using aggregation
            # Note: Firestore aggregation count is efficient and atomic within transaction
            turns_collection = char_ref.collection("narrative_turns")
            count_query = turns_collection.count()
            count_result = count_query.get(transaction=transaction)
            # The result structure is [[AggregationResult]] where AggregationResult has a value attribute
            total_turns = count_result[0][0].value

            return turn_ref, turn_data, turn_id, total_turns

        # Execute transaction
        turn_ref, turn_data, turn_id, total_turns = append_in_transaction(transaction)

        # Read back the written turn to get server timestamps
        turn_snapshot = turn_ref.get()
        if not turn_snapshot.exists:
            logger.error(
                "append_narrative_turn_not_found_after_creation",
                character_id=character_id,
                turn_id=turn_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Narrative turn was created but could not be retrieved",
            )

        # Convert to NarrativeTurn model
        turn_dict = turn_snapshot.to_dict()

        # Convert Firestore timestamp to datetime
        # Timestamp should always be present since we write it in the transaction,
        # but handle defensively
        if "timestamp" in turn_dict:
            turn_dict["timestamp"] = datetime_from_firestore(turn_dict["timestamp"])
        else:
            # This should never happen, but provide defensive fallback
            logger.error(
                "append_narrative_missing_timestamp_after_creation",
                character_id=character_id,
                turn_id=turn_id,
            )
            turn_dict["timestamp"] = datetime.now(timezone.utc)

        # Create NarrativeTurn object (using aliases for conversion)
        # Use direct access for required fields that were written in the transaction
        stored_turn = NarrativeTurn(
            turn_id=turn_dict.get("turn_id", turn_id),
            user_action=turn_dict["player_action"],
            ai_response=turn_dict["gm_response"],
            timestamp=turn_dict["timestamp"],
            turn_number=turn_dict.get("turn_number"),
            game_state_snapshot=turn_dict.get("game_state_snapshot"),
            metadata=turn_dict.get("metadata"),
        )

        logger.info(
            "append_narrative_success",
            character_id=character_id,
            turn_id=turn_id,
            total_turns=total_turns,
        )

        return AppendNarrativeResponse(
            turn=stored_turn,
            total_turns=total_turns,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "append_narrative_error",
            character_id=character_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to append narrative turn: {str(e)}",
        )


@router.get(
    "/{character_id}/narrative",
    response_model=GetNarrativeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get narrative turns for a character",
    description=(
        "Retrieve the last N narrative turns for a character ordered oldest-to-newest.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier (if provided, must match the character's owner_user_id)\n"
        "  - If header is provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n\n"
        "**Optional Query Parameters:**\n"
        "- `n`: Number of turns to retrieve (default: 10, min: 1, max: 100)\n"
        "- `since`: ISO 8601 timestamp to filter turns strictly after this time (exclusive, timestamp > since)\n\n"
        "**Response:**\n"
        "- Returns list of NarrativeTurn objects ordered oldest-to-newest\n"
        "- Includes metadata with requested_n, returned_count, and total_available\n"
        "- Empty list returned if character has no narrative turns\n\n"
        "**Ordering:**\n"
        "- Results are always returned in chronological order (oldest first)\n"
        "- This ensures LLM context is built in the correct sequence\n\n"
        "**Error Responses:**\n"
        "- `400`: Invalid query parameters (n out of range, invalid since timestamp) or empty X-User-Id\n"
        "- `403`: X-User-Id provided but does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def get_narrative_turns(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
    n: int = 10,
    since: Optional[str] = None,
) -> GetNarrativeResponse:
    """
    Retrieve last N narrative turns for a character with optional time filtering.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates n parameter (default 10, max 100)
    3. Validates optional since timestamp format
    4. Optionally verifies X-User-Id matches owner_user_id
    5. Queries Firestore for narrative turns with filtering (timestamp > since)
    6. Returns turns in oldest-to-newest order with metadata

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control
        n: Number of turns to retrieve (default 10, max 100)
        since: Optional ISO 8601 timestamp to filter turns strictly after this time (exclusive)

    Returns:
        GetNarrativeResponse with turns list and metadata

    Raises:
        HTTPException:
            - 400: Invalid parameters (n out of range, invalid since timestamp)
            - 403: User ID mismatch (access denied)
            - 404: Character not found
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_narrative_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Validate n parameter
    if n < 1 or n > settings.narrative_turns_max_query_size:
        logger.warning(
            "get_narrative_invalid_n",
            character_id=character_id,
            n=n,
            max_allowed=settings.narrative_turns_max_query_size,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parameter 'n' must be between 1 and {settings.narrative_turns_max_query_size} (got {n})",
        )

    # Parse and validate since timestamp if provided
    since_dt: Optional[datetime] = None
    if since:
        try:
            since_dt = datetime_to_firestore(since)
        except ValueError as e:
            logger.warning(
                "get_narrative_invalid_since",
                character_id=character_id,
                since=since,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid timestamp format for 'since' parameter: {str(e)}",
            )

    # Log retrieval attempt
    logger.info(
        "get_narrative_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
        n=n,
        has_since_filter=since_dt is not None,
    )

    try:
        # 1. Verify character exists
        characters_ref = db.collection(settings.firestore_characters_collection)
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(
                "get_narrative_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # 2. Verify ownership if X-User-Id is provided
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_narrative_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )

            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if stripped_user_id != owner_user_id:
                logger.warning(
                    "get_narrative_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        # 3. Build query for narrative turns
        turns_collection = char_ref.collection("narrative_turns")
        # Query Strategy: Order by timestamp DESCENDING to efficiently get the N most recent turns
        # The DESCENDING order ensures we get the latest turns first, then we reverse to chronological
        query = turns_collection.order_by(
            "timestamp", direction=firestore.Query.DESCENDING
        )

        # Apply since filter if provided (strict inequality: turns AFTER the timestamp)
        # Note: The filter is applied BEFORE ordering, so it correctly limits the result set
        # before selecting the N most recent turns from the filtered set
        if since_dt:
            query = query.where("timestamp", ">", since_dt)

        # Apply limit to get at most N turns
        query = query.limit(n)

        # Execute query - returns up to N turns in DESCENDING order (newest first)
        turn_docs = list(query.stream())

        # Reverse to get oldest-to-newest order (chronological reading order for LLM context)
        turn_docs.reverse()

        # Convert to NarrativeTurn models
        turns = []
        for doc in turn_docs:
            turn_data = doc.to_dict()
            turn = narrative_turn_from_firestore(turn_data, turn_id=doc.id)
            turns.append(turn)

        # 4. Get total count (expensive, but needed for metadata)
        # Note: This is a separate query that counts all matching documents
        # Performance consideration: For characters with many turns, consider caching
        # Count all turns matching the since filter if provided (strict inequality)
        if since_dt:
            count_query = turns_collection.where("timestamp", ">", since_dt).count()
        else:
            count_query = turns_collection.count()

        count_result = count_query.get()
        total_available = count_result[0][0].value

        # 5. Prepare metadata
        metadata = NarrativeMetadata(
            requested_n=n,
            returned_count=len(turns),
            total_available=total_available,
        )

        logger.info(
            "get_narrative_success",
            character_id=character_id,
            requested_n=n,
            returned_count=len(turns),
            total_available=total_available,
        )

        return GetNarrativeResponse(
            turns=turns,
            metadata=metadata,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_narrative_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve narrative turns due to an internal error",
        )


# ==============================================================================
# POI Management Endpoints
# ==============================================================================


class CreatePOIRequest(BaseModel):
    """
    Request model for creating a new POI for a character.

    Required fields:
    - name: POI name (1-200 characters)
    - description: POI description (1-2000 characters)

    Optional fields:
    - timestamp: When the POI was discovered (ISO 8601 string, defaults to server UTC now)
    - tags: List of tags for categorizing the POI (max 20 tags, each max 50 chars)
    """

    model_config = {"extra": "forbid"}

    name: str = Field(
        min_length=1, max_length=200, description="POI name (1-200 characters)"
    )
    description: str = Field(
        min_length=1, max_length=2000, description="POI description (1-2000 characters)"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Optional ISO 8601 timestamp when POI was discovered. Defaults to server UTC now if omitted.",
    )
    tags: Optional[list[str]] = Field(
        default=None,
        max_length=20,
        description="Optional list of tags for categorizing the POI (max 20 tags)",
    )

    @model_validator(mode="after")
    def validate_tags(self) -> "CreatePOIRequest":
        """Validate tags list size and individual tag lengths."""
        if self.tags is not None:
            if len(self.tags) > 20:
                raise ValueError(
                    f"tags list cannot exceed 20 entries (got {len(self.tags)}). "
                    "Consider using more general tags or removing redundant ones."
                )
            for tag in self.tags:
                if len(tag) > 50:
                    raise ValueError(
                        f"Individual tag cannot exceed 50 characters (got {len(tag)} for tag: {tag[:20]}...)"
                    )
                if not tag.strip():
                    raise ValueError("Tags cannot be empty or only whitespace")
        return self


class CreatePOIResponse(BaseModel):
    """Response model for POI creation."""

    poi: PointOfInterest = Field(
        description="The created POI with server-assigned created_at"
    )


class GetPOIsResponse(BaseModel):
    """Response model for getting POIs with pagination."""

    pois: list[PointOfInterest] = Field(
        description="List of POIs sorted by created_at desc"
    )
    count: int = Field(description="Number of POIs returned in this response")
    cursor: Optional[str] = Field(
        default=None, description="Cursor for next page (None if no more results)"
    )


class GetRandomPOIsResponse(BaseModel):
    """Response model for random POI sampling."""

    pois: list[PointOfInterest] = Field(description="Randomly sampled POIs")
    count: int = Field(description="Number of POIs returned")
    requested_n: int = Field(description="Number of POIs requested")
    total_available: int = Field(description="Total number of POIs available")


class GetPOISummaryResponse(BaseModel):
    """Response model for lightweight POI summary."""

    total_count: int = Field(description="Total number of POIs for this character")
    preview: list[PointOfInterest] = Field(
        description="Preview of POIs (capped sample, newest first)"
    )
    preview_count: int = Field(description="Number of POIs in preview")


class UpdatePOIRequest(BaseModel):
    """Request model for updating an existing POI."""

    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="POI name (1-200 characters)",
    )
    description: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="POI description (1-2000 characters)",
    )
    visited: Optional[bool] = Field(
        default=None, description="Whether the POI has been visited"
    )
    tags: Optional[list[str]] = Field(
        default=None,
        max_length=20,
        description="Tags for categorizing the POI (max 20 tags)",
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "UpdatePOIRequest":
        """Validate that at least one field is provided for update."""
        if not any(
            [
                self.name is not None,
                self.description is not None,
                self.visited is not None,
                self.tags is not None,
            ]
        ):
            raise ValueError(
                "At least one field must be provided for update (name, description, visited, or tags)"
            )
        return self

    @model_validator(mode="after")
    def validate_tags(self) -> "UpdatePOIRequest":
        """Validate tags list size and individual tag lengths."""
        if self.tags is not None:
            if len(self.tags) > 20:
                raise ValueError(
                    f"tags list cannot exceed 20 entries (got {len(self.tags)})"
                )
            for tag in self.tags:
                if len(tag) > 50:
                    raise ValueError(
                        f"Individual tag cannot exceed 50 characters (got {len(tag)} for tag: {tag[:20]}...)"
                    )
                if not tag.strip():
                    raise ValueError("Tags cannot be empty or only whitespace")
        return self


class UpdatePOIResponse(BaseModel):
    """Response model for POI update."""

    poi: PointOfInterest = Field(description="The updated POI")


@router.post(
    "/{character_id}/pois",
    response_model=CreatePOIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a POI to a character",
    description=(
        "Create a new Point of Interest in a character's pois subcollection.\n\n"
        "**Authoritative Storage:** POIs are stored in `characters/{character_id}/pois/{poi_id}` subcollection.\n\n"
        "**Copy-on-Write Migration:** On first POI write, embedded POIs (if any) are automatically migrated to the subcollection.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (must match character owner for access control)\n\n"
        "**Request Body:**\n"
        "- `name`: POI name (1-200 characters)\n"
        "- `description`: POI description (1-2000 characters)\n"
        "- `timestamp`: Optional ISO 8601 timestamp (defaults to server UTC now)\n"
        "- `tags`: Optional list of tags (max 20 tags, each max 50 characters)\n\n"
        "**Validation:**\n"
        "- name: required, 1-200 characters\n"
        "- description: required, 1-2000 characters\n"
        "- tags: max 20 entries, each max 50 characters\n"
        "- Duplicate POI names are allowed (each has unique id)\n\n"
        "**Atomicity:**\n"
        "Uses Firestore transaction to atomically:\n"
        "1. Verify character exists and user owns it\n"
        "2. Migrate embedded POIs to subcollection (if migration enabled and needed)\n"
        "3. Create POI in subcollection with generated id and timestamp\n"
        "4. Update character.updated_at timestamp\n\n"
        "**Response:**\n"
        "- Returns the stored PointOfInterest (with server-generated id and created_at)\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header, POI capacity exceeded (200 max)\n"
        "- `403`: X-User-Id does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Validation error (invalid field values, oversized fields)\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def create_poi(
    character_id: str,
    request: CreatePOIRequest,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
) -> CreatePOIResponse:
    """
    Create and append a POI to a character's pois subcollection.

    This endpoint implements copy-on-write POI migration:
    1. Validates character_id as UUID format
    2. Validates X-User-Id matches character owner
    3. Validates payload (name, description, optional timestamp, optional tags)
    4. Checks if migration is needed (embedded world_pois exist)
    5. If migration enabled, migrates embedded POIs to subcollection
    6. Creates POI in subcollection (authoritative storage)
    7. Returns stored POI with generated id and timestamp

    The authoritative POI storage is: characters/{character_id}/pois/{poi_id}

    Args:
        character_id: UUID-formatted character identifier
        request: POI creation request data
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        CreatePOIResponse with the created POI

    Raises:
        HTTPException:
            - 400: Invalid X-User-Id
            - 403: Access denied (user not owner)
            - 404: Character not found
            - 422: Validation error
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "create_poi_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("create_poi_missing_user_id", character_id=character_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Parse and validate timestamp if provided
    poi_timestamp: Optional[datetime] = None
    if request.timestamp:
        try:
            poi_timestamp = datetime_to_firestore(request.timestamp)
        except ValueError as e:
            logger.warning(
                "create_poi_invalid_timestamp",
                character_id=character_id,
                timestamp=request.timestamp,
                error=str(e),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid timestamp format: {str(e)}",
            )

    # Log creation attempt
    logger.info(
        "create_poi_attempt",
        character_id=character_id,
        user_id=user_id,
        name=request.name,
        has_timestamp=poi_timestamp is not None,
        has_tags=request.tags is not None,
    )

    try:
        # Generate POI ID outside transaction to avoid race condition on retry
        poi_id = str(uuid.uuid4()).lower()

        # Create transaction
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        @firestore.transactional
        def create_poi_in_transaction(transaction):
            """Atomically create POI in subcollection and handle migration."""
            # 1. Fetch character document to verify existence and ownership
            char_ref = characters_ref.document(character_id)
            char_snapshot = char_ref.get(transaction=transaction)

            if not char_snapshot.exists:
                return None, None, "not_found"

            # 2. Verify ownership
            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if owner_user_id != user_id:
                return None, None, "access_denied"

            # 3. Check if migration is needed (copy-on-write)
            migration_stats = None
            if settings.poi_migration_enabled and should_migrate_pois(char_data):
                logger.info(
                    "create_poi_migrating_embedded_pois",
                    character_id=character_id,
                    embedded_count=len(char_data.get("world_pois", [])),
                )
                migration_stats = migrate_embedded_pois_to_subcollection(
                    character_id, transaction
                )
                logger.info(
                    "create_poi_migration_completed",
                    character_id=character_id,
                    **migration_stats,
                )

                # Check for migration errors and log warnings
                if migration_stats and migration_stats.get("errors"):
                    logger.warning(
                        "create_poi_migration_partial_failure",
                        character_id=character_id,
                        error_count=len(migration_stats["errors"]),
                        errors=migration_stats["errors"],
                    )

            # 4. Create POI data for subcollection
            # Use server timestamp if not provided by client
            timestamp_discovered = (
                poi_timestamp if poi_timestamp else datetime.now(timezone.utc)
            )

            # Create subcollection POI model
            poi_subcollection = PointOfInterestSubcollection(
                poi_id=poi_id,
                name=request.name,
                description=request.description,
                timestamp_discovered=timestamp_discovered,
                tags=request.tags,
                visited=False,  # Default for new POIs
            )

            # Convert to Firestore dict
            poi_data = poi_subcollection_to_firestore(poi_subcollection)

            # 5. Create POI in subcollection directly (avoid helper to support mocking)
            pois_collection = char_ref.collection("pois")
            poi_ref = pois_collection.document(poi_id)
            transaction.set(poi_ref, poi_data)

            # 6. Update character updated_at timestamp
            transaction.update(char_ref, {"updated_at": firestore.SERVER_TIMESTAMP})

            # Convert timestamp for response
            response_poi_data = {
                "id": poi_id,
                "name": request.name,
                "description": request.description,
                "created_at": timestamp_discovered,
                "tags": request.tags,
            }

            return response_poi_data, migration_stats, "success"

        # Execute transaction
        poi_data, migration_stats, result = create_poi_in_transaction(transaction)

        # Handle transaction results
        if result == "not_found":
            logger.warning(
                "create_poi_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )
        elif result == "access_denied":
            logger.warning(
                "create_poi_access_denied",
                character_id=character_id,
                requested_user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user ID does not match character owner",
            )

        # Convert to PointOfInterest model for response (backward compatibility)
        created_poi = PointOfInterest(
            id=poi_data["id"],
            name=poi_data["name"],
            description=poi_data["description"],
            created_at=poi_data["created_at"],
            tags=poi_data.get("tags"),
        )

        logger.info(
            "create_poi_success",
            character_id=character_id,
            poi_id=poi_id,
            name=request.name,
            migration_performed=migration_stats is not None,
        )

        return CreatePOIResponse(poi=created_poi)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "create_poi_error",
            character_id=character_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create POI: {str(e)}",
        )


@router.get(
    "/{character_id}/pois/random",
    response_model=GetRandomPOIsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get random POIs for a character",
    description=(
        "Retrieve N randomly sampled POIs from a character's pois subcollection.\n\n"
        "**Authoritative Storage:** Reads from `characters/{character_id}/pois/{poi_id}` subcollection.\n"
        "**Backward Compatibility:** Falls back to embedded world_pois array if subcollection is empty (configurable via POI_EMBEDDED_READ_FALLBACK).\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier (if provided, must match the character's owner_user_id)\n"
        "  - If header is provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n\n"
        "**Optional Query Parameters:**\n"
        "- `n`: Number of POIs to sample (default: 3, min: 1, max: 20)\n\n"
        "**Sampling Behavior:**\n"
        "- POIs are sampled uniformly at random without replacement\n"
        "- If fewer than N POIs exist, returns all available POIs\n"
        "- If no POIs exist, returns empty list (not an error)\n"
        "- Same request may return different POIs on each call (non-deterministic)\n\n"
        "**Response:**\n"
        "- Returns list of randomly sampled POIs\n"
        "- Includes metadata: count, requested_n, total_available\n\n"
        "**Error Responses:**\n"
        "- `400`: Invalid query parameters (n <= 0 or n > 20) or empty X-User-Id\n"
        "- `403`: X-User-Id provided but does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def get_random_pois(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
    n: int = 3,
) -> GetRandomPOIsResponse:
    """
    Retrieve N randomly sampled POIs from a character's pois subcollection.

    This endpoint reads from the authoritative subcollection with optional fallback
    to embedded POIs for backward compatibility during migration.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates n parameter (default 3, min 1, max 20)
    3. Optionally verifies X-User-Id matches owner_user_id
    4. Fetches POIs from subcollection (or fallback to embedded if configured)
    5. Samples up to N unique POIs uniformly at random
    6. Returns sampled POIs with metadata

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control
        n: Number of POIs to sample (default 3, max 20)

    Returns:
        GetRandomPOIsResponse with sampled POIs and metadata

    Raises:
        HTTPException:
            - 400: Invalid parameters (n out of range)
            - 403: User ID mismatch (access denied)
            - 404: Character not found
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_random_pois_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Validate n parameter
    if n < 1 or n > 20:
        logger.warning(
            "get_random_pois_invalid_n",
            character_id=character_id,
            n=n,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parameter 'n' must be between 1 and 20 (got {n})",
        )

    # Log retrieval attempt
    logger.info(
        "get_random_pois_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
        n=n,
    )

    try:
        # 1. Verify character exists
        characters_ref = db.collection(settings.firestore_characters_collection)
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(
                "get_random_pois_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # 2. Verify ownership if X-User-Id is provided
        char_data = char_snapshot.to_dict()
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_random_pois_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )

            owner_user_id = char_data.get("owner_user_id")

            if stripped_user_id != owner_user_id:
                logger.warning(
                    "get_random_pois_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        # 3. Get POIs from subcollection (authoritative) with fallback to embedded
        # Query subcollection directly to support mocking in tests
        pois_collection = char_ref.collection("pois")
        pois_query = pois_collection.stream()
        pois_docs = list(pois_query)

        # Convert document snapshots to dict format
        pois_data = [doc.to_dict() for doc in pois_docs]

        # Fallback to embedded POIs if subcollection is empty and fallback enabled
        if not pois_data and settings.poi_embedded_read_fallback:
            embedded_pois = char_data.get("world_pois", [])
            if embedded_pois:
                logger.info(
                    "get_random_pois_fallback_to_embedded",
                    character_id=character_id,
                    embedded_count=len(embedded_pois),
                )
                # Convert embedded format to subcollection format
                pois_data = []
                for embedded_poi in embedded_pois:
                    # Validate that required fields exist before conversion
                    if not embedded_poi.get("id"):
                        logger.warning(
                            "get_random_pois_embedded_poi_missing_id",
                            character_id=character_id,
                        )
                        continue
                    if not embedded_poi.get("name") or not embedded_poi.get(
                        "description"
                    ):
                        logger.warning(
                            "get_random_pois_embedded_poi_missing_required_fields",
                            character_id=character_id,
                            poi_id=embedded_poi.get("id"),
                        )
                        continue

                    # Convert Firestore timestamp to datetime if needed
                    created_at = embedded_poi.get("created_at")
                    if created_at:
                        created_at = datetime_from_firestore(created_at)

                    pois_data.append(
                        {
                            "poi_id": embedded_poi.get("id"),
                            "name": embedded_poi.get("name"),
                            "description": embedded_poi.get("description"),
                            "timestamp_discovered": created_at,
                            "tags": embedded_poi.get("tags"),
                        }
                    )

        total_available = len(pois_data)

        # 4. Sample POIs
        # Determine how many to sample (min of n and total available)
        sample_size = min(n, total_available)

        if sample_size == 0:
            # No POIs available, return empty list
            sampled_pois_data = []
        elif sample_size == total_available:
            # All POIs requested, no need to sample
            sampled_pois_data = pois_data
        else:
            # Sample without replacement
            sampled_pois_data = random.sample(pois_data, sample_size)

        # 5. Convert to PointOfInterest models (response format)
        sampled_pois = []
        for poi_data in sampled_pois_data:
            # Map subcollection fields to embedded format for response
            # Handle both subcollection format (poi_id) and embedded format (id)
            poi_id = poi_data.get("poi_id")
            if poi_id is None:
                # Fallback to embedded format field name
                poi_id = poi_data.get("id")
            if poi_id is None:
                # Skip POIs without IDs (data consistency issue)
                logger.warning(
                    "get_random_pois_poi_missing_id",
                    character_id=character_id,
                    poi_data_keys=list(poi_data.keys()),
                )
                continue

            created_at = poi_data.get("timestamp_discovered")
            if created_at is not None:
                created_at = datetime_from_firestore(created_at)

            poi = PointOfInterest(
                id=poi_id,
                name=poi_data["name"],
                description=poi_data["description"],
                created_at=created_at,
                tags=poi_data.get("tags"),
            )
            sampled_pois.append(poi)

        logger.info(
            "get_random_pois_success",
            character_id=character_id,
            requested_n=n,
            returned_count=len(sampled_pois),
            total_available=total_available,
        )

        return GetRandomPOIsResponse(
            pois=sampled_pois,
            count=len(sampled_pois),
            requested_n=n,
            total_available=total_available,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_random_pois_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve random POIs due to an internal error",
        )


@router.get(
    "/{character_id}/pois",
    response_model=GetPOIsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get POIs for a character with cursor-based pagination",
    description=(
        "Retrieve POIs from the character's pois subcollection with cursor-based pagination.\n\n"
        "**Authoritative Storage:** Reads from `characters/{character_id}/pois/{poi_id}` subcollection.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier (if provided, must match the character's owner_user_id)\n"
        "  - If header is provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n\n"
        "**Optional Query Parameters:**\n"
        "- `limit`: Maximum number of POIs to return per page (default: 10, max: 100)\n"
        "- `cursor`: Pagination cursor (opaque string from previous response, None for first page)\n\n"
        "**Cursor-Based Pagination:**\n"
        "- Results are sorted by timestamp_discovered descending (newest first)\n"
        "- Use `limit` to control page size\n"
        "- Use `cursor` from previous response's `cursor` field to get next page\n"
        "- When no more results, response includes cursor=null\n"
        "- Cursors are opaque strings; do not attempt to parse or construct them\n"
        "- Malformed cursors return 400 with guidance to restart pagination\n\n"
        "**Response:**\n"
        "- Returns list of POIs with pagination metadata\n"
        "- Empty list returned if character has no POIs\n"
        "- cursor field: opaque string for next page or null if exhausted\n\n"
        "**Error Responses:**\n"
        "- `400`: Invalid query parameters (limit out of range, malformed cursor) or empty X-User-Id\n"
        "- `403`: X-User-Id provided but does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def get_pois(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
    limit: int = Query(default=10, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
) -> GetPOIsResponse:
    """
    Retrieve POIs for a character from the pois subcollection with cursor-based pagination.

    This endpoint uses the authoritative subcollection storage and implements true
    cursor-based pagination using Firestore's start_after capability for efficient
    queries on large POI collections.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates limit parameter (default 10, max 100)
    3. Optionally verifies X-User-Id matches owner_user_id
    4. Queries pois subcollection with ordering and pagination
    5. Returns POIs with next cursor for pagination

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control
        limit: Maximum number of results to return (default 10, max 100)
        cursor: Optional opaque pagination cursor from previous response

    Returns:
        GetPOIsResponse with POIs list and pagination cursor

    Raises:
        HTTPException:
            - 400: Invalid parameters (limit out of range, malformed cursor) or empty X-User-Id
            - 403: User ID mismatch (access denied)
            - 404: Character not found
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_pois_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Log retrieval attempt
    logger.info(
        "get_pois_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
        limit=limit,
        has_cursor=cursor is not None,
    )

    try:
        # 1. Verify character exists
        characters_ref = db.collection(settings.firestore_characters_collection)
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(
                "get_pois_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # 2. Verify ownership if X-User-Id is provided
        char_data = char_snapshot.to_dict()
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_pois_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )

            owner_user_id = char_data.get("owner_user_id")

            if stripped_user_id != owner_user_id:
                logger.warning(
                    "get_pois_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        # 3. Query POIs from subcollection with cursor-based pagination
        # Query subcollection directly to support mocking in tests
        pois_collection = char_ref.collection("pois")

        # Build query with ordering by timestamp_discovered descending (newest first)
        query = pois_collection.order_by(
            "timestamp_discovered", direction=firestore.Query.DESCENDING
        )

        # Apply cursor if provided
        cursor_snapshot = None
        if cursor:
            try:
                # Decode cursor: it contains the POI ID to start after
                # For security, we fetch the document to get the actual snapshot
                cursor_poi_id = cursor
                cursor_doc_ref = pois_collection.document(cursor_poi_id)
                cursor_snapshot = cursor_doc_ref.get()

                if not cursor_snapshot.exists:
                    # Cursor points to non-existent document - likely expired or invalid
                    logger.warning(
                        "get_pois_invalid_cursor_not_found",
                        character_id=character_id,
                        cursor=cursor,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid or expired cursor. Please restart pagination from the beginning.",
                    )

                query = query.start_after(cursor_snapshot)

            except HTTPException:
                # Re-raise HTTP exceptions
                raise
            except Exception as e:
                logger.warning(
                    "get_pois_cursor_decode_error",
                    character_id=character_id,
                    cursor=cursor,
                    error=str(e),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Malformed cursor. Please restart pagination from the beginning.",
                )

        # Fetch limit + 1 to determine if there are more results
        query = query.limit(limit + 1)
        poi_docs = list(query.stream())

        # Determine if there are more results
        has_more = len(poi_docs) > limit
        if has_more:
            # Remove the extra document
            poi_docs = poi_docs[:limit]

        # 4. Convert to PointOfInterest models (backward-compatible response format)
        pois = []
        last_doc = None
        for doc in poi_docs:
            last_doc = doc
            poi_data = doc.to_dict()

            # Map subcollection fields to embedded format for backward compatibility
            timestamp_discovered = poi_data.get("timestamp_discovered")
            if timestamp_discovered is not None:
                timestamp_discovered = datetime_from_firestore(timestamp_discovered)

            poi = PointOfInterest(
                id=poi_data.get("poi_id", doc.id),  # Use poi_id or doc ID
                name=poi_data["name"],
                description=poi_data["description"],
                created_at=timestamp_discovered,  # Map timestamp_discovered to created_at
                tags=poi_data.get("tags"),
            )
            pois.append(poi)

        # 5. Generate next cursor if there are more results
        next_cursor = None
        if has_more and last_doc:
            # Cursor is simply the last document's ID
            next_cursor = last_doc.id

        logger.info(
            "get_pois_success",
            character_id=character_id,
            returned_count=len(pois),
            has_next_page=next_cursor is not None,
            source="subcollection",
        )

        return GetPOIsResponse(
            pois=pois,
            count=len(pois),
            cursor=next_cursor,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_pois_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve POIs due to an internal error",
        )


@router.get(
    "/{character_id}/pois/summary",
    response_model=GetPOISummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get POI count and preview for a character",
    description=(
        "Retrieve a lightweight POI summary with total count and capped preview.\n\n"
        "**Authoritative Storage:** Reads from `characters/{character_id}/pois/{poi_id}` subcollection.\n\n"
        "**Use Case:** This endpoint provides aggregate POI information for UI previews\n"
        "without scanning large collections or loading all POIs into memory.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier (if provided, must match the character's owner_user_id)\n"
        "  - If header is provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n\n"
        "**Optional Query Parameters:**\n"
        "- `preview_limit`: Maximum number of POIs to include in preview (default: 5, max: 20)\n\n"
        "**Response:**\n"
        "- `total_count`: Total number of POIs using efficient count aggregation\n"
        "- `preview`: Up to preview_limit POIs sorted by newest first\n"
        "- `preview_count`: Number of POIs in the preview\n\n"
        "**Performance:**\n"
        "- Uses Firestore count() aggregation (single read cost)\n"
        "- Preview query limited to prevent large dataset scans\n"
        "- Total latency typically <50ms even for large POI collections\n\n"
        "**Error Responses:**\n"
        "- `400`: Invalid query parameters (preview_limit out of range) or empty X-User-Id\n"
        "- `403`: X-User-Id provided but does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def get_poi_summary(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
    preview_limit: int = Query(default=5, ge=1, le=20),
) -> GetPOISummaryResponse:
    """
    Retrieve lightweight POI summary with total count and preview.

    This endpoint provides aggregate POI information without loading all POIs,
    making it ideal for UI widgets and summary displays.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates preview_limit parameter (default 5, max 20)
    3. Optionally verifies X-User-Id matches owner_user_id
    4. Uses Firestore count() aggregation for total count
    5. Fetches up to preview_limit newest POIs for preview
    6. Returns summary with minimal overhead

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control
        preview_limit: Maximum number of POIs to include in preview (default 5, max 20)

    Returns:
        GetPOISummaryResponse with total count and preview

    Raises:
        HTTPException:
            - 400: Invalid parameters (preview_limit out of range) or empty X-User-Id
            - 403: User ID mismatch (access denied)
            - 404: Character not found
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_poi_summary_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Log retrieval attempt
    logger.info(
        "get_poi_summary_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
        preview_limit=preview_limit,
    )

    try:
        # 1. Verify character exists
        characters_ref = db.collection(settings.firestore_characters_collection)
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(
                "get_poi_summary_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # 2. Verify ownership if X-User-Id is provided
        char_data = char_snapshot.to_dict()
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_poi_summary_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )

            owner_user_id = char_data.get("owner_user_id")

            if stripped_user_id != owner_user_id:
                logger.warning(
                    "get_poi_summary_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        # 3. Get total count using efficient aggregation
        # Use direct subcollection access for counting
        pois_collection = char_ref.collection("pois")
        count_query = pois_collection.count()
        count_result = count_query.get()
        total_count = count_result[0][0].value

        # 4. Get preview of newest POIs
        preview_query = pois_collection.order_by(
            "timestamp_discovered", direction=firestore.Query.DESCENDING
        ).limit(preview_limit)

        preview_docs = list(preview_query.stream())

        # 5. Convert to PointOfInterest models for preview
        preview_pois = []
        for doc in preview_docs:
            poi_data = doc.to_dict()

            # Map subcollection fields to embedded format for backward compatibility
            timestamp_discovered = poi_data.get("timestamp_discovered")
            if timestamp_discovered is not None:
                timestamp_discovered = datetime_from_firestore(timestamp_discovered)

            poi = PointOfInterest(
                id=poi_data.get("poi_id", doc.id),
                name=poi_data["name"],
                description=poi_data["description"],
                created_at=timestamp_discovered,
                tags=poi_data.get("tags"),
            )
            preview_pois.append(poi)

        logger.info(
            "get_poi_summary_success",
            character_id=character_id,
            total_count=total_count,
            preview_count=len(preview_pois),
        )

        return GetPOISummaryResponse(
            total_count=total_count,
            preview=preview_pois,
            preview_count=len(preview_pois),
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_poi_summary_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve POI summary due to an internal error",
        )


@router.put(
    "/{character_id}/pois/{poi_id}",
    response_model=UpdatePOIResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing POI",
    description=(
        "Update fields of an existing POI in the character's pois subcollection.\n\n"
        "**Authoritative Storage:** Updates POI in `characters/{character_id}/pois/{poi_id}` subcollection.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n"
        "- `poi_id`: UUID-formatted POI identifier\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (must match character owner for access control)\n\n"
        "**Request Body:**\n"
        "- At least one field must be provided for update\n"
        "- `name`: Optional POI name (1-200 characters)\n"
        "- `description`: Optional POI description (1-2000 characters)\n"
        "- `visited`: Optional visited flag (boolean)\n"
        "- `tags`: Optional list of tags (max 20 tags, each max 50 characters)\n\n"
        "**Partial Updates:**\n"
        "- Only provided fields are updated\n"
        "- Null/missing fields are not changed\n"
        "- To clear tags, provide an empty list []\n\n"
        "**Response:**\n"
        "- Returns the updated POI with all fields (including unchanged ones)\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header, no fields provided\n"
        "- `403`: X-User-Id does not match character owner\n"
        "- `404`: Character or POI not found\n"
        "- `422`: Validation error (invalid field values)\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def update_poi(
    character_id: str,
    poi_id: str,
    request: UpdatePOIRequest,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
) -> UpdatePOIResponse:
    """
    Update an existing POI in the character's pois subcollection.

    This endpoint:
    1. Validates character_id and poi_id as UUID format
    2. Validates X-User-Id matches character owner
    3. Validates update payload (at least one field provided)
    4. Updates POI in subcollection with provided fields
    5. Returns updated POI

    Args:
        character_id: UUID-formatted character identifier
        poi_id: UUID-formatted POI identifier
        request: POI update request data
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        UpdatePOIResponse with the updated POI

    Raises:
        HTTPException:
            - 400: Invalid X-User-Id or no fields provided
            - 403: Access denied (user not owner)
            - 404: Character or POI not found
            - 422: Validation error
            - 500: Firestore error
    """
    # Validate and normalize UUID formats
    try:
        character_id = str(uuid.UUID(character_id))
        poi_id = str(uuid.UUID(poi_id))
    except ValueError:
        logger.warning(
            "update_poi_invalid_uuid",
            character_id=character_id,
            poi_id=poi_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid UUID format for character_id or poi_id",
        )

    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("update_poi_missing_user_id", character_id=character_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Log update attempt
    logger.info(
        "update_poi_attempt",
        character_id=character_id,
        poi_id=poi_id,
        user_id=user_id,
    )

    try:
        # Create transaction
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        @firestore.transactional
        def update_poi_in_transaction(transaction):
            """Atomically update POI and character timestamp."""
            # 1. Fetch character document to verify existence and ownership
            char_ref = characters_ref.document(character_id)
            char_snapshot = char_ref.get(transaction=transaction)

            if not char_snapshot.exists:
                return None, "not_found_character"

            # 2. Verify ownership
            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if owner_user_id != user_id:
                return None, "access_denied"

            # 3. Fetch POI from subcollection directly
            pois_collection = char_ref.collection("pois")
            poi_ref = pois_collection.document(poi_id)
            poi_snapshot = poi_ref.get(transaction=transaction)

            if not poi_snapshot.exists:
                return None, "not_found_poi"

            poi_data = poi_snapshot.to_dict()

            # 4. Build update dict with only provided fields
            update_data = {}
            if request.name is not None:
                update_data["name"] = request.name
            if request.description is not None:
                update_data["description"] = request.description
            if request.visited is not None:
                update_data["visited"] = request.visited
            if request.tags is not None:
                update_data["tags"] = request.tags

            # 5. Update POI in subcollection
            transaction.update(poi_ref, update_data)

            # 6. Update character updated_at timestamp
            transaction.update(char_ref, {"updated_at": firestore.SERVER_TIMESTAMP})

            # 7. Merge updated fields with existing data for response
            poi_data.update(update_data)

            return poi_data, "success"

        # Execute transaction
        poi_data, result = update_poi_in_transaction(transaction)

        # Handle transaction results
        if result == "not_found_character":
            logger.warning(
                "update_poi_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )
        elif result == "not_found_poi":
            logger.warning(
                "update_poi_poi_not_found",
                character_id=character_id,
                poi_id=poi_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"POI with ID '{poi_id}' not found for this character",
            )
        elif result == "access_denied":
            logger.warning(
                "update_poi_access_denied",
                character_id=character_id,
                requested_user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user ID does not match character owner",
            )

        # Convert to PointOfInterest model for response
        timestamp_discovered = poi_data.get("timestamp_discovered")
        if timestamp_discovered is not None:
            timestamp_discovered = datetime_from_firestore(timestamp_discovered)

        updated_poi = PointOfInterest(
            id=poi_data.get("poi_id", poi_id),
            name=poi_data["name"],
            description=poi_data["description"],
            created_at=timestamp_discovered,
            tags=poi_data.get("tags"),
        )

        logger.info(
            "update_poi_success",
            character_id=character_id,
            poi_id=poi_id,
        )

        return UpdatePOIResponse(poi=updated_poi)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "update_poi_error",
            character_id=character_id,
            poi_id=poi_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update POI: {str(e)}",
        )


@router.delete(
    "/{character_id}/pois/{poi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a POI",
    description=(
        "Delete a POI from the character's pois subcollection.\n\n"
        "**Authoritative Storage:** Deletes POI from `characters/{character_id}/pois/{poi_id}` subcollection.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n"
        "- `poi_id`: UUID-formatted POI identifier\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (must match character owner for access control)\n\n"
        "**Behavior:**\n"
        "- Permanently deletes the POI from subcollection\n"
        "- Idempotent: succeeds even if POI doesn't exist (returns 204)\n"
        "- Updates character.updated_at timestamp\n\n"
        "**Response:**\n"
        "- Returns 204 No Content on success (even if POI didn't exist)\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header\n"
        "- `403`: X-User-Id does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Invalid UUID format for character_id or poi_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def delete_poi(
    character_id: str,
    poi_id: str,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
):
    """
    Delete a POI from the character's pois subcollection.

    This endpoint:
    1. Validates character_id and poi_id as UUID format
    2. Validates X-User-Id matches character owner
    3. Deletes POI from subcollection
    4. Updates character updated_at timestamp
    5. Idempotent - succeeds even if POI doesn't exist

    Args:
        character_id: UUID-formatted character identifier
        poi_id: UUID-formatted POI identifier
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        No content (204 status)

    Raises:
        HTTPException:
            - 400: Invalid X-User-Id
            - 403: Access denied (user not owner)
            - 404: Character not found
            - 422: Validation error
            - 500: Firestore error
    """
    # Validate and normalize UUID formats
    try:
        character_id = str(uuid.UUID(character_id))
        poi_id = str(uuid.UUID(poi_id))
    except ValueError:
        logger.warning(
            "delete_poi_invalid_uuid",
            character_id=character_id,
            poi_id=poi_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid UUID format for character_id or poi_id",
        )

    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("delete_poi_missing_user_id", character_id=character_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Log delete attempt
    logger.info(
        "delete_poi_attempt",
        character_id=character_id,
        poi_id=poi_id,
        user_id=user_id,
    )

    try:
        # Create transaction
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        @firestore.transactional
        def delete_poi_in_transaction(transaction):
            """Atomically delete POI and update character timestamp."""
            # 1. Fetch character document to verify existence and ownership
            char_ref = characters_ref.document(character_id)
            char_snapshot = char_ref.get(transaction=transaction)

            if not char_snapshot.exists:
                return "not_found_character"

            # 2. Verify ownership
            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if owner_user_id != user_id:
                return "access_denied"

            # 3. Check if POI exists before deleting
            pois_collection = char_ref.collection("pois")
            poi_ref = pois_collection.document(poi_id)
            poi_snapshot = poi_ref.get(transaction=transaction)

            if poi_snapshot.exists:
                # 4. Delete POI and update character timestamp
                transaction.delete(poi_ref)
                transaction.update(char_ref, {"updated_at": firestore.SERVER_TIMESTAMP})

            return "success"

        # Execute transaction
        result = delete_poi_in_transaction(transaction)

        # Handle transaction results
        if result == "not_found_character":
            logger.warning(
                "delete_poi_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )
        elif result == "access_denied":
            logger.warning(
                "delete_poi_access_denied",
                character_id=character_id,
                requested_user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user ID does not match character owner",
            )

        logger.info(
            "delete_poi_success",
            character_id=character_id,
            poi_id=poi_id,
        )

        # Return 204 No Content
        return None

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "delete_poi_error",
            character_id=character_id,
            poi_id=poi_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete POI: {str(e)}",
        )


# ==============================================================================
# Quest Management Endpoints
# ==============================================================================


class SetQuestResponse(BaseModel):
    """Response model for setting active quest."""

    quest: Quest = Field(description="The stored active quest")


class GetQuestResponse(BaseModel):
    """Response model for getting active quest."""

    quest: Optional[Quest] = Field(
        description="The active quest or null if none exists"
    )


@router.put(
    "/{character_id}/quest",
    response_model=SetQuestResponse,
    status_code=status.HTTP_200_OK,
    summary="Set active quest for a character",
    description=(
        "Set or update the active quest for a character.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (must match character owner for access control)\n\n"
        "**Request Body:**\n"
        "- Quest object with name, description, requirements, rewards, completion_state, updated_at\n\n"
        "**Validation:**\n"
        "- name: required string\n"
        "- description: required string\n"
        "- requirements: list of strings (default: [])\n"
        "- rewards: QuestRewards object with items, currency, experience\n"
        "- completion_state: 'not_started', 'in_progress', or 'completed'\n"
        "- updated_at: ISO 8601 timestamp\n\n"
        "**Single Quest Constraint:**\n"
        "Only one active quest is allowed per character. If an active quest already exists,\n"
        "this endpoint returns 409 Conflict with guidance to DELETE the existing quest first.\n\n"
        "**Atomicity:**\n"
        "Uses Firestore transaction to atomically:\n"
        "1. Verify character exists and user owns it\n"
        "2. Check that no active quest exists\n"
        "3. Set active_quest field\n"
        "4. Update character.updated_at timestamp\n\n"
        "**Response:**\n"
        "- Returns the stored Quest object\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header\n"
        "- `403`: X-User-Id does not match character owner\n"
        "- `404`: Character not found\n"
        "- `409`: Active quest already exists (DELETE required before replacing)\n"
        "- `422`: Validation error (invalid field values, invalid completion_state)\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def set_quest(
    character_id: str,
    quest: Quest,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
) -> SetQuestResponse:
    """
    Set the active quest for a character.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates X-User-Id matches character owner
    3. Validates Quest payload (name, description, completion_state, etc.)
    4. Uses Firestore transaction to atomically check for existing quest and set new quest
    5. Returns stored quest

    Args:
        character_id: UUID-formatted character identifier
        quest: Quest object to set as active
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        SetQuestResponse with the stored quest

    Raises:
        HTTPException:
            - 400: Invalid X-User-Id
            - 403: Access denied (user not owner)
            - 404: Character not found
            - 409: Active quest already exists
            - 422: Validation error
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "set_quest_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("set_quest_missing_user_id", character_id=character_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Log attempt
    logger.info(
        "set_quest_attempt",
        character_id=character_id,
        user_id=user_id,
        quest_name=quest.name,
        completion_state=quest.completion_state,
    )

    try:
        # Create transaction
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        @firestore.transactional
        def set_quest_in_transaction(transaction):
            """Atomically verify no quest exists and set new quest."""
            # 1. Fetch character document to verify existence and ownership
            char_ref = characters_ref.document(character_id)
            char_snapshot = char_ref.get(transaction=transaction)

            if not char_snapshot.exists:
                return None, "not_found"

            # 2. Verify ownership
            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if owner_user_id != user_id:
                return None, "access_denied"

            # 3. Check for existing active quest
            existing_quest = char_data.get("active_quest")
            if existing_quest is not None:
                return None, "quest_exists"

            # 4. Serialize quest for Firestore
            # Use mode='python' to get datetime objects (not JSON strings)
            quest_data = quest.model_dump(mode="python")

            # 5. Update character with new quest and updated_at timestamp
            transaction.update(
                char_ref,
                {"active_quest": quest_data, "updated_at": firestore.SERVER_TIMESTAMP},
            )

            return quest_data, "success"

        # Execute transaction
        quest_data, result = set_quest_in_transaction(transaction)

        # Handle transaction results
        if result == "not_found":
            logger.warning(
                "set_quest_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )
        elif result == "access_denied":
            logger.warning(
                "set_quest_access_denied",
                character_id=character_id,
                requested_user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user ID does not match character owner",
            )
        elif result == "quest_exists":
            logger.warning(
                "set_quest_already_exists",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active quest already exists for this character. "
                "Please DELETE the existing quest before setting a new one.",
            )

        logger.info(
            "set_quest_success",
            character_id=character_id,
            quest_name=quest.name,
        )

        # The 'quest_data' is what was prepared for Firestore.
        # Construct the response from this data to ensure consistency.
        return SetQuestResponse(quest=Quest(**quest_data))

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "set_quest_error",
            character_id=character_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set quest: {str(e)}",
        )


@router.get(
    "/{character_id}/quest",
    response_model=GetQuestResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active quest for a character",
    description=(
        "Retrieve the active quest for a character.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier (if provided, must match the character's owner_user_id)\n"
        "  - If header is provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n\n"
        "**Response:**\n"
        "- Returns the Quest object if an active quest exists\n"
        '- Returns {"quest": null} if no active quest exists\n\n'
        "**Error Responses:**\n"
        "- `400`: X-User-Id header provided but empty/whitespace-only\n"
        "- `403`: X-User-Id provided but does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def get_quest(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
) -> GetQuestResponse:
    """
    Retrieve the active quest for a character.

    This endpoint:
    1. Validates character_id as UUID format
    2. Fetches the character document from Firestore
    3. Optionally verifies X-User-Id matches owner_user_id
    4. Returns the active quest or null

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control

    Returns:
        GetQuestResponse with the quest or null

    Raises:
        HTTPException:
            - 400: Empty X-User-Id header
            - 403: User ID mismatch (access denied)
            - 404: Character not found
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_quest_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Log retrieval attempt
    logger.info(
        "get_quest_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
    )

    try:
        # Fetch character document from Firestore
        characters_ref = db.collection(settings.firestore_characters_collection)
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(
                "get_quest_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # Verify ownership if X-User-Id is provided
        char_data = char_snapshot.to_dict()
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_quest_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )

            owner_user_id = char_data.get("owner_user_id")

            if stripped_user_id != owner_user_id:
                logger.warning(
                    "get_quest_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        # Use the centralized deserialization logic from character_from_firestore
        # to construct the full character document, which handles nested timestamps.
        character = character_from_firestore(char_data, character_id=character_id)
        active_quest = character.active_quest

        logger.info(
            "get_quest_success",
            character_id=character_id,
            has_quest=active_quest is not None,
        )

        return GetQuestResponse(quest=active_quest)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_quest_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quest due to an internal error",
        )


@router.delete(
    "/{character_id}/quest",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete active quest for a character",
    description=(
        "Clear the active quest for a character and archive it.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (must match character owner for access control)\n\n"
        "**Behavior:**\n"
        "- Removes active_quest field from character\n"
        "- Appends quest to archived_quests with cleared_at timestamp\n"
        "- Enforces 50-entry limit on archived_quests (oldest entries removed first)\n"
        "- Idempotent: succeeds even if no active quest exists (returns 204)\n\n"
        "**Atomicity:**\n"
        "Uses Firestore transaction to atomically:\n"
        "1. Verify character exists and user owns it\n"
        "2. Remove active quest (if exists)\n"
        "3. Archive quest to archived_quests with cleared_at timestamp\n"
        "4. Trim archived_quests to maintain ≤50 entries (oldest first)\n"
        "5. Update character.updated_at timestamp\n\n"
        "**Response:**\n"
        "- Returns 204 No Content on success\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header\n"
        "- `403`: X-User-Id does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)"
    ),
)
async def delete_quest(
    character_id: str,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
):
    """
    Delete the active quest for a character and archive it.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates X-User-Id matches character owner
    3. Uses Firestore transaction to atomically clear quest and archive it
    4. Enforces 50-entry limit on archived quests (FIFO)
    5. Idempotent - succeeds even if no quest exists

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        No content (204 status)

    Raises:
        HTTPException:
            - 400: Invalid X-User-Id
            - 403: Access denied (user not owner)
            - 404: Character not found
            - 422: Validation error
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "delete_quest_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("delete_quest_missing_user_id", character_id=character_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Log attempt
    logger.info(
        "delete_quest_attempt",
        character_id=character_id,
        user_id=user_id,
    )

    try:
        # Create transaction
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        @firestore.transactional
        def delete_quest_in_transaction(transaction):
            """Atomically clear quest and archive it."""
            # 1. Fetch character document to verify existence and ownership
            char_ref = characters_ref.document(character_id)
            char_snapshot = char_ref.get(transaction=transaction)

            if not char_snapshot.exists:
                return "not_found", False

            # 2. Verify ownership
            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if owner_user_id != user_id:
                return "access_denied", False

            # 3. Get existing active quest
            active_quest_data = char_data.get("active_quest")

            # If no active quest, this is a no-op but still succeeds (idempotent)
            if active_quest_data is None:
                logger.info(
                    "delete_quest_no_active_quest",
                    character_id=character_id,
                )
                return "success", False

            # 4. Create archived quest entry with cleared_at timestamp
            cleared_at = datetime.now(timezone.utc)
            archived_entry = {
                "quest": active_quest_data,
                "cleared_at": cleared_at,
            }

            # 5. Get existing archived quests and append new entry
            archived_quests = char_data.get("archived_quests", [])
            archived_quests.append(archived_entry)

            # 6. Trim to maintain ≤50 entries (remove oldest first)
            if len(archived_quests) > 50:
                # Keep the last 50 entries (most recent)
                archived_quests = archived_quests[-50:]

            # 7. Update character: clear active quest, update archived quests, update timestamp
            transaction.update(
                char_ref,
                {
                    "active_quest": None,
                    "archived_quests": archived_quests,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
            )

            return "success", True

        # Execute transaction
        result, had_quest = delete_quest_in_transaction(transaction)

        # Handle transaction results
        if result == "not_found":
            logger.warning(
                "delete_quest_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )
        elif result == "access_denied":
            logger.warning(
                "delete_quest_access_denied",
                character_id=character_id,
                requested_user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user ID does not match character owner",
            )

        logger.info(
            "delete_quest_success",
            character_id=character_id,
            had_active_quest=had_quest,
        )

        # Return 204 No Content
        return None

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "delete_quest_error",
            character_id=character_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete quest: {str(e)}",
        )


# ==============================================================================
# Combat Management Endpoints
# ==============================================================================


class UpdateCombatRequest(BaseModel):
    """
    Request model for updating combat state.

    The combat_state field accepts a full CombatState object or null to clear combat.
    Server-side validation ensures ≤5 enemies and valid status enum values.
    """

    model_config = {"extra": "forbid"}

    combat_state: Optional[CombatState] = Field(
        description="Full combat state to set, or null to clear combat"
    )


class UpdateCombatResponse(BaseModel):
    """
    Response model for combat state updates.

    Returns the active/inactive status and the resulting combat state.
    """

    model_config = {"extra": "forbid"}

    active: bool = Field(
        description="Whether combat is currently active (any enemy not Dead)"
    )
    state: Optional[CombatState] = Field(
        description="Current combat state, or null if combat is cleared"
    )


@router.put(
    "/{character_id}/combat",
    response_model=UpdateCombatResponse,
    status_code=status.HTTP_200_OK,
    summary="Update combat state for a character",
    description=(
        "Set or clear the combat state for a character with full state replacement.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Required Headers:**\n"
        "- `X-User-Id`: User identifier (must match character owner for access control)\n\n"
        "**Request Body:**\n"
        "- `combat_state`: Full CombatState object or null to clear combat\n\n"
        "**CombatState Validation:**\n"
        "- Maximum 5 enemies per combat (422 error if exceeded)\n"
        "- All enemy statuses must be valid enum values (Healthy, Wounded, Dead)\n"
        "- All required fields must be present (combat_id, started_at, enemies)\n"
        "- Empty enemies list is allowed and sets active=false\n\n"
        "**Server-Side is_active Computation:**\n"
        "- active=true when any enemy has status != Dead\n"
        "- active=false when all enemies are Dead or enemies list is empty\n"
        "- active=false when combat_state is null\n\n"
        "**Atomicity:**\n"
        "Uses Firestore transaction to atomically:\n"
        "1. Verify character exists and user owns it\n"
        "2. Update combat_state field (or clear to null)\n"
        "3. Update character.updated_at timestamp\n"
        "4. Log when combat transitions from active to inactive\n\n"
        "**Response:**\n"
        '- Returns {"active": bool, "state": CombatState | null}\n'
        "- HTTP 200 for successful updates (both set and clear operations)\n\n"
        "**Error Responses:**\n"
        "- `400`: Missing or invalid X-User-Id header\n"
        "- `403`: X-User-Id does not match character owner\n"
        "- `404`: Character not found\n"
        "- `422`: Validation error (>5 enemies, invalid status, missing required fields)\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)\n\n"
        "**Edge Cases:**\n"
        "- Submitting >5 enemies returns 422 with detailed error\n"
        '- Submitting null clears combat and returns {"active": false, "state": null}\n'
        '- All enemies Dead returns {"active": false, "state": <combat_state>}\n'
        "- Race conditions: last writer wins without corrupting other fields\n"
        "- Unknown status strings cause explicit validation errors"
    ),
)
async def update_combat(
    character_id: str,
    request: UpdateCombatRequest,
    db: FirestoreClient,
    x_user_id: str = Header(..., description="User identifier for ownership"),
) -> UpdateCombatResponse:
    """
    Update or clear combat state for a character with atomic transaction.

    This endpoint:
    1. Validates character_id as UUID format
    2. Validates X-User-Id matches character owner
    3. Validates CombatState payload (≤5 enemies, valid status enum)
    4. Computes is_active flag server-side based on enemy statuses
    5. Uses Firestore transaction to atomically update combat_state and updated_at
    6. Logs when combat transitions from active to inactive
    7. Returns stable schema: {"active": bool, "state": CombatState | null}

    Args:
        character_id: UUID-formatted character identifier
        request: Combat state update request (combat_state or null)
        db: Firestore client (dependency injection)
        x_user_id: User ID from X-User-Id header

    Returns:
        UpdateCombatResponse with active flag and current combat state

    Raises:
        HTTPException:
            - 400: Invalid X-User-Id
            - 403: Access denied (user not owner)
            - 404: Character not found
            - 422: Validation error (>5 enemies, invalid status)
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "update_combat_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Validate X-User-Id
    if not x_user_id or not x_user_id.strip():
        logger.warning("update_combat_missing_user_id", character_id=character_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header is required and cannot be empty",
        )

    user_id = x_user_id.strip()

    # Compute is_active flag for the new combat state
    new_combat_state = request.combat_state
    is_active = False

    if new_combat_state is not None:
        # Use the is_active property from CombatState model
        is_active = new_combat_state.is_active

    # Log attempt
    logger.info(
        "update_combat_attempt",
        character_id=character_id,
        user_id=user_id,
        clearing_combat=new_combat_state is None,
        new_active_state=is_active,
    )

    try:
        # Create transaction
        transaction = db.transaction()
        characters_ref = db.collection(settings.firestore_characters_collection)

        @firestore.transactional
        def update_combat_in_transaction(transaction):
            """Atomically update combat state and log transitions."""
            # 1. Fetch character document to verify existence and ownership
            char_ref = characters_ref.document(character_id)
            char_snapshot = char_ref.get(transaction=transaction)

            if not char_snapshot.exists:
                return None, None, "not_found"

            # 2. Verify ownership
            char_data = char_snapshot.to_dict()
            owner_user_id = char_data.get("owner_user_id")

            if owner_user_id != user_id:
                return None, None, "access_denied"

            # 3. Get existing combat state to detect transitions
            existing_combat_data = char_data.get("combat_state")
            was_active = False

            if existing_combat_data is not None:
                try:
                    # Reuse the logic from the CombatState model to determine if it was active
                    existing_combat_state = CombatState(**existing_combat_data)
                    was_active = existing_combat_state.is_active
                except Exception:
                    # Fallback for potentially malformed data in DB, though unlikely.
                    # This preserves the original behavior in an edge case.
                    logger.warning(
                        "update_combat_malformed_existing_state",
                        character_id=character_id,
                        exc_info=True,
                    )
                    enemies = existing_combat_data.get("enemies", [])
                    was_active = any(enemy.get("status") != "Dead" for enemy in enemies)

            # 4. Detect transition from active to inactive for logging
            transition_to_inactive = was_active and not is_active

            # 5. Serialize new combat state for Firestore (or None to clear)
            combat_state_data = None
            if new_combat_state is not None:
                # Use mode='python' to get datetime objects (not JSON strings)
                combat_state_data = new_combat_state.model_dump(mode="python")

            # 6. Update character with new combat state and updated_at timestamp
            transaction.update(
                char_ref,
                {
                    "combat_state": combat_state_data,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                },
            )

            return combat_state_data, transition_to_inactive, "success"

        # Execute transaction
        combat_state_data, transition_to_inactive, result = (
            update_combat_in_transaction(transaction)
        )

        # Handle transaction results
        if result == "not_found":
            logger.warning(
                "update_combat_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )
        elif result == "access_denied":
            logger.warning(
                "update_combat_access_denied",
                character_id=character_id,
                requested_user_id=user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: user ID does not match character owner",
            )

        # Log transition from active to inactive if it occurred
        if transition_to_inactive:
            logger.info(
                "combat_transitioned_to_inactive",
                character_id=character_id,
                reason="all_enemies_dead_or_cleared",
            )

        logger.info(
            "update_combat_success",
            character_id=character_id,
            active=is_active,
            cleared=new_combat_state is None,
        )

        # Construct response using the validated request data
        return UpdateCombatResponse(
            active=is_active,
            state=request.combat_state,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "update_combat_error",
            character_id=character_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update combat state: {str(e)}",
        )


class GetCombatResponse(BaseModel):
    """
    Response model for combat state retrieval.

    Returns the active/inactive status and the current combat state.
    This is the standard envelope for LLM-driven Directors to poll combat state.
    """

    model_config = {"extra": "forbid"}

    active: bool = Field(
        description="Whether combat is currently active (any enemy not Dead)"
    )
    state: Optional[CombatState] = Field(
        description="Current combat state, or null if no combat is active"
    )


@router.get(
    "/{character_id}/combat",
    response_model=GetCombatResponse,
    status_code=status.HTTP_200_OK,
    summary="Get combat state for a character",
    description=(
        "Retrieve the current combat state for a character with a predictable JSON envelope.\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier (if provided, must match the character's owner_user_id)\n"
        "  - If header is provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n\n"
        "**Response:**\n"
        '- Always returns HTTP 200 with JSON object: {"active": bool, "state": CombatState | null}\n'
        "- `active=true, state=<CombatState>` when any enemy has status != Dead\n"
        "- `active=false, state=null` when combat_state is absent, empty, or all enemies are Dead\n"
        "- Never returns 204 No Content - always provides the active/state envelope\n\n"
        "**Combat Inactivity Detection:**\n"
        "Combat is considered inactive when:\n"
        "- combat_state field is None/missing in the character document\n"
        "- enemies list is empty\n"
        "- all enemies have status == Dead\n\n"
        "**Response Consistency:**\n"
        "- Uses the same CombatState serialization as PUT responses\n"
        "- Respects the ≤5 enemies constraint (defensive filtering on read)\n"
        "- All fields (is_active, traits, weapons) stay consistent with PUT responses\n\n"
        "**Error Responses:**\n"
        "- `400`: X-User-Id header provided but empty/whitespace-only\n"
        "- `403`: X-User-Id provided but does not match character owner\n"
        "- `404`: Character not found (NOT returned for 'no combat active' case)\n"
        "- `422`: Invalid UUID format for character_id\n"
        "- `500`: Internal server error (e.g., Firestore transient errors)\n\n"
        "**Edge Cases:**\n"
        "- Stored documents with >5 enemies (legacy data) trigger defensive filtering\n"
        "- Race conditions where combat cleared between read start/finish return inactive\n"
        "- Malformed stored data is handled gracefully with fallback to inactive\n"
        '- Characters with no combat history return {"active": false, "state": null}'
    ),
)
async def get_combat(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
) -> GetCombatResponse:
    """
    Retrieve the current combat state for a character.

    This endpoint provides an idempotent read operation that always returns a
    predictable JSON envelope describing combat status. LLM-driven Directors can
    use this to poll combat state without special handling for 204 responses.

    This endpoint:
    1. Validates character_id as UUID format
    2. Fetches the character document from Firestore
    3. Optionally verifies X-User-Id matches owner_user_id
    4. Detects combat inactivity based on combat_state field
    5. Returns {\"active\": bool, \"state\": CombatState | null} envelope

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control

    Returns:
        GetCombatResponse with active flag and combat state

    Raises:
        HTTPException:
            - 400: Empty X-User-Id header
            - 403: User ID mismatch (access denied)
            - 404: Character not found
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_combat_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Log retrieval attempt
    logger.info(
        "get_combat_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
    )

    try:
        # Fetch character document from Firestore
        characters_ref = db.collection(settings.firestore_characters_collection)
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(
                "get_combat_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # Verify ownership if X-User-Id is provided
        char_data = char_snapshot.to_dict()
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_combat_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )

            owner_user_id = char_data.get("owner_user_id")

            if stripped_user_id != owner_user_id:
                logger.warning(
                    "get_combat_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        # Get combat_state from character document
        combat_state_data = char_data.get("combat_state")

        # Detect inactivity - combat_state is None or missing
        if combat_state_data is None:
            logger.info(
                "get_combat_no_combat_state",
                character_id=character_id,
            )
            return GetCombatResponse(active=False, state=None)

        # Parse combat state and determine if active
        try:
            # Directly parse the combat_state data into the Pydantic model
            # This is more efficient than deserializing the entire character document
            combat_state = CombatState(**combat_state_data)

            # Use the is_active property from the CombatState model
            # Combat is active when any enemy has status != Dead
            is_active = combat_state.is_active

            logger.info(
                "get_combat_success",
                character_id=character_id,
                active=is_active,
                num_enemies=len(combat_state.enemies),
            )

            # When inactive (all enemies dead), return null state per acceptance criteria
            # When active, return the full combat state
            return GetCombatResponse(
                active=is_active, state=combat_state if is_active else None
            )

        except (ValueError, TypeError, KeyError) as e:
            # Defensive: if combat_state is malformed or has invalid data, treat as inactive
            # This handles cases where stored data doesn't match the expected schema
            # Note: ValidationError from Pydantic (>5 enemies) will be caught here as ValueError
            logger.warning(
                "get_combat_malformed_state",
                character_id=character_id,
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            return GetCombatResponse(active=False, state=None)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_combat_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve combat state due to an internal error",
        )


# ==============================================================================
# Context Aggregation Endpoint
# ==============================================================================


@router.get(
    "/{character_id}/context",
    response_model=CharacterContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated character context for Director/LLM integration",
    description=(
        "Retrieve a comprehensive context payload for AI-driven narrative generation.\n\n"
        "This endpoint aggregates:\n"
        "- Player state (identity, status, level, equipment, location)\n"
        "- Active quest with derived has_active_quest flag\n"
        "- Combat state with derived active flag\n"
        "- Recent narrative turns (configurable window, ordered oldest-to-newest)\n"
        "- Optional world POIs sample (can be suppressed via include_pois flag)\n\n"
        "**Path Parameters:**\n"
        "- `character_id`: UUID-formatted character identifier\n\n"
        "**Optional Headers:**\n"
        "- `X-User-Id`: User identifier for access control\n"
        "  - If provided but empty/whitespace-only, returns 400 error\n"
        "  - If omitted entirely, allows anonymous access without verification\n"
        "  - If provided, must match the character's owner_user_id\n\n"
        "**Optional Query Parameters:**\n"
        "- `recent_n` (integer): Number of recent narrative turns to include (default: 20, min: 1, max: configured limit)\n"
        "- `include_pois` (boolean): Whether to include POI sample in world state (default: true)\n\n"
        "**Response Structure:**\n"
        "```json\n"
        "{\n"
        '  "character_id": "uuid",\n'
        '  "player_state": { ... },\n'
        '  "quest": { ... } or null,\n'
        '  "combat": {\n'
        '    "active": true/false,\n'
        '    "state": { ... } or null\n'
        "  },\n"
        '  "narrative": {\n'
        '    "recent_turns": [ ... ],\n'
        '    "requested_n": 20,\n'
        '    "returned_n": 15,\n'
        '    "max_n": 100\n'
        "  },\n"
        '  "world": {\n'
        '    "pois_sample": [ ... ],\n'
        '    "include_pois": true\n'
        "  },\n"
        '  "has_active_quest": true/false\n'
        "}\n"
        "```\n\n"
        "**Derived Fields:**\n"
        "- `has_active_quest`: Computed as `quest is not None`\n"
        "- `combat.active`: Computed as `any enemy status != Dead`\n"
        "- `narrative.returned_n`: Actual number of turns returned (may be less than requested_n)\n"
        "- `narrative.max_n`: Server-configured maximum (informs clients of limits)\n\n"
        "**Performance Notes:**\n"
        "- Character document: Single Firestore read (embedded state)\n"
        "- Narrative turns: Subcollection query (indexed by timestamp)\n"
        "- POI sample: In-memory sampling from embedded world_pois array\n"
        "- Total latency typically <100ms for moderate datasets\n\n"
        "**Error Responses:**\n"
        "- `400 Bad Request`: Invalid query parameters (recent_n out of range) or empty X-User-Id\n"
        "- `403 Forbidden`: X-User-Id provided but does not match character owner\n"
        "- `404 Not Found`: Character not found\n"
        "- `422 Unprocessable Entity`: Invalid UUID format for character_id\n"
        "- `500 Internal Server Error`: Firestore transient errors\n\n"
        "**Edge Cases:**\n"
        "- Empty narrative history: Returns empty recent_turns array with returned_n=0\n"
        "- No active quest: Returns quest=null, has_active_quest=false\n"
        "- Inactive combat: Returns combat.active=false, combat.state=null\n"
        "- include_pois=false: Returns world.pois_sample=[], world.include_pois=false\n"
        "- recent_n exceeds available turns: Returns all available turns without error\n"
    ),
)
async def get_character_context(
    character_id: str,
    db: FirestoreClient,
    x_user_id: Optional[str] = Header(
        None, description="User identifier for access control"
    ),
    recent_n: int = Query(
        default=settings.context_recent_n_default,
        ge=1,
        le=settings.context_recent_n_max,
        description=f"Number of recent narrative turns to include (default: {settings.context_recent_n_default}, max: {settings.context_recent_n_max})",
    ),
    include_pois: bool = Query(
        default=True,
        description="Whether to include POI sample in world state (default: true)",
    ),
) -> CharacterContextResponse:
    """
    Retrieve aggregated character context for Director/LLM integration.

    This endpoint provides a single comprehensive payload containing all relevant
    character state for AI-driven narrative generation. It aggregates:
    - Player state (identity, status, equipment, location)
    - Active quest with derived has_active_quest flag
    - Combat state with derived active flag
    - Recent narrative turns with metadata (ordered oldest-to-newest)
    - Optional world POIs sample

    The response structure is designed to be consumed directly by LLM Directors
    without additional transformation.

    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control
        recent_n: Number of recent narrative turns to include (default: 20, max: configured)
        include_pois: Whether to include POI sample in response (default: true)

    Returns:
        CharacterContextResponse with aggregated context

    Raises:
        HTTPException:
            - 400: Invalid parameters (recent_n out of range) or empty X-User-Id
            - 403: User ID mismatch (access denied)
            - 404: Character not found
            - 422: Invalid UUID format
            - 500: Firestore error
    """
    # Validate and normalize UUID format
    try:
        character_id = str(uuid.UUID(character_id))
    except ValueError:
        logger.warning(
            "get_context_invalid_uuid",
            character_id=character_id,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid UUID format for character_id: {character_id}",
        )

    # Log retrieval attempt
    logger.info(
        "get_context_attempt",
        character_id=character_id,
        user_id=x_user_id if x_user_id else "anonymous",
        recent_n=recent_n,
        include_pois=include_pois,
    )

    try:
        # 1. Fetch character document
        characters_ref = db.collection(settings.firestore_characters_collection)
        char_ref = characters_ref.document(character_id)
        char_snapshot = char_ref.get()

        if not char_snapshot.exists:
            logger.warning(
                "get_context_character_not_found",
                character_id=character_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Character with ID '{character_id}' not found",
            )

        # 2. Verify ownership if X-User-Id is provided
        char_data = char_snapshot.to_dict()
        if x_user_id is not None:
            stripped_user_id = x_user_id.strip()
            # Empty/whitespace-only header is treated as a client error
            if not stripped_user_id:
                logger.warning(
                    "get_context_empty_user_id",
                    character_id=character_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="X-User-Id header cannot be empty",
                )

            owner_user_id = char_data.get("owner_user_id")

            if stripped_user_id != owner_user_id:
                logger.warning(
                    "get_context_user_mismatch",
                    character_id=character_id,
                    requested_user_id=stripped_user_id,
                    owner_user_id=owner_user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: user ID does not match character owner",
                )

        # 3. Deserialize character document
        character = character_from_firestore(char_data, character_id=character_id)

        # 4. Fetch recent narrative turns
        turns_collection = char_ref.collection("narrative_turns")
        query = turns_collection.order_by(
            "timestamp", direction=firestore.Query.DESCENDING
        ).limit(recent_n)

        turn_docs = list(query.stream())
        # Reverse to get oldest-to-newest order (chronological)
        turn_docs.reverse()

        recent_turns = []
        for doc in turn_docs:
            turn_data = doc.to_dict()
            turn = narrative_turn_from_firestore(turn_data, turn_id=doc.id)
            recent_turns.append(turn)

        # 5. Prepare combat state with derived active flag
        combat_state_data = char_data.get("combat_state")
        combat_active = False
        combat_state_obj = None

        if combat_state_data is not None:
            try:
                combat_state_obj = CombatState(**combat_state_data)
                combat_active = combat_state_obj.is_active
            except (ValueError, TypeError, KeyError) as e:
                # Defensive: malformed combat state, treat as inactive
                logger.warning(
                    "get_context_malformed_combat_state",
                    character_id=character_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                combat_state_obj = None
                combat_active = False

        # When combat is inactive, set state to None per acceptance criteria
        combat_context = CombatEnvelope(
            active=combat_active,
            state=combat_state_obj if combat_active else None,
        )

        # 6. Prepare world POI sample from subcollection
        pois_sample_list = []
        if include_pois:
            # Query POIs from subcollection (authoritative storage) directly
            pois_collection = char_ref.collection("pois")

            # Use offset-based random sampling for better performance
            # First, get a rough count (or use a limited query)
            sample_size = settings.context_poi_cap

            # Fetch POIs ordered by document ID for consistent results
            pois_query = pois_collection.order_by("__name__").limit(sample_size * 3)
            pois_docs = list(pois_query.stream())

            # Convert document snapshots to dict format
            pois_data = [doc.to_dict() for doc in pois_docs]

            # If subcollection is empty and fallback enabled, try embedded POIs
            if not pois_data and settings.poi_embedded_read_fallback:
                world_pois_data = char_data.get("world_pois", [])
                if world_pois_data:
                    logger.info(
                        "get_context_fallback_to_embedded_pois",
                        character_id=character_id,
                        embedded_count=len(world_pois_data),
                    )
                    # Convert embedded format to subcollection format for consistent handling
                    pois_data = []
                    for embedded_poi in world_pois_data:
                        if not embedded_poi.get("id"):
                            continue
                        created_at = embedded_poi.get("created_at")
                        if created_at:
                            created_at = datetime_from_firestore(created_at)
                        pois_data.append(
                            {
                                "poi_id": embedded_poi.get("id"),
                                "name": embedded_poi.get("name"),
                                "description": embedded_poi.get("description"),
                                "timestamp_discovered": created_at,
                                "tags": embedded_poi.get("tags"),
                            }
                        )

            # Sample POIs randomly using configured sample size
            actual_sample_size = min(sample_size, len(pois_data))
            if actual_sample_size > 0:
                sampled_data = random.sample(pois_data, actual_sample_size)
                for poi_data_item in sampled_data:
                    try:
                        # Handle both subcollection format and embedded format fields
                        poi_id = poi_data_item.get("poi_id") or poi_data_item.get("id")
                        timestamp_discovered = poi_data_item.get(
                            "timestamp_discovered"
                        ) or poi_data_item.get("created_at")
                        if timestamp_discovered is not None:
                            timestamp_discovered = datetime_from_firestore(
                                timestamp_discovered
                            )

                        poi = PointOfInterest(
                            id=poi_id,
                            name=poi_data_item["name"],
                            description=poi_data_item["description"],
                            created_at=timestamp_discovered,
                            tags=poi_data_item.get("tags"),
                        )
                        pois_sample_list.append(poi)
                    except (KeyError, ValueError, TypeError) as e:
                        # Skip malformed POI data and log warning
                        logger.warning(
                            "get_context_malformed_poi",
                            character_id=character_id,
                            poi_id=poi_data_item.get("poi_id")
                            or poi_data_item.get("id", "unknown"),
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )

        world_context = WorldContextState(
            pois_sample=pois_sample_list,
            pois_cap=settings.context_poi_cap,
            include_pois=include_pois,
        )

        # 7. Prepare narrative context
        narrative_context = NarrativeContext(
            turns=recent_turns,
            requested_n=recent_n,
            max_n=settings.context_recent_n_max,
        )

        # 8. Prepare context metadata
        context_metadata = ContextCapsMetadata(
            narrative_max_n=settings.context_recent_n_max,
            narrative_requested_n=recent_n,
            pois_cap=settings.context_poi_cap,
            pois_requested=include_pois,
        )

        # 9. Build context response
        context_response = CharacterContextResponse(
            character_id=character.character_id,
            player_state=character.player_state,
            quest=character.active_quest,
            has_active_quest=character.active_quest is not None,
            combat=combat_context,
            narrative=narrative_context,
            world=world_context,
            metadata=context_metadata,
        )

        logger.info(
            "get_context_success",
            character_id=character_id,
            returned_turns=len(recent_turns),
            has_quest=character.active_quest is not None,
            combat_active=combat_active,
            pois_included=len(pois_sample_list),
        )

        return context_response

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and convert to 500 error
        logger.error(
            "get_context_error",
            character_id=character_id,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve character context due to an internal error",
        )
