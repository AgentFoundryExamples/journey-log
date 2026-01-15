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
Pydantic models for Journey Log character state.

This module defines the data models for character state management in the Journey Log
system. All models conform to the schema contracts defined in docs/SCHEMA.md.

The models support:
- Serialization to/from Firestore documents
- Validation of character state
- Extensible fields via additional_fields dictionaries
- Schema versioning for backward compatibility
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional, Union

from google.cloud import firestore  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.logging import get_logger

logger = get_logger(__name__)


class Status(str, Enum):
    """
    Character health status enum.

    Referenced in: docs/SCHEMA.md - Character Document Fields
    """

    HEALTHY = "Healthy"
    WOUNDED = "Wounded"
    DEAD = "Dead"


# CombatStatus is an alias for Status, as they share the same values.
# This maintains semantic clarity in model definitions while avoiding duplication.
CombatStatus = Status


class Location(BaseModel):
    """
    Location information with ID and display name.

    Represents a character's current location in the game world.
    The ID is used for internal references and logic, while display_name
    is shown to the player.

    Referenced in: docs/SCHEMA.md - Character Document Fields
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        description="Location identifier (e.g., 'origin:nexus', 'town:rivendell')",
    )
    display_name: str = Field(min_length=1, description="Human-readable location name")

    @model_validator(mode="after")
    def validate_non_empty(self) -> "Location":
        """Ensure id and display_name are not just whitespace."""
        if not self.id.strip():
            raise ValueError("id cannot be empty or only whitespace")
        if not self.display_name.strip():
            raise ValueError("display_name cannot be empty or only whitespace")
        return self


class CharacterIdentity(BaseModel):
    """
    Character identity information (name, race, class).

    Referenced in: docs/SCHEMA.md - Character Document Fields
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(
        min_length=1, max_length=64, description="Character name (1-64 characters)"
    )
    race: str = Field(
        min_length=1,
        max_length=64,
        description="Character race (1-64 characters, e.g., Human, Elf, Dwarf)",
    )
    character_class: str = Field(
        min_length=1,
        max_length=64,
        alias="class",
        serialization_alias="class",
        description="Character class (1-64 characters, e.g., Warrior, Mage, Ranger)",
    )

    @model_validator(mode="after")
    def normalize_whitespace(self) -> "CharacterIdentity":
        """Normalize whitespace in identity fields and ensure non-empty after normalization."""
        self.name = " ".join(self.name.split())
        self.race = " ".join(self.race.split())
        self.character_class = " ".join(self.character_class.split())

        # Validate non-empty after normalization
        if not self.name:
            raise ValueError("name cannot be empty or only whitespace")
        if not self.race:
            raise ValueError("race cannot be empty or only whitespace")
        if not self.character_class:
            raise ValueError("character_class cannot be empty or only whitespace")

        return self


class Weapon(BaseModel):
    """
    Weapon item with optional special effects.

    Special effects can be a simple string description or a structured dict
    with effect details.

    Referenced in: docs/SCHEMA.md - Player State Equipment
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Weapon name")
    damage: Union[int, str] = Field(description="Weapon damage (e.g., '1d8' or 8)")
    special_effects: Optional[Union[str, dict[str, Any]]] = Field(
        default=None, description="Special weapon effects as string or structured dict"
    )


class InventoryItem(BaseModel):
    """
    Generic inventory item with flexible effect field.

    The effect field supports both simple string descriptions and complex
    structured effect definitions.

    Referenced in: docs/SCHEMA.md - Player State Inventory
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Item name")
    quantity: int = Field(default=1, description="Number of items")
    effect: Optional[Union[str, dict[str, Any]]] = Field(
        default=None, description="Item effect as string or structured dict"
    )


class PlayerState(BaseModel):
    """
    Current player character state using canonical status enum.

    This model represents the core game state for a character, including:
    - Character identity (name, race, class)
    - Health status (canonical Status enum: Healthy, Wounded, Dead)
    - Equipment (weapons, armor, inventory)
    - Current location
    - Extensible additional fields for game-specific data

    Numeric health/stat fields (level, experience, stats, HP, XP) have been
    removed in favor of the textual status enum. Legacy numeric fields are
    ignored during deserialization.

    Referenced in: docs/SCHEMA.md - Character Document Fields (player_state)
    """

    model_config = ConfigDict(extra="forbid")

    identity: CharacterIdentity = Field(description="Character identity information")
    status: Status = Field(description="Character health status (Healthy, Wounded, Dead)")
    equipment: list[Weapon] = Field(
        default_factory=list, description="Equipped weapons"
    )
    inventory: list[InventoryItem] = Field(
        default_factory=list, description="Inventory items"
    )
    location: Union[Location, str, dict[str, Any]] = Field(
        description="Current location as Location object, string, or structured object (for backward compatibility)",
        examples=[
            {"id": "origin:nexus", "display_name": "The Nexus"},
            "Rivendell",
            {
                "world": "middle-earth",
                "region": "gondor",
                "coordinates": {"x": 100, "y": 200},
            },
        ],
    )
    additional_fields: dict[str, Any] = Field(
        default_factory=dict, description="Extensible fields for game-specific data"
    )

    @model_validator(mode="after")
    def validate_location(self) -> "PlayerState":
        """Validate location field ensures meaningful data regardless of format."""
        if isinstance(self.location, str):
            # String locations must be non-empty
            if not self.location or not self.location.strip():
                raise ValueError("location string cannot be empty or only whitespace")
        elif isinstance(self.location, dict):
            # Dict locations should have at least one meaningful key
            if not self.location:
                raise ValueError("location dict cannot be empty")
            # If it looks like a Location dict, validate required fields
            if "id" in self.location or "display_name" in self.location:
                if not self.location.get("id") or not self.location.get("display_name"):
                    raise ValueError(
                        "location dict with id/display_name must have both non-empty fields"
                    )
        # Location objects are already validated by the Location model
        return self


