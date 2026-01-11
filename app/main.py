"""
Journey Log API Service - Main Application

FastAPI application with health and info endpoints.
"""

from typing import Any
from fastapi import FastAPI

from app.config import get_settings

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
        },
        "configuration": {
            "gcp_project_id": settings.gcp_project_id or "not-configured",
            "firestore_journeys_collection": settings.firestore_journeys_collection,
            "firestore_entries_collection": settings.firestore_entries_collection,
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
