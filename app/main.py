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
Journey Log API Service - Main Application

FastAPI application with health and info endpoints.
"""

from typing import Any
from fastapi import FastAPI

from app.config import get_settings
from app.routers import firestore_test

# Load settings
settings = get_settings()

# Create FastAPI application
app = FastAPI(
    title="Journey Log API",
    description="A service for managing journey logs and entries",
    version=settings.build_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include routers
app.include_router(firestore_test.router)


@app.get("/health")
async def health() -> dict[str, Any]:
    """
    Health check endpoint.
    
    Returns the service status and basic identifiers.
    Always returns 200 OK when the service is running.
    """
    return {
        "status": "healthy",
        "service": settings.service_name,
        "environment": settings.service_environment,
        "version": settings.build_version,
    }


@app.get("/info")
async def info() -> dict[str, Any]:
    """
    Service information endpoint.
    
    Returns build and version metadata from environment variables.
    """
    return {
        "service": settings.service_name,
        "version": settings.build_version,
        "environment": settings.service_environment,
        "build": {
            "version": settings.build_version,
            "commit": settings.build_commit or "unknown",
            "timestamp": settings.build_timestamp or "unknown",
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