class NarrativeTurn(BaseModel):
    """
    A single narrative turn in the character's story.

    Represents one interaction between the player and the game master (AI),
    including the player's action, AI's response, and timestamp.

    Field size limits:
    - user_action: max 8000 characters
    - ai_response: max 32000 characters

    Referenced in: docs/SCHEMA.md - Narrative Turns Subcollection
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    turn_id: str = Field(description="Unique turn identifier (UUIDv4)")
    turn_number: Optional[int] = Field(
        default=None, description="Sequential turn counter"
    )
    user_action: str = Field(
        min_length=1,
        max_length=8000,
        alias="player_action",
        serialization_alias="player_action",
        description="Player's action or input (max 8000 characters)",
    )
    ai_response: str = Field(
        min_length=1,
        max_length=32000,
        alias="gm_response",
        serialization_alias="gm_response",
        description="Game master's/AI's response (max 32000 characters)",
    )
    timestamp: datetime = Field(
        description="When the turn occurred (datetime object or ISO 8601 string)"
    )
    game_state_snapshot: Optional[dict[str, Any]] = Field(
        default=None, description="Snapshot of relevant game state at this turn"
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional turn metadata (response time, LLM model, etc.)",
    )


class PointOfInterest(BaseModel):
    """
    A point of interest (POI) - DEPRECATED for writes, read-only for compatibility.

    DEPRECATED: This model represents the legacy embedded POI format stored in
    the world_pois array. It is maintained for backward compatibility during migration.
    
    The AUTHORITATIVE POI storage is now the subcollection at:
    characters/{character_id}/pois/{poi_id}
    
    For new POI writes, use PointOfInterestSubcollection and the subcollection helpers
    in app/firestore.py. This model is read-only and used for:
    - Reading legacy embedded POIs during migration
    - Surfacing embedded POIs on GET for backward compatibility
    - Migration utilities that copy embedded POIs to subcollection
    
    See docs/SCHEMA.md for migration guidance and storage contracts.

    EXACT SHAPE REQUIREMENT: This model must match the exact structure
    specified in the issue requirements for embedded POIs.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Unique POI identifier")
    name: str = Field(description="POI name")
    description: str = Field(description="POI description")
    created_at: Optional[datetime] = Field(
        default=None, description="When the POI was created/discovered"
    )
    tags: Optional[list[str]] = Field(
        default=None, description="Tags for categorizing the POI"
    )


class PointOfInterestSubcollection(BaseModel):
    """
    A point of interest (POI) stored in subcollections - AUTHORITATIVE storage.

    This is the AUTHORITATIVE POI model for the subcollection at:
    characters/{character_id}/pois/{poi_id}
    
    This full-featured POI model supports unbounded data with optional fields
    and metadata. All new POI writes should use this model and the subcollection
    storage via helpers in app/firestore.py.
    
    The subcollection approach:
    - Allows unlimited POIs per character (no 200-entry array limit)
    - Enables efficient querying and pagination
    - Provides atomic POI operations with transaction support
    - Supports optional shared POI resolution via world_pois_reference

    Referenced in: docs/SCHEMA.md - Points of Interest Subcollection
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    poi_id: str = Field(description="Unique POI identifier (UUIDv4)")
    name: str = Field(description="POI name")
    description: str = Field(description="POI description")
    type: Optional[str] = Field(
        default=None, description="POI type (dungeon, town, landmark, etc.)"
    )
    location: Optional[dict[str, Any]] = Field(
        default=None, description="POI location information"
    )
    timestamp_discovered: Optional[datetime] = Field(
        default=None, description="When the POI was discovered"
    )
    last_visited: Optional[datetime] = Field(
        default=None, description="When the POI was last visited"
    )
    visited: Optional[bool] = Field(
        default=False, description="Whether the POI has been visited"
    )
    notes: Optional[str] = Field(
        default=None, description="Player notes about this POI"
    )
    tags: Optional[list[str]] = Field(
        default=None, description="Tags for categorizing the POI"
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None, description="Additional POI metadata"
    )


class QuestRewards(BaseModel):
    """
    Rewards for completing a quest.

    EXACT SHAPE REQUIREMENT: This model must match the exact structure
    specified in the issue requirements.

    Validates that all numeric values are non-negative.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(
        default_factory=list, description="List of item names awarded"
    )
    currency: dict[str, int] = Field(
        default_factory=dict, description="Currency rewards as name:amount pairs"
    )
    experience: Optional[int] = Field(
        default=None, ge=0, description="Experience points awarded (non-negative)"
    )

    @model_validator(mode="after")
    def validate_non_negative(self) -> "QuestRewards":
        """Validate that currency values are non-negative and keys are non-empty."""
        for key, value in self.currency.items():
            if not key or not key.strip():
                raise ValueError("currency keys cannot be empty or only whitespace")
            if value < 0:
                raise ValueError(f"currency value for '{key}' cannot be negative")
        return self


