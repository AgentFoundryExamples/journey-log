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
from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import (
    get_settings,
    DEFAULT_CHARACTER_STATUS,
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
        # Check for duplicate (user_id, name, race, class) tuple
        characters_ref = db.collection(settings.firestore_characters_collection)
        
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
        
        existing = query.get()
        if existing:
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
        
        # Generate character ID (lowercase UUIDv4)
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
        now = datetime.now(timezone.utc)
        character = CharacterDocument(
            character_id=character_id,
            owner_user_id=user_id,
            adventure_prompt=request.adventure_prompt,
            player_state=player_state,
            world_pois_reference=f"characters/{character_id}/pois",
            narrative_turns_reference=f"characters/{character_id}/narrative_turns",
            schema_version="1.0.0",
            created_at=now,
            updated_at=now,
            world_state=None,
            active_quest=None,
            combat_state=None,
            additional_metadata={},
        )
        
        # Serialize to Firestore format
        character_data = character_to_firestore(character, use_server_timestamp=False)
        
        # Use Firestore server timestamp for consistency
        character_data["created_at"] = firestore.SERVER_TIMESTAMP
        character_data["updated_at"] = firestore.SERVER_TIMESTAMP
        
        # Persist to Firestore
        doc_ref = characters_ref.document(character_id)
        doc_ref.set(character_data)
        
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
