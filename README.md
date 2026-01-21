# Journey Log API

A FastAPI-based service for managing journey logs and entries. Built with Python 3.12+ (targeting Python 3.14), FastAPI, and Google Cloud Firestore.

## Documentation

- **[Data Schema](docs/SCHEMA.md)** - Comprehensive documentation of the character data schema, Firestore structure, and database design patterns
- **[Deployment Guide](docs/deployment.md)** - Instructions for deploying to Google Cloud Run

## Features

- **Health Check Endpoint**: `/health` - Returns service status and basic identifiers
- **Info Endpoint**: `/info` - Returns build and configuration metadata
- **Firestore Connectivity Test**: `/firestore-test` - Verifies Firestore read/write access (operational endpoint)
- **Character Management API**: RESTful endpoints for creating and managing characters
  - `POST /characters` - Create new characters with validation and uniqueness constraints
  - `GET /characters` - List all characters for a user (save-slot UI support)
  - `GET /characters/{id}` - Get full character details by ID
  - `POST /characters/{id}/narrative` - Append narrative turns to character history
  - `GET /characters/{id}/narrative` - Retrieve narrative turns with filtering (last N, since timestamp)
- **Point of Interest (POI) Management**: Track discovered locations and landmarks using subcollection storage
  - `POST /characters/{id}/pois` - Add new POI to character's subcollection (supports unlimited POIs)
  - `GET /characters/{id}/pois/random` - Sample N random POIs for narrative context (default: 3, max: 20)
  - `GET /characters/{id}/pois` - Retrieve all POIs with cursor-based pagination, sorted by discovery time
  - `GET /characters/{id}/pois/summary` - Get total POI count and preview of newest POIs (efficient aggregation)
  - `PUT /characters/{id}/pois/{poi_id}` - Update an existing POI
  - `DELETE /characters/{id}/pois/{poi_id}` - Delete a POI from the character's collection
- **Quest Management**: Single-active-quest system with archival
  - `PUT /characters/{id}/quest` - Set active quest (enforces single-quest invariant, returns 409 if quest exists)
  - `GET /characters/{id}/quest` - Retrieve active quest (returns null if none)
  - `DELETE /characters/{id}/quest` - Clear active quest and archive it (max 50 archived quests, FIFO)
- **Combat Management**: Track combat encounters with automatic active/inactive detection
  - `PUT /characters/{id}/combat` - Set or clear combat state (max 5 enemies per combat)
  - `GET /characters/{id}/combat` - Retrieve combat state with stable active/inactive envelope

## Primary Director Integration Endpoint

**Context Aggregation for Directors**: The `/characters/{id}/context` endpoint is the **primary integration surface** for AI Directors and LLM-driven narrative systems.

- **`GET /characters/{id}/context`** - Comprehensive aggregated context payload in a single request
  - **Aggregates**: Player state, quest, combat, narrative history, and world POIs
  - **Derived fields**: `has_active_quest`, `combat.active`, narrative metadata for client convenience
  - **Configurable narrative window**: Use `recent_n` parameter (default: 20, max: 100) to control history depth
  - **Optional POI inclusion**: Set `include_pois=false` to exclude POIs for smaller payloads
  - **Performance**: Exactly 2 Firestore reads (1 character document + 1 narrative subcollection query), typically <100ms
  - **Response structure**: Stable JSON schema with all context fields always present, optimized for LLM consumption

### Why Use the Context Endpoint?

Directors should prefer this endpoint over individual endpoints because:
1. **Single request**: Get all necessary context without multiple API calls
2. **Optimized performance**: Minimal Firestore reads with efficient query patterns
3. **Derived fields**: Server-computed convenience fields (combat.active, has_active_quest)
4. **Stable schema**: Always returns same structure, simplifying client code
5. **Narrative ordering**: Recent turns returned oldest-to-newest for proper LLM context building

