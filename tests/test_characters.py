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
Tests for character management endpoints.

Tests cover character creation, validation, uniqueness constraints,
and default value application.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import Mock, MagicMock, patch
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.models import CharacterDocument, Status as CharacterStatus
from app.dependencies import get_db


@pytest.fixture
def test_client():
    """Create a test client that bypasses Firestore for validation tests."""
    # Create a mock DB that won't be called for validation failures
    mock_db = Mock()
    
    def override_get_db():
        return mock_db
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_firestore_client():
    """Create a mock Firestore client."""
    mock_client = Mock()
    mock_collection = Mock()
    mock_query = Mock()
    mock_doc_ref = Mock()
    mock_transaction = Mock()
    
    # Configure transaction mock to work with @firestore.transactional decorator
    mock_transaction._max_attempts = 5
    mock_transaction._id = None
    
    # Setup the mock chain
    mock_client.collection.return_value = mock_collection
    mock_client.transaction.return_value = mock_transaction
    mock_collection.where.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.stream.return_value = []  # No existing characters by default
    mock_collection.document.return_value = mock_doc_ref
    
    return mock_client


@pytest.fixture
def test_client_with_mock_db(mock_firestore_client):
    """Create a test client with mocked Firestore dependency."""
    def override_get_db():
        return mock_firestore_client
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def valid_create_request():
    """Valid character creation request data."""
    return {
        "name": "Test Hero",
        "race": "Human",
        "class": "Warrior",
        "adventure_prompt": "I seek adventure in the forgotten realms"
    }