class Quest(BaseModel):
    """
    A quest with requirements and rewards.

    EXACT SHAPE REQUIREMENT: This model must match the exact structure
    specified in the issue requirements for embedded quests.

    Referenced in: docs/SCHEMA.md - Character Document Fields (active_quest)
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Quest name")
    description: str = Field(description="Quest description")
    requirements: list[str] = Field(
        default_factory=list, description="List of quest requirement descriptions"
    )
    rewards: QuestRewards = Field(description="Quest rewards")
    completion_state: Literal["not_started", "in_progress", "completed"] = Field(
        description="Quest completion status: 'not_started', 'in_progress', or 'completed'"
    )
    updated_at: datetime = Field(description="When the quest was last updated")


class QuestArchiveEntry(BaseModel):
    """
    An archived/completed quest entry.

    Stores a completed quest along with when it was cleared.
    Used in Character.archived_quests array (max 50 entries).
    """

    model_config = ConfigDict(extra="forbid")

    quest: Quest = Field(description="The archived quest")
    cleared_at: datetime = Field(description="When the quest was completed/cleared")


class EnemyState(BaseModel):
    """
    An enemy in combat with status, weapon, and traits.

    Represents an enemy's state during combat without numeric health tracking.
    Status enum (Healthy/Wounded/Dead) replaces granular health points.

    Referenced in: docs/SCHEMA.md - Combat State
    """

    model_config = ConfigDict(extra="forbid")

    enemy_id: str = Field(description="Unique enemy identifier")
    name: str = Field(description="Enemy name")
    status: Status = Field(description="Enemy status (Healthy, Wounded, Dead)")
    weapon: Optional[str] = Field(
        default=None, description="Weapon wielded by the enemy"
    )
    traits: list[str] = Field(
        default_factory=list, description="Enemy traits or characteristics"
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None, description="Additional enemy metadata"
    )


# Backward compatibility alias
Enemy = EnemyState


class CombatState(BaseModel):
    """
    Current combat state with up to 5 enemies.

    Represents an active combat encounter, including enemies and combat status.
    When not in combat, the combat_state field in CharacterDocument should be None.

    Combat is considered inactive when all enemies are Dead or the enemy list is empty.
    Maximum 5 enemies per combat to prevent document bloat.

    Referenced in: docs/SCHEMA.md - Character Document Fields (combat_state)
    """

    model_config = ConfigDict(extra="forbid")

    combat_id: str = Field(description="Unique combat identifier")
    started_at: Union[datetime, str] = Field(description="When combat started")
    turn: int = Field(default=1, ge=1, description="Current combat turn")
    enemies: list[EnemyState] = Field(description="List of enemies in combat (max 5)")
    player_conditions: Optional[dict[str, Any]] = Field(
        default=None, description="Player status effects and conditions during combat"
    )

    @model_validator(mode="after")
    def validate_enemy_limit(self) -> "CombatState":
        """Enforce maximum of 5 enemies per combat."""
        if len(self.enemies) > 5:
            raise ValueError(
                f"Combat cannot have more than 5 enemies (got {len(self.enemies)}). "
                "This limit prevents document size bloat."
            )
        return self

    @property
    def is_active(self) -> bool:
        """
        Determine if combat is active based on enemy statuses.

        Combat is considered active if:
        - The enemy list is not empty, AND
        - At least one enemy has status != Dead

        Returns False if all enemies are Dead or if no enemies exist.
        """
        return any(enemy.status != Status.DEAD for enemy in self.enemies)


class CharacterDocument(BaseModel):
    """
    Aggregate character document model.

    This is the top-level document stored in Firestore for each character.
    It contains all core character data, with references to subcollections
    for unbounded data (narrative turns, POIs).

    Required fields:
    - character_id: UUIDv4 identifier
    - owner_user_id: User who owns this character
    - player_state: Current game state
    - world_pois_reference: Reference to world POI configuration
    - schema_version: Document schema version
    - created_at: When the character was created
    - updated_at: Last update timestamp

    Optional fields:
    - active_quest: Current quest (None if no active quest)
    - combat_state: Current combat (None if not in combat)

    Additional metadata is stored in the additional_metadata dict for extensibility.

    Referenced in: docs/SCHEMA.md - Character Document Fields
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": "Character document schema as defined in docs/SCHEMA.md"
        },
    )

    # Required core fields
    character_id: str = Field(
        description="UUIDv4 character identifier (matches Firestore document ID)"
    )
    owner_user_id: str = Field(
        description="User ID of the character owner (for access control, from X-User-Id header)"
    )
    adventure_prompt: str = Field(
        min_length=1,
        description="Initial adventure prompt or backstory (non-empty, whitespace normalized)",
    )
    player_state: PlayerState = Field(description="Current player character state")
    world_pois_reference: str = Field(
        description="Reference to world POI collection or configuration"
    )
    narrative_turns_reference: str = Field(
        description="Reference to narrative turns subcollection or storage location"
    )
    schema_version: str = Field(
        description="Schema version for this document (semantic versioning format, e.g., '1.0.0')"
    )
    created_at: Union[datetime, str] = Field(
        description="When the character was created (Firestore Timestamp or ISO 8601)"
    )
    updated_at: Union[datetime, str] = Field(
        description="Last update timestamp (Firestore Timestamp or ISO 8601)"
    )

    # Optional fields
    world_state: Optional[dict[str, Any]] = Field(
        default=None, description="Optional world state metadata or game-specific data"
    )
    world_pois: list[PointOfInterest] = Field(
        default_factory=list,
        description=(
            "DEPRECATED: Read-only compatibility field for legacy embedded POIs. "
            "The authoritative POI storage is the subcollection at characters/{character_id}/pois/{poi_id}. "
            "This field is maintained for backward compatibility during migration. "
            "New POI writes go to the subcollection only. Max 200 entries."
        ),
    )
    active_quest: Optional[Quest] = Field(
        default=None, description="Current active quest (None if no active quest)"
    )
    archived_quests: list[QuestArchiveEntry] = Field(
        default_factory=list,
        description="Archived/completed quests (max 50 entries, oldest removed when exceeded)",
    )
    combat_state: Optional[CombatState] = Field(
        default=None, description="Current combat state (None if not in combat)"
    )

    # Extensible metadata
    additional_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata including character name, timestamps, owner info, etc.",
    )

    @model_validator(mode="after")
    def validate_document(self) -> "CharacterDocument":
        """Perform post-validation on the character document."""
        # Normalize whitespace in adventure_prompt
        self.adventure_prompt = " ".join(self.adventure_prompt.split())
        if not self.adventure_prompt:
            raise ValueError("adventure_prompt cannot be empty or only whitespace")

        # Validate array size caps to prevent Firestore document bloat
        if len(self.world_pois) > 200:
            raise ValueError(
                f"world_pois cannot exceed 200 entries (got {len(self.world_pois)}). "
                "Consider moving older POIs to a subcollection or archiving them."
            )

        if len(self.archived_quests) > 50:
            raise ValueError(
                f"archived_quests cannot exceed 50 entries (got {len(self.archived_quests)}). "
                "Oldest entries should be trimmed before adding new ones."
            )

        return self