See [Context Endpoint Examples](#context-endpoint-examples) below for usage patterns.
- **Status-Based Health Tracking**: Character health is tracked through status enum ("Healthy", "Wounded", "Dead")
- **Environment-based Configuration**: Uses Pydantic Settings for type-safe configuration
- **Google Cloud Integration**: Ready for Cloud Run deployment with Firestore support
- **Structured Logging**: JSON-formatted logs compatible with Cloud Logging
- **Request ID Tracking**: Automatic request ID generation and propagation for distributed tracing
- **Global Error Handling**: Standardized JSON error responses with request IDs

## Requirements

- **Python**: 3.12+ (targeting 3.14 for production)
- **Package Manager**: `uv` (preferred) or `pip`
- **Dependencies**: See `requirements.txt`

## Local Development Setup

### 1. Create a Virtual Environment

```bash
# Using Python's built-in venv
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# OR using uv (preferred)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Using pip
pip install -r requirements.txt

# OR using uv (preferred)
uv pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment file and customize it:

```bash
cp .env.example .env
```

Edit `.env` and set the required variables:
- `GCP_PROJECT_ID`: Your Google Cloud Project ID (required for non-dev environments)
- `SERVICE_ENVIRONMENT`: Set to `dev`, `staging`, or `prod`
- Other optional variables as needed

### 4. Run the Service Locally

```bash
# Using uvicorn directly
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# OR using Python module
python -m app.main

# OR using uv (preferred)
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

The service will be available at:
- **API**: http://127.0.0.1:8080
- **Health Check**: http://127.0.0.1:8080/health
- **Info**: http://127.0.0.1:8080/info
- **Firestore Test**: http://127.0.0.1:8080/firestore-test
- **API Docs**: http://127.0.0.1:8080/docs
- **ReDoc**: http://127.0.0.1:8080/redoc

## Running Without Firestore Credentials

For local development, you can run the service without Firestore credentials. The `/health` and `/info` endpoints do not require Firestore access.

### Testing Firestore Connectivity

To test Firestore connectivity, you have two options:

#### Option 1: Use Firestore Emulator (Recommended for Local Development)

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Start Firestore emulator
firebase emulators:start --only firestore --project=demo-project

# In your .env file, set:
FIRESTORE_EMULATOR_HOST=localhost:8080
GCP_PROJECT_ID=demo-project

# Run the service
uvicorn app.main:app --reload
```

**Note**: The Firestore emulator does not require indexes for development, so queries will work without creating composite indexes. However, you'll need to create indexes when deploying to production Firestore.

#### Option 2: Use Application Default Credentials

```bash
# Login with your Google account
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Ensure your user has Firestore permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="user:your-email@example.com" \
    --role="roles/datastore.user"

# Create required Firestore indexes (production only)
gcloud firestore indexes composite create \
    --collection-group=characters \
    --query-scope=COLLECTION \
    --field-config=field-path=owner_user_id,order=ASCENDING \
    --field-config=field-path=updated_at,order=DESCENDING \
    --project=YOUR_PROJECT_ID

# In your .env file, set:
GCP_PROJECT_ID=YOUR_PROJECT_ID
# Leave FIRESTORE_EMULATOR_HOST empty
```

### Using the Connectivity Test Endpoint

Once configured, test Firestore connectivity:

```bash
# POST request (recommended)
curl -X POST http://localhost:8080/firestore-test

# Expected response:
{
  "status": "success",
  "message": "Successfully wrote to and read from Firestore collection 'connectivity_test'",
  "document_id": "test_20260111_123456_789012",
  "data": {
    "test_type": "connectivity_check",
    "timestamp": "2026-01-11T12:34:56.789012+00:00",
    "message": "Firestore connectivity test document",
    "service": "journey-log",
    "environment": "dev"
  },
  "timestamp": "2026-01-11T12:34:56.789012+00:00"
}
```

**Note**: Test documents are NOT automatically cleaned up. Use the cleanup endpoint to remove them:

```bash
# DELETE request to clean up test documents
curl -X DELETE http://localhost:8080/firestore-test

# Expected response:
{
  "status": "success",
  "message": "Successfully deleted N test document(s) from collection 'connectivity_test'",
  "deleted_count": N,
  "timestamp": "2026-01-11T12:34:56.789012+00:00"
}
```

**Security Note**: In production, protect these endpoints with authentication (e.g., Cloud Run IAM) to prevent unauthorized access.

## Usage Examples

### POI Management

#### POI Storage Architecture

POIs (Points of Interest) are stored in **per-character Firestore subcollections** at the path `characters/{character_id}/pois/{poi_id}`. This architecture provides:

- **Unlimited storage**: No hard limit on POIs per character (previously limited to 200 in embedded arrays)
- **Efficient queries**: Firestore indexes enable fast pagination and filtering on large POI collections
- **Cursor-based pagination**: True pagination using Firestore cursors for optimal performance
- **Count aggregation**: Efficient total count queries without loading all documents

**World POI Reference**: Characters have a `world_pois_reference` field that can point to:
- **Firestore collection paths**: `"characters/{character_id}/pois"` for character-specific POIs, or `"worlds/{world_id}/pois"` for world-global shared POIs
- **Configuration keys**: Named world configurations like `"world-v1"` or `"middle-earth-pois"` for preset POI sets

**Migration Status**: The embedded `world_pois` array in character documents is **deprecated** and read-only. New POIs are written exclusively to the subcollection. See [Migration Guide](docs/deployment.md#poi-migration) for migration details.

#### POI API Examples

```bash
# Add a new POI to a character's subcollection
curl -X POST http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Ancient Dragon Lair",
    "description": "A massive cavern filled with treasure and danger",
    "tags": ["dungeon", "dragon", "high-level"]
  }'

