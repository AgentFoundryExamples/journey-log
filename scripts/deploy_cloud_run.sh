#!/usr/bin/env bash
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

#
# deploy_cloud_run.sh - Deploy Journey Log API to Google Cloud Run
#
# This script builds a Docker container, pushes it to Artifact Registry,
# and deploys it to Cloud Run with proper IAM and Firestore access.
#
# Usage:
#   ./scripts/deploy_cloud_run.sh
#
# Required Environment Variables:
#   GCP_PROJECT_ID          - GCP Project ID
#   REGION                  - GCP region (e.g., us-central1)
#   SERVICE_NAME            - Cloud Run service name (e.g., journey-log)
#   ARTIFACT_REGISTRY_REPO  - Artifact Registry repository name
#   SERVICE_ACCOUNT         - Service account email for Cloud Run
#
# Optional Environment Variables:
#   IMAGE_TAG               - Container image tag (default: latest)
#   SERVICE_ENVIRONMENT     - Environment (dev/staging/prod, default: prod)
#   MIN_INSTANCES           - Minimum instances (default: 0)
#   MAX_INSTANCES           - Maximum instances (default: 10)
#   MEMORY                  - Memory allocation (default: 512Mi)
#   CPU                     - CPU allocation (default: 1)
#   CONCURRENCY             - Request concurrency per instance (default: 80)
#   TIMEOUT                 - Request timeout in seconds (default: 300)
#   ALLOW_UNAUTHENTICATED   - Allow public access (default: false)
#   BUILD_VERSION           - Build version for env var
#   BUILD_COMMIT            - Git commit SHA for env var
#   BUILD_TIMESTAMP         - Build timestamp for env var
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate required environment variables
validate_env() {
    local missing_vars=()
    
    if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
        missing_vars+=("GCP_PROJECT_ID")
    fi
    
    if [[ -z "${REGION:-}" ]]; then
        missing_vars+=("REGION")
    fi
    
    if [[ -z "${SERVICE_NAME:-}" ]]; then
        missing_vars+=("SERVICE_NAME")
    fi
    
    if [[ -z "${ARTIFACT_REGISTRY_REPO:-}" ]]; then
        missing_vars+=("ARTIFACT_REGISTRY_REPO")
    fi
    
    if [[ -z "${SERVICE_ACCOUNT:-}" ]]; then
        missing_vars+=("SERVICE_ACCOUNT")
    fi
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "  - $var"
        done
        echo ""
        echo "Example usage:"
        echo "  export GCP_PROJECT_ID=my-project"
        echo "  export REGION=us-central1"
        echo "  export SERVICE_NAME=journey-log"
        echo "  export ARTIFACT_REGISTRY_REPO=cloud-run-apps"
        echo "  export SERVICE_ACCOUNT=journey-log-sa@my-project.iam.gserviceaccount.com"
        echo "  ./scripts/deploy_cloud_run.sh"
        exit 1
    fi
}

# Set default values
IMAGE_TAG="${IMAGE_TAG:-latest}"
SERVICE_ENVIRONMENT="${SERVICE_ENVIRONMENT:-prod}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"
MEMORY="${MEMORY:-512Mi}"
CPU="${CPU:-1}"
CONCURRENCY="${CONCURRENCY:-80}"
TIMEOUT="${TIMEOUT:-300}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-false}"

# Build metadata defaults
BUILD_VERSION="${BUILD_VERSION:-$(git describe --tags --always 2>/dev/null || echo 'unknown')}"
BUILD_COMMIT="${BUILD_COMMIT:-$(git rev-parse HEAD 2>/dev/null || echo 'unknown')}"
BUILD_TIMESTAMP="${BUILD_TIMESTAMP:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}"

