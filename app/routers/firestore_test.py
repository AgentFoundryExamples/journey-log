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

SECURITY WARNING: This endpoint should be protected with authentication
in production environments. Consider using Cloud Run IAM or other
authentication mechanisms to prevent unauthorized access.
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


class CleanupResponse(BaseModel):
    """Response model for cleanup operation."""

    status: str = Field(description="Cleanup status (success or error)")
    message: str = Field(description="Human-readable message")
    deleted_count: int = Field(description="Number of documents deleted")
    timestamp: str = Field(description="ISO 8601 timestamp of the operation")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(description="Error type")
    message: str = Field(description="Error message")
    timestamp: str = Field(description="ISO 8601 timestamp of the error")


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
    summary="Test Firestore connectivity",
    description=(
        "**OPERATIONAL ENDPOINT** - Verifies Firestore read/write access.\n\n"
        "**SECURITY WARNING**: This endpoint should be protected with authentication "
        "in production. Use Cloud Run IAM or other auth mechanisms.\n\n"
        "This endpoint performs the following operations:\n"
        "1. Writes a test document to the configured test collection\n"
        "2. Reads the document back to verify read access\n"
        "3. Returns the document data\n\n"
        "Test documents are NOT automatically cleaned up. Use the DELETE endpoint "
        "to remove old test documents.\n\n"
        "**Required IAM Roles:**\n"
        "- `roles/datastore.user` (or equivalent Firestore permissions)\n"
        "- `roles/run.invoker` (to access the endpoint on Cloud Run)"
    ),
)
async def test_firestore_post(db: FirestoreClient) -> FirestoreTestResponse:
    """
    Test Firestore connectivity with a read/write operation.

    This endpoint writes a test document and reads it back to verify
    that the service has proper Firestore permissions.
    """
    return await _perform_firestore_test(db)


@router.delete(
    "",
    response_model=CleanupResponse,
    responses={
        200: {
            "description": "Test documents cleaned up successfully",
            "model": CleanupResponse,
        },
        500: {
            "description": "Cleanup operation failed",
            "model": ErrorResponse,
        },
    },
    summary="Clean up test documents",
    description=(
        "**OPERATIONAL ENDPOINT** - Removes test documents from Firestore.\n\n"
        "**SECURITY WARNING**: This endpoint should be protected with authentication "
        "in production. Use Cloud Run IAM or other auth mechanisms.\n\n"
        "This endpoint deletes all documents from the test collection to prevent "
        "accumulation of test data. Use this periodically to maintain a clean database.\n\n"
        "**Required IAM Roles:**\n"
        "- `roles/datastore.user` (or equivalent Firestore permissions)\n"
        "- `roles/run.invoker` (to access the endpoint on Cloud Run)"
    ),
)
async def cleanup_test_documents(db: FirestoreClient) -> CleanupResponse:
    """
    Clean up test documents from Firestore.

    This endpoint removes all documents from the connectivity test collection
    to prevent accumulation of test data over time.
    """
    return await _perform_cleanup(db)


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

        # Don't expose sensitive error details in production
        if settings.service_environment == "prod":
            error_message = (
                "Firestore operation failed. Check service logs for details."
            )
        else:
            # In dev/staging, provide more context for debugging
            error_message = f"Firestore operation failed: {str(e)}"

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": error_type,
                "message": error_message,
                "timestamp": timestamp,
            },
        )


async def _perform_cleanup(db: FirestoreClient) -> CleanupResponse:
    """
    Internal helper to clean up test documents from Firestore.

    Args:
        db: Firestore client from dependency injection

    Returns:
        CleanupResponse with cleanup results

    Raises:
        HTTPException: If cleanup operation fails
    """
    settings = get_settings()
    test_collection = settings.firestore_test_collection
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        # Get all documents in the test collection
        collection_ref = db.collection(test_collection)
        docs = collection_ref.stream()

        # Delete each document
        deleted_count = 0
        for doc in docs:
            doc.reference.delete()
            deleted_count += 1

        return CleanupResponse(
            status="success",
            message=f"Successfully deleted {deleted_count} test document(s) from collection '{test_collection}'",
            deleted_count=deleted_count,
            timestamp=timestamp,
        )

    except Exception as e:
        # Catch any exceptions and return structured error
        error_type = type(e).__name__

        # Don't expose sensitive error details in production
        if settings.service_environment == "prod":
            error_message = "Cleanup operation failed. Check service logs for details."
        else:
            # In dev/staging, provide more context for debugging
            error_message = f"Cleanup operation failed: {str(e)}"

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": error_type,
                "message": error_message,
                "timestamp": timestamp,
            },
        )