# Get POI count and preview of newest POIs (efficient aggregation)
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/summary?preview_limit=5" \
  -H "X-User-Id: user123"
# Response: {"total_count": 150, "preview": [...], "preview_count": 5}

# Get 5 random POIs for narrative context
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/random?n=5" \
  -H "X-User-Id: user123"

# List POIs with cursor-based pagination (default: 50 per page, sorted by discovery time)
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois?limit=20" \
  -H "X-User-Id: user123"
# Response: {"pois": [...], "count": 20, "cursor": "eyJwb2lfaWQiOiJhYmMxMjMifQ=="}

# Get next page using cursor from previous response
# Cursor format: Opaque base64-encoded string containing Firestore document reference
# - DO NOT parse, decode, or construct cursors manually
# - Cursors are tied to the query (order, filters) that generated them
# - Invalid/expired cursors return 400 error with message to restart pagination
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois?limit=20&cursor=eyJwb2lfaWQiOiJhYmMxMjMifQ==" \
  -H "X-User-Id: user123"
# Response: {"pois": [...], "count": 20, "cursor": "eyJwb2lfaWQiOiJ4eXo3ODkifQ=="} or {"cursor": null} if no more pages

# Update an existing POI
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/abc-123 \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "visited": true,
    "tags": ["dungeon", "dragon", "high-level", "completed"]
  }'

# Delete a POI
curl -X DELETE http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/abc-123 \
  -H "X-User-Id: user123"
```

### Quest Management

```bash
# Set an active quest
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Slay the Dragon",
    "description": "Defeat the ancient red dragon threatening the kingdom",
    "requirements": ["Gather party", "Forge dragonslayer sword", "Storm the lair"],
    "rewards": {
      "items": ["Dragon Scale Armor", "Ancient Crown"],
      "currency": {"gold": 10000},
      "experience": 5000
    },
    "completion_state": "in_progress",
    "updated_at": "2026-01-12T10:00:00Z"
  }'

# Get active quest
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "X-User-Id: user123"

# Try to set another quest (will fail with 409)
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Find the Lost Crown",
    "description": "Locate and retrieve the ancient crown from the forbidden forest",
    "requirements": ["Obtain forest map", "Defeat guardian"],
    "rewards": {
      "items": ["Ancient Crown"],
      "currency": {"gold": 500},
      "experience": 2000
    },
    "completion_state": "not_started",
    "updated_at": "2026-01-12T10:00:00Z"
  }'
# Error: 409 Conflict - Must DELETE existing quest first

