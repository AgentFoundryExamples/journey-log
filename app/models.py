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

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class Status(str, Enum):
    """
    Character health status enum.
    
    Referenced in: docs/SCHEMA.md - Character Document Fields
    """
    HEALTHY = "Healthy"
    WOUNDED = "Wounded"
    DEAD = "Dead"


class CombatStatus(str, Enum):
    """
    Combat-specific status enum.
    
    Referenced in: docs/SCHEMA.md - Combat State
    """
    HEALTHY = "Healthy"
    WOUNDED = "Wounded"
    DEAD = "Dead"


class CompletionState(str, Enum):
    """
    Quest completion state enum.
    
    Referenced in: docs/SCHEMA.md - Quest Management
    """
    NOT_STARTED = "NotStarted"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"


class CharacterIdentity(BaseModel):
    """
    Character identity information (name, race, class).
    
    Referenced in: docs/SCHEMA.md - Character Document Fields
    """
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(description="Character name")
    race: str = Field(description="Character race (e.g., Human, Elf, Dwarf)")
    character_class: str = Field(
        alias="class",
        description="Character class (e.g., Warrior, Mage, Ranger)"
    )


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
        default=None,
        description="Special weapon effects as string or structured dict"
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
        default=None,
        description="Item effect as string or structured dict"
    )


class PlayerState(BaseModel):
    """
    Current player character state including equipment, stats, and location.
    
    This model represents the core game state for a character, including:
    - Character identity (name, race, class)
    - Health status
    - Equipment (weapons, armor, inventory)
    - Current location
    - Extensible additional fields for game-specific data
    
    Referenced in: docs/SCHEMA.md - Character Document Fields (player_state)
    """
    model_config = ConfigDict(extra="allow")
    
    identity: CharacterIdentity = Field(description="Character identity information")
    status: Status = Field(description="Character health status")
    level: int = Field(default=1, ge=1, description="Character level")
    experience: int = Field(default=0, ge=0, description="Experience points")
    health: dict[str, int] = Field(
        description="Health points (current and max)",
        examples=[{"current": 100, "max": 100}]
    )
    stats: dict[str, int] = Field(
        description="Character stats (strength, dexterity, etc.)",
        examples=[{
            "strength": 18,
            "dexterity": 14,
            "constitution": 16,
            "intelligence": 12,
            "wisdom": 13,
            "charisma": 15
        }]
    )
    equipment: list[Weapon] = Field(
        default_factory=list,
        description="Equipped weapons"
    )
    inventory: list[InventoryItem] = Field(
        default_factory=list,
        description="Inventory items"
    )
    location: Union[str, dict[str, Any]] = Field(
        description="Current location as string or structured object",
        examples=["Rivendell", {"world": "middle-earth", "region": "gondor", "coordinates": {"x": 100, "y": 200}}]
    )
    additional_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible fields for game-specific data"
    )


class NarrativeTurn(BaseModel):
    """
    A single narrative turn in the character's story.
    
    Represents one interaction between the player and the game master (AI),
    including the player's action, AI's response, and timestamp.
    
    Referenced in: docs/SCHEMA.md - Narrative Turns Subcollection
    """
    model_config = ConfigDict(extra="forbid")
    
    turn_id: str = Field(description="Unique turn identifier (UUIDv4)")
    turn_number: Optional[int] = Field(default=None, description="Sequential turn counter")
    user_action: str = Field(
        alias="player_action",
        description="Player's action or input"
    )
    ai_response: str = Field(
        alias="gm_response",
        description="Game master's/AI's response"
    )
    timestamp: Union[datetime, str] = Field(
        description="When the turn occurred (datetime or ISO 8601 string)"
    )
    game_state_snapshot: Optional[dict[str, Any]] = Field(
        default=None,
        description="Snapshot of relevant game state at this turn"
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional turn metadata (response time, LLM model, etc.)"
    )


class PointOfInterest(BaseModel):
    """
    A point of interest (POI) in the game world.
    
    POIs represent locations, dungeons, towns, or other places the character
    has discovered or visited.
    
    Referenced in: docs/SCHEMA.md - Points of Interest Subcollection
    """
    model_config = ConfigDict(extra="forbid")
    
    id: str = Field(alias="poi_id", description="Unique POI identifier (UUIDv4)")
    name: str = Field(description="POI name")
    description: str = Field(description="POI description")
    type: Optional[str] = Field(default=None, description="POI type (dungeon, town, landmark, etc.)")
    location: Optional[dict[str, Any]] = Field(
        default=None,
        description="POI location information"
    )
    timestamp_discovered: Optional[Union[datetime, str]] = Field(
        default=None,
        alias="discovered_at",
        description="When the POI was discovered"
    )
    last_visited: Optional[Union[datetime, str]] = Field(
        default=None,
        alias="visited_at",
        description="When the POI was last visited"
    )
    visited: Optional[bool] = Field(default=False, description="Whether the POI has been visited")
    notes: Optional[str] = Field(default=None, description="Player notes about this POI")
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional POI metadata"
    )


