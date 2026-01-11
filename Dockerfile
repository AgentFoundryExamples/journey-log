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

# Multi-stage build for production-ready Journey Log API
# Base: Python 3.14-slim (aligned with infrastructure_versions.txt)
# Target: Google Cloud Run

# Stage 1: Builder - Install dependencies
FROM python:3.14-slim AS builder

# Copy uv for faster dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY requirements.txt .

# Install dependencies using uv for faster installation
# Using --system to install globally for smaller final image
RUN uv pip install --system --no-cache -r requirements.txt

# Stage 2: Runtime - Minimal production image
FROM python:3.14-slim

# Install security updates and create non-root user
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r appuser && \
    useradd -r -g appuser -u 1001 -m -s /sbin/nologin appuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appuser . .

# Set ownership for app directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Cloud Run sets PORT environment variable, default to 8080
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port (documentation only, Cloud Run manages this)
EXPOSE 8080

# Health check (optional, Cloud Run has built-in health checks)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health').read()" || exit 1

# Run uvicorn with production settings
# - host 0.0.0.0 to accept external connections
# - port from $PORT (Cloud Run sets this)
# - workers: Cloud Run manages concurrency, use 1 worker per instance
# - timeout-keep-alive: 75 seconds (Cloud Run timeout is configurable)
# - limit-concurrency: Let Cloud Run manage this
CMD uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --timeout-keep-alive 75 \
    --log-level info