# Complete and archive quest
curl -X DELETE http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "X-User-Id: user123"
# Success: 204 No Content, quest is now archived
```

### Combat Management

```bash
# Start a combat encounter with 2 enemies
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "combat_state": {
      "combat_id": "combat_001",
      "started_at": "2026-01-12T10:00:00Z",
      "turn": 1,
      "enemies": [
        {
          "enemy_id": "orc_001",
          "name": "Orc Chieftain",
          "status": "Healthy",
          "weapon": "Great Axe",
          "traits": ["leader", "aggressive", "armored"]
        },
        {
          "enemy_id": "goblin_001",
          "name": "Goblin Scout",
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
  }'
# Response: {"active": true, "state": {...}}

# Update combat (mark one enemy as dead, orc wounded)
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "combat_state": {
      "combat_id": "combat_001",
      "started_at": "2026-01-12T10:00:00Z",
      "turn": 3,
      "enemies": [
        {
          "enemy_id": "orc_001",
          "name": "Orc Chieftain",
          "status": "Wounded",
          "weapon": "Great Axe",
          "traits": ["leader", "aggressive"]
        },
        {
          "enemy_id": "goblin_001",
          "name": "Goblin Scout",
          "status": "Dead",
          "weapon": "Short Bow",
          "traits": ["ranged", "cowardly"]
        }
      ]
    }
  }'
# Response: {"active": true, "state": {...}} (still active because orc is alive)
# Note: Traits can be modified arbitrarily by Directors; keeping traits on dead enemies is valid

# End combat (all enemies dead)
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "combat_state": {
      "combat_id": "combat_001",
      "started_at": "2026-01-12T10:00:00Z",
      "turn": 5,
      "enemies": [
        {
          "enemy_id": "orc_001",
          "name": "Orc Chieftain",
          "status": "Dead",
          "weapon": "Great Axe",
          "traits": []
        },
        {
          "enemy_id": "goblin_001",
          "name": "Goblin Scout",
          "status": "Dead",
          "weapon": "Short Bow",
          "traits": []
        }
      ]
    }
  }'
# Response: {"active": false, "state": {...}} (inactive because all enemies dead)

# Get current combat state
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "X-User-Id: user123"
# Response: {"active": false, "state": null} or {"active": true, "state": {...}}

# Clear combat completely
curl -X PUT http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/combat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{"combat_state": null}'
# Response: {"active": false, "state": null}
```

### Context Endpoint Examples

The context aggregation endpoint is the **primary integration point for AI Directors**. Use this endpoint to retrieve all relevant character state in a single optimized request.

```bash
# Get full context with default settings (20 recent narrative turns, POIs included)
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/context \
  -H "X-User-Id: user123"

# Response structure:
{
  "character_id": "550e8400-e29b-41d4-a716-446655440000",
  "player_state": {
    "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
    "status": "Healthy",
    "level": 5,
    "location": {"id": "town:start", "display_name": "Starting Town"},
    ...
  },
  "quest": {
    "name": "Slay the Dragon",
    "description": "...",
    "completion_state": "in_progress",
    ...
  },
  "combat": {
    "active": true,
    "state": {
      "combat_id": "combat_001",
      "enemies": [...],
      ...
    }
  },
  "narrative": {
    "recent_turns": [
      {"player_action": "I explore...", "ai_response": "You discover...", ...},
      ...
    ],
    "requested_n": 20,
    "returned_n": 15,  // May be less if fewer turns exist
    "max_n": 100
  },
  "world": {
    "pois_sample": [
      {"id": "poi1", "name": "Ancient Temple", "description": "...", ...},
      ...
    ],
    "include_pois": true
  },
  "has_active_quest": true  // Derived convenience field
}

# Get more narrative history for complex scenarios
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=50" \
  -H "X-User-Id: user123"

# Get smaller payload without POIs for performance
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/context?include_pois=false" \
  -H "X-User-Id: user123"
