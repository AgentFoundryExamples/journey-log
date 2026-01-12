# Journey Log Data Schema

This document defines the canonical data schema for the Journey Log system, specifically focusing on character data storage in Google Cloud Firestore.

## Table of Contents

1. [Overview](#overview)
2. [Character Collection Structure](#character-collection-structure)
3. [Character Identifier Strategy](#character-identifier-strategy)
4. [Character Document Fields](#character-document-fields)
5. [Subcollections](#subcollections)
6. [Embedded vs Subcollection Rationale](#embedded-vs-subcollection-rationale)
7. [Timestamp Conventions](#timestamp-conventions)
8. [Edge Cases and Migration](#edge-cases-and-migration)
9. [Firestore Sizing and Consistency Considerations](#firestore-sizing-and-consistency-considerations)
10. [Serialization Testing](#serialization-testing)
11. [API Endpoints](#api-endpoints)

---

## Overview

The Journey Log system stores character data in Google Cloud Firestore using a single-document-per-character model with supporting subcollections for narrative history and points of interest (POIs). This design balances document size constraints with query efficiency and data consistency.

**Key Design Principles:**
- Single source of truth for character state
- Separate subcollections for unbounded data (narrative history, POIs)
- Schema versioning for backward compatibility
- Owner-based access control support

---

## Character Collection Structure

The primary collection for character data is:

```
characters/
  {character_id}/                    # Document ID (UUIDv4 string)
    - Core character data fields     # See "Character Document Fields" section
    narrative_turns/                 # Subcollection
      {turn_id}/                     # Individual narrative turn documents
    pois/                            # Subcollection
      {poi_id}/                      # Individual POI documents
```

**Collection Name:** `characters`

**Document Path Format:** `characters/{character_id}`

---

## Character Identifier Strategy

### Character ID Generation

Each character is uniquely identified by a **UUIDv4 string** used as the Firestore document ID.

**Format:** UUIDv4 (RFC 4122)
- **Example:** `550e8400-e29b-41d4-a716-446655440000`
- **Representation:** String (lowercase hexadecimal with hyphens)

### Generation Rules

1. **Client-Side Generation (Recommended):**
   - Generate UUIDv4 on the client before creating the character document
   - This allows the client to know the character_id immediately without a round-trip
   - Use standard UUID libraries (Python: `uuid.uuid4()`, JavaScript: `crypto.randomUUID()`)

2. **Server-Side Generation (Alternative):**
   - Generate UUIDv4 on the server when creating a new character
   - Return the character_id to the client in the response

### Validation Rules

- **Format:** Must be a valid UUIDv4 string (36 characters with hyphens)
- **Case:** Accept both uppercase and lowercase, but **store as lowercase**
- **Uniqueness:** Firestore document IDs are unique within a collection by design
- **Immutability:** character_id should never change once created

### Validation Error Handling

**API Boundary Validation:**
- **Invalid Format:** Reject requests with malformed UUIDs immediately at API boundaries
- **HTTP Status:** Return `400 Bad Request` for invalid character_id format
- **Error Response:** Include descriptive error message indicating the expected format
- **Normalization:** Convert valid uppercase UUIDs to lowercase before storage

**Example Validation:**
```python
import re
import uuid

def validate_character_id(character_id: str) -> tuple[bool, str]:
    """
    Validate character_id format.
    
    Returns:
        Tuple of (is_valid, normalized_id or error_message)
    """
    # Check basic format (36 characters with hyphens)
    uuid_pattern = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )
    
    if not uuid_pattern.match(character_id):
        return False, "Invalid character_id format. Expected UUIDv4 (e.g., '550e8400-e29b-41d4-a716-446655440000')"
    
    # Verify it's a valid UUID (will raise ValueError if not)
    try:
        uuid_obj = uuid.UUID(character_id, version=4)
        # Normalize to lowercase
        return True, str(uuid_obj).lower()
    except ValueError:
        return False, "Invalid UUIDv4. Character ID must be a valid version 4 UUID"

# Usage in API endpoint
is_valid, result = validate_character_id(request.character_id)
if not is_valid:
    raise HTTPException(status_code=400, detail=result)
character_id = result  # Use normalized ID
```

### Example Generation Code

```python
import uuid

# Generate a new character_id
character_id = str(uuid.uuid4())  # Returns: "550e8400-e29b-41d4-a716-446655440000"
```

```javascript
// Generate a new character_id
const character_id = crypto.randomUUID();  // Returns: "550e8400-e29b-41d4-a716-446655440000"
```

---

## Character Document Fields

Each character document contains the following top-level fields:

### Required Fields

| Field Name | Type | Description |
|------------|------|-------------|
| `character_id` | `string` | The UUIDv4 identifier (same as document ID, stored for convenience) |
| `owner_user_id` | `string` | The user ID of the character owner (from X-User-Id header, for access control) |
| `adventure_prompt` | `string` | Initial adventure prompt or backstory (1+ chars, whitespace normalized) |
| `player_state` | `map` | Current player state (HP, level, inventory, location, etc.) |
| `world_pois_reference` | `string` | Reference to the world's POI collection or configuration |
| `narrative_turns_reference` | `string` | Reference to narrative turns subcollection |
| `schema_version` | `string` | Schema version for this document (e.g., "1.0.0") |
| `created_at` | `Timestamp` | Firestore Timestamp of character creation |
| `updated_at` | `Timestamp` | Firestore Timestamp of last update |

### Optional Fields

| Field Name | Type | Description |
|------------|------|-------------|
| `world_state` | `map` or `null` | Optional world state metadata or game-specific data |
| `active_quest` | `map` or `null` | Current quest information, or null if no active quest |
| `combat_state` | `map` or `null` | Current combat state, or null if not in combat |
| `additional_metadata` | `map` | Extensible metadata (character name, tags, etc.) - defaults to empty dict |

### Field Details

#### `character_id`
- **Type:** String (UUIDv4)
- **Required:** Yes
- **Immutable:** Yes
- **Description:** Redundant with document ID, but stored for convenience when querying or returning documents
- **Rationale for Redundancy:**
  - **Convenience:** Simplifies API responses by including the ID in the document data without requiring clients to track the document path separately
  - **Consistency:** Ensures all character data is self-contained when serialized
  - **Queries:** Firestore queries can filter/return this field, while document IDs require separate handling
  - **Cost:** Minimal storage overhead (~36 bytes) compared to benefits
- **Note:** Always keep `character_id` synchronized with the Firestore document ID. Never allow mismatches.

#### `owner_user_id`
- **Type:** String
- **Required:** Yes
- **Immutable:** Yes (should not change after creation)
- **Description:** Firebase Auth UID or equivalent user identifier for access control
- **Usage:** Used in Firestore security rules to restrict access to the character owner
- **Validation:** Must be a non-empty string matching your authentication system's user ID format
- **Security:** 
  - Always validate that the authenticated user matches the owner_user_id when accessing or modifying characters
  - Never expose owner_user_id in public APIs or responses to unauthorized users
  - Use Firestore security rules to enforce ownership: `allow read, write: if request.auth.uid == resource.data.owner_user_id`

**Example Validation:**
```python
def validate_owner_user_id(owner_user_id: str, authenticated_user_id: str) -> bool:
    """
    Validate that the owner_user_id is valid and matches the authenticated user.
    
    Args:
        owner_user_id: The claimed owner user ID
        authenticated_user_id: The ID of the authenticated user making the request
        
    Returns:
        True if valid, raises HTTPException otherwise
    """
    if not owner_user_id or not owner_user_id.strip():
        raise HTTPException(status_code=400, detail="owner_user_id cannot be empty")
    
    # For new character creation, ensure authenticated user is the owner
    if owner_user_id != authenticated_user_id:
        raise HTTPException(
            status_code=403, 
            detail="Cannot create character for another user"
        )
    
    return True
```

#### `adventure_prompt`
- **Type:** String
- **Required:** Yes
- **Immutable:** No (but typically set once at character creation)
- **Description:** Initial adventure prompt or character backstory that guides the narrative
- **Validation:** 
  - Must be at least 1 character long after whitespace normalization
  - Cannot be empty or only whitespace
  - Whitespace is automatically normalized (multiple spaces collapsed to single spaces, leading/trailing trimmed)
- **Default:** None (must be provided)
- **Usage:** 
  - Set during character creation to establish the character's background and motivation
  - Used by AI/LLM to generate contextually appropriate narrative responses
  - Can be updated during gameplay if the character's direction changes significantly
- **Examples:**
  - `"A brave warrior seeking to avenge their fallen comrades"`
  - `"An exiled mage searching for forbidden knowledge to restore their homeland"`
  - `"A cunning rogue fleeing from a dark past and seeking redemption"`

**Example Validation:**
```python
from pydantic import BaseModel, Field, model_validator

class CharacterDocument(BaseModel):
    adventure_prompt: str = Field(min_length=1, description="Adventure prompt")
    
    @model_validator(mode='after')
    def normalize_adventure_prompt(self) -> 'CharacterDocument':
        """Normalize whitespace in adventure_prompt."""
        self.adventure_prompt = ' '.join(self.adventure_prompt.split())
        if not self.adventure_prompt:
            raise ValueError("adventure_prompt cannot be empty or only whitespace")
        return self
```

#### `player_state`
- **Type:** Map (nested object)
- **Required:** Yes
- **Description:** Current state of the player character including identity, stats, equipment, and location
- **Nested Fields:**
  - `identity` (map): Character name, race, and class with validation
    - `name` (string, 1-64 chars): Character name with normalized whitespace
    - `race` (string, 1-64 chars): Character race with normalized whitespace
    - `class` (string, 1-64 chars): Character class with normalized whitespace
  - `status` (string): Character health status (enum: "Healthy", "Wounded", "Dead")
  - `level` (integer): Character level (≥1)
  - `experience` (integer): Experience points (≥0)
  - `health` (map): Current and max health points
    - `current` (integer, ≥0): Current health
    - `max` (integer, ≥0): Maximum health
  - `stats` (map): Character stats (strength, dexterity, etc.)
  - `equipment` (array): List of weapon objects
  - `inventory` (array): List of inventory item objects
  - `location` (map, string, or Location object): Current location (see Location Structure below)
  - `additional_fields` (map): Extensible fields for game-specific data

**Location Structure:**

The `location` field supports three formats for backward compatibility:

1. **Location Object (Recommended):**
   ```json
   {
     "id": "origin:nexus",
     "display_name": "The Nexus"
   }
   ```
   - `id` (string): Location identifier for internal logic (e.g., "origin:nexus", "town:rivendell", "dungeon:dragon-lair")
   - `display_name` (string): Human-readable location name shown to players

2. **String (Legacy):**
   ```json
   "location": "Rivendell"
   ```

3. **Dict (Legacy):**
   ```json
   {
     "world": "middle-earth",
     "region": "gondor",
     "coordinates": {"x": 100, "y": 200}
   }
   ```

**Default Location:**
- When creating a new character, use the default starting location defined in `app/config.py`:
  - `DEFAULT_LOCATION_ID = "origin:nexus"`
  - `DEFAULT_LOCATION_DISPLAY_NAME = "The Nexus"`

**Identity Validation:**
All identity fields (name, race, class) are validated to:
- Be between 1 and 64 characters in length (inclusive)
- Have normalized whitespace (multiple spaces collapsed, leading/trailing trimmed)
- Be non-empty after normalization

**Default Character Status:**
- The default character status is defined in `app/config.py`:
  - `DEFAULT_CHARACTER_STATUS = "Healthy"`

**Example Structure:**
  ```json
  {
    "identity": {
      "name": "Aragorn",
      "race": "Human",
      "class": "Ranger"
    },
    "status": "Healthy",
    "level": 10,
    "experience": 5000,
    "health": {
      "current": 100,
      "max": 100
    },
    "stats": {
      "strength": 18,
      "dexterity": 14,
      "constitution": 16,
      "intelligence": 12,
      "wisdom": 13,
      "charisma": 15
    },
    "equipment": [
      {
        "name": "Anduril",
        "damage": "2d6",
        "special_effects": "Glows blue near enemies"
      }
    ],
    "inventory": [
      {
        "name": "Healing Potion",
        "quantity": 3,
        "effect": "Restores 50 HP"
      }
    ],
    "location": {
      "id": "town:rivendell",
      "display_name": "Rivendell"
    },
    "additional_fields": {}
  }
  ```

**Character Name Storage:**
- The character's name is stored in `player_state.identity.name` as the authoritative source
- The `additional_metadata.character_name` field may also contain the name for convenience and backward compatibility, but `identity.name` should be considered the primary field

#### `world_state`
- **Type:** Map or null
- **Required:** No (optional)
- **Description:** Optional world state metadata or game-specific global data
- **Default:** null (not present unless explicitly set)
- **Usage:**
  - Store global world state that affects gameplay (time of day, weather, faction relations)
  - Track world-level events or conditions (dragon awakened, kingdom at war)
  - Maintain persistent world data across game sessions
  - Flexible structure allows for game-specific extensions
- **Example Structure:**
  ```json
  {
    "time_of_day": "morning",
    "weather": "sunny",
    "factions": {
      "kingdom": "friendly",
      "orcs": "hostile",
      "elves": "neutral"
    },
    "global_events": ["dragon_awakened", "festival_in_progress"],
    "season": "spring",
    "game_day": 42
  }
  ```

#### `active_quest`
- **Type:** Map or null
- **Required:** Yes (can be null)
- **Description:** Information about the currently active quest, or null if no quest is active
- **Example Structure:**
  ```json
  {
    "quest_id": "quest_001",
    "title": "Destroy the Ring",
    "description": "Take the One Ring to Mount Doom",
    "objectives": [
      {
        "id": "obj_001",
        "description": "Reach Rivendell",
        "completed": true
      },
      {
        "id": "obj_002",
        "description": "Form the Fellowship",
        "completed": true
      },
      {
        "id": "obj_003",
        "description": "Reach Mordor",
        "completed": false
      }
    ],
    "started_at": "2026-01-11T12:00:00.000000Z"
  }
  ```

**Note:** Timestamps within nested objects like `started_at` should use ISO 8601 format for consistency when storing as strings, or use Firestore Timestamp objects if you need to query/sort by these dates.

#### `world_pois_reference`
- **Type:** String
- **Required:** Yes
- **Description:** Reference to the world's POI configuration or collection
- **Format:** Can be a collection path, document ID, or configuration key
- **Example:** `"worlds/middle-earth/pois"` or `"middle-earth-v1"`

#### `combat_state`
- **Type:** Map or null
- **Required:** Yes (can be null)
- **Description:** Current combat state, or null if not in combat. Maximum 5 enemies per combat.
- **Combat Active Logic:** Combat is considered inactive when all enemies have status "Dead" or the enemies list is empty.
- **Example Structure:**
  ```json
  {
    "combat_id": "combat_123",
    "started_at": "2026-01-11T14:30:00Z",
    "turn": 3,
    "enemies": [
      {
        "enemy_id": "orc_001",
        "name": "Orc Warrior",
        "status": "Wounded",
        "weapon": "Rusty Axe",
        "traits": ["aggressive", "armored"],
        "metadata": {
          "difficulty": "medium",
          "loot_table": "orc_warrior"
        }
      },
      {
        "enemy_id": "goblin_002",
        "name": "Goblin Archer",
        "status": "Healthy",
        "weapon": "Short Bow",
        "traits": ["ranged", "cowardly"],
        "metadata": null
      }
    ],
    "player_conditions": {
      "status_effects": [],
      "temporary_buffs": ["shield_of_valor"]
    }
  }
  ```

**EnemyState Fields:**
- `enemy_id` (string, required): Unique identifier for the enemy
- `name` (string, required): Enemy display name
- `status` (string, required): Enemy health status - one of "Healthy", "Wounded", or "Dead"
- `weapon` (string, optional): Weapon wielded by the enemy
- `traits` (array of strings, optional): List of enemy traits or characteristics
- `metadata` (object, optional): Additional enemy metadata

**CombatState Fields:**
- `combat_id` (string, required): Unique combat identifier
- `started_at` (string, required): ISO 8601 timestamp when combat started
- `turn` (integer, required): Current combat turn (≥1)
- `enemies` (array, required): List of EnemyState objects (max 5)
- `player_conditions` (object, optional): Player status effects and conditions
- **Computed Property:** `is_active` (boolean): Server-computed property (NOT persisted to Firestore)
  - Computed at runtime based on enemy statuses
  - Returns `false` if all enemies are Dead or enemies list is empty
  - Returns `true` if at least one enemy is not Dead
  - This field is derived from the `enemies` array and should not be sent by clients or stored in Firestore

**Validation Rules:**
- Maximum 5 enemies per combat (enforced at model validation layer)
- Payloads with more than 5 enemies are rejected before Firestore writes
- Empty enemies array implies inactive combat (is_active = false)
- All enemies Dead implies inactive combat (is_active = false)
- Unknown enemy statuses cause deterministic validation errors

**Storage Isolation:**
- Firestore writes to combat_state use field masks or transactions to avoid clobbering unrelated character fields
- Combat state updates do not overwrite narrative, quest, or other character data

#### `additional_metadata`
- **Type:** Map
- **Required:** Yes
- **Description:** Extensible metadata for character customization and game-specific data
- **Example Structure:**
  ```json
  {
    "character_name": "Aragorn",
    "character_class": "Ranger",
    "race": "Human",
    "background": "Noble",
    "tags": ["main-campaign", "multiplayer-ready"],
    "preferences": {
      "difficulty": "normal",
      "tutorial_completed": true
    }
  }
  ```

#### `schema_version`
- **Type:** String (semantic versioning)
- **Required:** Yes
- **Description:** Version of the schema this document conforms to
- **Format:** Semantic versioning (e.g., "1.0.0", "1.1.0", "2.0.0")
- **Usage:** Used for schema migrations and backward compatibility
- **Current Version:** "1.0.0"

#### `created_at`
- **Type:** Firestore Timestamp
- **Required:** Yes
- **Immutable:** Yes
- **Description:** Timestamp when the character was created
- **Set By:** Server on document creation

#### `updated_at`
- **Type:** Firestore Timestamp
- **Required:** Yes
- **Mutable:** Yes (updated on every write)
- **Description:** Timestamp of the last update to the character document
- **Set By:** Server on every document update

---

## Subcollections

Character documents have two required subcollections for unbounded data:

### 1. Narrative Turns Subcollection

**Path:** `characters/{character_id}/narrative_turns/{turn_id}`

**Purpose:** Stores the history of narrative turns/interactions for the character.

**Storage Strategy:**
- Narrative turns persist indefinitely per character (no automatic trimming or deletion)
- Each turn is stored as a separate document in the subcollection
- Subcollection grows unbounded - monitoring recommended to track storage costs
- Field size limits enforced to prevent oversized documents

**Document Structure:**
```json
{
  "turn_id": "turn_001",
  "turn_number": 1,
  "timestamp": "2026-01-11T12:00:00Z",
  "player_action": "I draw my sword and approach the cave entrance.",
  "gm_response": "As you approach the dark cave, you hear a low growl echoing from within.",
  "game_state_snapshot": {
    "location": "Cave Entrance",
    "health": 100,
    "active_effects": []
  },
  "metadata": {
    "response_time_ms": 1250,
    "llm_model": "gpt-5.1",
    "tokens_used": 150
  }
}
```

**Key Fields:**
- `turn_id`: Unique identifier for the turn (UUIDv4, required)
- `turn_number`: Sequential turn counter (optional, integer)
- `timestamp`: When the turn occurred (Firestore Timestamp, required)
  - Server defaults to current time when omitted on write
  - Used for ordering queries (see Ordering section below)
- `player_action`: What the player did (required, max 8000 characters)
- `gm_response`: The game master's/AI's response (required, max 32000 characters)
- `game_state_snapshot`: Snapshot of relevant game state (optional, map)
- `metadata`: Additional context like LLM metrics (optional, map)

**Field Size Limits:**
- `player_action`: Maximum 8000 characters (validated by Pydantic model)
- `gm_response`: Maximum 32000 characters (validated by Pydantic model)
- These limits are enforced to prevent individual documents from becoming too large
- Configurable via environment variables (see Configuration section below)

**Ordering and Query Guarantees:**
- Documents are indexed by `timestamp` descending for efficient recent-turn queries
- Query helpers return results in oldest-to-newest order (natural reading order)
- `timestamp` precision is microseconds (Firestore Timestamp)
- Timestamp ordering is guaranteed consistent even for concurrent writes
- Firestore automatically maintains indexes for timestamp-based queries

**Default Query Behavior:**
- Default query size: 10 turns (configurable via `NARRATIVE_TURNS_DEFAULT_QUERY_SIZE`)
- Maximum query size: 100 turns (configurable via `NARRATIVE_TURNS_MAX_QUERY_SIZE`)
- Queries automatically reversed to oldest-first for natural chronological order
- Pagination supported for accessing older turns beyond the query limit

**Helper Functions:**
The following helper functions are provided in `app/firestore.py`:
- `write_narrative_turn(character_id, turn_data)`: Write a new turn
- `query_narrative_turns(character_id, limit=None)`: Query recent turns (oldest-to-newest)
- `get_narrative_turn_by_id(character_id, turn_id)`: Get a specific turn
- `count_narrative_turns(character_id)`: Count total turns (expensive for large collections)

**Configuration:**
Narrative turn behavior is configurable via environment variables (see `.env.example`):
- `NARRATIVE_TURNS_DEFAULT_QUERY_SIZE`: Default number of turns to retrieve (default: 10, range: 1-100)
- `NARRATIVE_TURNS_MAX_QUERY_SIZE`: Maximum turns per query (default: 100, range: 1-1000)
- `NARRATIVE_TURNS_MAX_USER_ACTION_LENGTH`: Max characters in player_action (default: 8000)
- `NARRATIVE_TURNS_MAX_AI_RESPONSE_LENGTH`: Max characters in gm_response (default: 32000)

**Edge Cases:**
- **Empty history**: Characters with no turns return empty list (not an error)
- **Future timestamps**: Accepted but may affect ordering - validation recommended
- **Past timestamps**: Accepted for backfilling historical data
- **Missing timestamp**: Server automatically sets to current time on write
- **Duplicate turn_id**: Will overwrite existing turn (use unique UUIDs)
- **Large collections**: Pagination recommended when total turns exceed max query size

**Example Usage:**
```python
from app.firestore import query_narrative_turns, write_narrative_turn
from app.models import NarrativeTurn, narrative_turn_to_firestore
from datetime import datetime, timezone
import uuid

# Write a new turn
turn = NarrativeTurn(
    turn_id=str(uuid.uuid4()),
    turn_number=1,
    player_action="I explore the forest",
    gm_response="You discover a hidden path",
    timestamp=datetime.now(timezone.utc)
)
turn_data = narrative_turn_to_firestore(turn)
write_narrative_turn(character_id, turn_data)

# Query last 10 turns (oldest to newest)
recent_turns = query_narrative_turns(character_id, limit=10)
for turn in recent_turns:
    print(f"Turn {turn['turn_number']}: {turn['player_action']}")
```

### 2. Points of Interest (POIs) Subcollection

**Path:** `characters/{character_id}/pois/{poi_id}`

**Purpose:** Stores discovered or player-specific points of interest.

**Document Structure:**
```json
{
  "poi_id": "poi_123",
  "name": "Hidden Temple",
  "type": "dungeon",
  "location": {
    "world": "middle-earth",
    "region": "mirkwood",
    "coordinates": {"x": 250, "y": 300}
  },
  "discovered_at": "2026-01-10T15:30:00Z",
  "visited": true,
  "visited_at": "2026-01-10T16:00:00Z",
  "notes": "Found a magical artifact here.",
  "metadata": {
    "difficulty": "hard",
    "rewards": ["experience", "loot"],
    "quest_related": true,
    "quest_id": "quest_001"
  }
}
```

**Key Fields:**
- `poi_id`: Unique identifier for the POI (UUIDv4)
- `name`: Display name of the POI
- `type`: Category (dungeon, town, landmark, etc.)
- `location`: Where the POI is located
- `discovered_at`: When the player discovered it (Firestore Timestamp)
- `visited`: Whether the player has visited
- `visited_at`: When the player visited (Firestore Timestamp)
- `notes`: Player-specific notes
- `metadata`: Additional POI metadata

**Note:** POIs can be either world-global (referenced from `world_pois_reference`) or character-specific (stored in this subcollection). Character-specific POIs allow for personalized discoveries and notes.

---

## Embedded vs Subcollection Rationale

### Why Core State is Embedded in the Character Document

**Embedded Fields:** `player_state`, `active_quest`, `combat_state`, `additional_metadata`, `schema_version`, timestamps, `owner_user_id`

**Rationale:**
1. **Atomic Updates:** All core state can be updated in a single transaction
2. **Read Efficiency:** One document read gets all essential character data
3. **Document Size:** Core state is bounded and unlikely to exceed Firestore's 1 MB limit
4. **Consistency:** Strong consistency for related fields (e.g., updating level and health together)
5. **Simplicity:** Simpler code for common operations (get character state, update character)

### Why Narrative History and POIs Use Subcollections

**Subcollections:** `narrative_turns`, `pois`

**Rationale:**
1. **Unbounded Growth:** Narrative history and POIs can grow indefinitely over time
2. **Document Size Limits:** Keeping these separate prevents the character document from exceeding Firestore's 1 MB limit
3. **Query Flexibility:** Subcollections can be queried independently (e.g., "last 10 turns", "all dungeons")
4. **Pagination:** Large datasets can be paginated efficiently
5. **Partial Loading:** Load only what's needed (e.g., load character without entire narrative history)
6. **Write Isolation:** Adding a narrative turn doesn't trigger a read-modify-write of the entire character document

### Firestore Document Size Considerations

- **Maximum Document Size:** 1 MB (Firestore hard limit)
- **Practical Limit:** Keep documents under 100 KB for optimal performance
- **Character Document Size:** Core state typically 5-50 KB
- **Subcollection Documents:** Individual turns/POIs typically 1-10 KB each

**Why This Matters:**
- Large documents increase latency and bandwidth usage
- Approaching the 1 MB limit risks write failures
- Subcollections allow unlimited total data per character
- Querying subcollections is more efficient than scanning large arrays

---

## Timestamp Conventions

The system uses **Firestore Timestamp** objects for all timestamps stored in Firestore documents.

### Firestore Timestamp

- **Type:** Use `firestore.SERVER_TIMESTAMP` for writes, stored as Firestore `Timestamp` object
- **Precision:** Microsecond precision (UTC)
- **Usage:** All `*_at` fields in character documents and subcollections
- **Serialization:** Automatically converted to ISO 8601 strings in API responses

**Note:** `SERVER_TIMESTAMP` is a sentinel value that tells Firestore to use the server's current time when writing. The actual stored value is a `Timestamp` object.

### Serialization Helpers

The system provides serialization helpers in `app/models.py` for converting between Pydantic models and Firestore documents:

**Core Functions:**
- `datetime_to_firestore(dt)` - Convert Python datetime/ISO string to Firestore-compatible format
- `datetime_from_firestore(value)` - Convert Firestore Timestamp/ISO string to Python datetime
- `character_to_firestore(character)` - Serialize CharacterDocument to Firestore dict
- `character_from_firestore(data)` - Deserialize Firestore dict to CharacterDocument
- `narrative_turn_to_firestore(turn)` - Serialize NarrativeTurn to Firestore dict
- `narrative_turn_from_firestore(data)` - Deserialize Firestore dict to NarrativeTurn
- `poi_to_firestore(poi)` - Serialize PointOfInterest to Firestore dict
- `poi_from_firestore(data)` - Deserialize Firestore dict to PointOfInterest

**Timestamp Handling:**
All serialization helpers automatically:
- Convert timezone-aware datetimes to UTC
- Handle both Firestore Timestamp objects and ISO 8601 strings
- Preserve None values for optional timestamp fields
- Assume UTC for naive datetimes

**Schema Version Defaults:**
- New character documents should use schema_version "1.0.0"
- The schema_version field is required and stored in every document
- See "Edge Cases and Migration" for handling legacy documents

**Example Usage:**
```python
from app.models import (
    CharacterDocument,
    character_to_firestore,
    character_from_firestore
)
from google.cloud import firestore

# Create or get Firestore client
db = firestore.Client()

# Serialize character for writing to Firestore
character_data = character_to_firestore(character)
db.collection('characters').document(character.character_id).set(character_data)

# Deserialize character when reading from Firestore
doc_ref = db.collection('characters').document(character_id)
doc = doc_ref.get()
if doc.exists:
    character = character_from_firestore(doc.to_dict(), character_id=doc.id)
```

### When to Use Firestore Timestamp vs ISO String

| Context | Use |
|---------|-----|
| **Stored in Firestore** | Firestore `Timestamp` object |
| **API Request/Response** | ISO 8601 string (e.g., `"2026-01-11T12:34:56.789012Z"`) |
| **Server-side logic** | Python `datetime` (convert from Firestore `Timestamp`) |
| **Client-side logic** | Native Date object or ISO string |

### Example: Setting Timestamps

**Python (Server-Side):**
```python
from google.cloud import firestore

# Use server timestamp for auto-generated timestamps
character_doc = {
    "character_id": character_id,
    "created_at": firestore.SERVER_TIMESTAMP,
    "updated_at": firestore.SERVER_TIMESTAMP,
    # ... other fields
}
```

**API Response (JSON):**
```json
{
  "character_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-01-11T12:34:56.789012Z",
  "updated_at": "2026-01-11T12:34:56.789012Z"
}
```

### Best Practices

1. **Always use `SERVER_TIMESTAMP`** for `created_at` and `updated_at` to ensure consistency
2. **Convert to ISO 8601** when returning timestamps in API responses
3. **Accept ISO 8601** in API requests, but convert to Firestore `Timestamp` before storing
4. **Use UTC** for all timestamps (no local timezones in storage)
5. **Use serialization helpers** from `app/models.py` to ensure consistent conversion
6. **Exclude None values** when serializing to reduce storage (default behavior)
7. **Handle missing fields gracefully** when deserializing from Firestore

**Handling Optional Fields:**
- When serializing: `character_to_firestore()` excludes None values by default to save storage
- When deserializing: `character_from_firestore()` treats missing fields as None
- Empty lists and empty dicts are preserved (not treated as None)
- Optional timestamp fields (e.g., `started_at`, `timestamp_discovered`) support None

**Example: Updating a character with timestamps**
```python
from google.cloud import firestore
from app.models import character_to_firestore

# When updating an existing character
character_data = character_to_firestore(character)
character_data['updated_at'] = firestore.SERVER_TIMESTAMP

db.collection('characters').document(character.character_id).update(character_data)
```

**Example: Creating a new narrative turn**
```python
from google.cloud import firestore
from app.models import narrative_turn_to_firestore, NarrativeTurn

turn = NarrativeTurn(
    turn_id=str(uuid.uuid4()),
    turn_number=1,
    player_action="I draw my sword",
    gm_response="You hear a growl in the distance",
    timestamp=datetime.now(timezone.utc)
)

turn_data = narrative_turn_to_firestore(turn)
turn_data['timestamp'] = firestore.SERVER_TIMESTAMP  # Use server time

db.collection('characters').document(character_id)\
  .collection('narrative_turns').document(turn.turn_id)\
  .set(turn_data)
```

---

## Edge Cases and Migration

### 1. Missing Subcollections for Fresh Characters

**Scenario:** A newly created character has no narrative turns or POIs yet.

**Handling:**
- **Subcollections do not need to be pre-created** in Firestore
- Subcollections are created automatically when the first document is added
- Client code should handle empty subcollection queries gracefully

**Lazy Initialization:**
```python
# Query returns empty result set if subcollection doesn't exist yet
narrative_turns = character_ref.collection("narrative_turns").limit(10).stream()
turns_list = list(narrative_turns)  # Empty list if no turns yet

if not turns_list:
    # Handle fresh character case
    print("This character has no narrative history yet.")
```

**Best Practice:**
- Check for empty results when querying subcollections
- Show appropriate UI for "no data" states (e.g., "No narrative history yet")

### 2. Legacy Documents Lacking `schema_version` or Metadata Fields

**Scenario:** Characters created before schema versioning was implemented.

**Detection:**
```python
character_doc = character_ref.get().to_dict()

if "schema_version" not in character_doc:
    # Legacy document detected
    current_version = "unknown"
else:
    current_version = character_doc["schema_version"]
```

**Migration Strategy:**

**Option 1: On-Demand Migration (Recommended)**
- Detect missing fields when reading a character
- Apply default values or migrate to current schema
- Write back the updated document with `schema_version` set
- Use transactions to prevent race conditions

```python
from google.cloud import firestore

@firestore.transactional
def migrate_character_if_needed(transaction, character_ref):
    """
    Migrate a character document to the current schema version.
    
    Uses a transaction to prevent race conditions when multiple
    requests attempt to migrate the same document simultaneously.
    
    Args:
        transaction: Firestore transaction object
        character_ref: Reference to the character document
        
    Returns:
        dict: The migrated character document data
    """
    character_snapshot = character_ref.get(transaction=transaction)
    
    if not character_snapshot.exists:
        raise ValueError(f"Character document does not exist: {character_ref.id}")
    
    character_doc = character_snapshot.to_dict()
    
    needs_migration = False
    updates = {}
    
    # Check for missing schema_version
    if "schema_version" not in character_doc:
        updates["schema_version"] = "1.0.0"
        needs_migration = True
    
    # Check for missing additional_metadata
    if "additional_metadata" not in character_doc:
        updates["additional_metadata"] = {
            "character_name": character_doc.get("name", "Unknown"),
            "tags": [],
            "preferences": {}
        }
        needs_migration = True
    
    # Check for missing timestamps
    if "created_at" not in character_doc:
        updates["created_at"] = firestore.SERVER_TIMESTAMP
        needs_migration = True
    
    if "updated_at" not in character_doc:
        updates["updated_at"] = firestore.SERVER_TIMESTAMP
        needs_migration = True
    
    # Apply migration within the transaction
    if needs_migration:
        transaction.update(character_ref, updates)
        print(f"Migrated character {character_doc['character_id']} to schema 1.0.0")
        # Return the migrated document data
        migrated_doc = character_doc.copy()
        migrated_doc.update(updates)
        return migrated_doc
    
    return character_doc

# Usage example
db = firestore.Client()
character_ref = db.collection("characters").document(character_id)
transaction = db.transaction()
migrated_character = migrate_character_if_needed(transaction, character_ref)
```

**Option 2: Batch Migration**
- Run a one-time migration script to update all legacy documents
- Useful for large-scale schema changes

```python
def batch_migrate_characters():
    db = firestore.Client()
    characters_ref = db.collection("characters")
    
    batch = db.batch()
    count = 0
    
    for character_doc in characters_ref.stream():
        character_data = character_doc.to_dict()
        
        if "schema_version" not in character_data:
            # Apply migration
            batch.update(character_doc.reference, {
                "schema_version": "1.0.0",
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            count += 1
            
            # Firestore batch limit is 500 operations
            if count >= 500:
                batch.commit()
                batch = db.batch()
                count = 0
    
    # Commit remaining updates
    if count > 0:
        batch.commit()
```

### 3. Handling Missing Required Fields

**Scenario:** A character document is missing required fields due to a bug or incomplete creation.

**Validation:**
```python
REQUIRED_FIELDS = [
    "character_id",
    "owner_user_id",
    "player_state",
    "active_quest",  # Can be null, but must exist
    "world_pois_reference",
    "combat_state",  # Can be null, but must exist
    "additional_metadata",
    "schema_version",
    "created_at",
    "updated_at"
]

def validate_character_document(character_doc):
    missing_fields = [field for field in REQUIRED_FIELDS if field not in character_doc]
    
    if missing_fields:
        raise ValueError(f"Character document missing required fields: {missing_fields}")
    
    return True
```

**Recovery:**
- If a required field is missing, either:
  1. Reject the document and require re-creation (strict)
  2. Apply sensible defaults and migrate (lenient)

### 4. Schema Version Mismatch

**Scenario:** A character has `schema_version: "2.0.0"` but the current code expects `"1.0.0"`.

**Handling:**
```python
CURRENT_SCHEMA_VERSION = "1.0.0"

def check_schema_compatibility(character_doc):
    doc_version = character_doc.get("schema_version", "unknown")
    
    if doc_version == "unknown":
        # Legacy document, needs migration
        return "needs_migration"
    
    if doc_version == CURRENT_SCHEMA_VERSION:
        return "compatible"
    
    # Parse versions
    doc_major = int(doc_version.split(".")[0])
    current_major = int(CURRENT_SCHEMA_VERSION.split(".")[0])
    
    if doc_major > current_major:
        # Future schema version, cannot read
        return "incompatible"
    
    if doc_major < current_major:
        # Old schema version, needs migration
        return "needs_migration"
    
    # Same major version, compatible with differences
    return "compatible"
```

**Best Practice:**
- Use semantic versioning for `schema_version`
- Major version changes = breaking changes (require migration)
- Minor version changes = backward-compatible additions
- Patch version changes = fixes (no schema change)

---

## Firestore Sizing and Consistency Considerations

### Document Size Management

**Character Document Size Estimates:**
- **Minimal character:** ~2 KB (basic fields only)
- **Typical character:** ~10-20 KB (with player state, quest, combat)
- **Complex character:** ~50-100 KB (with large inventory, detailed stats)
- **Maximum safe size:** 100 KB (leave headroom for Firestore's 1 MB limit)

**Monitoring Document Size:**

⚠️ **IMPORTANT:** The following method provides only a rough approximation of Firestore document size. Due to Firestore's internal binary encoding, actual storage size can differ significantly from JSON estimates, especially for documents with many Timestamp objects, References, or GeoPoints.

```python
import json

character_doc = character_ref.get().to_dict()

# Helper function to serialize Firestore types
def firestore_serializer(obj):
    """Serialize Firestore-specific types for size estimation."""
    if hasattr(obj, 'isoformat'):  # datetime/Timestamp
        return obj.isoformat()
    return str(obj)

# Estimate Firestore document size (in bytes)
doc_size_bytes = len(json.dumps(character_doc, default=firestore_serializer).encode('utf-8'))
doc_size_kb = doc_size_bytes / 1024

if doc_size_kb > 100:
    print(f"Warning: Character document is {doc_size_kb:.2f} KB (consider moving data to subcollections)")
```

**Important Limitations of Size Estimation:**
- **Binary Encoding:** Firestore uses Protocol Buffers internally, which is more space-efficient than JSON for most data
- **Type Overhead:** Firestore-specific types (Timestamps, References, GeoPoints) have different sizes than their JSON string representations
- **Metadata:** Firestore adds metadata that isn't reflected in the document data
- **Inaccuracy Range:** Estimates can be off by 20-50% or more depending on document composition

**For Critical Sizing Decisions:**
1. Test with actual Firestore documents in your project
2. Monitor document sizes via the Firestore console
3. Check quota usage in Google Cloud Console
4. Use Firestore's built-in size limits (1 MB) as a hard constraint, but aim for 100 KB practical limit
5. Consider moving data to subcollections well before approaching the 1 MB limit

**When to Move Data to Subcollections:**
- Arrays with unbounded growth (use subcollections instead)
- Historical data that doesn't need to be loaded every time
- Data that can be queried independently

### Consistency Guarantees

**Strong Consistency (Character Document):**
- All fields in the character document are strongly consistent
- Reads immediately reflect the latest writes
- Transactions ensure atomic updates across multiple fields

**Eventual Consistency (Subcollections):**
- Subcollection queries may not immediately reflect recent writes
- Usually consistent within milliseconds, but not guaranteed
- For real-time applications, consider reading specific documents by ID

**Transaction Example:**
```python
@firestore.transactional
def update_character_level(transaction, character_ref, new_level):
    # Read current state
    character_doc = character_ref.get(transaction=transaction).to_dict()
    
    # Calculate new stats
    new_stats = calculate_stats_for_level(new_level)
    
    # Atomic update
    transaction.update(character_ref, {
        "player_state.level": new_level,
        "player_state.stats": new_stats,
        "updated_at": firestore.SERVER_TIMESTAMP
    })
```

### Query Performance Considerations

**Efficient Queries:**
```python
# Good: Load character without subcollections
character_doc = db.collection("characters").document(character_id).get()

# Good: Load last 10 narrative turns
recent_turns = (db.collection("characters")
                .document(character_id)
                .collection("narrative_turns")
                .order_by("turn_number", direction=firestore.Query.DESCENDING)
                .limit(10)
                .stream())

# Avoid: Loading all turns for every character read (inefficient)
```

**Indexing:**
- Firestore automatically indexes all fields
- Composite indexes needed for complex queries (e.g., `where` + `order_by`)
- Define indexes in `firestore.indexes.json` for production

### Write Frequency Limits

**Firestore Limits:**
- **Document writes:** 1 write per second per document (recommended maximum)
- **Sustained writes:** Can exceed 1/sec, but may be throttled

**Implications:**
- High-frequency updates (e.g., real-time position updates) should be batched
- Use subcollections for frequent writes (e.g., narrative turns)
- Consider caching or local state for rapid updates

**Batched Writes Example:**
```python
# Batch multiple updates together
batch = db.batch()

# Update character
character_ref = db.collection("characters").document(character_id)
batch.update(character_ref, {"player_state.health.current": 95})

# Add narrative turn
turn_ref = character_ref.collection("narrative_turns").document()
batch.set(turn_ref, {
    "turn_id": str(uuid.uuid4()),
    "timestamp": firestore.SERVER_TIMESTAMP,
    "player_action": "Drinks healing potion",
    "gm_response": "You feel refreshed."
})

# Commit all at once
batch.commit()
```

### Cost Considerations

**Read Costs:**
- Each document read = 1 read operation
- Subcollection queries count each document returned
- Use `.limit()` to control read costs

**Write Costs:**
- Each document write/update = 1 write operation
- Batch writes count each document

**Optimization Tips:**
- Cache frequently read data (e.g., character state) on the client
- Use subcollections to avoid reading unnecessary data
- Batch writes when possible to reduce round-trips

---

## Future Considerations

### Planned Schema Enhancements

**Version 1.1.0:**
- Add `skills` map to `player_state` for skill progression
- Add `achievements` array to `additional_metadata`
- Add `party_id` field for multiplayer support

**Version 2.0.0 (Breaking Changes):**
- Separate `player_state` into multiple subcollections for scalability
- Introduce shared world POIs collection (separate from character POIs)
- Add support for multiple active quests

### Migration Path

When introducing schema changes:
1. Increment `schema_version` appropriately
2. Write migration logic (see "Edge Cases and Migration" section)
3. Test migration with a subset of characters
4. Roll out migration gradually (on-demand or batch)
5. Monitor for errors and rollback if needed

---

## Summary

This schema provides a robust foundation for character data storage in Journey Log:

- **Identifier Strategy:** UUIDv4 strings for character_id, generated client or server-side
- **Core State:** Embedded in character document for atomic updates and read efficiency
- **Unbounded Data:** Subcollections for narrative history and POIs to avoid document size limits
- **Schema Versioning:** `schema_version` field for backward compatibility and migrations
- **Timestamps:** Firestore Timestamps for storage, ISO 8601 for APIs
- **Edge Cases:** Lazy subcollection initialization, on-demand migration for legacy documents
- **Firestore Best Practices:** Document size management, consistency guarantees, query optimization

For API endpoint implementation, refer to the character-related routers in `app/routers/` and follow the patterns established in this schema.

---

## Serialization Testing

### Overview

The Journey Log system includes comprehensive round-trip serialization tests to validate that all models can be serialized to Firestore-compatible dictionaries and deserialized back to equivalent model instances without data loss.

**Test Location:** `tests/test_serialization.py`

**Purpose:**
- Ensure models and serializers align correctly
- Prevent silent regressions in serialization logic
- Validate timestamp preservation and timezone handling
- Test edge cases and schema evolution scenarios

### Test Coverage

The serialization test suite includes:

**CharacterDocument Tests:**
- Healthy characters with no quest or combat
- Wounded characters with in-progress quests
- Characters in combat with multiple enemies
- Dead characters with completed quests
- Characters with empty arrays vs. populated arrays
- Schema version variations (including future versions)
- Equipment and inventory serialization
- Additional metadata preservation

**NarrativeTurn Tests:**
- Basic narrative turns with minimal fields
- Turns with full metadata (game state, LLM metrics)
- Turns without optional turn_number field
- Timestamp preservation across timezones
- Timezone conversion to UTC

**PointOfInterest Tests:**
- Minimal POIs with required fields only
- Full POIs with all optional fields
- POIs discovered but not visited
- POIs with partial timestamp data
- Timestamp preservation

**Edge Case Tests:**
- Empty arrays vs. None values
- Multiple entries in arrays (enemies, status effects)
- Schema version increments
- Timezone-aware timestamp equality
- Firestore Timestamp object handling
- Narrative turn ordering metadata

### Running the Tests

To run all serialization tests:

```bash
pytest tests/test_serialization.py -v
```

To run a specific test class:

```bash
pytest tests/test_serialization.py::TestCharacterDocumentRoundTrip -v
```

To run all tests (including serialization):

```bash
pytest tests/ -v
# or
make test
```

### Extending the Tests for Schema Evolution

When adding new fields or modifying the schema:

1. **Add New Fixture Methods:**
   - Create fixtures for new schema variations in `tests/test_serialization.py`
   - Follow the naming convention: `character_<variant>`, `narrative_turn_<variant>`, `poi_<variant>`

2. **Add Round-Trip Test Methods:**
   - Test that the new fields serialize and deserialize correctly
   - Verify optional fields handle None values
   - Test arrays with empty and populated values

3. **Test Compatibility:**
   - Test forward compatibility (old schema → new schema)
   - Test backward compatibility (new schema → old schema)
   - Handle missing fields gracefully with defaults

4. **Update Documentation:**
   - Document schema changes in this file
   - Update the `schema_version` field as appropriate
   - Add migration notes if breaking changes are introduced

**Example: Adding a New Field to CharacterDocument**

```python
# 1. Add fixture with new field
@pytest.fixture
def character_with_new_field(base_player_state):
    return CharacterDocument(
        # ... existing fields ...
        new_field="test_value",  # New field
        schema_version="1.1.0"  # Increment version
    )

# 2. Add round-trip test
def test_character_with_new_field_roundtrip(character_with_new_field):
    data = character_to_firestore(character_with_new_field)
    restored = character_from_firestore(data)
    assert restored.new_field == character_with_new_field.new_field

# 3. Test backward compatibility (missing field)
def test_character_missing_new_field():
    data = {
        # ... required fields ...
        "schema_version": "1.0.0"
        # new_field is missing
    }
    restored = character_from_firestore(data)
    assert restored.new_field is None  # or default value
```

### Key Testing Principles

1. **Timestamp Handling:**
   - All timestamps must be timezone-aware (UTC)
   - Test conversion from different timezone representations
   - Verify timestamps survive round-trips with equality

2. **Optional Fields:**
   - Test None values are excluded from serialization
   - Test missing fields deserialize to None or defaults
   - Distinguish between None and empty arrays/dicts

3. **Schema Versioning:**
   - Always include schema_version in test fixtures
   - Test handling of future schema versions
   - Verify version field survives round-trips unchanged

4. **Arrays and Collections:**
   - Test empty arrays separately from None values
   - Test arrays with multiple entries
   - Verify array ordering is preserved

5. **Nested Structures:**
   - Test deeply nested models (combat_state, active_quest)
   - Verify all nested fields survive round-trips
   - Test optional nested structures (None vs. populated)

### Continuous Integration

The serialization tests are run automatically:
- On every pull request
- On every commit to main
- As part of the full test suite (`make test`)

All serialization tests must pass before merging code changes.

---

## API Endpoints

### Character Management Endpoints

The Journey Log API provides RESTful endpoints for managing character documents. All character endpoints are prefixed with `/characters`.

#### List Characters

**Endpoint:** `GET /characters`

**Description:** Retrieve all character saves for a user to drive save-slot UIs. Returns lightweight metadata for each character owned by the user.

**Required Headers:**
- `X-User-Id` (string): User identifier for ownership and access control

**Optional Query Parameters:**
- `limit` (integer): Maximum number of characters to return (default: unlimited)
- `offset` (integer): Number of characters to skip for pagination (default: 0)

**Response Format:**
```json
{
  "characters": [
    {
      "character_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Aragorn",
      "race": "Human",
      "class": "Ranger",
      "status": "Healthy",
      "created_at": "2026-01-10T10:00:00Z",
      "updated_at": "2026-01-11T12:00:00Z"
    }
  ],
  "count": 1
}
```

**Response Fields:**
- `characters` (array): List of character metadata objects
  - `character_id` (string): UUID character identifier
  - `name` (string): Character name (from `player_state.identity.name`, defaults to "Unknown" if missing)
  - `race` (string): Character race (from `player_state.identity.race`, defaults to "Unknown" if missing)
  - `class` (string): Character class (from `player_state.identity.class`, defaults to "Unknown" if missing)
  - `status` (string): Character health status - "Healthy", "Wounded", or "Dead" (defaults to "Healthy" if missing)
  - `created_at` (string): ISO 8601 timestamp of character creation
  - `updated_at` (string): ISO 8601 timestamp of last update
- `count` (integer): Number of characters returned in this response (after pagination is applied, not the total count of all user's characters)

**Sorting:**
Results are sorted by `updated_at` descending (most recently updated first).

**Pagination:**
Use `limit` and `offset` parameters for pagination:
- First page: `GET /characters?limit=10`
- Second page: `GET /characters?limit=10&offset=10`
- Third page: `GET /characters?limit=10&offset=20`

**Error Responses:**
- `400 Bad Request`: Missing or empty `X-User-Id` header
- `422 Unprocessable Entity`: Missing required `X-User-Id` header
- `500 Internal Server Error`: Firestore or internal errors

**Access Control:**
- Only returns characters owned by the user specified in `X-User-Id`
- Empty array `[]` returned if user has no characters
- Never returns other users' characters

**Example Requests:**
```bash
# List all characters for a user
curl -H "X-User-Id: user123" http://localhost:8080/characters

# List first 5 characters
curl -H "X-User-Id: user123" "http://localhost:8080/characters?limit=5"

# List next 5 characters (pagination)
curl -H "X-User-Id: user123" "http://localhost:8080/characters?limit=5&offset=5"
```

**Edge Cases:**
- Missing `X-User-Id` header yields 422 error before Firestore query
- Empty `X-User-Id` header yields 400 error
- Legacy documents lacking `status` default to "Healthy" in projection
- Users with high save counts receive deterministic pagination when `limit` provided
- Firestore query timeouts handled gracefully with 500 error and logging

---

#### Get Narrative Turns

**Endpoint:** `GET /characters/{character_id}/narrative`

**Description:** Retrieve the last N narrative turns for a character ordered oldest-to-newest with optional time filtering. This endpoint provides recent narrative context for LLMs or UI display.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Optional Headers:**
- `X-User-Id` (string): User identifier for access control
  - If provided but empty/whitespace-only, returns 400 error
  - If omitted entirely, allows anonymous access without verification
  - If provided, must match the character's owner_user_id

**Optional Query Parameters:**
- `n` (integer): Number of turns to retrieve (default: 10, min: 1, max: 100)
- `since` (string): ISO 8601 timestamp to filter turns after this time (optional)

**Response Format:**
```json
{
  "turns": [
    {
      "turn_id": "turn-001",
      "turn_number": 1,
      "player_action": "I explore the ancient ruins",
      "gm_response": "You discover a hidden chamber",
      "timestamp": "2026-01-11T12:00:00Z",
      "game_state_snapshot": null,
      "metadata": null
    }
  ],
  "metadata": {
    "requested_n": 10,
    "returned_count": 1,
    "total_available": 5
  }
}
```

**Response Fields:**
- `turns` (array): List of NarrativeTurn objects ordered oldest-to-newest (chronological reading order)
  - `turn_id` (string): Unique turn identifier (UUIDv4)
  - `turn_number` (integer, nullable): Sequential turn counter
  - `player_action` (string): Player's action or input (max 8000 characters)
  - `gm_response` (string): Game master's/AI's response (max 32000 characters)
  - `timestamp` (string): ISO 8601 timestamp when the turn occurred
  - `game_state_snapshot` (object, nullable): Snapshot of game state at this turn
  - `metadata` (object, nullable): Additional turn metadata (LLM metrics, etc.)
- `metadata` (object): Query result metadata
  - `requested_n` (integer): Number of turns requested (n parameter value)
  - `returned_count` (integer): Number of turns actually returned (may be less than requested)
  - `total_available` (integer): Total number of turns available for this character (matching filters)

**Ordering:**
- Results are always returned in chronological order (oldest first)
- This ensures LLM context is built in the correct sequence
- Query internally uses descending order for efficiency, then reverses results

**Time Filtering:**
- Use `since` parameter to retrieve only turns **after** a specific timestamp (strict inequality: `timestamp > since`)
- The filter applies before selecting the N most recent turns, ensuring you get the most recent turns from the filtered set
- Useful for incremental updates or pagination by time
- Empty list returned with 200 status if no turns match the filter
- Note: If you need to include turns at the exact timestamp, consider using a timestamp slightly before the desired cutoff

**Error Responses:**
- `400 Bad Request`: Invalid query parameters (n out of range, invalid since timestamp) or empty X-User-Id
- `403 Forbidden`: X-User-Id provided but does not match character owner
- `404 Not Found`: Character not found
- `422 Unprocessable Entity`: Invalid UUID format for character_id
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Get last 10 turns (default)
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/narrative

# Get last 5 turns
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=5"

# Get last 20 turns with access control
curl -H "X-User-Id: user123" \
  "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=20"

# Get turns since a specific timestamp
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/narrative?since=2026-01-11T12:00:00Z"

# Combine n and since parameters
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=50&since=2026-01-10T00:00:00Z"
```

**Edge Cases:**
- `n` greater than available turns returns all available turns without error
- `since` timestamp newer than all stored turns returns empty list with 200 status
- Character with no narrative turns returns empty array with 200 status
- Requests near max limit (100) remain efficient via indexed timestamp queries
- Missing `X-User-Id` allows anonymous access (useful for public character viewing)
- Empty/whitespace-only `X-User-Id` returns 400 error (client error)

**Performance Notes:**
- Queries use Firestore's built-in timestamp index for efficiency
- Count aggregation is efficient but incurs one document read cost
- Max limit (100) balances context needs with query performance
- Consider caching results client-side for frequently accessed narratives

---

### POI Management Endpoints

Points of Interest (POIs) are stored in the character's `world_pois` array (max 200 entries). These endpoints allow Directors to add POIs, retrieve all POIs, or sample random POIs for contextual world-building.

**POI Storage Model:**
- **Embedded POIs** (`world_pois` array): Character-specific discovered POIs, limited to 200 entries. Used by these API endpoints.
- **World POI Reference** (`world_pois_reference` field): String reference to world-global POI configuration (e.g., "world-v1" or "characters/{id}/pois"). This field indicates where the character's world POIs originate from, separate from character-specific discoveries.
- **POI Subcollection** (optional): For unbounded POI data, characters can have a `pois/` subcollection referenced by `world_pois_reference`. Not currently exposed via these API endpoints.

The API endpoints documented below operate on the **embedded `world_pois` array** within the character document for performance and simplicity.

#### Create POI

**Endpoint:** `POST /characters/{character_id}/pois`

**Description:** Add a new Point of Interest to a character's world_pois array. Each POI is assigned a unique ID and optional timestamp. This endpoint is used by Directors to record discovered locations, landmarks, dungeons, or other notable places in the game world.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Required Headers:**
- `X-User-Id` (string): User identifier (must match character owner for access control)

**Request Body:**
```json
{
  "name": "Ancient Dragon's Lair",
  "description": "A vast cavern system deep beneath the mountains, rumored to house an ancient red dragon and untold treasures.",
  "timestamp": "2026-01-11T14:30:00Z",
  "tags": ["dungeon", "dragon", "mountain", "high-danger"]
}
```

**Request Fields:**
- `name` (string, required): POI name (minimum 1 character, maximum 200 characters)
- `description` (string, required): POI description (minimum 1 character, maximum 2000 characters)
- `timestamp` (string, optional): ISO 8601 timestamp when POI was discovered. Defaults to server UTC now if omitted. Note: The response will return this as `created_at`.
- `tags` (array of strings, optional): List of tags for categorizing the POI
  - Maximum 20 tags in the array
  - Each tag maximum 50 characters
  - Tags cannot be empty or only whitespace

**Response Format:**
```json
{
  "poi": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Ancient Dragon's Lair",
    "description": "A vast cavern system deep beneath the mountains, rumored to house an ancient red dragon and untold treasures.",
    "created_at": "2026-01-11T14:30:00Z",
    "tags": ["dungeon", "dragon", "mountain", "high-danger"]
  }
}
```

**Response Fields:**
- `poi` (object): The created PointOfInterest with server-assigned ID and timestamp
  - `id` (string): Unique POI identifier (UUIDv4, server-generated)
  - `name` (string): POI name
  - `description` (string): POI description
  - `created_at` (string): ISO 8601 timestamp when POI was created
  - `tags` (array of strings, nullable): Tags for categorizing the POI

**Storage Capacity:**
- Maximum 200 POIs per character (enforced by `world_pois` array limit)
- Attempting to add a POI when at capacity returns 400 Bad Request
- Consider archiving or removing old POIs before adding new ones

**Atomicity:**
Uses Firestore transaction to atomically:
1. Verify character exists and user owns it
2. Check `world_pois` array is not at capacity (200 max)
3. Generate unique POI ID and append to array
4. Update character.updated_at timestamp

**Error Responses:**
- `400 Bad Request`: Missing/invalid X-User-Id header, POI capacity exceeded (200 max)
- `403 Forbidden`: X-User-Id does not match character owner
- `404 Not Found`: Character not found
- `422 Unprocessable Entity`: Validation error (invalid UUID, oversized fields, invalid timestamp, too many/long tags)
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Add a POI with server-generated timestamp
curl -X POST http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Whispering Woods",
    "description": "A mysterious forest where the trees seem to whisper ancient secrets."
  }'

# Add a POI with explicit timestamp and tags
curl -X POST http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Abandoned Temple",
    "description": "An overgrown temple dedicated to a forgotten deity.",
    "timestamp": "2026-01-11T10:00:00Z",
    "tags": ["temple", "ruins", "exploration"]
  }'

# HTTPie example
http POST http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois \
  X-User-Id:user123 \
  name="Haunted Mansion" \
  description="A decrepit mansion on the hill, locals say it's cursed."
```

**Edge Cases:**
- Duplicate POI names are allowed (each has a unique ID)
- Empty tags array is valid (tags are optional)
- Timestamps in the past are accepted (for backfilling historical discoveries)
- Timestamps in the future are accepted (no validation, but may affect sorting)
- When capacity (200) is reached, returns clear error message suggesting archival

---

#### Get Random POIs

**Endpoint:** `GET /characters/{character_id}/pois/random`

**Description:** Retrieve N randomly sampled POIs from a character's world_pois array without replacement. This endpoint is useful for Directors who want to inject contextual variety into narratives by referencing previously discovered locations. Sampling is non-deterministic - the same request may return different POIs on each call.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Optional Headers:**
- `X-User-Id` (string): User identifier for access control
  - If provided but empty/whitespace-only, returns 400 error
  - If omitted entirely, allows anonymous access without verification
  - If provided, must match the character's owner_user_id

**Optional Query Parameters:**
- `n` (integer): Number of POIs to sample (default: 3, min: 1, max: 20)

**Response Format:**
```json
{
  "pois": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Ancient Dragon's Lair",
      "description": "A vast cavern system deep beneath the mountains.",
      "created_at": "2026-01-11T14:30:00Z",
      "tags": ["dungeon", "dragon", "mountain", "high-danger"]
    },
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "name": "Whispering Woods",
      "description": "A mysterious forest where the trees whisper.",
      "created_at": "2026-01-11T15:00:00Z",
      "tags": null
    }
  ],
  "count": 2,
  "requested_n": 3,
  "total_available": 15
}
```

**Response Fields:**
- `pois` (array): Randomly sampled POIs (up to N)
- `count` (integer): Number of POIs returned (may be less than requested_n if fewer POIs exist)
- `requested_n` (integer): Number of POIs requested (n parameter value)
- `total_available` (integer): Total number of POIs available for this character

**Sampling Behavior:**
- POIs are sampled uniformly at random without replacement
- If fewer than N POIs exist, returns all available POIs (no error)
- If no POIs exist, returns empty list with count=0 (not an error)
- Same request may return different POIs on each call (non-deterministic)
- Default sampling limit: 3 POIs (configurable via n parameter)
- Maximum sampling limit: 20 POIs (enforced by validation)

**Default Limits:**
- Default n=3: Provides enough context without overwhelming the narrative
- Maximum n=20: Balances response size with utility for Directors

**Error Responses:**
- `400 Bad Request`: Invalid query parameters (n <= 0 or n > 20) or empty X-User-Id
- `403 Forbidden`: X-User-Id provided but does not match character owner
- `404 Not Found`: Character not found
- `422 Unprocessable Entity`: Invalid UUID format for character_id
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Get 3 random POIs (default)
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/random

# Get 5 random POIs
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/random?n=5"

# Get 10 random POIs with access control
curl -H "X-User-Id: user123" \
  "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/random?n=10"

# HTTPie example
http GET http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/random \
  n==7 \
  X-User-Id:user123
```

**Edge Cases:**
- When POI count < n: Returns all available POIs without error (e.g., requesting 5 but only 3 exist returns 3)
- When POI count = 0: Returns empty array with count=0, total_available=0
- When n=1: Returns single random POI (useful for "surprise encounter" mechanics)
- When n >= total_available: Returns all POIs in random order
- Missing `X-User-Id` allows anonymous access (useful for public character viewing)
- Empty/whitespace-only `X-User-Id` returns 400 error (client error)

**Use Cases for Directors:**
- Inject previously discovered locations into narrative prompts
- Create random encounters at familiar locations
- Remind players of unexplored areas
- Generate location-based quest hooks

---

#### Get All POIs

**Endpoint:** `GET /characters/{character_id}/pois`

**Description:** Retrieve all POIs for a character sorted by created_at descending (newest first). This endpoint supports pagination for characters with many POIs. Directors can use this to review all discovered locations or to populate UI elements showing the character's exploration history.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Optional Headers:**
- `X-User-Id` (string): User identifier for access control
  - If provided but empty/whitespace-only, returns 400 error
  - If omitted entirely, allows anonymous access without verification
  - If provided, must match the character's owner_user_id

**Optional Query Parameters:**
- `limit` (integer): Maximum number of POIs to return (default: unlimited, max: 200)
- `cursor` (string): Pagination cursor from previous response (None for first page)

**Response Format:**
```json
{
  "pois": [
    {
      "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "name": "Crystal Cavern",
      "description": "A glittering cave filled with luminescent crystals.",
      "created_at": "2026-01-12T08:00:00Z",
      "tags": ["cave", "magic", "rare-resource"]
    },
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Ancient Dragon's Lair",
      "description": "A vast cavern system deep beneath the mountains.",
      "created_at": "2026-01-11T14:30:00Z",
      "tags": ["dungeon", "dragon", "mountain", "high-danger"]
    }
  ],
  "count": 2,
  "cursor": "10"
}
```

**Response Fields:**
- `pois` (array): List of POIs sorted by created_at descending (newest first)
- `count` (integer): Number of POIs returned in this response
- `cursor` (string, nullable): Pagination cursor for next page (null if no more results)

**Pagination:**
- Results are sorted by `created_at` descending (newest first)
- Use `limit` to control page size
- Use `cursor` from previous response to get next page
- When cursor is exhausted (null), no more pages available
- Simple offset-based pagination: cursor is the integer index for next page start

**Sorting:**
- POIs are sorted by `created_at` timestamp descending (newest discoveries first)
- POIs without `created_at` timestamp are sorted to the end (using datetime.min as fallback)

**Error Responses:**
- `400 Bad Request`: Invalid query parameters (limit out of range 1-200, invalid cursor) or empty X-User-Id
- `403 Forbidden`: X-User-Id provided but does not match character owner
- `404 Not Found`: Character not found
- `422 Unprocessable Entity`: Invalid UUID format for character_id
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Get all POIs (no pagination)
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois

# Get first 10 POIs
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois?limit=10"

# Get next 10 POIs using cursor from previous response
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois?limit=10&cursor=10"

# Get all POIs with access control
curl -H "X-User-Id: user123" \
  http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois

# HTTPie example with pagination
http GET http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois \
  limit==20 \
  cursor==0 \
  X-User-Id:user123
```

**Edge Cases:**
- Character with no POIs returns empty array (not an error)
- When limit > remaining POIs: Returns all remaining POIs with cursor=null
- Invalid cursor format returns 400 error with clear message
- Missing `created_at` timestamps are handled gracefully (sorted to end)
- Requesting all POIs without limit returns entire array (up to 200 max)

---

### Quest Management Endpoints

Quest management follows a **single-active-quest invariant**: only one quest can be active per character at any time. This design simplifies narrative focus and prevents quest conflict. Completed quests are automatically archived when deleted, maintaining a history of up to 50 quests (oldest removed first).

#### Set Active Quest

**Endpoint:** `PUT /characters/{character_id}/quest`

**Description:** Set or update the active quest for a character. Only one quest can be active at a time - attempting to set a quest when one already exists returns 409 Conflict. Directors must DELETE the existing quest before setting a new one to enforce intentional quest progression.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Required Headers:**
- `X-User-Id` (string): User identifier (must match character owner for access control)

**Request Body:**
```json
{
  "name": "Retrieve the Lost Amulet",
  "description": "The village elder has tasked you with recovering the Amulet of Light from the Ancient Dragon's Lair. The amulet was stolen decades ago and is said to protect the village from dark forces.",
  "requirements": [
    "Locate the Ancient Dragon's Lair",
    "Defeat or negotiate with the dragon",
    "Retrieve the Amulet of Light"
  ],
  "rewards": {
    "items": ["Amulet of Light", "Dragon Scale Shield"],
    "currency": {
      "gold": 500,
      "reputation": 100
    },
    "experience": 1000
  },
  "completion_state": "in_progress",
  "updated_at": "2026-01-11T15:00:00Z"
}
```

**Request Fields:**
- `name` (string, required): Quest name
- `description` (string, required): Quest description/objectives
- `requirements` (array of strings, optional): List of quest requirement descriptions (default: [])
- `rewards` (object, required): Quest rewards upon completion
  - `items` (array of strings, optional): List of item names awarded (default: [])
  - `currency` (object, optional): Currency rewards as name:amount pairs (default: {}, amounts must be non-negative)
  - `experience` (integer, optional, nullable): Experience points awarded (must be non-negative)
- `completion_state` (string, required): Quest status - must be one of: `"not_started"`, `"in_progress"`, or `"completed"`
- `updated_at` (string, required): ISO 8601 timestamp when quest was last updated

**Response Format:**
```json
{
  "quest": {
    "name": "Retrieve the Lost Amulet",
    "description": "The village elder has tasked you with recovering the Amulet of Light...",
    "requirements": [
      "Locate the Ancient Dragon's Lair",
      "Defeat or negotiate with the dragon",
      "Retrieve the Amulet of Light"
    ],
    "rewards": {
      "items": ["Amulet of Light", "Dragon Scale Shield"],
      "currency": {
        "gold": 500,
        "reputation": 100
      },
      "experience": 1000
    },
    "completion_state": "in_progress",
    "updated_at": "2026-01-11T15:00:00Z"
  }
}
```

**Response Fields:**
- `quest` (object): The stored Quest object with all fields as provided in request

**Single-Active-Quest Invariant:**
- Only one active quest is allowed per character
- Attempting to set a quest when one already exists returns **409 Conflict**
- The 409 response includes guidance to DELETE the existing quest first
- This enforces intentional quest progression and prevents conflicts
- Directors must explicitly clear the current quest before setting a new one

**Atomicity:**
Uses Firestore transaction to atomically:
1. Verify character exists and user owns it
2. Check that no active quest exists (enforces single-quest invariant)
3. Set `active_quest` field with validated Quest data
4. Update character.updated_at timestamp

**Error Responses:**
- `400 Bad Request`: Missing/invalid X-User-Id header
- `403 Forbidden`: X-User-Id does not match character owner
- `404 Not Found`: Character not found
- `409 Conflict`: Active quest already exists (DELETE required before replacing)
- `422 Unprocessable Entity`: Validation error (invalid UUID, invalid completion_state, negative currency/experience, empty currency keys)
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Set a new quest with minimal rewards
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Explore the Whispering Woods",
    "description": "Investigate strange sounds coming from the forest.",
    "requirements": ["Enter the forest", "Find the source of whispers"],
    "rewards": {
      "items": [],
      "currency": {},
      "experience": 100
    },
    "completion_state": "not_started",
    "updated_at": "2026-01-11T10:00:00Z"
  }'

# Set a quest with complex rewards
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Defeat the Necromancer",
    "description": "The necromancer threatens the kingdom. Defeat him.",
    "requirements": ["Gather allies", "Storm the tower", "Defeat necromancer"],
    "rewards": {
      "items": ["Staff of Light", "Crown of Heroes"],
      "currency": {"gold": 1000, "gems": 50},
      "experience": 5000
    },
    "completion_state": "in_progress",
    "updated_at": "2026-01-12T08:00:00Z"
  }'

# HTTPie example
http PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  X-User-Id:user123 \
  name="Find the Hidden Treasure" \
  description="A map was discovered pointing to buried treasure." \
  requirements:='["Decode the map", "Travel to the island", "Dig for treasure"]' \
  rewards:='{"items": ["Treasure Chest"], "currency": {"gold": 2000}, "experience": 500}' \
  completion_state="not_started" \
  updated_at="2026-01-11T12:00:00Z"
```

**Edge Cases:**
- When active quest exists: Returns **409 Conflict** with clear error message
  - Error message: "An active quest already exists for this character. Please DELETE the existing quest before setting a new one."
  - This enforces the single-active-quest invariant
- Empty requirements array is valid (optional objectives)
- Empty rewards.items array is valid
- Empty rewards.currency dict is valid (quest gives only experience)
- Null experience is valid (quest gives only items/currency)
- Currency keys must be non-empty strings
- Currency amounts and experience must be non-negative (validated by model)

---

#### Get Active Quest

**Endpoint:** `GET /characters/{character_id}/quest`

**Description:** Retrieve the active quest for a character. Returns the Quest object if one exists, or null if no active quest. Directors can use this to check quest status or retrieve quest details for narrative context.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Optional Headers:**
- `X-User-Id` (string): User identifier for access control
  - If provided but empty/whitespace-only, returns 400 error
  - If omitted entirely, allows anonymous access without verification
  - If provided, must match the character's owner_user_id

**Response Format (quest exists):**
```json
{
  "quest": {
    "name": "Retrieve the Lost Amulet",
    "description": "The village elder has tasked you with recovering the Amulet of Light...",
    "requirements": [
      "Locate the Ancient Dragon's Lair",
      "Defeat or negotiate with the dragon",
      "Retrieve the Amulet of Light"
    ],
    "rewards": {
      "items": ["Amulet of Light", "Dragon Scale Shield"],
      "currency": {
        "gold": 500,
        "reputation": 100
      },
      "experience": 1000
    },
    "completion_state": "in_progress",
    "updated_at": "2026-01-11T15:00:00Z"
  }
}
```

**Response Format (no quest):**
```json
{
  "quest": null
}
```

**Response Fields:**
- `quest` (object or null): The active Quest object or null if no active quest exists

**Error Responses:**
- `400 Bad Request`: X-User-Id header provided but empty/whitespace-only
- `403 Forbidden`: X-User-Id provided but does not match character owner
- `404 Not Found`: Character not found
- `422 Unprocessable Entity`: Invalid UUID format for character_id
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Get active quest (anonymous access)
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest

# Get active quest with access control
curl -H "X-User-Id: user123" \
  http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest

# HTTPie example
http GET http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  X-User-Id:user123
```

**Edge Cases:**
- Character with no active quest returns `{"quest": null}` (not an error, 200 status)
- Missing `X-User-Id` allows anonymous access (useful for public character viewing)
- Empty/whitespace-only `X-User-Id` returns 400 error (client error)

---

#### Delete Active Quest

**Endpoint:** `DELETE /characters/{character_id}/quest`

**Description:** Clear the active quest for a character and automatically archive it to the `archived_quests` array. This operation is idempotent - succeeds even if no active quest exists. The archived quest is stored with a `cleared_at` timestamp for history tracking. The archived_quests array maintains a maximum of 50 entries (oldest removed first when limit exceeded).

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Required Headers:**
- `X-User-Id` (string): User identifier (must match character owner for access control)

**Response:**
- **204 No Content**: Quest successfully deleted (or no quest existed)
- No response body

**Archival Behavior:**
- When a quest is deleted, it is automatically appended to `archived_quests` array
- Each archived entry includes:
  - `quest`: The full Quest object
  - `cleared_at`: ISO 8601 timestamp when the quest was cleared
- Maximum 50 archived quests maintained (oldest entries removed first when exceeded)
- Provides quest history for Directors and players

**Atomicity:**
Uses Firestore transaction to atomically:
1. Verify character exists and user owns it
2. Remove `active_quest` field (set to null)
3. Append quest to `archived_quests` array with `cleared_at` timestamp
4. Trim `archived_quests` to maintain ≤50 entries (oldest first)
5. Update character.updated_at timestamp

**Idempotency:**
- Operation succeeds even if no active quest exists
- Returns 204 No Content in both cases (quest deleted or already absent)
- Safe to call multiple times without side effects

**Error Responses:**
- `400 Bad Request`: Missing/invalid X-User-Id header
- `403 Forbidden`: X-User-Id does not match character owner
- `404 Not Found`: Character not found
- `422 Unprocessable Entity`: Invalid UUID format for character_id
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Delete active quest
curl -X DELETE http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "X-User-Id: user123"

# HTTPie example
http DELETE http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  X-User-Id:user123

# Expected success response (no body, 204 status)
# HTTP/1.1 204 No Content
```

**Edge Cases:**
- When no active quest exists: Succeeds with 204 (idempotent, no-op)
- When `archived_quests` reaches 50 entries: Oldest quest is removed before adding new one
- Empty `archived_quests` array is created if it doesn't exist
- Quest with all null optional fields still gets archived correctly

**Workflow Example:**
```bash
# 1. Set initial quest
curl -X PUT http://localhost:8080/characters/<ID>/quest -H "X-User-Id: user123" -d '{...}'
# Success: 200 OK

# 2. Try to set another quest without deleting first
curl -X PUT http://localhost:8080/characters/<ID>/quest -H "X-User-Id: user123" -d '{...}'
# Error: 409 Conflict - "An active quest already exists..."

# 3. Delete existing quest (archives it)
curl -X DELETE http://localhost:8080/characters/<ID>/quest -H "X-User-Id: user123"
# Success: 204 No Content

# 4. Now can set new quest
curl -X PUT http://localhost:8080/characters/<ID>/quest -H "X-User-Id: user123" -d '{...}'
# Success: 200 OK
```

---

### Combat Management Endpoints

Combat management endpoints allow Directors to manage combat encounters for characters. The system enforces a maximum of 5 enemies per combat and automatically computes combat active/inactive status based on enemy health.

#### Update Combat State

**Endpoint:** `PUT /characters/{character_id}/combat`

**Description:** Set or clear the combat state for a character with full state replacement. The server automatically computes whether combat is active based on enemy statuses.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Required Headers:**
- `X-User-Id` (string): User identifier (must match character owner for access control)

**Request Body:**
```json
{
  "combat_state": {
    "combat_id": "combat_123",
    "started_at": "2026-01-11T14:30:00Z",
    "turn": 1,
    "enemies": [
      {
        "enemy_id": "orc_001",
        "name": "Orc Warrior",
        "status": "Wounded",
        "weapon": "Rusty Axe",
        "traits": ["aggressive", "armored"]
      },
      {
        "enemy_id": "goblin_002",
        "name": "Goblin Archer",
        "status": "Healthy",
        "weapon": "Short Bow",
        "traits": ["ranged", "cowardly"]
      }
    ],
    "player_conditions": {
      "status_effects": [],
      "temporary_buffs": ["shield_of_valor"]
    }
  }
}
```

**Request Fields:**
- `combat_state` (object or null, required): CombatState object to set, or null to clear combat
  - `combat_id` (string, required): Unique combat identifier
  - `started_at` (string, required): ISO 8601 timestamp when combat started
  - `turn` (integer, optional): Current combat turn (≥1, default: 1)
  - `enemies` (array, required): List of EnemyState objects (max 5)
    - `enemy_id` (string, required): Unique enemy identifier
    - `name` (string, required): Enemy display name
    - `status` (string, required): Enemy health status - "Healthy", "Wounded", or "Dead"
    - `weapon` (string, optional): Weapon wielded by the enemy
    - `traits` (array of strings, optional): List of enemy traits or characteristics (default: [])
    - `metadata` (object, optional): Additional enemy metadata
  - `player_conditions` (object, optional): Player status effects and conditions

**Response Format:**
```json
{
  "active": true,
  "state": {
    "combat_id": "combat_123",
    "started_at": "2026-01-11T14:30:00Z",
    "turn": 1,
    "enemies": [
      {
        "enemy_id": "orc_001",
        "name": "Orc Warrior",
        "status": "Wounded",
        "weapon": "Rusty Axe",
        "traits": ["aggressive", "armored"]
      },
      {
        "enemy_id": "goblin_002",
        "name": "Goblin Archer",
        "status": "Healthy",
        "weapon": "Short Bow",
        "traits": ["ranged", "cowardly"]
      }
    ],
    "player_conditions": {
      "status_effects": [],
      "temporary_buffs": ["shield_of_valor"]
    }
  }
}
```

**Response Fields:**
- `active` (boolean): Whether combat is currently active
  - `true` when at least one enemy has status != "Dead"
  - `false` when all enemies are "Dead" or enemies list is empty or combat_state is null
- `state` (object or null): Current combat state
  - Same structure as request CombatState
  - `null` when combat is cleared (combat_state: null in request)

**Server-Side Active Status Computation:**
The server automatically computes `active` based on enemy statuses:
- `active=true`: At least one enemy has status != "Dead"
- `active=false`: All enemies are "Dead" OR enemies list is empty OR combat_state is null

**Validation Rules:**
- Maximum 5 enemies per combat (enforced at model validation layer)
- All enemy statuses must be valid enum values: "Healthy", "Wounded", or "Dead"
- Payloads with >5 enemies are rejected with 422 Unprocessable Entity error before Firestore writes
- Empty enemies array is valid and sets active=false
- Unknown enemy statuses cause 422 Unprocessable Entity validation errors with detailed field-level error messages

**Atomicity:**
Uses Firestore transaction to atomically:
1. Verify character exists and user owns it
2. Update combat_state field (or clear to null)
3. Update character.updated_at timestamp
4. Log when combat transitions from active to inactive

**Storage Isolation:**
Firestore writes to combat_state use transactions to avoid clobbering unrelated character fields. Combat state updates do not overwrite narrative, quest, or other character data.

**Error Responses:**
- `400 Bad Request`: Missing or invalid X-User-Id header
- `403 Forbidden`: X-User-Id does not match character owner
- `404 Not Found`: Character not found
- `422 Unprocessable Entity`: Validation error (>5 enemies, invalid status, missing required fields, invalid UUID)
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Set combat with 2 enemies
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "combat_state": {
      "combat_id": "combat_001",
      "started_at": "2026-01-11T14:30:00Z",
      "turn": 1,
      "enemies": [
        {
          "enemy_id": "orc_001",
          "name": "Orc Warrior",
          "status": "Healthy",
          "weapon": "Battle Axe",
          "traits": ["aggressive"]
        },
        {
          "enemy_id": "goblin_001",
          "name": "Goblin Scout",
          "status": "Wounded",
          "weapon": "Dagger",
          "traits": ["cowardly", "quick"]
        }
      ]
    }
  }'

# Clear combat state
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{"combat_state": null}'

# Update combat with all enemies dead (returns active=false)
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "combat_state": {
      "combat_id": "combat_001",
      "started_at": "2026-01-11T14:30:00Z",
      "turn": 5,
      "enemies": [
        {
          "enemy_id": "orc_001",
          "name": "Orc Warrior",
          "status": "Dead",
          "weapon": "Battle Axe",
          "traits": []
        },
        {
          "enemy_id": "goblin_001",
          "name": "Goblin Scout",
          "status": "Dead",
          "weapon": "Dagger",
          "traits": []
        }
      ]
    }
  }'
```

**Edge Cases:**
- Submitting >5 enemies returns 422 with detailed error message
- Submitting null clears combat and returns `{"active": false, "state": null}`
- All enemies Dead returns `{"active": false, "state": <combat_state>}` per acceptance criteria
- Empty enemies array sets active=false: `{"active": false, "state": <combat_state with empty enemies>}`
- Race conditions: Last writer wins without corrupting other fields (transactional writes)
- Unknown status strings cause explicit validation errors at request boundary
- Directors can jump directly to "Dead" status without intermediate states

---

#### Get Combat State

**Endpoint:** `GET /characters/{character_id}/combat`

**Description:** Retrieve the current combat state for a character with a predictable JSON envelope. This endpoint always returns an `active` flag and `state` field, providing a stable response format for Directors.

**Path Parameters:**
- `character_id` (string, required): UUID-formatted character identifier

**Optional Headers:**
- `X-User-Id` (string): User identifier for access control
  - If provided but empty/whitespace-only, returns 400 error
  - If omitted entirely, allows anonymous access without verification
  - If provided, must match the character's owner_user_id

**Response Format (active combat):**
```json
{
  "active": true,
  "state": {
    "combat_id": "combat_123",
    "started_at": "2026-01-11T14:30:00Z",
    "turn": 3,
    "enemies": [
      {
        "enemy_id": "orc_001",
        "name": "Orc Warrior",
        "status": "Wounded",
        "weapon": "Battle Axe",
        "traits": ["aggressive"]
      }
    ],
    "player_conditions": {
      "status_effects": ["blessed"],
      "temporary_buffs": []
    }
  }
}
```

**Response Format (inactive combat):**
```json
{
  "active": false,
  "state": null
}
```

**Response Fields:**
- `active` (boolean): Whether combat is currently active
  - `true` when any enemy has status != "Dead"
  - `false` when combat_state is null/missing, enemies list is empty, or all enemies are "Dead"
- `state` (object or null): Current combat state
  - Full CombatState object when combat exists and is active
  - `null` when combat is inactive (per acceptance criteria for stable inactive response)

**Inactive Response Behavior:**
The endpoint returns `{"active": false, "state": null}` when:
- `combat_state` field is None/missing in the character document
- `enemies` list is empty
- All enemies have status == "Dead"

This stable inactive response format ensures Directors can reliably detect combat end conditions.

**Response Consistency:**
- Uses the same CombatState serialization as PUT responses
- Respects the ≤5 enemies constraint (defensive filtering on read for legacy data)
- All fields (active status, traits, weapons) stay consistent with PUT responses
- Always returns HTTP 200 with JSON object (never 204 No Content)

**Error Responses:**
- `400 Bad Request`: X-User-Id header provided but empty/whitespace-only
- `403 Forbidden`: X-User-Id provided but does not match character owner
- `404 Not Found`: Character not found (NOT returned for 'no combat active' case)
- `422 Unprocessable Entity`: Invalid UUID format for character_id
- `500 Internal Server Error`: Firestore transient errors

**Example Requests:**
```bash
# Get combat state (anonymous access)
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat

# Get combat state with access control
curl -H "X-User-Id: user123" \
  http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat

# HTTPie example
http GET http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  X-User-Id:user123
```

**Edge Cases:**
- Character with no combat history returns `{"active": false, "state": null}` (not an error, 200 status)
- Stored documents with >5 enemies (legacy data from before validation was added) are handled defensively: the endpoint returns `{"active": false, "state": null}` to avoid exposing invalid data. The server logs a warning about the legacy data violation. Directors should use PUT to fix the combat state with ≤5 enemies.
- Race conditions where combat cleared between read start/finish return inactive safely
- Malformed stored data is handled gracefully with fallback to inactive response
- Missing `X-User-Id` allows anonymous access (useful for public character viewing)
- Empty/whitespace-only `X-User-Id` returns 400 error (client error)

**Operational Notes:**
- Directors control combat lifecycle - server stores what it receives
- Status transitions are unrestricted (Directors can jump directly to "Dead")
- Payloads with zero enemies are valid and will clear combat
- Inactive responses stay stable even if HTTP status is 200 rather than 204
- Logging/metrics track combat transitions for operational monitoring

---

## References

- [Firestore Data Model](https://cloud.google.com/firestore/docs/data-model)
- [Firestore Best Practices](https://cloud.google.com/firestore/docs/best-practices)
- [Firestore Quotas and Limits](https://cloud.google.com/firestore/quotas)
- [UUID RFC 4122](https://tools.ietf.org/html/rfc4122)
- [Semantic Versioning](https://semver.org/)