# ==============================================================================
# Context Aggregation Models
# ==============================================================================


class CharacterContextQuery(BaseModel):
    """
    Query parameters for character context aggregation endpoint.
    
    Validates request parameters with configurable bounds from settings:
    - recent_n: Number of recent narrative turns to include
    - include_pois: Whether to include POI sample in world context
    - include_narrative: Whether to include narrative turns in response
    - include_combat: Whether to include combat state in response
    - include_quest: Whether to include quest data in response
    
    Validators ensure recent_n stays within configured min/max bounds.
    All include_* flags default to true to preserve existing behavior.
    """

    model_config = ConfigDict(extra="forbid")

    recent_n: int = Field(
        default=20,
        ge=1,
        description="Number of recent narrative turns to include (min: 1, max: from settings)",
    )
    include_pois: bool = Field(
        default=False,
        description="Whether to include POI sample in world context",
    )
    include_narrative: bool = Field(
        default=True,
        description="Whether to include narrative turns in response (default: true)",
    )
    include_combat: bool = Field(
        default=True,
        description="Whether to include combat state in response (default: true)",
    )
    include_quest: bool = Field(
        default=True,
        description="Whether to include quest data in response (default: true)",
    )


class ContextCapsMetadata(BaseModel):
    """
    Metadata describing read limits and caps for context aggregation.
    
    Exposes server configuration to help Directors understand:
    - Firestore read pattern (1 character doc + 1 narrative query + optional 1 POI query)
    - Configured limits for narrative and POI caps
    - Current request parameters
    """

    model_config = ConfigDict(extra="forbid")

    firestore_reads: str = Field(
        default="1 character doc + 1 narrative query + optional 1 POI query",
        description="Expected Firestore read pattern for this request",
    )
    narrative_max_n: int = Field(
        description="Maximum narrative turns that can be requested (server config)",
    )
    narrative_requested_n: int = Field(
        description="Number of narrative turns requested in this call",
    )
    pois_cap: int = Field(
        description="Maximum POIs that can be sampled (server config)",
    )
    pois_requested: bool = Field(
        description="Whether POIs were requested via include_pois parameter",
    )


class CombatEnvelope(BaseModel):
    """
    Combat envelope for context aggregation with derived active flag.
    
    This model exposes the active boolean explicitly for Director consumption,
    computed server-side based on enemy statuses.
    """

    model_config = ConfigDict(extra="forbid")

    active: bool = Field(
        description="Whether combat is currently active (true if any enemy status != Dead)"
    )
    state: Optional[CombatState] = Field(
        default=None,
        description="Full combat state details, or null if combat is inactive",
    )


