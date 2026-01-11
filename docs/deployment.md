# Deployment Guide

This document provides detailed instructions for deploying the Journey Log API to Google Cloud Platform and configuring Firestore access.

## Table of Contents

- [Prerequisites](#prerequisites)
- [IAM Roles and Permissions](#iam-roles-and-permissions)
- [Local Development Setup](#local-development-setup)
- [Firestore Configuration](#firestore-configuration)
- [Cloud Run Deployment](#cloud-run-deployment)
- [Testing Connectivity](#testing-connectivity)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before deploying the Journey Log API, ensure you have:

1. **Google Cloud Project**: An active GCP project with billing enabled
2. **gcloud CLI**: Installed and configured ([Installation Guide](https://cloud.google.com/sdk/docs/install))
3. **Firestore Database**: A Firestore database created in your project (Native mode recommended)
4. **Docker** (optional): For local container testing
5. **Python 3.12+**: For local development

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

### Build and Deploy

```bash
# Set variables
PROJECT_ID="your-project-id"
REGION="us-central1"
SERVICE_NAME="journey-log"
IMAGE_NAME="journey-log"

# Build and push to Artifact Registry
gcloud builds submit \
    --tag="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${IMAGE_NAME}" \
    --project="${PROJECT_ID}"

# Deploy to Cloud Run
gcloud run deploy "${SERVICE_NAME}" \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${IMAGE_NAME}" \
    --platform=managed \
    --region="${REGION}" \
    --allow-unauthenticated \
    --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},SERVICE_ENVIRONMENT=prod" \
    --service-account="${SERVICE_ACCOUNT}" \
    --memory=512Mi \
    --cpu=1 \
    --project="${PROJECT_ID}"
```

### Using Dockerfile

Create a `Dockerfile` in your project root:

```dockerfile
FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Then deploy:

```bash
gcloud run deploy journey-log \
    --source=. \
    --region=us-central1 \
    --allow-unauthenticated
```

## Testing Connectivity

### Local Testing

Once the service is running locally:

```bash
# Test with GET request
curl http://localhost:8080/firestore-test

# Test with POST request
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

### Cloud Run Testing

After deploying to Cloud Run:

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe journey-log \
    --region=us-central1 \
    --format='value(status.url)')

# Test connectivity
curl "${SERVICE_URL}/firestore-test"

# Or use httpie
http GET "${SERVICE_URL}/firestore-test"
```

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

1. **Use Workload Identity Federation** for CI/CD instead of service account keys
2. **Rotate service account keys** regularly if you must use them
3. **Restrict IAM roles** to the minimum required permissions
4. **Enable audit logging** to track Firestore access
5. **Use Secret Manager** for sensitive configuration values
6. **Don't commit** service account keys or `.env` files to version control
7. **Review and clean up** test documents from the connectivity_test collection regularly

## Additional Resources

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Firestore Documentation](https://cloud.google.com/firestore/docs)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
- [IAM Roles for Firestore](https://cloud.google.com/firestore/docs/security/iam)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