class QuestRequirement(BaseModel):
    """
    A requirement for completing a quest.
    
    Requirements can be simple string descriptions or complex structured data.
    
    Referenced in: docs/SCHEMA.md - Quest Structure
    """
    model_config = ConfigDict(extra="forbid")
    
    type: str = Field(description="Requirement type (e.g., 'kill', 'collect', 'visit')")
    details: Union[str, dict[str, Any]] = Field(
        description="Requirement details as string or structured dict"
    )


class QuestReward(BaseModel):
    """
    A reward for completing a quest.
    
    Rewards can be simple string descriptions or complex structured data.
    
    Referenced in: docs/SCHEMA.md - Quest Structure
    """
    model_config = ConfigDict(extra="forbid")
    
    type: str = Field(description="Reward type (e.g., 'experience', 'gold', 'item')")
    details: Union[str, dict[str, Any]] = Field(
        description="Reward details as string or structured dict"
    )


class Quest(BaseModel):
    """
    A quest with objectives, requirements, and rewards.
    
    Quests represent missions or tasks the character can undertake.
    
    Referenced in: docs/SCHEMA.md - Character Document Fields (active_quest)
    """
    model_config = ConfigDict(extra="forbid")
    
    quest_id: str = Field(description="Unique quest identifier")
    title: str = Field(description="Quest title")
    description: str = Field(description="Quest description")
    completion_state: CompletionState = Field(
        description="Quest completion status"
    )
    objectives: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of quest objectives"
    )
    requirements: list[QuestRequirement] = Field(
        default_factory=list,
        description="Quest requirements"
    )
    rewards: list[QuestReward] = Field(
        default_factory=list,
        description="Quest rewards"
    )
    started_at: Optional[Union[datetime, str]] = Field(
        default=None,
        description="When the quest was started"
    )


class Enemy(BaseModel):
    """
    An enemy in combat.
    
    Referenced in: docs/SCHEMA.md - Combat State
    """
    model_config = ConfigDict(extra="forbid")
    
    enemy_id: str = Field(description="Unique enemy identifier")
    name: str = Field(description="Enemy name")
    health: dict[str, int] = Field(
        description="Enemy health (current and max)",
        examples=[{"current": 50, "max": 50}]
    )
    status_effects: list[str] = Field(
        default_factory=list,
        description="Active status effects on the enemy"
    )


class CombatState(BaseModel):
    """
    Current combat state.
    
    Represents an active combat encounter, including enemies and combat status.
    When not in combat, the combat_state field in CharacterDocument should be None.
    
    Referenced in: docs/SCHEMA.md - Character Document Fields (combat_state)
    """
    model_config = ConfigDict(extra="forbid")
    
    combat_id: str = Field(description="Unique combat identifier")
    started_at: Union[datetime, str] = Field(
        description="When combat started"
    )
    turn: int = Field(default=1, ge=1, description="Current combat turn")
    enemies: list[Enemy] = Field(
        description="List of enemies in combat"
    )
    player_conditions: Optional[dict[str, Any]] = Field(
        default=None,
        description="Player status effects and conditions during combat"
    )
    
    @property
    def is_active(self) -> bool:
        """
        Helper property to determine if combat is active.
        
        Combat is considered active if there are any enemies with current health > 0.
        """
        return any(
            enemy.health.get("current", 0) > 0
            for enemy in self.enemies
        )


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
        }
    )
    
    # Required core fields
    character_id: str = Field(
        description="UUIDv4 character identifier (matches Firestore document ID)"
    )
    owner_user_id: str = Field(
        description="User ID of the character owner (for access control)"
    )
    player_state: PlayerState = Field(
        description="Current player character state"
    )
    world_pois_reference: str = Field(
        description="Reference to world POI collection or configuration"
    )
    schema_version: int = Field(
        description="Schema version for this document (integer)"
    )
    created_at: Union[datetime, str] = Field(
        description="When the character was created (Firestore Timestamp or ISO 8601)"
    )
    updated_at: Union[datetime, str] = Field(
        description="Last update timestamp (Firestore Timestamp or ISO 8601)"
    )
    
    # Optional fields
    active_quest: Optional[Quest] = Field(
        default=None,
        description="Current active quest (None if no active quest)"
    )
    combat_state: Optional[CombatState] = Field(
        default=None,
        description="Current combat state (None if not in combat)"
    )
    
    # Extensible metadata
    additional_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extensible metadata including character name, timestamps, owner info, etc."
    )