```

**Key Features for Directors:**
- **Single request**: All context in one API call (2 Firestore reads total)
- **Derived fields**: `has_active_quest` and `combat.active` computed server-side
- **Stable response**: All fields always present, even when null/empty
- **Chronological narrative**: Recent turns ordered oldest-to-newest for LLM context
- **Flexible configuration**: Adjust narrative window and POI inclusion per request
- **Error handling**: Returns 404 for missing character, 403 for unauthorized access

**Performance Characteristics:**
- **Latency**: Typically <100ms for moderate datasets (20 turns, 200 POIs)
- **Firestore reads**: Exactly 2 (1 character document + 1 narrative query)
- **Payload size**: ~5-50KB depending on narrative length and POI inclusion
- **Caching friendly**: Use ETags or timestamps for conditional requests

### Status-Based Health Tracking

Character health is tracked using a **status enum field** with three possible values: `"Healthy"`, `"Wounded"`, and `"Dead"`. This provides a simplified health model that focuses on game state transitions rather than numerical health tracking.

#### Status Values

- `Healthy`: Character is in good health and can perform all actions
- `Wounded`: Character is injured and may have reduced capabilities
- `Dead`: Character is deceased and cannot perform actions

#### Status Transitions

Game mechanics should transition character status based on damage or healing:
- `Healthy` → `Wounded`: When character takes damage in combat
- `Wounded` → `Dead`: When character takes critical damage or is defeated
- `Wounded` → `Healthy`: When character is healed or rests
- `Dead` → `Healthy`: Through resurrection mechanics (if applicable)

#### No Numeric Health Fields

The system **does not use or store numeric health fields**. The following fields are **deprecated and ignored**:
- `level`, `experience`, `stats` - Numeric progression fields
- `current_hp`, `max_hp` - HP-style health tracking
- `current_health`, `max_health` - Alternative health tracking
- `health` (any numeric or nested format) - Any health objects

**Backward Compatibility:** If legacy documents containing these fields are read from Firestore, the numeric fields are automatically stripped during deserialization and never persisted back to storage. This ensures a clean migration to the status-only model.

#### Validation Rules

- The `status` field is **required** on all character and enemy states
- Only the three enum values (`"Healthy"`, `"Wounded"`, `"Dead"`) are accepted
- Invalid status values are rejected with HTTP 422 validation errors
- API requests with numeric health fields in the payload are processed normally, but numeric fields are ignored

#### Usage in Combat

Combat state transitions are managed through status changes, with combat being considered active when any enemy has a status other than `"Dead"`. Directors and game logic should update status fields rather than tracking numerical HP values. This ensures consistency with the status-based health model across all game mechanics.

#### Example Character State

```json
{
  "player_state": {
    "identity": {
      "name": "Aragorn",
      "race": "Human",
      "class": "Ranger"
    },
    "status": "Healthy",
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
        "effect": "Restores wounds"
      }
    ],
    "location": {
      "id": "town:rivendell",
      "display_name": "Rivendell"
    },
    "additional_fields": {}
  }
}
```

#### Cleanup Script

For operators who need to remove legacy numeric health fields from existing Firestore documents, a cleanup utility is provided at `scripts/remove_numeric_health.py`. This script:

- Scans character documents in Firestore for legacy numeric health fields
- Removes deprecated fields (`level`, `experience`, `stats`, `current_hp`, `max_hp`, etc.)
- Supports dry-run mode to preview changes before applying them
- Logs all actions for audit purposes
- Handles documents missing status fields without crashing

See the [Deployment Guide](docs/deployment.md#cleanup-script) for usage instructions and required environment variables.

## Environment Variables

See `.env.example` for a complete list of available environment variables with descriptions.

**Note for POI/Quest Features:** No new environment variables or secrets are needed for POI and Quest endpoints. All POI and quest data is stored in the existing Firestore character documents using the existing `GCP_PROJECT_ID` configuration. The existing `.env.example` entries are sufficient for all features.

### Required Variables
- `GCP_PROJECT_ID`: Required in `staging` and `prod` environments

### Optional Variables
- `SERVICE_ENVIRONMENT`: Defaults to `dev`
- `SERVICE_NAME`: Defaults to `journey-log`
- `FIRESTORE_JOURNEYS_COLLECTION`: Defaults to `journeys`
- `FIRESTORE_ENTRIES_COLLECTION`: Defaults to `entries`
- `FIRESTORE_TEST_COLLECTION`: Defaults to `connectivity_test`
- `FIRESTORE_EMULATOR_HOST`: Empty by default (set to `localhost:8080` for local emulator)
- `API_HOST`: Defaults to `127.0.0.1`
- `API_PORT`: Defaults to `8080`
- `LOG_LEVEL`: Defaults to `INFO`
- `REQUEST_ID_HEADER`: Defaults to `X-Request-ID` (for Cloud Run compatibility)

## Structured Logging

The service uses structured logging with JSON output compatible with Google Cloud Logging. All logs include:

- **timestamp**: ISO 8601 formatted timestamp
- **level**: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **message**: Log message
- **service**: Service name (from `SERVICE_NAME`)
- **environment**: Environment (dev/staging/prod)
- **request_id**: Unique request identifier for distributed tracing
- **path**: Request path (for request-scoped logs)
- **method**: HTTP method (for request-scoped logs)

### Local Development Logging

In **development mode** (`SERVICE_ENVIRONMENT=dev`), logs are formatted for human readability with color coding and pretty-printing:

```
2026-01-11T12:34:56.789012Z [info     ] request_started                environment=dev method=GET path=/health request_id=550e8400-e29b-41d4-a716-446655440000 service=journey-log
```

### Production Logging (Cloud Run)

In **production and staging**, logs are emitted as JSON for Cloud Logging:

```json
{
  "timestamp": "2026-01-11T12:34:56.789012Z",
  "level": "info",
  "message": "request_started",
  "service": "journey-log",
  "environment": "prod",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "path": "/health",
  "method": "GET"
}
```

Cloud Logging will automatically parse these JSON logs and extract fields for filtering and analysis.

### Request ID Propagation

Every request automatically gets a unique **request ID** that flows through all logs and responses:

1. **Incoming Request**: The service checks for a `X-Request-ID` header (configurable via `REQUEST_ID_HEADER`)
2. **Generation**: If no header is present, a UUID is automatically generated
3. **Logging Context**: The request ID is added to all logs during that request
4. **Response Header**: The request ID is included in the response `X-Request-ID` header
5. **Error Responses**: All error responses include the `request_id` field

This enables end-to-end request tracing across services and logs.

### Debug Logging

To enable debug logging locally:

```bash
# In your .env file
LOG_LEVEL=DEBUG

