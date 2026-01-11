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
Firestore client module with lazy initialization.

Provides a singleton Firestore client instance that is lazily initialized
on first use. Supports both production (Application Default Credentials)
and local development (Firestore emulator) configurations.
"""

import os
from typing import Optional
from google.cloud import firestore  # type: ignore[import-untyped]

from app.config import get_settings

# Module-level singleton client
_firestore_client: Optional[firestore.Client] = None


def get_firestore_client() -> firestore.Client:
    """
    Get or create a Firestore client instance.

    This function implements lazy initialization of the Firestore client,
    creating it only on first use and reusing the same instance for
    subsequent calls (singleton pattern per process).

    Configuration:
    - Uses GCP_PROJECT_ID from settings for production
    - Supports Firestore emulator via FIRESTORE_EMULATOR_HOST env var
    - Uses Application Default Credentials (ADC) in production

    Returns:
        firestore.Client: The initialized Firestore client

    Raises:
        ValueError: If GCP_PROJECT_ID is not set in non-dev environments

    Example:
        >>> client = get_firestore_client()
        >>> doc_ref = client.collection('test').document('doc1')
    """
    global _firestore_client

    if _firestore_client is None:
        settings = get_settings()

        # Check if using emulator
        emulator_host = settings.firestore_emulator_host
        if emulator_host:
            # Set environment variable for Firestore emulator
            os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
            # For emulator, project_id can be any non-empty string
            project_id = settings.gcp_project_id or "demo-project"
        else:
            # Production mode - project_id is required
            project_id = settings.gcp_project_id
            if not project_id:
                raise ValueError(
                    "GCP_PROJECT_ID must be set when not using Firestore emulator. "
                    "Set FIRESTORE_EMULATOR_HOST for local development."
                )

        # Initialize the Firestore client
        _firestore_client = firestore.Client(project=project_id)

    return _firestore_client


def reset_firestore_client() -> None:
    """
    Reset the Firestore client singleton.

    This function is primarily used for testing to ensure a fresh
    client instance is created with new settings.

    Warning:
        This should not be called in production code as it may cause
        connection issues with ongoing operations.
    """
    global _firestore_client
    _firestore_client = None
