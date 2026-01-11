"""
Configuration module for the Journey Log API service.

Loads environment variables and provides validated settings.
"""

from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables.
    See .env.example for all available options.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Service Configuration
    service_environment: Literal["dev", "staging", "prod"] = Field(
        default="dev",
        description="The environment the service is running in"
    )
    service_name: str = Field(
        default="journey-log",
        description="The name of this service"
    )
    
    # GCP Configuration
    gcp_project_id: str = Field(
        default="",
        description="GCP Project ID - REQUIRED in production"
    )
    
    # Firestore Configuration
    firestore_journeys_collection: str = Field(
        default="journeys",
        description="Firestore collection name for journeys"
    )
    firestore_entries_collection: str = Field(
        default="entries",
        description="Firestore collection name for entries"
    )
    
    # Build Metadata (Optional)
    build_version: str = Field(
        default="0.1.0",
        description="Version/tag of the current build"
    )
    build_commit: str = Field(
        default="",
        description="Git commit SHA of the current build"
    )
    build_timestamp: str = Field(
        default="",
        description="Build timestamp (ISO 8601 format)"
    )
    
    # API Configuration
    api_host: str = Field(
        default="127.0.0.1",
        description="Host to bind the server to"
    )
    api_port: int = Field(
        default=8080,
        description="Port to bind the server to"
    )
    
    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    
    @field_validator("service_environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate that environment is one of the allowed values."""
        allowed = ["dev", "staging", "prod"]
        if v not in allowed:
            raise ValueError(
                f"Invalid environment '{v}'. Must be one of: {', '.join(allowed)}"
            )
        return v
    
    @field_validator("gcp_project_id")
    @classmethod
    def validate_gcp_project_id(cls, v: str, info) -> str:
        """Validate GCP project ID is provided in non-dev environments."""
        environment = info.data.get("service_environment", "dev")
        if environment in ["staging", "prod"] and not v:
            raise ValueError(
                f"GCP_PROJECT_ID is required in {environment} environment"
            )
        return v


def get_settings() -> Settings:
    """
    Get the application settings.
    
    Returns a cached instance of Settings to avoid reloading from environment
    on every call.
    """
    return Settings()