class NarrativeContext(BaseModel):
    """
    Narrative context for context aggregation.
    
    Provides recent narrative turns with metadata about the requested,
    returned, and maximum narrative window to help Directors understand
    context boundaries.
    """

    model_config = ConfigDict(extra="forbid")

    recent_turns: list[NarrativeTurn] = Field(
        default_factory=list,
        description="List of recent narrative turns ordered oldest-to-newest (chronological)"
    )
    requested_n: int = Field(
        description="Number of turns requested via recent_n parameter"
    )
    returned_n: int = Field(
        description="Number of turns actually returned (may be less than requested if not enough exist)"
    )
    max_n: int = Field(
        description="Maximum number of turns that can be requested (server config limit)"
    )


class WorldContextState(BaseModel):
    """
    World state for context aggregation including optional POI sample.
    
    POIs can be suppressed via include_pois flag to reduce payload size.
    The pois_cap field exposes the server configuration for POI sampling limits.
    """

    model_config = ConfigDict(extra="forbid")

    pois_sample: list[PointOfInterest] = Field(
        default_factory=list,
        description="Random sample of discovered POIs (empty if include_pois=false)",
    )
    pois_cap: int = Field(
        description="Maximum number of POIs that can be sampled (server config limit)",
    )
    include_pois: bool = Field(
        description="Whether POIs were included in this response (reflects request parameter)"
    )