# Or via environment variable
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload
```

Debug logs include additional detail about internal operations, helpful for troubleshooting.

### Custom Request ID Header

If your load balancer or proxy uses a different header name for request IDs, configure it:

```bash
# In your .env file
REQUEST_ID_HEADER=X-Cloud-Trace-Context

# Or for GCP-specific tracing
REQUEST_ID_HEADER=X-Cloud-Trace-Context
```

## Global Error Handling

The service provides standardized JSON error responses for all errors, including:

### HTTP Exceptions

When a route raises an `HTTPException`, the response includes:

```json
{
  "error": "http_error",
  "message": "Not Found",
  "status_code": 404,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Validation Errors

Request validation errors return detailed information including field location, error message, and expected values.

**General validation error:**
```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "errors": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ],
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Invalid status enum validation:**
```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "errors": [
    {
      "loc": ["body", "combat_state", "enemies", 0, "status"],
      "msg": "Input should be 'Healthy', 'Wounded' or 'Dead'",
      "type": "enum",
      "ctx": {
        "expected": "'Healthy', 'Wounded' or 'Dead'"
      }
    }
  ],
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

All validation errors:
- Return HTTP 422 (Unprocessable Entity)
- Include precise field location in the `loc` array
- Provide clear error messages with expected values
- Include context information for enum and other constrained fields

### Unhandled Exceptions

For unexpected errors:

- **Development**: Returns detailed error information including exception type and message
- **Production**: Returns generic error message to avoid leaking sensitive information

Development response:
```json
{
  "error": "internal_error",
  "message": "ValueError: Invalid input",
  "type": "ValueError",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Production response:
```json
{
  "error": "internal_error",
  "message": "An internal error occurred. Please contact support with the request ID.",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

All errors are logged with stack traces for debugging, while responses protect sensitive information in production.

## Development

### Testing

The project includes comprehensive integration tests for all endpoints, with special focus on the context aggregation endpoint.

#### Running Tests

```bash
# Run all tests
make test
# OR
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_context_aggregation.py -v

# Run specific test function
pytest tests/test_context_aggregation.py::TestGetCharacterContext::test_get_context_success_with_all_data -v

# Run tests with coverage report
pytest --cov=app --cov-report=html
```

#### Test Organization

- **`tests/test_characters.py`** - Character CRUD operations, validation, uniqueness constraints
- **`tests/test_context_aggregation.py`** - Context endpoint integration tests (primary Director integration)
- **`tests/test_combat.py`** - Combat state management and active/inactive detection
- **`tests/test_narrative_turns.py`** - Narrative turn creation and retrieval
- **`tests/test_models.py`** - Pydantic model validation and serialization
- **`tests/test_serialization.py`** - Firestore serialization/deserialization
- **`tests/test_firestore_serialization.py`** - Firestore-specific type conversions

#### Context Endpoint Test Coverage

The context aggregation endpoint (`GET /characters/{id}/context`) has extensive test coverage including:

**Success Cases:**
- ✅ Full context aggregation with all data (player, quest, combat, narrative, POIs)
- ✅ Quest present vs absent (has_active_quest derived field)
- ✅ Combat active vs inactive (combat.active toggles based on enemy status)
- ✅ Multiple recent_n values (default, custom, max limit)
- ✅ include_pois flag (true/false)
- ✅ Empty narrative history (returns empty array, not error)
- ✅ Empty POIs (returns empty array, not error)

**Edge Cases:**
- ✅ Character not found (404 response)
- ✅ Invalid character UUID format (422 response)
- ✅ User verification and access control (403 for mismatch)
- ✅ Empty/whitespace X-User-Id header (400 response)
- ✅ Invalid recent_n values (zero, negative, exceeding max → 422)
- ✅ Narrative ordering (oldest-to-newest for LLM context)
- ✅ Firestore read efficiency (validates exactly 2 reads as documented)

**Key Test Scenarios:**
```bash
# Test recent_n clamping behavior (when requested > available)
pytest tests/test_context_aggregation.py::TestGetCharacterContext::test_get_context_success_with_all_data -v
# Verifies: requested_n=20, returned_n=3 when only 3 turns exist

# Test combat.active transitions
pytest tests/test_context_aggregation.py::TestGetCharacterContext::test_get_context_combat_all_enemies_dead -v
# Verifies: combat.active=false when all enemies status="Dead"

# Test performance characteristics
pytest tests/test_context_aggregation.py::TestGetCharacterContext::test_get_context_firestore_read_count -v
# Verifies: Exactly 2 Firestore reads (1 character doc + 1 narrative query)
```

#### Test Configuration

Tests use mocked Firestore clients (no emulator required). To run tests against a real Firestore emulator:

```bash
# Start Firestore emulator
firebase emulators:start --only firestore --project=demo-project

# In another terminal, set emulator environment variable and run tests
export FIRESTORE_EMULATOR_HOST=localhost:8080
export GCP_PROJECT_ID=demo-project
pytest tests/test_context_aggregation.py -v
```

#### Environment Variables for Testing

No additional environment variables are required for basic testing (mocked Firestore). For integration tests against real Firestore:

- `FIRESTORE_EMULATOR_HOST` - Set to `localhost:8080` when using Firebase emulator
- `GCP_PROJECT_ID` - Set to your project ID or `demo-project` for emulator
- `SERVICE_ENVIRONMENT` - Set to `dev` for local testing (default)

See `.env.example` for all available configuration options including:
- `CONTEXT_DEFAULT_RECENT_N` - Default narrative window (default: 20)
- `CONTEXT_MAX_RECENT_N` - Maximum narrative window (default: 100)
- `CONTEXT_DEFAULT_POI_SAMPLE_SIZE` - Default POI sample size (default: 3)

### Code Quality

This project uses:
- **Ruff**: For linting and formatting
- **MyPy**: For static type checking
- **Pytest**: For testing

```bash
# Run linter
ruff check .

# Format code
ruff format .

# Type checking
mypy app/

# Run tests
pytest
```

## Deployment

This service is designed to run on Google Cloud Run with containerized deployment. 

### Quick Start - Docker Build and Run

```bash
# Build the Docker image
make docker-build

# Run locally in Docker
make docker-run

# Deploy to Cloud Run (requires environment variables)
make deploy
```

### Deployment Guide

See `docs/deployment.md` for comprehensive deployment instructions, including:

- **Docker Containerization**: Building and running the container locally
- **IAM Configuration**: Service account setup and role assignments
- **Artifact Registry**: Container image registry setup
- **Cloud Run Deployment**: Automated deployment script with environment variables
- **Firestore Setup**: Database configuration and permissions
- **Authentication**: IAM-based access control (default: no public access)
- **Testing**: Connectivity testing procedures for local and Cloud Run
- **Troubleshooting**: Common issues and solutions

### Required Environment Variables for Deployment

```bash
export GCP_PROJECT_ID="your-project-id"
export REGION="us-central1"
export SERVICE_NAME="journey-log"
export ARTIFACT_REGISTRY_REPO="cloud-run-apps"
export SERVICE_ACCOUNT="journey-log-sa@your-project-id.iam.gserviceaccount.com"
```

Then run: `./scripts/deploy_cloud_run.sh`

### Key Features

- **Production-ready Dockerfile**: Multi-stage build with Python 3.14-slim, non-root user
- **Automated Deployment**: Script handles build, push, and deployment with validation
- **Secure by Default**: Deploys with authentication required (no public access)
- **IAM-only Access**: Uses Cloud Run service account with Firestore permissions
- **Environment Support**: Configurable for dev, staging, and production environments



# Permanents (License, Contributing, Author)

Do not change any of the below sections

## License

This Agent Foundry Project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Contributing

Feel free to submit issues and enhancement requests!

## Author

Created by Agent Foundry and John Brosnihan
