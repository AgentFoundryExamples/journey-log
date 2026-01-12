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

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, status
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
    Health,
    Location,
    NarrativeTurn,
    PlayerState,
    Status,
    character_to_firestore,
    character_from_firestore,
    datetime_from_firestore,
    datetime_to_firestore,
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
        min_length=1,
        max_length=64,
        description="Character name (1-64 characters)"
    )
    race: str = Field(
        min_length=1,
        max_length=64,
        description="Character race (1-64 characters)"
    )
    character_class: str = Field(
        min_length=1,
        max_length=64,
        alias="class",
        description="Character class (1-64 characters)"
    )
    adventure_prompt: str = Field(
        min_length=1,
        description="Initial adventure prompt or backstory"
    )
    location_id: Optional[str] = Field(
        default=None,
        description="Optional location ID override (default: origin:nexus)"
    )
    location_display_name: Optional[str] = Field(
        default=None,
        description="Display name for location override"
    )
    
    @model_validator(mode='after')
    def validate_location_override(self) -> 'CreateCharacterRequest':
        """Validate that if one location field is provided, both must be provided."""
        location_id = self.location_id
        location_display_name = self.location_display_name
        
        # Both must be provided or both must be None
        if (location_id is None) != (location_display_name is None):
            if location_id is not None:
                raise ValueError("location_display_name is required when location_id is provided")
            else:
                raise ValueError("location_id is required when location_display_name is provided")
        
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
        alias="class",
        serialization_alias="class",
        description="Character class"
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
        "- `level`: 1\n"
        "- `experience`: 0\n"
        "- `health`: {current: 100, max: 100}\n"
        "- `stats`: Empty dictionary\n"
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
                characters_ref
                .where("owner_user_id", "==", user_id)
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
            name=request.name,
            race=request.race,
            **{"class": request.character_class}
        )
        
        # Create player state with defaults
        player_state = PlayerState(
            identity=identity,
            status=Status.HEALTHY,
            level=1,
            experience=0,
            health=Health(current=100, max=100),
            stats={},
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
    x_user_id: Optional[str] = Header(None, description="User identifier for access control"),
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
        description="Player's action or input (max 8000 characters)"
    )
    ai_response: str = Field(
        min_length=1,
        max_length=32000,
        description="Game master's/AI's response (max 32000 characters)"
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="Optional ISO 8601 timestamp. Defaults to server UTC now if omitted."
    )
    
    @model_validator(mode='after')
    def validate_combined_length(self) -> 'AppendNarrativeRequest':
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
    total_turns: int = Field(description="Total number of narrative turns for this character")


class NarrativeMetadata(BaseModel):
    """Metadata for narrative retrieval response."""
    model_config = {"extra": "forbid"}
    
    requested_n: int = Field(description="Number of turns requested (n parameter)")
    returned_count: int = Field(description="Number of turns actually returned")
    total_available: int = Field(description="Total number of turns available for this character")


class GetNarrativeResponse(BaseModel):
    """Response model for GET narrative endpoint."""
    turns: list[NarrativeTurn] = Field(description="List of narrative turns ordered oldest-to-newest")
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
                "timestamp": turn_timestamp if turn_timestamp else firestore.SERVER_TIMESTAMP,
            }
            
            # 4. Write turn to subcollection
            turn_ref = char_ref.collection("narrative_turns").document(turn_id)
            transaction.set(turn_ref, turn_data)
            
            # 5. Update character.updated_at
            transaction.update(char_ref, {
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
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
        "- `since`: ISO 8601 timestamp to filter turns after this time (optional)\n\n"
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
    x_user_id: Optional[str] = Header(None, description="User identifier for access control"),
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
    5. Queries Firestore for narrative turns with filtering
    6. Returns turns in oldest-to-newest order with metadata
    
    Args:
        character_id: UUID-formatted character identifier
        db: Firestore client (dependency injection)
        x_user_id: Optional user ID from X-User-Id header for access control
        n: Number of turns to retrieve (default 10, max 100)
        since: Optional ISO 8601 timestamp to filter turns after this time
        
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
        query = turns_collection.order_by("timestamp", direction=firestore.Query.DESCENDING)
        
        # Apply since filter if provided
        if since_dt:
            query = query.where("timestamp", ">=", since_dt)
        
        # Apply limit
        query = query.limit(n)
        
        # Execute query
        turn_docs = list(query.stream())
        
        # Reverse to get oldest-to-newest order (chronological reading order)
        turn_docs.reverse()
        
        # Convert to NarrativeTurn models
        from app.models import narrative_turn_from_firestore
        turns = []
        for doc in turn_docs:
            turn_data = doc.to_dict()
            turn_data["turn_id"] = doc.id  # Ensure turn_id is present
            turn = narrative_turn_from_firestore(turn_data, turn_id=doc.id)
            turns.append(turn)
        
        # 4. Get total count (expensive, but needed for metadata)
        # Count all turns matching the since filter if provided
        if since_dt:
            count_query = turns_collection.where("timestamp", ">=", since_dt).count()
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
