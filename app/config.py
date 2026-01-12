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
Configuration module for the Journey Log API service.

Loads environment variables and provides validated settings.
"""

from functools import lru_cache
from typing import Literal
from pydantic import Field, field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via environment variables.
    See .env.example for all available options.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Service Configuration
    service_environment: Literal["dev", "staging", "prod"] = Field(
        default="dev", description="The environment the service is running in"
    )
    service_name: str = Field(
        default="journey-log", description="The name of this service"
    )

    # GCP Configuration
    gcp_project_id: str = Field(
        default="", description="GCP Project ID - REQUIRED in production"
    )

    # Firestore Configuration
    firestore_characters_collection: str = Field(
        default="characters", description="Firestore collection name for characters"
    )
    firestore_journeys_collection: str = Field(
        default="journeys", description="Firestore collection name for journeys"
    )
    firestore_entries_collection: str = Field(
        default="entries", description="Firestore collection name for entries"
    )
    firestore_test_collection: str = Field(
        default="connectivity_test",
        description="Firestore collection name for connectivity tests",
    )
    firestore_emulator_host: str = Field(
        default="",
        description="Firestore emulator host (e.g., localhost:8080) for local development",
    )

    # Build Metadata (Optional)
    build_version: str = Field(
        default="0.1.0", description="Version/tag of the current build"
    )
    build_commit: str = Field(
        default="", description="Git commit SHA of the current build"
    )
    build_timestamp: str = Field(
        default="", description="Build timestamp (ISO 8601 format)"
    )

    # API Configuration
    api_host: str = Field(default="127.0.0.1", description="Host to bind the server to")
    api_port: int = Field(default=8080, description="Port to bind the server to")

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    request_id_header: str = Field(
        default="X-Request-ID",
        description="Header name for request ID (for Cloud Run/Load Balancer compatibility)",
    )

    # Narrative Turns Configuration
    narrative_turns_default_query_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Default number of narrative turns to retrieve in queries (1-100)"
    )
    narrative_turns_max_query_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description=(
            "Maximum number of narrative turns that can be retrieved in a single query (1-1000). "
            "Higher limits may impact query performance and memory usage. "
            "The 1000 limit is set to balance query flexibility with performance considerations, "
            "as Firestore queries are most efficient with smaller result sets."
        )
    )
    narrative_turns_max_user_action_length: int = Field(
        default=8000,
        ge=1,
        description="Maximum length of user_action field in narrative turns (characters)"
    )
    narrative_turns_max_ai_response_length: int = Field(
        default=32000,
        ge=1,
        description="Maximum length of ai_response field in narrative turns (characters)"
    )

    @field_validator("gcp_project_id")
    @classmethod
    def validate_gcp_project_id(cls, v: str, info: ValidationInfo) -> str:
        """Validate GCP project ID is provided in non-dev environments."""
        environment = info.data.get("service_environment", "dev")
        if environment in ["staging", "prod"] and not v:
            raise ValueError(f"GCP_PROJECT_ID is required in {environment} environment")
        return v


# ==============================================================================
# Character Defaults and Constants
# ==============================================================================

# Default character status when creating new characters
DEFAULT_CHARACTER_STATUS = "Healthy"

# Default starting location for new characters
DEFAULT_LOCATION_ID = "origin:nexus"
DEFAULT_LOCATION_DISPLAY_NAME = "The Nexus"


@lru_cache
def get_settings() -> Settings:
    """
    Get the application settings.

    Returns a cached instance of Settings to avoid reloading from environment
    on every call.
    """
    return Settings()
