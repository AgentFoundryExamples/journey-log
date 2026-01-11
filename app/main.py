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
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import get_settings
from app.routers import firestore_test
from app.logging import configure_logging, get_logger
from app.middleware import RequestIDMiddleware

# Configure structured logging
configure_logging()
logger = get_logger(__name__)

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

# Add middleware
app.add_middleware(RequestIDMiddleware)

# Include routers
app.include_router(firestore_test.router)


# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handle HTTPException with structured JSON response.

    Returns a standardized JSON error response for HTTP exceptions,
    including the request ID for traceability.

    Args:
        request: The request that caused the exception
        exc: The HTTPException

    Returns:
        JSON response with error details
    """
    # Extract request ID from headers if available
    request_id = request.headers.get(settings.request_id_header.lower(), "unknown")

    # Log the exception
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        request_id=request_id,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "message": exc.detail,
            "status_code": exc.status_code,
            "request_id": request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle request validation errors with structured JSON response.

    Returns a standardized JSON error response for validation errors,
    including the request ID for traceability.

    Args:
        request: The request that caused the exception
        exc: The RequestValidationError

    Returns:
        JSON response with validation error details
    """
    # Extract request ID from headers if available
    request_id = request.headers.get(settings.request_id_header.lower(), "unknown")

    # Log the validation error
    logger.warning(
        "validation_error",
        errors=exc.errors(),
        request_id=request_id,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "errors": exc.errors(),
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle generic exceptions with structured JSON response.

    Returns a standardized JSON error response for uncaught exceptions.
    In production, hides stack traces and sensitive details. In dev mode,
    provides more verbose error information for debugging.

    Args:
        request: The request that caused the exception
        exc: The exception

    Returns:
        JSON response with error details
    """
    # Extract request ID from headers if available
    request_id = request.headers.get(settings.request_id_header.lower(), "unknown")

    # Log the exception with stack trace
    logger.error(
        "unhandled_exception",
        error_type=type(exc).__name__,
        error_message=str(exc),
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exc_info=True,  # Include stack trace in logs
    )

    # Prepare error response based on environment
    if settings.service_environment == "dev":
        # In dev, provide detailed error information
        error_response = {
            "error": "internal_error",
            "message": f"{type(exc).__name__}: {str(exc)}",
            "type": type(exc).__name__,
            "request_id": request_id,
        }
    else:
        # In production, hide sensitive details
        error_response = {
            "error": "internal_error",
            "message": "An internal error occurred. Please contact support with the request ID.",
            "request_id": request_id,
        }

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response,
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    """
    Health check endpoint.

    Returns the service status and basic identifiers.
    Always returns 200 OK when the service is running.
    """
    logger.info("health_check_requested")
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
    logger.info("info_requested")
    return {
        "service": settings.service_name,
        "version": settings.build_version,
        "environment": settings.service_environment,
        "build": {
            "version": settings.build_version,
            "commit": settings.build_commit or "unknown",
            "timestamp": settings.build_timestamp or "unknown",
        },
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