# Main deployment flow
main() {
    log_info "Starting Cloud Run deployment for ${SERVICE_NAME}"
    echo ""
    
    # Validate environment
    validate_env
    
    # Construct image name
    IMAGE_NAME="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY_REPO}/${SERVICE_NAME}:${IMAGE_TAG}"
    
    log_info "Configuration:"
    echo "  Project ID:          ${GCP_PROJECT_ID}"
    echo "  Region:              ${REGION}"
    echo "  Service Name:        ${SERVICE_NAME}"
    echo "  Image:               ${IMAGE_NAME}"
    echo "  Service Account:     ${SERVICE_ACCOUNT}"
    echo "  Environment:         ${SERVICE_ENVIRONMENT}"
    echo "  Min Instances:       ${MIN_INSTANCES}"
    echo "  Max Instances:       ${MAX_INSTANCES}"
    echo "  Memory:              ${MEMORY}"
    echo "  CPU:                 ${CPU}"
    echo "  Concurrency:         ${CONCURRENCY}"
    echo "  Timeout:             ${TIMEOUT}s"
    echo "  Public Access:       ${ALLOW_UNAUTHENTICATED}"
    echo ""
    
    # Security check: Prevent accidental public deployment
    if [[ "${ALLOW_UNAUTHENTICATED}" == "true" ]]; then
        log_warn "WARNING: Deploying with public access enabled (--allow-unauthenticated)"
        log_warn "This will allow anyone on the internet to access your service."
        read -p "Are you sure you want to continue? (yes/no): " -r
        echo
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            log_error "Deployment cancelled by user"
            exit 1
        fi
    fi
    
    # Step 1: Verify gcloud authentication
    log_info "Verifying gcloud authentication..."
    ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -n 1)
    if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
        log_error "Not authenticated with gcloud. Run: gcloud auth login"
        exit 1
    fi
    log_info "✓ Authenticated as ${ACTIVE_ACCOUNT}"
    echo ""
    
    # Step 2: Set active project
    log_info "Setting active project to ${GCP_PROJECT_ID}..."
    gcloud config set project "${GCP_PROJECT_ID}"
    echo ""
    
    # Step 3: Enable required APIs
    log_info "Ensuring required APIs are enabled..."
    gcloud services enable \
        artifactregistry.googleapis.com \
        run.googleapis.com \
        firestore.googleapis.com \
        cloudbuild.googleapis.com \
        --project="${GCP_PROJECT_ID}" \
        --quiet
    log_info "✓ APIs enabled"
    echo ""
    
    # Step 4: Configure Docker authentication
    log_info "Configuring Docker authentication for Artifact Registry..."
    gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
    echo ""
    
    # Step 5: Build container image
    log_info "Building container image..."
    docker build \
        --platform linux/amd64 \
        --tag "${IMAGE_NAME}" \
        --build-arg BUILD_VERSION="${BUILD_VERSION}" \
        --build-arg BUILD_COMMIT="${BUILD_COMMIT}" \
        --build-arg BUILD_TIMESTAMP="${BUILD_TIMESTAMP}" \
        .
    log_info "✓ Image built successfully"
    echo ""
    
    # Step 6: Push image to Artifact Registry
    log_info "Pushing image to Artifact Registry..."
    docker push "${IMAGE_NAME}"
    log_info "✓ Image pushed successfully"
    echo ""
    
    # Step 7: Deploy to Cloud Run
    log_info "Deploying to Cloud Run..."
    
    # Build gcloud command with authentication flag
    DEPLOY_CMD=(
        gcloud run deploy "${SERVICE_NAME}"
        --image="${IMAGE_NAME}"
        --platform=managed
        --region="${REGION}"
        --service-account="${SERVICE_ACCOUNT}"
        --memory="${MEMORY}"
        --cpu="${CPU}"
        --concurrency="${CONCURRENCY}"
        --timeout="${TIMEOUT}"
        --min-instances="${MIN_INSTANCES}"
        --max-instances="${MAX_INSTANCES}"
        --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},SERVICE_ENVIRONMENT=${SERVICE_ENVIRONMENT},SERVICE_NAME=${SERVICE_NAME},BUILD_VERSION=${BUILD_VERSION},BUILD_COMMIT=${BUILD_COMMIT},BUILD_TIMESTAMP=${BUILD_TIMESTAMP}"
        --project="${GCP_PROJECT_ID}"
        --quiet
    )
    
    # Add authentication flag
    if [[ "${ALLOW_UNAUTHENTICATED}" == "true" ]]; then
        DEPLOY_CMD+=(--allow-unauthenticated)
    else
        DEPLOY_CMD+=(--no-allow-unauthenticated)
    fi
    
    # Execute deployment
    "${DEPLOY_CMD[@]}"
    
    log_info "✓ Deployment successful!"
    echo ""
    
    # Step 8: Get service URL
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --project="${GCP_PROJECT_ID}" \
        --format='value(status.url)')
    
    log_info "Service deployed successfully!"
    echo ""
    echo "Service URL: ${SERVICE_URL}"
    echo ""
    
    # Step 9: Show next steps
    log_info "Next steps:"
    echo ""
    
    if [[ "${ALLOW_UNAUTHENTICATED}" == "true" ]]; then
        echo "Test the service:"
        echo "  curl ${SERVICE_URL}/health"
        echo "  curl ${SERVICE_URL}/info"
        echo "  curl -X POST ${SERVICE_URL}/firestore-test"
    else
        echo "The service requires authentication. Grant access to users/service accounts:"
        echo ""
        echo "  gcloud run services add-iam-policy-binding ${SERVICE_NAME} \\"
        echo "    --region=${REGION} \\"
        echo "    --member='user:YOUR_EMAIL@example.com' \\"
        echo "    --role='roles/run.invoker' \\"
        echo "    --project=${GCP_PROJECT_ID}"
        echo ""
        echo "Test the service with authentication:"
        echo "  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" \\"
        echo "    ${SERVICE_URL}/health"
        echo ""
        echo "  curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" \\"
        echo "    -X POST ${SERVICE_URL}/firestore-test"
    fi
    echo ""
    
    log_info "View logs:"
    echo "  gcloud logging tail \"resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}\" \\"
    echo "    --project=${GCP_PROJECT_ID}"
    echo ""
}

# Run main function
main "$@"