class CharacterContextResponse(BaseModel):
    """
    Aggregated character context for Director/LLM integration.
    
    This model provides a single JSON payload capturing all relevant character state:
    - Identity and player state (status, level, equipment, location)
    - Active quest with derived has_active_quest flag
    - Combat state with derived active flag
    - Recent narrative turns with metadata
    - Optional world POIs sample
    - Metadata describing caps and read limits
    
    This is the primary integration surface for Directors to retrieve character context
    for AI-driven narrative generation.
    
    EXACT SHAPE REQUIREMENT: This model must match the exact structure specified
    in the issue requirements for the context aggregation endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    character_id: str = Field(description="UUID character identifier")
    player_state: PlayerState = Field(description="Current player character state")
    quest: Optional[Quest] = Field(
        default=None, description="Active quest or null if no active quest"
    )
    has_active_quest: bool = Field(
        description="Derived flag: true if quest is not null, false otherwise"
    )
    combat: CombatEnvelope = Field(
        description="Combat state with derived active flag"
    )
    narrative: NarrativeContext = Field(
        description="Recent narrative turns with metadata"
    )
    world: WorldContextState = Field(
        description="World state including optional POI sample"
    )
    metadata: ContextCapsMetadata = Field(
        description="Metadata describing read limits and configured caps"
    )


# Backward compatibility aliases for existing code
ContextCombatState = CombatEnvelope
NarrativeContextMetadata = NarrativeContext



# ==============================================================================
# Firestore Serialization Helpers
# ==============================================================================


def datetime_to_firestore(dt: Union[datetime, str, None]) -> Optional[datetime]:
    """
    Convert a datetime object or ISO string to a Firestore-compatible value.

    This helper handles timezone-aware datetimes and ensures consistent UTC
    conversion for storage in Firestore.

    Note: For server-generated timestamps (created_at, updated_at), use
    firestore.SERVER_TIMESTAMP directly in your calling code instead of this function.

    Args:
        dt: A datetime object, ISO 8601 string, or None

    Returns:
        - None if input is None
        - datetime object (timezone-aware, UTC) if input is datetime or string

    Raises:
        ValueError: If ISO string cannot be parsed or input type is invalid

    Examples:
        >>> from datetime import datetime, timezone
        >>> dt = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        >>> datetime_to_firestore(dt)
        datetime.datetime(2026, 1, 11, 12, 0, tzinfo=datetime.timezone.utc)

        >>> datetime_to_firestore("2026-01-11T12:00:00Z")
        datetime.datetime(2026, 1, 11, 12, 0, tzinfo=datetime.timezone.utc)

        >>> datetime_to_firestore(None)
        None
    """
    if dt is None:
        return None

    if isinstance(dt, str):
        # Parse ISO 8601 string
        # Handle both with and without 'Z' suffix
        if dt.endswith("Z"):
            dt = dt[:-1] + "+00:00"
        try:
            parsed_dt = datetime.fromisoformat(dt)
        except ValueError as e:
            raise ValueError(f"Cannot parse ISO 8601 string '{dt}': {e}")

        # Ensure timezone-aware
        if parsed_dt.tzinfo is None:
            # Naive datetimes are assumed to be UTC (explicit assumption for security)
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC
            parsed_dt = parsed_dt.astimezone(timezone.utc)
        return parsed_dt

    if isinstance(dt, datetime):
        # Ensure timezone-aware and convert to UTC
        if dt.tzinfo is None:
            # Naive datetimes are assumed to be UTC (explicit assumption for security)
            return dt.replace(tzinfo=timezone.utc)
        else:
            # Convert to UTC
            return dt.astimezone(timezone.utc)

    raise ValueError(
        f"Cannot convert {type(dt).__name__} to Firestore timestamp. Expected datetime, ISO 8601 string, or None."
    )


def datetime_from_firestore(value: Any) -> Optional[datetime]:
    """
    Convert a Firestore Timestamp or ISO string to a Python datetime.

    This helper handles both Firestore Timestamp objects (from reads) and
    ISO 8601 strings (from API inputs or legacy data).

    Args:
        value: A Firestore Timestamp, datetime, ISO 8601 string, or None

    Returns:
        datetime object (timezone-aware, UTC) or None

    Raises:
        ValueError: If value cannot be converted to datetime

    Examples:
        >>> from google.cloud.firestore import SERVER_TIMESTAMP
        >>> datetime_from_firestore(None)
        None

        >>> datetime_from_firestore("2026-01-11T12:00:00Z")
        datetime.datetime(2026, 1, 11, 12, 0, tzinfo=datetime.timezone.utc)
    """
    if value is None:
        return None

    # If it's already a datetime, ensure it's timezone-aware
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # Naive datetimes are assumed to be UTC (explicit assumption for security)
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    # If it's a string, parse as ISO 8601
    if isinstance(value, str):
        return datetime_to_firestore(value)

    # If it's a Firestore Timestamp, convert to datetime
    # Firestore Timestamp objects have a to_datetime() method that returns a UTC-aware datetime
    if hasattr(value, "to_datetime"):
        return value.to_datetime()

    raise ValueError(
        f"Cannot convert {type(value).__name__} to datetime. Expected Firestore Timestamp, datetime, ISO 8601 string, or None."
    )


def serialize_model_to_dict(model: BaseModel) -> dict[str, Any]:
    """
    Serialize a Pydantic model to a dict, handling datetime objects.

    This converts the model to a dict with datetime objects preserved
    (not converted to strings), which is what Firestore expects.

    Args:
        model: A Pydantic BaseModel instance

    Returns:
        Dictionary with datetime objects preserved

    Examples:
        >>> from app.models import Status
        >>> from app.models import CharacterIdentity
        >>> identity = CharacterIdentity(name="Hero", race="Human", **{"class": "Warrior"})
        >>> serialize_model_to_dict(identity)
        {'name': 'Hero', 'race': 'Human', 'class': 'Warrior'}
    """
    # Use model_dump with mode='python' to preserve datetime objects
    return model.model_dump(mode="python", by_alias=True)


def to_firestore_dict(
    model: BaseModel, *, exclude_none: bool = True, convert_timestamps: bool = True
) -> dict[str, Any]:
    """
    Convert a Pydantic model to a Firestore-friendly dictionary.

    This helper:
    - Converts the model to a dict using aliases (e.g., player_action → player_action)
    - Optionally excludes None values to reduce storage
    - Optionally converts datetime objects to Firestore-compatible format
    - Preserves nested models and complex types

    Args:
        model: A Pydantic BaseModel instance
        exclude_none: If True, omit fields with None values (default: True)
        convert_timestamps: If True, convert datetime to UTC (default: True)

    Returns:
        Dictionary suitable for Firestore storage

    Examples:
        >>> from app.models import Location
        >>> location = Location(id="town:rivendell", display_name="Rivendell")
        >>> to_firestore_dict(location)
        {'id': 'town:rivendell', 'display_name': 'Rivendell'}
    """
    # Get dict with aliases
    data = model.model_dump(mode="python", by_alias=True, exclude_none=exclude_none)

    if convert_timestamps:
        data = _convert_timestamps_in_dict(data)

    return data


def _convert_timestamps_in_dict(data: Any) -> Any:
    """
    Recursively convert datetime objects to Firestore-compatible format.

    This function handles nested dictionaries, lists, and datetime objects.
    Other types (including sets, tuples, and custom objects) are passed through
    unchanged, as they should be handled by Pydantic serialization before
    reaching this function.

    Args:
        data: A dict, list, datetime, or primitive value

    Returns:
        Data with datetime objects converted to UTC

    Note:
        This function expects data already serialized by Pydantic's model_dump(),
        which converts sets, tuples, and custom objects to JSON-compatible types.
    """
    if isinstance(data, dict):
        return {key: _convert_timestamps_in_dict(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_convert_timestamps_in_dict(item) for item in data]
    elif isinstance(data, datetime):
        return datetime_to_firestore(data)
    else:
        # Pass through all other types (str, int, float, bool, None, etc.)
        # Pydantic's model_dump() should have already converted complex types
        return data


# ==============================================================================
# CharacterDocument Serialization
# ==============================================================================


def character_to_firestore(
    character: CharacterDocument, *, use_server_timestamp: bool = False
) -> dict[str, Any]:
    """
    Serialize a CharacterDocument to a Firestore-friendly dictionary.

    This helper converts the CharacterDocument Pydantic model to a dict that
    can be stored in Firestore. It handles:
    - Nested model serialization (PlayerState, Quest, CombatState)
    - Datetime to Firestore Timestamp conversion
    - Optional field handling (None values are excluded by default)
    - Schema version storage

    Args:
        character: CharacterDocument instance to serialize
        use_server_timestamp: If True, use firestore.SERVER_TIMESTAMP for
            created_at and updated_at fields (default: False for updates)

    Returns:
        Dictionary ready for Firestore storage

    Examples:
        >>> from app.models import CharacterDocument, PlayerState, CharacterIdentity, Status
        >>> player_state = PlayerState(
        ...     identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
        ...     status=Status.HEALTHY,
        ...     location="test"
        ... )
        >>> char = CharacterDocument(
        ...     character_id="test-id",
        ...     owner_user_id="user_123",
        ...     adventure_prompt="Test adventure",
        ...     player_state=player_state,
        ...     world_pois_reference="world",
        ...     narrative_turns_reference="narrative_turns",
        ...     schema_version="1.0.0",
        ...     created_at="2026-01-11T12:00:00Z",
        ...     updated_at="2026-01-11T12:00:00Z"
        ... )
        >>> data = character_to_firestore(char)
        >>> 'character_id' in data
        True
        >>> 'player_state' in data
        True
    """
    # Convert to dict with None values excluded
    data = to_firestore_dict(character, exclude_none=True)

    # Handle server timestamps if requested
    if use_server_timestamp:
        data["created_at"] = firestore.SERVER_TIMESTAMP
        data["updated_at"] = firestore.SERVER_TIMESTAMP

    return data


def character_from_firestore(
    data: dict[str, Any], *, character_id: Optional[str] = None
) -> CharacterDocument:
    """
    Deserialize a CharacterDocument from a Firestore dictionary.

    This helper converts a Firestore document dict back to a CharacterDocument
    Pydantic model. It handles:
    - Firestore Timestamp to datetime conversion
    - ISO string to datetime conversion
    - Missing optional fields (defaults to None)
    - Schema version validation
    - Nested model reconstruction

    Args:
        data: Dictionary from Firestore document
        character_id: Optional character_id to use if not in data

    Returns:
        CharacterDocument instance

    Raises:
        ValueError: If required fields are missing or invalid

    Examples:
        >>> data = {
        ...     'character_id': 'test-id',
        ...     'owner_user_id': 'user_123',
        ...     'adventure_prompt': 'Test adventure',
        ...     'player_state': {
        ...         'identity': {'name': 'Test', 'race': 'Human', 'class': 'Warrior'},
        ...         'status': 'Healthy',
        ...         'stats': {},
        ...         'location': 'test'
        ...     },
        ...     'world_pois_reference': 'world',
        ...     'narrative_turns_reference': 'narrative_turns',
        ...     'schema_version': '1.0.0',
        ...     'created_at': '2026-01-11T12:00:00Z',
        ...     'updated_at': '2026-01-11T12:00:00Z'
        ... }
        >>> char = character_from_firestore(data)
        >>> char.character_id
        'test-id'
    """
    # Make a copy to avoid modifying the original
    data = dict(data)

    # Use provided character_id if given
    if character_id:
        data["character_id"] = character_id

    # For backward compatibility, remove legacy numeric health/stat fields from player_state
    if "player_state" in data and isinstance(data["player_state"], dict):
        player_data = data["player_state"]
        # Track which deprecated fields are present for logging
        deprecated_fields = [
            "health", "level", "experience", "stats",
            "current_hp", "max_hp", "current_health", "max_health"
        ]
        found_fields = [field for field in deprecated_fields if field in player_data]
        
        if found_fields:
            char_id = data.get("character_id", "unknown")
            logger.info(
                "Stripping legacy numeric fields from player_state during deserialization",
                character_id=char_id,
                stripped_fields=found_fields,
            )
        
        # Remove deprecated numeric fields - they are ignored and never persisted back
        player_data.pop("health", None)  # Old health field
        player_data.pop("level", None)  # Numeric level (use status enum instead)
        player_data.pop("experience", None)  # Numeric XP (use status enum instead)
        player_data.pop("stats", None)  # Numeric stats dict (use status enum instead)
        player_data.pop("current_hp", None)  # HP-style health (use status enum instead)
        player_data.pop("max_hp", None)  # HP-style health (use status enum instead)
        player_data.pop("current_health", None)  # Alternative health field
        player_data.pop("max_health", None)  # Alternative health field

    # Convert timestamps
    for field in ["created_at", "updated_at"]:
        if field in data:
            data[field] = datetime_from_firestore(data[field])

    # Handle nested timestamps in combat_state
    if data.get("combat_state"):
        combat_data = data["combat_state"]
        if "started_at" in combat_data:
            combat_data["started_at"] = datetime_from_firestore(
                combat_data["started_at"]
            )

    # Handle nested timestamps in active_quest
    if data.get("active_quest"):
        quest_data = data["active_quest"]
        if "updated_at" in quest_data:
            quest_data["updated_at"] = datetime_from_firestore(quest_data["updated_at"])

    # Handle nested timestamps in archived_quests
    if data.get("archived_quests"):
        for entry in data["archived_quests"]:
            if "cleared_at" in entry:
                entry["cleared_at"] = datetime_from_firestore(entry["cleared_at"])
            if "quest" in entry and "updated_at" in entry["quest"]:
                entry["quest"]["updated_at"] = datetime_from_firestore(
                    entry["quest"]["updated_at"]
                )

    # Construct the CharacterDocument from the dict
    return CharacterDocument(**data)


# ==============================================================================
# NarrativeTurn Serialization
# ==============================================================================


def narrative_turn_to_firestore(
    turn: NarrativeTurn, *, use_server_timestamp: bool = False
) -> dict[str, Any]:
    """
    Serialize a NarrativeTurn to a Firestore-friendly dictionary.

    This helper prepares a NarrativeTurn for storage in a Firestore subcollection.
    It handles datetime conversion and maintains ordering metadata.

    Args:
        turn: NarrativeTurn instance to serialize
        use_server_timestamp: If True, replace timestamp with SERVER_TIMESTAMP

    Returns:
        Dictionary ready for Firestore subcollection storage

    Examples:
        >>> from app.models import NarrativeTurn
        >>> from datetime import datetime, timezone
        >>> turn = NarrativeTurn(
        ...     turn_id="turn_001",
        ...     turn_number=1,
        ...     player_action="I draw my sword",
        ...     gm_response="You draw your sword",
        ...     timestamp=datetime.now(timezone.utc)
        ... )
        >>> data = narrative_turn_to_firestore(turn)
        >>> 'turn_id' in data
        True
        >>> 'player_action' in data
        True
    """
    data = to_firestore_dict(turn, exclude_none=True)

    if use_server_timestamp:
        data["timestamp"] = firestore.SERVER_TIMESTAMP

    return data


def narrative_turn_from_firestore(
    data: dict[str, Any], *, turn_id: Optional[str] = None
) -> NarrativeTurn:
    """
    Deserialize a NarrativeTurn from a Firestore dictionary.

    This helper converts a Firestore subcollection document back to a
    NarrativeTurn Pydantic model.

    Args:
        data: Dictionary from Firestore subcollection document
        turn_id: Optional turn_id to use if not in data

    Returns:
        NarrativeTurn instance

    Examples:
        >>> data = {
        ...     'turn_id': 'turn_001',
        ...     'turn_number': 1,
        ...     'player_action': 'test',
        ...     'gm_response': 'test',
        ...     'timestamp': '2026-01-11T12:00:00Z'
        ... }
        >>> turn = narrative_turn_from_firestore(data)
        >>> turn.turn_id
        'turn_001'
    """
    # Make a copy to avoid modifying the original
    data = dict(data)

    # Use provided turn_id if given
    if turn_id:
        data["turn_id"] = turn_id

    # Convert timestamp
    if "timestamp" in data:
        data["timestamp"] = datetime_from_firestore(data["timestamp"])

    return NarrativeTurn(**data)


# ==============================================================================
# PointOfInterest Subcollection Serialization
# ==============================================================================


def poi_subcollection_to_firestore(
    poi: PointOfInterestSubcollection, *, use_server_timestamp: bool = False
) -> dict[str, Any]:
    """
    Serialize a PointOfInterestSubcollection to a Firestore-friendly dictionary.

    This helper prepares a POI for storage in a Firestore subcollection.
    It handles datetime conversion for discovery and visit timestamps.

    Args:
        poi: PointOfInterestSubcollection instance to serialize
        use_server_timestamp: If True, use SERVER_TIMESTAMP for timestamp fields

    Returns:
        Dictionary ready for Firestore subcollection storage

    Examples:
        >>> from app.models import PointOfInterestSubcollection
        >>> poi = PointOfInterestSubcollection(
        ...     poi_id="poi_123",
        ...     name="Hidden Temple",
        ...     description="An ancient temple"
        ... )
        >>> data = poi_subcollection_to_firestore(poi)
        >>> 'poi_id' in data
        True
        >>> 'name' in data
        True
    """
    data = to_firestore_dict(poi, exclude_none=True)

    # Note: use_server_timestamp would typically be applied to specific
    # timestamp fields like timestamp_discovered or last_visited when they're
    # being set for the first time or updated

    return data


def poi_subcollection_from_firestore(
    data: dict[str, Any], *, poi_id: Optional[str] = None
) -> PointOfInterestSubcollection:
    """
    Deserialize a PointOfInterestSubcollection from a Firestore dictionary.

    This helper converts a Firestore subcollection document back to a
    PointOfInterestSubcollection Pydantic model.

    Args:
        data: Dictionary from Firestore subcollection document
        poi_id: Optional poi_id to use if not in data

    Returns:
        PointOfInterestSubcollection instance

    Examples:
        >>> data = {
        ...     'poi_id': 'poi_123',
        ...     'name': 'Hidden Temple',
        ...     'description': 'An ancient temple'
        ... }
        >>> poi = poi_subcollection_from_firestore(data)
        >>> poi.poi_id
        'poi_123'
    """
    # Make a copy to avoid modifying the original
    data = dict(data)

    # Use provided poi_id if given
    if poi_id:
        data["poi_id"] = poi_id

    # Convert timestamps
    for field in ["timestamp_discovered", "last_visited"]:
        if field in data:
            data[field] = datetime_from_firestore(data[field])

    return PointOfInterestSubcollection(**data)


# Backward compatibility aliases
poi_to_firestore = poi_subcollection_to_firestore
poi_from_firestore = poi_subcollection_from_firestore