class TestCreateCharacter:
    """Tests for POST /characters endpoint."""
    
    def test_create_character_success(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_create_request,
    ):
        """Test successful character creation with all defaults."""
        
        # Mock Firestore operations for transaction
        mock_query = mock_firestore_client.collection.return_value.where.return_value
        mock_query.stream.return_value = []  # No existing character
        
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        
        # Mock document retrieval after creation
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {
            "character_id": "test-uuid",
            "owner_user_id": "user123",
            "adventure_prompt": valid_create_request["adventure_prompt"],
            "player_state": {
                "identity": {
                    "name": valid_create_request["name"],
                    "race": valid_create_request["race"],
                    "class": valid_create_request["class"],
                },
                "status": "Healthy",
                "level": 1,
                "experience": 0,
                "health": {"current": 100, "max": 100},
                "stats": {},
                "equipment": [],
                "inventory": [],
                "location": {
                    "id": "origin:nexus",
                    "display_name": "The Nexus",
                },
                "additional_fields": {},
            },
            "world_pois_reference": "characters/test-uuid/pois",
            "narrative_turns_reference": "characters/test-uuid/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request
        response = test_client_with_mock_db.post(
            "/characters",
            json=valid_create_request,
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "character" in data
        
        character = data["character"]
        assert character["owner_user_id"] == "user123"
        assert character["player_state"]["identity"]["name"] == valid_create_request["name"]
        assert character["player_state"]["identity"]["race"] == valid_create_request["race"]
        assert character["player_state"]["identity"]["class"] == valid_create_request["class"]
        assert character["player_state"]["status"] == "Healthy"
        assert character["player_state"]["level"] == 1
        assert character["player_state"]["experience"] == 0
        assert character["player_state"]["health"]["current"] == 100
        assert character["player_state"]["health"]["max"] == 100
        assert character["player_state"]["equipment"] == []
        assert character["player_state"]["inventory"] == []
        assert character["player_state"]["location"]["id"] == "origin:nexus"
        assert character["schema_version"] == "1.0.0"
    
    def test_create_character_missing_user_id(self, test_client, valid_create_request):
        """Test that missing X-User-Id header returns 422."""
        response = test_client.post(
            "/characters",
            json=valid_create_request,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        # FastAPI validation error for missing required header
    
    def test_create_character_empty_user_id(self, test_client_with_mock_db, valid_create_request):
        """Test that empty X-User-Id header returns 400."""
        response = test_client_with_mock_db.post(
            "/characters",
            json=valid_create_request,
            headers={"X-User-Id": "   "},
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "X-User-Id" in response_data["message"]
    
    def test_create_character_missing_name(self, test_client):
        """Test that missing name field returns 422."""
        request_data = {
            "race": "Human",
            "class": "Warrior",
            "adventure_prompt": "Test adventure"
        }
        
        response = test_client.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_missing_race(self, test_client):
        """Test that missing race field returns 422."""
        request_data = {
            "name": "Test Hero",
            "class": "Warrior",
            "adventure_prompt": "Test adventure"
        }
        
        response = test_client.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_missing_class(self, test_client):
        """Test that missing class field returns 422."""
        request_data = {
            "name": "Test Hero",
            "race": "Human",
            "adventure_prompt": "Test adventure"
        }
        
        response = test_client.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_missing_adventure_prompt(self, test_client):
        """Test that missing adventure_prompt field returns 422."""
        request_data = {
            "name": "Test Hero",
            "race": "Human",
            "class": "Warrior"
        }
        
        response = test_client.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_name_too_long(self, test_client):
        """Test that name exceeding 64 characters returns 422."""
        request_data = {
            "name": "A" * 65,
            "race": "Human",
            "class": "Warrior",
            "adventure_prompt": "Test adventure"
        }
        
        response = test_client.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_empty_adventure_prompt(self, test_client):
        """Test that empty adventure_prompt returns 422."""
        request_data = {
            "name": "Test Hero",
            "race": "Human",
            "class": "Warrior",
            "adventure_prompt": ""
        }
        
        response = test_client.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_duplicate_returns_409(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_create_request,
    ):
        """Test that duplicate (user_id, name, race, class) returns 409."""
        
        # Mock existing character in transaction
        existing_doc = Mock()
        existing_doc.exists = True
        mock_query = mock_firestore_client.collection.return_value.where.return_value
        mock_query.stream.return_value = [existing_doc]  # Character exists
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=valid_create_request,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_409_CONFLICT
        response_data = response.json()
        assert "error" in response_data
        assert "already exists" in response_data["message"]
    
    def test_create_character_with_location_override(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_create_request,
    ):
        """Test character creation with custom location override."""
        
        # Mock Firestore operations for transaction
        mock_query = mock_firestore_client.collection.return_value.where.return_value
        mock_query.stream.return_value = []  # No existing character
        
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        
        # Mock document retrieval with custom location
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {
            "character_id": "test-uuid",
            "owner_user_id": "user123",
            "adventure_prompt": valid_create_request["adventure_prompt"],
            "player_state": {
                "identity": {
                    "name": valid_create_request["name"],
                    "race": valid_create_request["race"],
                    "class": valid_create_request["class"],
                },
                "status": "Healthy",
                "level": 1,
                "experience": 0,
                "health": {"current": 100, "max": 100},
                "stats": {},
                "equipment": [],
                "inventory": [],
                "location": {
                    "id": "town:rivendell",
                    "display_name": "Rivendell",
                },
                "additional_fields": {},
            },
            "world_pois_reference": "characters/test-uuid/pois",
            "narrative_turns_reference": "characters/test-uuid/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Add location override to request
        request_with_location = {
            **valid_create_request,
            "location_id": "town:rivendell",
            "location_display_name": "Rivendell",
        }
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=request_with_location,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["character"]["player_state"]["location"]["id"] == "town:rivendell"
        assert data["character"]["player_state"]["location"]["display_name"] == "Rivendell"
    
    def test_create_character_location_id_without_display_name(
        self, test_client_with_mock_db, valid_create_request
    ):
        """Test that location_id without display_name returns 422."""
        request_data = {
            **valid_create_request,
            "location_id": "town:rivendell",
        }
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_location_display_name_without_id(
        self, test_client_with_mock_db, valid_create_request
    ):
        """Test that location_display_name without id returns 422."""
        request_data = {
            **valid_create_request,
            "location_display_name": "Rivendell",
        }
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_create_character_firestore_error_returns_500(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_create_request,
    ):
        """Test that Firestore errors return 500."""
        
        # Mock Firestore error
        mock_firestore_client.collection.side_effect = Exception("Firestore connection error")
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=valid_create_request,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        response_data = response.json()
        assert "error" in response_data
        assert "Failed to create character" in response_data["message"]
    
    def test_create_character_extra_fields_rejected(self, test_client_with_mock_db, valid_create_request):
        """Test that extra fields in request are rejected."""
        request_data = {
            **valid_create_request,
            "extra_field": "should be rejected",
        }
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestCharacterDefaultValues:
    """Tests to verify default values are correctly applied."""
    
    def test_default_status_is_healthy(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_create_request,
    ):
        """Test that default status is Healthy."""
        
        # Setup mocks for transaction
        mock_query = mock_firestore_client.collection.return_value.where.return_value
        mock_query.stream.return_value = []
        
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        
        # Mock return document
        mock_doc_snapshot.to_dict.return_value = {
            "character_id": "test-uuid",
            "owner_user_id": "user123",
            "adventure_prompt": valid_create_request["adventure_prompt"],
            "player_state": {
                "identity": {
                    "name": valid_create_request["name"],
                    "race": valid_create_request["race"],
                    "class": valid_create_request["class"],
                },
                "status": "Healthy",
                "level": 1,
                "experience": 0,
                "health": {"current": 100, "max": 100},
                "stats": {},
                "equipment": [],
                "inventory": [],
                "location": {"id": "origin:nexus", "display_name": "The Nexus"},
                "additional_fields": {},
            },
            "world_pois_reference": "characters/test-uuid/pois",
            "narrative_turns_reference": "characters/test-uuid/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=valid_create_request,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        character = response.json()["character"]
        assert character["player_state"]["status"] == "Healthy"
    
    def test_default_location_is_origin_nexus(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_create_request,
    ):
        """Test that default location is origin:nexus/The Nexus."""
        
        # Setup mocks for transaction
        mock_query = mock_firestore_client.collection.return_value.where.return_value
        mock_query.stream.return_value = []
        
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {
            "character_id": "test-uuid",
            "owner_user_id": "user123",
            "adventure_prompt": valid_create_request["adventure_prompt"],
            "player_state": {
                "identity": {
                    "name": valid_create_request["name"],
                    "race": valid_create_request["race"],
                    "class": valid_create_request["class"],
                },
                "status": "Healthy",
                "level": 1,
                "experience": 0,
                "health": {"current": 100, "max": 100},
                "stats": {},
                "equipment": [],
                "inventory": [],
                "location": {"id": "origin:nexus", "display_name": "The Nexus"},
                "additional_fields": {},
            },
            "world_pois_reference": "characters/test-uuid/pois",
            "narrative_turns_reference": "characters/test-uuid/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        response = test_client_with_mock_db.post(
            "/characters",
            json=valid_create_request,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        character = response.json()["character"]
        assert character["player_state"]["location"]["id"] == "origin:nexus"
        assert character["player_state"]["location"]["display_name"] == "The Nexus"
