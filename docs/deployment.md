# Deployment Guide

This document provides detailed instructions for deploying the Journey Log API to Google Cloud Platform and configuring Firestore access.

## Table of Contents

- [Prerequisites](#prerequisites)
- [IAM Roles and Permissions](#iam-roles-and-permissions)
- [Local Development Setup](#local-development-setup)
- [Docker Containerization](#docker-containerization)
- [Firestore Configuration](#firestore-configuration)
- [Cloud Run Deployment](#cloud-run-deployment)
- [Testing Connectivity](#testing-connectivity)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before deploying the Journey Log API, ensure you have:

1. **Google Cloud Project**: An active GCP project with billing enabled
2. **gcloud CLI**: Installed and configured ([Installation Guide](https://cloud.google.com/sdk/docs/install))
3. **Firestore Database**: A Firestore database created in your project (Native mode recommended)
4. **Docker**: Required for container builds (version 29.1.4+)
5. **Python 3.14+**: For local development (targeting 3.14 per infrastructure_versions.txt)
6. **Artifact Registry**: A repository for storing container images

## IAM Roles and Permissions

### Service Account for Cloud Run

When deploying to Cloud Run, your service needs appropriate permissions to access Firestore. The Cloud Run service account requires:

#### Recommended Role

- **`roles/datastore.user`**: Provides read/write access to Firestore
  - Grants permissions: `datastore.entities.*`, `datastore.indexes.*`, `datastore.namespaces.*`

#### Alternative Roles

If you need more granular control:

- **`roles/datastore.viewer`**: Read-only access to Firestore
- **`roles/datastore.owner`**: Full access including administrative operations

#### Grant Permissions

```bash
# Get your Cloud Run service account (default format)
PROJECT_ID="your-project-id"
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Or create a dedicated service account (recommended for production)
gcloud iam service-accounts create journey-log-sa \
    --display-name="Journey Log Service Account" \
    --project="${PROJECT_ID}"

SERVICE_ACCOUNT="journey-log-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant Firestore access
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/datastore.user"
```

### Invoker Permissions

To allow authenticated access to your Cloud Run service:

```bash
# Allow public access (for testing)
gcloud run services add-iam-policy-binding journey-log \
    --region=us-central1 \
    --member="allUsers" \
    --role="roles/run.invoker"

# Or restrict to specific users/service accounts
gcloud run services add-iam-policy-binding journey-log \
    --region=us-central1 \
    --member="user:your-email@example.com" \
    --role="roles/run.invoker"
```

## Local Development Setup

### Using Application Default Credentials (ADC)

For local development, you can authenticate using your user account or a service account.

#### Option 1: User Account (Recommended for Development)

```bash
# Login with your Google account
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Ensure your user has Firestore permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="user:your-email@example.com" \
    --role="roles/datastore.user"
```

#### Option 2: Service Account Key (Use with Caution)

**Warning**: Service account keys are security risks. Use Workload Identity Federation for CI/CD instead.

```bash
# Create a service account
gcloud iam service-accounts create journey-log-dev \
    --display-name="Journey Log Development"

# Grant Firestore permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:journey-log-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/datastore.user"

# Create and download key (keep this secure!)
gcloud iam service-accounts keys create ~/journey-log-dev-key.json \
    --iam-account=journey-log-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/journey-log-dev-key.json"
```

### Using Firestore Emulator (Offline Development)

For local development without GCP credentials:

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Start Firestore emulator
firebase emulators:start --only firestore --project=demo-project

# In another terminal, configure your application
export FIRESTORE_EMULATOR_HOST="localhost:8080"
export GCP_PROJECT_ID="demo-project"

# Run your application
uvicorn app.main:app --reload
```

Update your `.env` file:

```bash
FIRESTORE_EMULATOR_HOST=localhost:8080
GCP_PROJECT_ID=demo-project
SERVICE_ENVIRONMENT=dev
```

## Docker Containerization

The Journey Log API uses a production-ready Dockerfile optimized for Cloud Run deployment.

### Dockerfile Features

- **Base Image**: Python 3.14-slim (aligned with infrastructure_versions.txt)
- **Multi-stage Build**: Separates build dependencies from runtime for smaller images
- **Non-root User**: Runs as `appuser` (UID 1001) for security
- **Cloud Run Compatible**: Uses `$PORT` environment variable set by Cloud Run
- **Security Updates**: Includes latest security patches in base image
- **Health Check**: Built-in health check endpoint monitoring

### Building the Container Locally

Using Make (recommended):

```bash
# Build the Docker image
make docker-build

# This runs:
# docker build -t journey-log:latest .
```

Or using Docker directly:

```bash
# Build with build metadata
docker build -t journey-log:latest \
  --build-arg BUILD_VERSION=$(git describe --tags --always) \
  --build-arg BUILD_COMMIT=$(git rev-parse HEAD) \
  --build-arg BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  .
```

### Running the Container Locally

Using Make (recommended):

```bash
# Run the container with default settings
make docker-run

# Service will be available at http://localhost:8080
```

Or using Docker directly:

```bash
# Run with Firestore emulator
docker run --rm -it \
  -p 8080:8080 \
  -e SERVICE_ENVIRONMENT=dev \
  -e GCP_PROJECT_ID=demo-project \
  -e FIRESTORE_EMULATOR_HOST=host.docker.internal:8080 \
  journey-log:latest

# Run with real Firestore (requires ADC volume mount)
docker run --rm -it \
  -p 8080:8080 \
  -e SERVICE_ENVIRONMENT=dev \
  -e GCP_PROJECT_ID=your-project-id \
  -v ~/.config/gcloud:/home/appuser/.config/gcloud:ro \
  journey-log:latest
```

**Note**: On macOS/Windows, use `host.docker.internal` to access the host machine's localhost. On Linux, use `--network host` or the host's IP address.

### Testing the Containerized Application

Once the container is running:

```bash
# Health check
curl http://localhost:8080/health

# Info endpoint
curl http://localhost:8080/info

# Firestore connectivity test (if Firestore is configured)
curl -X POST http://localhost:8080/firestore-test
```

### Container Configuration

The Dockerfile is configured with the following production settings:

- **Workers**: 1 worker per instance (Cloud Run manages concurrency)
- **Timeout**: 75 seconds keep-alive (Cloud Run default is 60s, max 300s)
- **Port**: Uses `$PORT` environment variable (Cloud Run sets this to 8080)
- **Log Level**: info (configurable via `LOG_LEVEL` env var)

You can override these settings by passing environment variables:

```bash
docker run --rm -it \
  -p 8080:8080 \
  -e PORT=8080 \
  -e LOG_LEVEL=DEBUG \
  -e SERVICE_ENVIRONMENT=dev \
  journey-log:latest
```

## Firestore Configuration

### Creating Firestore Database

If you haven't created a Firestore database:

```bash
# Create Firestore database in Native mode
gcloud firestore databases create \
    --region=us-central1 \
    --project=YOUR_PROJECT_ID

# Note: You can only have one Firestore database per project
```

### Collections Used

The Journey Log API uses the following Firestore collections:

- **`journeys`**: Main journeys collection (configurable via `FIRESTORE_JOURNEYS_COLLECTION`)
- **`entries`**: Journey entries collection (configurable via `FIRESTORE_ENTRIES_COLLECTION`)
- **`connectivity_test`**: Test documents for connectivity checks (configurable via `FIRESTORE_TEST_COLLECTION`)

The connectivity test collection will contain test documents created by the `/firestore-test` endpoint. These documents are not automatically cleaned up.

### Cleanup Test Documents

To clean up test documents created by connectivity tests:

```bash
# Using gcloud CLI
gcloud firestore documents delete \
    "projects/YOUR_PROJECT_ID/databases/(default)/documents/connectivity_test/test_DOCUMENT_ID" \
    --project=YOUR_PROJECT_ID

# Or delete the entire test collection (use with caution)
gcloud firestore import gs://your-backup-bucket/test-backup \
    --collection-ids=connectivity_test \
    --async
```

## Cloud Run Deployment

The Journey Log API includes a deployment script (`scripts/deploy_cloud_run.sh`) that automates the entire deployment process to Cloud Run, including building the container, pushing to Artifact Registry, and deploying with proper IAM configuration.

### Prerequisites for Cloud Run Deployment

1. **Create an Artifact Registry repository** (one-time setup):

```bash
# Set your project and region
export GCP_PROJECT_ID="your-project-id"
export REGION="us-central1"

# Create Artifact Registry repository
gcloud artifacts repositories create cloud-run-apps \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Container images for Cloud Run applications" \
    --project="${GCP_PROJECT_ID}"
```

2. **Create a dedicated service account** (recommended for production):

```bash
# Create service account
gcloud iam service-accounts create journey-log-sa \
    --display-name="Journey Log Service Account" \
    --project="${GCP_PROJECT_ID}"

# Grant Firestore read/write permissions
gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
    --member="serviceAccount:journey-log-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/datastore.user"
```

### Required Environment Variables

The deployment script requires the following environment variables:

```bash
# Required variables
export GCP_PROJECT_ID="your-project-id"              # GCP Project ID
export REGION="us-central1"                          # GCP region
export SERVICE_NAME="journey-log"                    # Cloud Run service name
export ARTIFACT_REGISTRY_REPO="cloud-run-apps"       # Artifact Registry repo name
export SERVICE_ACCOUNT="journey-log-sa@your-project-id.iam.gserviceaccount.com"

# Optional variables (with defaults)
export IMAGE_TAG="latest"                            # Container image tag (default: latest)
export SERVICE_ENVIRONMENT="prod"                    # Environment (default: prod)
export MIN_INSTANCES="0"                             # Min instances (default: 0)
export MAX_INSTANCES="10"                            # Max instances (default: 10)
export MEMORY="512Mi"                                # Memory allocation (default: 512Mi)
export CPU="1"                                       # CPU allocation (default: 1)
export CONCURRENCY="80"                              # Request concurrency (default: 80)
export TIMEOUT="300"                                 # Request timeout in seconds (default: 300)
export ALLOW_UNAUTHENTICATED="false"                 # Public access (default: false)
```

### Deploying to Cloud Run

#### Using the Deployment Script (Recommended)

```bash
# Set required environment variables
export GCP_PROJECT_ID="your-project-id"
export REGION="us-central1"
export SERVICE_NAME="journey-log"
export ARTIFACT_REGISTRY_REPO="cloud-run-apps"
export SERVICE_ACCOUNT="journey-log-sa@your-project-id.iam.gserviceaccount.com"

# Run deployment script
./scripts/deploy_cloud_run.sh
```

Or using Make:

```bash
# Set environment variables, then run:
make deploy
```

The deployment script will:

1. ✓ Validate all required environment variables
2. ✓ Verify gcloud authentication
3. ✓ Enable required GCP APIs (Artifact Registry, Cloud Run, Firestore, Cloud Build)
4. ✓ Configure Docker authentication for Artifact Registry
5. ✓ Build the container image with build metadata
6. ✓ Push the image to Artifact Registry
7. ✓ Deploy to Cloud Run with specified configuration
8. ✓ Display the service URL and next steps

#### Security Note: Authenticated Deployment

**By default, the deployment script deploys with authentication required** (`--no-allow-unauthenticated`). This prevents public access and requires callers to have the `roles/run.invoker` role.

To allow public access (use with caution):

```bash
export ALLOW_UNAUTHENTICATED="true"
./scripts/deploy_cloud_run.sh
```

The script will prompt for confirmation before deploying with public access.

### Granting Access to Cloud Run Service

After deploying with authentication required, grant access to specific users or service accounts:

```bash
# Grant access to a specific user
gcloud run services add-iam-policy-binding journey-log \
    --region="${REGION}" \
    --member="user:your-email@example.com" \
    --role="roles/run.invoker" \
    --project="${GCP_PROJECT_ID}"

# Grant access to a service account (for service-to-service calls)
gcloud run services add-iam-policy-binding journey-log \
    --region="${REGION}" \
    --member="serviceAccount:caller-sa@project-id.iam.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --project="${GCP_PROJECT_ID}"

# Grant access to all authenticated users (less restrictive)
gcloud run services add-iam-policy-binding journey-log \
    --region="${REGION}" \
    --member="allAuthenticatedUsers" \
    --role="roles/run.invoker" \
    --project="${GCP_PROJECT_ID}"
```

### Environment-Specific Deployments

Deploy to different environments (dev, staging, prod) using environment variables:

```bash
# Deploy to staging
export SERVICE_ENVIRONMENT="staging"
export SERVICE_NAME="journey-log-staging"
export IMAGE_TAG="staging-$(git rev-parse --short HEAD)"
export MIN_INSTANCES="0"
export MAX_INSTANCES="5"
./scripts/deploy_cloud_run.sh

# Deploy to production
export SERVICE_ENVIRONMENT="prod"
export SERVICE_NAME="journey-log"
export IMAGE_TAG="prod-v1.0.0"
export MIN_INSTANCES="1"
export MAX_INSTANCES="10"
./scripts/deploy_cloud_run.sh
```

### Manual Deployment (Alternative)

If you prefer to deploy manually without the script:

```bash
# Build and push to Artifact Registry
IMAGE="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${SERVICE_NAME}:latest"

docker build -t "${IMAGE}" .
docker push "${IMAGE}"

# Deploy to Cloud Run
gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE}" \
    --platform=managed \
    --region="${REGION}" \
    --no-allow-unauthenticated \
    --service-account="${SERVICE_ACCOUNT}" \
    --memory=512Mi \
    --cpu=1 \
    --concurrency=80 \
    --timeout=300 \
    --min-instances=0 \
    --max-instances=10 \
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},SERVICE_ENVIRONMENT=prod,SERVICE_NAME=${SERVICE_NAME}" \
    --project="${GCP_PROJECT_ID}"
```

### IAM Role Summary

For a complete Cloud Run deployment, you need the following IAM roles:

#### Cloud Run Service Account (Runtime)

The service account used by Cloud Run to run your application:

- **`roles/datastore.user`**: Read/write access to Firestore
  - Required for: Writing/reading journey logs and entries

#### Caller/Invoker Principals

Users or service accounts that need to call the Cloud Run service:

- **`roles/run.invoker`**: Permission to invoke Cloud Run service
  - Required for: Any user or service account that needs to call the API

#### Deployment Principal (Your User/CI)

The account performing the deployment needs:

- **`roles/run.admin`**: Manage Cloud Run services
- **`roles/iam.serviceAccountUser`**: Use service accounts
- **`roles/artifactregistry.writer`**: Push images to Artifact Registry

### Viewing Deployment Details

After deployment, view service details:

```bash
# Get service URL
gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${GCP_PROJECT_ID}" \
    --format='value(status.url)'

# View service configuration
gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${GCP_PROJECT_ID}"

# List all Cloud Run services
gcloud run services list \
    --project="${GCP_PROJECT_ID}"
```

## Testing Connectivity

### Local Testing

Once the service is running locally:

```bash
# Test with POST request (recommended)
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

# Clean up test documents
curl -X DELETE http://localhost:8080/firestore-test

# Expected response:
{
  "status": "success",
  "message": "Successfully deleted N test document(s) from collection 'connectivity_test'",
  "deleted_count": N,
  "timestamp": "2026-01-11T12:34:56.789012+00:00"
}
```

**Security Note**: In production, these endpoints should be protected with authentication. See the security section below.

### Cloud Run Testing

After deploying to Cloud Run, test the deployment:

#### Testing with Authentication Required (Default)

If deployed without public access (recommended):

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${GCP_PROJECT_ID}" \
    --format='value(status.url)')

# Test health endpoint with authentication
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    "${SERVICE_URL}/health"

# Test info endpoint
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    "${SERVICE_URL}/info"

# Test Firestore connectivity (POST)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    -X POST "${SERVICE_URL}/firestore-test"

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
    "environment": "prod"
  },
  "timestamp": "2026-01-11T12:34:56.789012+00:00"
}

# Clean up test documents
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    -X DELETE "${SERVICE_URL}/firestore-test"

# Expected response:
{
  "status": "success",
  "message": "Successfully deleted N test document(s) from collection 'connectivity_test'",
  "deleted_count": N,
  "timestamp": "2026-01-11T12:34:56.789012+00:00"
}
```

#### Testing with Public Access

If deployed with `ALLOW_UNAUTHENTICATED=true`:

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${GCP_PROJECT_ID}" \
    --format='value(status.url)')

# Test without authentication
curl "${SERVICE_URL}/health"
curl "${SERVICE_URL}/info"
curl -X POST "${SERVICE_URL}/firestore-test"
curl -X DELETE "${SERVICE_URL}/firestore-test"
```

**Security Warning**: Public access should only be used for development/testing. Always use authentication for production deployments.

### API Documentation

Once deployed, access the interactive API documentation:

- **Swagger UI**: `https://your-service-url/docs`
- **ReDoc**: `https://your-service-url/redoc`

## Troubleshooting

### Common Issues

#### 1. Permission Denied Errors

**Error**: `PermissionDenied: 403 Missing or insufficient permissions`

**Solution**:
- Verify the service account has `roles/datastore.user` role
- Check that Firestore API is enabled: `gcloud services enable firestore.googleapis.com`
- Ensure you're using the correct project ID

```bash
# Enable Firestore API
gcloud services enable firestore.googleapis.com --project=YOUR_PROJECT_ID

# Verify IAM permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:YOUR_SERVICE_ACCOUNT"
```

#### 2. Project ID Not Set

**Error**: `ValueError: GCP_PROJECT_ID must be set when not using Firestore emulator`

**Solution**:
- Set `GCP_PROJECT_ID` environment variable
- Or set `FIRESTORE_EMULATOR_HOST` for local development

```bash
# For production
export GCP_PROJECT_ID="your-project-id"

# For local development
export FIRESTORE_EMULATOR_HOST="localhost:8080"
```

#### 3. ADC Not Found

**Error**: `DefaultCredentialsError: Could not automatically determine credentials`

**Solution**:
- Run `gcloud auth application-default login`
- Or set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key path

#### 4. Firestore Not Initialized

**Error**: `FailedPrecondition: 400 Firestore API has not been used in project before`

**Solution**:
- Create a Firestore database in the GCP Console
- Or use: `gcloud firestore databases create --region=us-central1`

### Debug Mode

Enable debug logging to troubleshoot issues:

```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG

# Run the service
uvicorn app.main:app --reload
```

### Checking Service Logs on Cloud Run

```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=journey-log" \
    --limit=50 \
    --format=json \
    --project=YOUR_PROJECT_ID

# Stream logs in real-time
gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=journey-log" \
    --project=YOUR_PROJECT_ID
```

## Security Best Practices

### Protect Operational Endpoints

The `/firestore-test` endpoint should be protected in production environments:

```bash
# Deploy with authentication required (no public access)
gcloud run deploy journey-log \
    --no-allow-unauthenticated \
    --region=us-central1

# Grant access to specific users/service accounts only
gcloud run services add-iam-policy-binding journey-log \
    --region=us-central1 \
    --member="user:admin@example.com" \
    --role="roles/run.invoker"

# Test authenticated endpoint
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    -X POST "${SERVICE_URL}/firestore-test"
```

### General Security Guidelines

1. **Use Workload Identity Federation** for CI/CD instead of service account keys
2. **Rotate service account keys** regularly if you must use them
3. **Restrict IAM roles** to the minimum required permissions
4. **Enable audit logging** to track Firestore access
5. **Use Secret Manager** for sensitive configuration values
6. **Don't commit** service account keys or `.env` files to version control
7. **Review and clean up** test documents from the connectivity_test collection regularly using the DELETE endpoint
8. **Protect operational endpoints** with authentication in production (see above)
9. **Monitor for unusual activity** on test endpoints
10. **Use environment-specific error messages** to avoid information disclosure

## Cleanup Script

### Overview

The cleanup script (`scripts/remove_numeric_health.py`) removes deprecated numeric health fields from existing Firestore character documents. This is useful when migrating from numeric health tracking to the status-only model.

### When to Use the Cleanup Script

- **After Migration:** When transitioning existing characters from numeric health to status-only model
- **Database Maintenance:** Periodically clean up legacy fields that may have been written by older code
- **Storage Optimization:** Remove unnecessary fields to reduce document size
- **Audit Compliance:** Ensure consistent schema across all stored documents

**Note:** The application automatically strips legacy fields when reading documents, so running the cleanup script is **optional**. It's primarily useful for:
1. Reducing stored document sizes
2. Ensuring consistent schema in the database
3. Simplifying manual database inspection/debugging

### Environment Variables

Add these variables to your `.env` file:

```bash
# Required for cleanup script
GCP_PROJECT_ID=your-project-id

# Optional: Specify custom collection name (defaults to "characters")
FIRESTORE_CHARACTERS_COLLECTION=characters

# Optional: For local testing with Firestore emulator
FIRESTORE_EMULATOR_HOST=localhost:8080
```

### Running the Script

#### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Authenticate with GCP

```bash
# For local development
gcloud auth application-default login

# Or use service account key
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

#### 3. Preview Changes (Dry Run)

**Always run in dry-run mode first to preview changes:**

```bash
python scripts/remove_numeric_health.py --dry-run
```

This will:
- Scan all character documents
- Identify legacy numeric health fields
- Log what **would** be removed
- **Not modify** any documents

#### 4. Apply Changes

After reviewing the dry-run output:

```bash
# Clean all documents
python scripts/remove_numeric_health.py

# Clean specific documents
python scripts/remove_numeric_health.py --character-ids char_001 char_002

# Clean first 100 documents (for testing)
python scripts/remove_numeric_health.py --limit 100
```

### Script Options

| Flag | Description | Default |
|------|-------------|---------|
| `--dry-run` | Preview changes without modifying documents | `False` |
| `--character-ids` | Process only specific character IDs (space-separated) | `None` (all) |
| `--limit` | Process at most N documents | `None` (all) |
| `--batch-size` | Number of documents per batch | `10` |
| `--batch-delay` | Seconds to wait between batches | `0.5` |

### Example Usage

```bash
# Preview changes for specific characters
python scripts/remove_numeric_health.py --dry-run --character-ids \
  550e8400-e29b-41d4-a716-446655440000 \
  660f9511-f39c-52e5-b827-557766551111

# Clean all documents with progress logging
python scripts/remove_numeric_health.py

# Conservative cleanup for large datasets (slower, avoids rate limits)
python scripts/remove_numeric_health.py --batch-size 5 --batch-delay 2.0

# Test on small subset first
python scripts/remove_numeric_health.py --limit 10
```

### What Gets Removed

The script removes these deprecated fields from `player_state`:
- `level` (numeric progression)
- `experience` (numeric XP)
- `stats` (nested stat object)
- `current_hp`, `max_hp` (HP-style health)
- `current_health`, `max_health` (alternative health fields)
- `health` (any format)

### Permissions Required

The script needs Firestore read/write permissions:

#### For Service Account

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/datastore.user"
```

#### For User Account

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:YOUR_EMAIL" \
  --role="roles/datastore.user"
```

### Rate Limits and Performance

**Firestore Quotas:**
- Standard tier: 10,000 writes/day free, then paid
- Read operations: 50,000/day free, then paid
- Consult [Firestore quotas](https://cloud.google.com/firestore/quotas) for your project tier

**Script Performance:**
- Default: ~1000 documents/minute
- Adjust `--batch-size` and `--batch-delay` to tune throughput
- Use conservative settings for heavily rate-limited projects

**Recommendations:**
- Start with `--limit 100` to test performance
- Monitor GCP Console → Firestore → Usage for quota consumption
- Increase batch size only if well within quota limits
- Add delays if encountering rate limit errors

### Safety Features

The script includes several safety mechanisms:

1. **Dry-run mode:** Preview without modifying data
2. **Atomic updates:** Each document update is atomic (no partial updates)
3. **Error isolation:** Failures on individual documents don't stop the batch
4. **Idempotent:** Safe to run multiple times
5. **Graceful handling:** Documents without legacy fields are skipped
6. **Audit logging:** All actions logged with character IDs and field names
7. **Status validation:** Documents missing status field are logged but not modified

### Validation After Cleanup

Verify the cleanup was successful:

```bash
# Run dry-run again - should find no documents to clean
python scripts/remove_numeric_health.py --dry-run
```

Expected output:
```
INFO: Dry run mode enabled - no changes will be made
INFO: Scanning character documents...
INFO: Processed 1000 documents
INFO: Documents with legacy fields: 0
INFO: Documents cleaned: 0 (dry run)
```

### Troubleshooting

**Permission Denied:**
```bash
# Verify authentication
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID

# Verify IAM roles
gcloud projects get-iam-policy YOUR_PROJECT_ID --flatten="bindings[].members" --filter="bindings.members:user:YOUR_EMAIL"
```

**Rate Limit Errors:**
```bash
# Reduce throughput
python scripts/remove_numeric_health.py --batch-size 2 --batch-delay 5.0
```

**Script Hangs:**
- Check network connectivity to GCP
- Verify Firestore database exists and is in active state
- Check for very large documents (>500KB) that may timeout

**Unexpected Results:**
- Review dry-run output carefully before applying
- Check application logs for automatic stripping behavior
- Verify `GCP_PROJECT_ID` and `FIRESTORE_CHARACTERS_COLLECTION` are correct

## Additional Resources

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Firestore Documentation](https://cloud.google.com/firestore/docs)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [IAM Roles for Firestore](https://cloud.google.com/firestore/docs/security/iam)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
