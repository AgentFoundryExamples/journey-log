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
Firestore connectivity test router.

OPERATIONAL USE ONLY - This endpoint is for verifying Firestore
connectivity and permissions during deployment and operations.
It should NOT be used for application logic.
"""

from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.dependencies import FirestoreClient
from app.config import get_settings

router = APIRouter(
    prefix="/firestore-test",
    tags=["operations"],
)


class FirestoreTestResponse(BaseModel):
    """Response model for Firestore connectivity test."""
    
    status: str = Field(description="Test status (success or error)")
    message: str = Field(description="Human-readable message")
    document_id: str = Field(description="ID of the test document")
    data: dict[str, Any] = Field(description="Document data read back from Firestore")
    timestamp: str = Field(description="ISO 8601 timestamp of the test")


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str = Field(description="Error type")
    message: str = Field(description="Error message")
    timestamp: str = Field(description="ISO 8601 timestamp of the error")


@router.get(
    "",
    response_model=FirestoreTestResponse,
    responses={
        200: {
            "description": "Firestore connectivity test successful",
            "model": FirestoreTestResponse,
        },
        500: {
            "description": "Firestore connectivity test failed",
            "model": ErrorResponse,
        },
    },
    summary="Test Firestore connectivity (GET)",
    description=(
        "**OPERATIONAL ENDPOINT** - Verifies Firestore read/write access.\n\n"
        "This endpoint performs the following operations:\n"
        "1. Writes a test document to the configured test collection\n"
        "2. Reads the document back to verify read access\n"
        "3. Returns the document data\n\n"
        "The test document includes a timestamp and is NOT automatically cleaned up. "
        "Use this endpoint to verify Cloud Run service account permissions.\n\n"
        "**Required IAM Roles:**\n"
        "- `roles/datastore.user` (or equivalent Firestore permissions)\n"
        "- `roles/run.invoker` (to access the endpoint on Cloud Run)"
    ),
)
async def test_firestore_get(db: FirestoreClient) -> FirestoreTestResponse:
    """
    Test Firestore connectivity with a read/write operation (GET).
    
    This endpoint writes a test document and reads it back to verify
    that the service has proper Firestore permissions.
    """
    return await _perform_firestore_test(db)


@router.post(
    "",
    response_model=FirestoreTestResponse,
    responses={
        200: {
            "description": "Firestore connectivity test successful",
            "model": FirestoreTestResponse,
        },
        500: {
            "description": "Firestore connectivity test failed",
            "model": ErrorResponse,
        },
    },
    summary="Test Firestore connectivity (POST)",
    description=(
        "**OPERATIONAL ENDPOINT** - Verifies Firestore read/write access.\n\n"
        "This endpoint performs the following operations:\n"
        "1. Writes a test document to the configured test collection\n"
        "2. Reads the document back to verify read access\n"
        "3. Returns the document data\n\n"
        "The test document includes a timestamp and is NOT automatically cleaned up. "
        "Use this endpoint to verify Cloud Run service account permissions.\n\n"
        "**Required IAM Roles:**\n"
        "- `roles/datastore.user` (or equivalent Firestore permissions)\n"
        "- `roles/run.invoker` (to access the endpoint on Cloud Run)"
    ),
)
async def test_firestore_post(db: FirestoreClient) -> FirestoreTestResponse:
    """
    Test Firestore connectivity with a read/write operation (POST).
    
    This endpoint writes a test document and reads it back to verify
    that the service has proper Firestore permissions.
    """
    return await _perform_firestore_test(db)


async def _perform_firestore_test(db: FirestoreClient) -> FirestoreTestResponse:
    """
    Internal helper to perform the actual Firestore connectivity test.
    
    Args:
        db: Firestore client from dependency injection
        
    Returns:
        FirestoreTestResponse with test results
        
    Raises:
        HTTPException: If Firestore operations fail
    """
    settings = get_settings()
    test_collection = settings.firestore_test_collection
    timestamp = datetime.now(timezone.utc).isoformat()
    
    try:
        # Generate a unique document ID based on timestamp
        doc_id = f"test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Test data to write
        test_data = {
            "test_type": "connectivity_check",
            "timestamp": timestamp,
            "message": "Firestore connectivity test document",
            "service": settings.service_name,
            "environment": settings.service_environment,
        }
        
        # Write the test document
        doc_ref = db.collection(test_collection).document(doc_id)
        doc_ref.set(test_data)
        
        # Read the document back to verify read access
        doc_snapshot = doc_ref.get()
        
        if not doc_snapshot.exists:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "read_verification_failed",
                    "message": "Document was written but could not be read back",
                    "timestamp": timestamp,
                },
            )
        
        # Get the data from the snapshot
        read_data = doc_snapshot.to_dict()
        
        return FirestoreTestResponse(
            status="success",
            message=f"Successfully wrote to and read from Firestore collection '{test_collection}'",
            document_id=doc_id,
            data=read_data or {},
            timestamp=timestamp,
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch any other exceptions and return structured error
        error_type = type(e).__name__
        error_message = str(e)
        
        # Don't expose full stack traces in production
        if settings.service_environment == "prod":
            error_message = "Firestore operation failed. Check service logs for details."
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": error_type,
                "message": error_message,
                "timestamp": timestamp,
            },
        )
