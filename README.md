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
- **Point of Interest (POI) Management**: Track discovered locations and landmarks
  - `POST /characters/{id}/pois` - Add new POI to character's world (max 200 per character)
  - `GET /characters/{id}/pois/random` - Sample N random POIs for narrative context (default: 3, max: 20)
  - `GET /characters/{id}/pois` - Retrieve all POIs with pagination, sorted by discovery time
- **Quest Management**: Single-active-quest system with archival
  - `PUT /characters/{id}/quest` - Set active quest (enforces single-quest invariant, returns 409 if quest exists)
  - `GET /characters/{id}/quest` - Retrieve active quest (returns null if none)
  - `DELETE /characters/{id}/quest` - Clear active quest and archive it (max 50 archived quests, FIFO)
- **Health Point (HP) Removal**: Character health is stored internally but never exposed in API responses for security
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

```bash
# Add a new POI to a character
curl -X POST http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user123" \
  -d '{
    "name": "Ancient Dragon Lair",
    "description": "A massive cavern filled with treasure and danger",
    "tags": ["dungeon", "dragon", "high-level"]
  }'

# Get 5 random POIs for narrative context
curl "http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois/random?n=5" \
  -H "X-User-Id: user123"

# List all POIs for a character
curl http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/pois \
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
  -d '{...}'
# Error: 409 Conflict - Must DELETE existing quest first

# Complete and archive quest
curl -X DELETE http://localhost:8080/characters/550e8400-e29b-41d4-a716-446655440000/quest \
  -H "X-User-Id: user123"
# Success: 204 No Content, quest is now archived
```

### Health Point (HP) Removal

Character health points are stored internally in the `player_state.health` field for game mechanics, but **are never exposed in API responses** for security reasons. This prevents external systems or users from directly inspecting or manipulating HP values. The `status` field ("Healthy", "Wounded", "Dead") provides sufficient information for UI/Director needs without exposing exact HP values.

**Internal Storage (Firestore):**
```json
{
  "player_state": {
    "health": {"current": 75, "max": 100},
    "status": "Healthy"
  }
}
```

**API Response (HP excluded):**
```json
{
  "character": {
    "player_state": {
      "status": "Healthy"
      // health field is omitted
    }
  }
}
```

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
- `NARRATIVE_TURNS_DEFAULT_QUERY_SIZE`: Default number of narrative turns to retrieve (default: 10)
- `NARRATIVE_TURNS_MAX_QUERY_SIZE`: Maximum narrative turns per query (default: 100)

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

Request validation errors return:

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
