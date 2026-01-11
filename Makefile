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

# Makefile for Journey Log API
# Provides common development and deployment tasks

.PHONY: help install dev clean lint format test build run docker-build docker-run deploy

# Default target
help:
	@echo "Journey Log API - Available targets:"
	@echo ""
	@echo "Development:"
	@echo "  make install         - Install dependencies"
	@echo "  make dev            - Run development server with hot reload"
	@echo "  make lint           - Run linter (ruff)"
	@echo "  make format         - Format code (ruff)"
	@echo "  make test           - Run tests (pytest)"
	@echo "  make clean          - Clean up temporary files"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build   - Build Docker image locally"
	@echo "  make docker-run     - Run Docker container locally"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy         - Deploy to Cloud Run (requires env vars)"
	@echo ""
	@echo "For Cloud Run deployment, set these environment variables:"
	@echo "  GCP_PROJECT_ID, REGION, SERVICE_NAME,"
	@echo "  ARTIFACT_REGISTRY_REPO, SERVICE_ACCOUNT"
	@echo ""

# Install dependencies
install:
	@echo "Installing dependencies..."
	pip install --upgrade pip
	pip install -r requirements.txt

# Run development server
dev:
	@echo "Starting development server..."
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".DS_Store" -delete

# Run linter
lint:
	@echo "Running linter..."
	ruff check .

# Format code
format:
	@echo "Formatting code..."
	ruff format .

# Run tests
test:
	@echo "Running tests..."
	pytest -v

# Build Docker image locally
docker-build:
	@echo "Building Docker image..."
	docker build -t journey-log:latest \
		--build-arg BUILD_VERSION=$$(git describe --tags --always 2>/dev/null || echo 'dev') \
		--build-arg BUILD_COMMIT=$$(git rev-parse HEAD 2>/dev/null || echo 'unknown') \
		--build-arg BUILD_TIMESTAMP=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
		.
	@echo "Image built: journey-log:latest"

# Run Docker container locally
docker-run:
	@echo "Running Docker container..."
	@echo "Service will be available at http://localhost:8080"
	docker run --rm -it \
		-p 8080:8080 \
		-e SERVICE_ENVIRONMENT=dev \
		-e GCP_PROJECT_ID=${GCP_PROJECT_ID:-demo-project} \
		-e FIRESTORE_EMULATOR_HOST=${FIRESTORE_EMULATOR_HOST:-} \
		journey-log:latest

# Deploy to Cloud Run
deploy:
	@echo "Deploying to Cloud Run..."
	./scripts/deploy_cloud_run.sh
