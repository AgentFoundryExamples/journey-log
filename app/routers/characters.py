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
    PlayerState,
    Status,
    character_to_firestore,
    character_from_firestore,
    datetime_from_firestore,
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
