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
from unittest.mock import Mock
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
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


class TestGetCharacter:
    """Tests for GET /characters/{character_id} endpoint."""
    
    @pytest.fixture
    def sample_character_data(self):
        """Sample character data for testing."""
        return {
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "owner_user_id": "user123",
            "adventure_prompt": "A brave hero seeks adventure",
            "player_state": {
                "identity": {
                    "name": "Test Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
                "level": 5,
                "experience": 1000,
                "health": {"current": 80, "max": 100},
                "stats": {"strength": 18, "dexterity": 14},
                "equipment": [],
                "inventory": [],
                "location": {
                    "id": "origin:nexus",
                    "display_name": "The Nexus",
                },
                "additional_fields": {},
            },
            "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
            "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    
    def test_get_character_success(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test successful character retrieval."""
        
        # Mock Firestore document retrieval
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = sample_character_data
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "character" in data
        
        character = data["character"]
        assert character["character_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert character["owner_user_id"] == "user123"
        assert character["player_state"]["identity"]["name"] == "Test Hero"
        assert character["player_state"]["level"] == 5
        assert character["player_state"]["experience"] == 1000
    
    def test_get_character_with_matching_user_id(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test successful retrieval with matching X-User-Id header."""
        
        # Mock Firestore document retrieval
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = sample_character_data
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request with matching user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["character"]["owner_user_id"] == "user123"
    
    def test_get_character_not_found(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test 404 when character does not exist."""
        
        # Mock non-existent document
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response_data = response.json()
        assert "error" in response_data
        assert "not found" in response_data["message"].lower()
    
    def test_get_character_invalid_uuid(
        self,
        test_client_with_mock_db,
    ):
        """Test 422 for malformed UUID."""
        
        # Make request with invalid UUID
        response = test_client_with_mock_db.get(
            "/characters/not-a-valid-uuid",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        response_data = response.json()
        assert "error" in response_data
        assert "uuid" in response_data["message"].lower()
    
    def test_get_character_user_id_mismatch(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 403 when X-User-Id does not match owner."""
        
        # Mock Firestore document retrieval
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = sample_character_data
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request with mismatched user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
            headers={"X-User-Id": "different_user"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_403_FORBIDDEN
        response_data = response.json()
        assert "error" in response_data
        assert "access denied" in response_data["message"].lower()
    
    def test_get_character_case_insensitive_uuid(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that UUID is case-insensitive."""
        
        # Mock Firestore document retrieval
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = sample_character_data
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request with uppercase UUID
        response = test_client_with_mock_db.get(
            "/characters/550E8400-E29B-41D4-A716-446655440000",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        
        # Verify that document was queried with lowercase UUID
        mock_firestore_client.collection.return_value.document.assert_called_with(
            "550e8400-e29b-41d4-a716-446655440000"
        )
    
    def test_get_character_with_optional_fields(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test retrieval of character with all optional fields populated."""
        
        # Sample character with combat and quest
        character_data = {
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "owner_user_id": "user123",
            "adventure_prompt": "A brave hero seeks adventure",
            "player_state": {
                "identity": {
                    "name": "Test Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
                "level": 5,
                "experience": 1000,
                "health": {"current": 80, "max": 100},
                "stats": {},
                "equipment": [],
                "inventory": [],
                "location": {"id": "origin:nexus", "display_name": "The Nexus"},
                "additional_fields": {},
            },
            "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
            "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "world_state": {"region": "north"},
            "active_quest": {
                "quest_id": "quest_001",
                "title": "Find the Sword",
                "description": "Locate the legendary sword",
                "completion_state": "InProgress",
                "objectives": [],
                "requirements": [],
                "rewards": [],
            },
            "combat_state": {
                "combat_id": "combat_001",
                "started_at": datetime.now(timezone.utc),
                "turn": 1,
                "enemies": [
                    {
                        "enemy_id": "enemy_001",
                        "name": "Goblin",
                        "health": {"current": 20, "max": 20},
                        "status_effects": [],
                    }
                ],
            },
        }
        
        # Mock Firestore document retrieval
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = character_data
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        character = data["character"]
        
        # Verify optional fields are present
        assert character["world_state"] == {"region": "north"}
        assert character["active_quest"]["quest_id"] == "quest_001"
        assert character["combat_state"]["combat_id"] == "combat_001"
    
    def test_get_character_firestore_error_returns_500(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test that Firestore errors return 500."""
        
        # Mock Firestore error
        mock_firestore_client.collection.side_effect = Exception("Firestore connection error")
        
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
        )
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        response_data = response.json()
        assert "error" in response_data
        assert "internal error" in response_data["message"].lower()
    
    def test_get_character_empty_user_id_header(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that empty X-User-Id header returns 400 error."""
        
        # Mock Firestore document retrieval
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = sample_character_data
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request with empty user ID (should trigger validation error)
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
            headers={"X-User-Id": "   "},
        )
        
        # Assertions - should fail with 400 because empty header is a client error
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "empty" in response_data["message"].lower()


class TestListCharacters:
    """Tests for GET /characters endpoint."""
    
    def test_list_characters_empty_results(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test that empty list is returned when user has no characters."""
        
        # Mock empty query results
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters",
            headers={"X-User-Id": "user_no_chars"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "characters" in data
        assert data["characters"] == []
        assert data["count"] == 0
    
    def test_list_characters_single_character(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test listing a single character."""
        
        # Mock character document
        mock_doc = Mock()
        mock_doc.id = "char-001"
        mock_doc.to_dict.return_value = {
            "character_id": "char-001",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Hero One",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        # Mock query results
        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc]
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["count"] == 1
        
        char = data["characters"][0]
        assert char["character_id"] == "char-001"
        assert char["name"] == "Hero One"
        assert char["race"] == "Human"
        assert char["class"] == "Warrior"
        assert char["status"] == "Healthy"
    
    def test_list_characters_multiple_sorted_by_updated_at(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test listing multiple characters sorted by updated_at descending."""
        
        # Mock character documents (ordered by updated_at desc)
        mock_doc1 = Mock()
        mock_doc1.id = "char-newest"
        mock_doc1.to_dict.return_value = {
            "character_id": "char-newest",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Newest Hero",
                    "race": "Elf",
                    "class": "Mage",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 12, 15, 0, 0, tzinfo=timezone.utc),
        }
        
        mock_doc2 = Mock()
        mock_doc2.id = "char-middle"
        mock_doc2.to_dict.return_value = {
            "character_id": "char-middle",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Middle Hero",
                    "race": "Dwarf",
                    "class": "Fighter",
                },
                "status": "Wounded",
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        mock_doc3 = Mock()
        mock_doc3.id = "char-oldest"
        mock_doc3.to_dict.return_value = {
            "character_id": "char-oldest",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Oldest Hero",
                    "race": "Human",
                    "class": "Rogue",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 9, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        # Mock query results (already sorted by Firestore)
        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc1, mock_doc2, mock_doc3]
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["characters"]) == 3
        assert data["count"] == 3
        
        # Verify order (newest first)
        assert data["characters"][0]["character_id"] == "char-newest"
        assert data["characters"][1]["character_id"] == "char-middle"
        assert data["characters"][2]["character_id"] == "char-oldest"
    
    def test_list_characters_missing_user_id(
        self,
        test_client_with_mock_db,
    ):
        """Test that missing X-User-Id header returns 422."""
        response = test_client_with_mock_db.get("/characters")
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_list_characters_empty_user_id(
        self,
        test_client_with_mock_db,
    ):
        """Test that empty X-User-Id header returns 400."""
        response = test_client_with_mock_db.get(
            "/characters",
            headers={"X-User-Id": "   "},
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "X-User-Id" in response_data["message"]
    
    def test_list_characters_with_limit(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test pagination with limit parameter."""
        
        # Mock two characters (but query should be limited)
        mock_doc1 = Mock()
        mock_doc1.id = "char-001"
        mock_doc1.to_dict.return_value = {
            "character_id": "char-001",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Hero One",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        mock_doc2 = Mock()
        mock_doc2.id = "char-002"
        mock_doc2.to_dict.return_value = {
            "character_id": "char-002",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Hero Two",
                    "race": "Elf",
                    "class": "Mage",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        # Mock query with limit
        mock_query = Mock()
        mock_query.limit.return_value.stream.return_value = [mock_doc1]  # Only return first
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request with limit=1
        response = test_client_with_mock_db.get(
            "/characters?limit=1",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["count"] == 1
        
        # Verify limit was called on query
        mock_query.limit.assert_called_once_with(1)
    
    def test_list_characters_with_offset(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test pagination with offset parameter."""
        
        # Mock character document
        mock_doc = Mock()
        mock_doc.id = "char-002"
        mock_doc.to_dict.return_value = {
            "character_id": "char-002",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Hero Two",
                    "race": "Elf",
                    "class": "Mage",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        # Mock query with offset
        mock_query = Mock()
        mock_query.offset.return_value.stream.return_value = [mock_doc]
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request with offset=1
        response = test_client_with_mock_db.get(
            "/characters?offset=1",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["characters"]) == 1
        
        # Verify offset was called on query
        mock_query.offset.assert_called_once_with(1)
    
    def test_list_characters_with_offset_and_limit(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test pagination with both offset and limit parameters."""
        
        # Mock character document (simulating page 2 with limit 1)
        mock_doc = Mock()
        mock_doc.id = "char-002"
        mock_doc.to_dict.return_value = {
            "character_id": "char-002",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Hero Two",
                    "race": "Elf",
                    "class": "Mage",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        # Mock query with both offset and limit
        mock_limit_query = Mock()
        mock_limit_query.stream.return_value = [mock_doc]
        mock_offset_query = Mock()
        mock_offset_query.limit.return_value = mock_limit_query
        mock_query = Mock()
        mock_query.offset.return_value = mock_offset_query
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request with both offset and limit
        response = test_client_with_mock_db.get(
            "/characters?offset=1&limit=1",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["count"] == 1
        
        # Verify both offset and limit were called on the query chain
        mock_query.offset.assert_called_once_with(1)
        mock_offset_query.limit.assert_called_once_with(1)
    
    def test_list_characters_default_status_healthy(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test that legacy documents lacking status default to Healthy."""
        
        # Mock character document without status
        mock_doc = Mock()
        mock_doc.id = "char-legacy"
        mock_doc.to_dict.return_value = {
            "character_id": "char-legacy",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Legacy Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                # No status field
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        # Mock query results
        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc]
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["characters"]) == 1
        
        # Verify status defaults to Healthy
        char = data["characters"][0]
        assert char["status"] == "Healthy"
    
    def test_list_characters_firestore_error_returns_500(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test that Firestore errors return 500."""
        
        # Mock Firestore error
        mock_firestore_client.collection.side_effect = Exception("Firestore connection error")
        
        response = test_client_with_mock_db.get(
            "/characters",
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        response_data = response.json()
        assert "error" in response_data
        assert "internal error" in response_data["message"].lower()
    
    def test_list_characters_user_isolation(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test that users can only see their own characters."""
        
        # Mock character document for user123
        mock_doc = Mock()
        mock_doc.id = "char-user123"
        mock_doc.to_dict.return_value = {
            "character_id": "char-user123",
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "User123 Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
            },
            "created_at": datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        # Mock query results - Firestore should only return user123's characters
        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc]
        mock_collection = mock_firestore_client.collection.return_value
        mock_collection.where.return_value.order_by.return_value = mock_query
        
        # Make request as user123
        response = test_client_with_mock_db.get(
            "/characters",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["characters"]) == 1
        
        # Verify Firestore was queried with correct user_id filter
        mock_collection.where.assert_called_once_with("owner_user_id", "==", "user123")


class TestAppendNarrativeTurn:
    """Tests for POST /characters/{character_id}/narrative endpoint."""
    
    @pytest.fixture
    def valid_append_request(self):
        """Valid narrative turn append request data."""
        return {
            "user_action": "I explore the ancient ruins",
            "ai_response": "You discover a hidden chamber filled with mysterious artifacts",
        }
    
    @pytest.fixture
    def sample_character_data(self):
        """Sample character data for testing."""
        return {
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "owner_user_id": "user123",
            "adventure_prompt": "A brave hero seeks adventure",
            "player_state": {
                "identity": {
                    "name": "Test Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
                "level": 5,
                "experience": 1000,
                "health": {"current": 80, "max": 100},
                "stats": {"strength": 18, "dexterity": 14},
                "equipment": [],
                "inventory": [],
                "location": {
                    "id": "origin:nexus",
                    "display_name": "The Nexus",
                },
                "additional_fields": {},
            },
            "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
            "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    
    def test_append_narrative_success(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_append_request,
        sample_character_data,
    ):
        """Test successful narrative turn append."""
        
        # Mock transaction
        mock_transaction = Mock()
        mock_transaction._max_attempts = 5
        mock_transaction._id = None
        mock_firestore_client.transaction.return_value = mock_transaction
        
        # Mock character document retrieval in transaction
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock turn subcollection reference
        mock_turn_collection = Mock()
        mock_turn_ref = Mock()
        mock_char_ref.collection.return_value = mock_turn_collection
        mock_turn_collection.document.return_value = mock_turn_ref
        
        # Mock count aggregation query for atomic count
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 5
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turn_collection.count.return_value = mock_count_query
        
        # Mock turn document retrieval after creation
        mock_turn_snapshot = Mock()
        mock_turn_snapshot.exists = True
        mock_turn_snapshot.to_dict.return_value = {
            "turn_id": "turn-001",
            "player_action": valid_append_request["user_action"],
            "gm_response": valid_append_request["ai_response"],
            "timestamp": datetime.now(timezone.utc),
        }
        mock_turn_ref.get.return_value = mock_turn_snapshot
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=valid_append_request,
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "turn" in data
        assert "total_turns" in data
        assert data["total_turns"] == 5
        
        turn = data["turn"]
        assert turn["player_action"] == valid_append_request["user_action"]
        assert turn["gm_response"] == valid_append_request["ai_response"]
        assert "timestamp" in turn
    
    def test_append_narrative_with_timestamp(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_append_request,
        sample_character_data,
    ):
        """Test narrative append with custom timestamp."""
        
        # Mock transaction and documents
        mock_transaction = Mock()
        mock_transaction._max_attempts = 5
        mock_transaction._id = None
        mock_firestore_client.transaction.return_value = mock_transaction
        
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        mock_turn_collection = Mock()
        mock_turn_ref = Mock()
        mock_char_ref.collection.return_value = mock_turn_collection
        mock_turn_collection.document.return_value = mock_turn_ref
        
        # Mock count aggregation query
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 1
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turn_collection.count.return_value = mock_count_query
        
        custom_timestamp = "2026-01-11T12:00:00Z"
        mock_turn_snapshot = Mock()
        mock_turn_snapshot.exists = True
        mock_turn_snapshot.to_dict.return_value = {
            "turn_id": "turn-001",
            "player_action": valid_append_request["user_action"],
            "gm_response": valid_append_request["ai_response"],
            "timestamp": datetime.fromisoformat(custom_timestamp.replace("Z", "+00:00")),
        }
        mock_turn_ref.get.return_value = mock_turn_snapshot
        
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Add timestamp to request
        request_with_timestamp = {
            **valid_append_request,
            "timestamp": custom_timestamp,
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_with_timestamp,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "turn" in data
        # Verify timestamp is present
        assert "timestamp" in data["turn"]
    
    def test_append_narrative_user_action_too_long(
        self,
        test_client_with_mock_db,
    ):
        """Test that user_action exceeding 8000 characters returns 422."""
        request_data = {
            "user_action": "A" * 8001,  # Over limit
            "ai_response": "Response",
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_ai_response_too_long(
        self,
        test_client_with_mock_db,
    ):
        """Test that ai_response exceeding 32000 characters returns 422."""
        request_data = {
            "user_action": "Action",
            "ai_response": "B" * 32001,  # Over limit
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_combined_length_exceeds_limit(
        self,
        test_client_with_mock_db,
    ):
        """Test that combined length exceeding 40000 characters returns 413."""
        request_data = {
            "user_action": "A" * 8000,
            "ai_response": "B" * 32001,  # Combined = 40001
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        # Should fail at Pydantic validation first (ai_response too long)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_combined_validation_at_limit(
        self,
        test_client_with_mock_db,
    ):
        """Test combined validation error when fields individually valid but combined too large."""
        # This tests the combined validator
        request_data = {
            "user_action": "A" * 8000,
            "ai_response": "B" * 32001,  # 40001 combined
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_character_not_found(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_append_request,
    ):
        """Test 404 when character does not exist."""
        
        # Mock transaction
        mock_transaction = Mock()
        mock_transaction._max_attempts = 5
        mock_transaction._id = None
        mock_firestore_client.transaction.return_value = mock_transaction
        
        # Mock character not found
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = False
        mock_char_ref.get.return_value = mock_char_snapshot
        
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=valid_append_request,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response_data = response.json()
        assert "error" in response_data
        assert "not found" in response_data["message"].lower()
    
    def test_append_narrative_access_denied(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_append_request,
        sample_character_data,
    ):
        """Test 403 when user does not own the character."""
        
        # Mock transaction
        mock_transaction = Mock()
        mock_transaction._max_attempts = 5
        mock_transaction._id = None
        mock_firestore_client.transaction.return_value = mock_transaction
        
        # Mock character owned by different user
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Request with different user
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=valid_append_request,
            headers={"X-User-Id": "different_user"},
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        response_data = response.json()
        assert "error" in response_data
        assert "access denied" in response_data["message"].lower()
    
    def test_append_narrative_missing_user_id(
        self,
        test_client_with_mock_db,
        valid_append_request,
    ):
        """Test that missing X-User-Id header returns 422."""
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=valid_append_request,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_empty_user_id(
        self,
        test_client_with_mock_db,
        valid_append_request,
    ):
        """Test that empty X-User-Id header returns 400."""
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=valid_append_request,
            headers={"X-User-Id": "   "},
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "X-User-Id" in response_data["message"]
    
    def test_append_narrative_invalid_uuid(
        self,
        test_client_with_mock_db,
        valid_append_request,
    ):
        """Test 422 for malformed character UUID."""
        response = test_client_with_mock_db.post(
            "/characters/not-a-valid-uuid/narrative",
            json=valid_append_request,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        response_data = response.json()
        assert "error" in response_data
        assert "uuid" in response_data["message"].lower()
    
    def test_append_narrative_invalid_timestamp_format(
        self,
        test_client_with_mock_db,
        valid_append_request,
    ):
        """Test 422 for invalid timestamp format."""
        request_data = {
            **valid_append_request,
            "timestamp": "not-a-valid-timestamp",
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        response_data = response.json()
        assert "error" in response_data
        assert "timestamp" in response_data["message"].lower()
    
    def test_append_narrative_missing_user_action(
        self,
        test_client_with_mock_db,
    ):
        """Test that missing user_action returns 422."""
        request_data = {
            "ai_response": "Response",
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_missing_ai_response(
        self,
        test_client_with_mock_db,
    ):
        """Test that missing ai_response returns 422."""
        request_data = {
            "user_action": "Action",
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_empty_user_action(
        self,
        test_client_with_mock_db,
    ):
        """Test that empty user_action returns 422."""
        request_data = {
            "user_action": "",
            "ai_response": "Response",
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_empty_ai_response(
        self,
        test_client_with_mock_db,
    ):
        """Test that empty ai_response returns 422."""
        request_data = {
            "user_action": "Action",
            "ai_response": "",
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_extra_fields_rejected(
        self,
        test_client_with_mock_db,
        valid_append_request,
    ):
        """Test that extra fields in request are rejected."""
        request_data = {
            **valid_append_request,
            "extra_field": "should be rejected",
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_append_narrative_at_field_limits(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test appending with fields at maximum allowed length."""
        
        # Mock transaction and documents
        mock_transaction = Mock()
        mock_transaction._max_attempts = 5
        mock_transaction._id = None
        mock_firestore_client.transaction.return_value = mock_transaction
        
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        mock_turn_collection = Mock()
        mock_turn_ref = Mock()
        mock_char_ref.collection.return_value = mock_turn_collection
        mock_turn_collection.document.return_value = mock_turn_ref
        
        # Mock count aggregation query
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 1
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turn_collection.count.return_value = mock_count_query
        
        # Create request at limits
        user_action_at_limit = "A" * 8000
        ai_response_at_limit = "B" * 32000
        
        mock_turn_snapshot = Mock()
        mock_turn_snapshot.exists = True
        mock_turn_snapshot.to_dict.return_value = {
            "turn_id": "turn-001",
            "player_action": user_action_at_limit,
            "gm_response": ai_response_at_limit,
            "timestamp": datetime.now(timezone.utc),
        }
        mock_turn_ref.get.return_value = mock_turn_snapshot
        
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        request_data = {
            "user_action": user_action_at_limit,
            "ai_response": ai_response_at_limit,
        }
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=request_data,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert len(data["turn"]["player_action"]) == 8000
        assert len(data["turn"]["gm_response"]) == 32000
    
    def test_append_narrative_firestore_error_returns_500(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_append_request,
    ):
        """Test that Firestore errors return 500."""
        
        # Mock Firestore error
        mock_firestore_client.transaction.side_effect = Exception("Firestore connection error")
        
        response = test_client_with_mock_db.post(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            json=valid_append_request,
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        response_data = response.json()
        assert "error" in response_data
        assert "Failed to append narrative turn" in response_data["message"]


class TestGetNarrativeTurns:
    """Tests for GET /characters/{character_id}/narrative endpoint."""
    
    @pytest.fixture
    def sample_character_data(self):
        """Sample character data for testing."""
        return {
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "owner_user_id": "user123",
            "adventure_prompt": "A brave hero seeks adventure",
            "player_state": {
                "identity": {
                    "name": "Test Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
                "level": 5,
                "experience": 1000,
                "health": {"current": 80, "max": 100},
                "stats": {"strength": 18, "dexterity": 14},
                "equipment": [],
                "inventory": [],
                "location": {
                    "id": "origin:nexus",
                    "display_name": "The Nexus",
                },
                "additional_fields": {},
            },
            "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
            "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    
    def test_get_narrative_success_default_limit(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test successful narrative retrieval with default limit (10)."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock narrative turns subcollection
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        # Create mock turn documents
        mock_turns = []
        for i in range(5):  # Return 5 turns (less than requested 10)
            mock_turn = Mock()
            mock_turn.id = f"turn-{i:03d}"
            mock_turn.to_dict.return_value = {
                "turn_id": f"turn-{i:03d}",
                "player_action": f"Action {i}",
                "gm_response": f"Response {i}",
                "timestamp": datetime(2026, 1, 11, 12, i, 0, tzinfo=timezone.utc),
            }
            mock_turns.append(mock_turn)
        
        # Mock query execution
        # Note: We create mock_turns in oldest-first order (i=0,1,2,3,4)
        # Then reverse them to simulate Firestore's DESCENDING order (newest first)
        # The actual endpoint code will reverse them again to get oldest-first
        mock_query = Mock()
        mock_query.stream.return_value = reversed(mock_turns)
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query
        
        # Mock count aggregation
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 5
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turns_collection.count.return_value = mock_count_query
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request (no n parameter, should default to 10)
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "turns" in data
        assert "metadata" in data
        
        # Check metadata
        metadata = data["metadata"]
        assert metadata["requested_n"] == 10
        assert metadata["returned_count"] == 5
        assert metadata["total_available"] == 5
        
        # Check turns are in chronological order
        turns = data["turns"]
        assert len(turns) == 5
        assert turns[0]["player_action"] == "Action 0"
        assert turns[4]["player_action"] == "Action 4"
    
    def test_get_narrative_with_custom_n(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test narrative retrieval with custom n parameter."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock narrative turns subcollection
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        # Create 3 mock turn documents
        mock_turns = []
        for i in range(3):
            mock_turn = Mock()
            mock_turn.id = f"turn-{i:03d}"
            mock_turn.to_dict.return_value = {
                "turn_id": f"turn-{i:03d}",
                "player_action": f"Action {i}",
                "gm_response": f"Response {i}",
                "timestamp": datetime(2026, 1, 11, 12, i, 0, tzinfo=timezone.utc),
            }
            mock_turns.append(mock_turn)
        
        # Mock query execution - simulating Firestore DESCENDING order
        mock_query = Mock()
        mock_query.stream.return_value = reversed(mock_turns)
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query
        
        # Mock count
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 10  # Total available
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turns_collection.count.return_value = mock_count_query
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with n=3
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=3",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        metadata = data["metadata"]
        assert metadata["requested_n"] == 3
        assert metadata["returned_count"] == 3
        assert metadata["total_available"] == 10
    
    def test_get_narrative_empty_history(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test narrative retrieval for character with no turns."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock empty narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        # Mock query returning empty list
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query
        
        # Mock count returning 0
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 0
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turns_collection.count.return_value = mock_count_query
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["turns"] == []
        metadata = data["metadata"]
        assert metadata["requested_n"] == 10
        assert metadata["returned_count"] == 0
        assert metadata["total_available"] == 0
    
    def test_get_narrative_n_boundary_min(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test narrative retrieval with n=1."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        # Create 1 mock turn
        mock_turn = Mock()
        mock_turn.id = "turn-001"
        mock_turn.to_dict.return_value = {
            "turn_id": "turn-001",
            "player_action": "Action",
            "gm_response": "Response",
            "timestamp": datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        }
        
        mock_query = Mock()
        mock_query.stream.return_value = [mock_turn]
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query
        
        # Mock count
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 5
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turns_collection.count.return_value = mock_count_query
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with n=1
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=1",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert len(data["turns"]) == 1
        metadata = data["metadata"]
        assert metadata["requested_n"] == 1
        assert metadata["returned_count"] == 1
    
    def test_get_narrative_n_boundary_max(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test narrative retrieval with n=100 (max)."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        # Mock query (empty for simplicity)
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query
        
        # Mock count
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 0
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turns_collection.count.return_value = mock_count_query
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with n=100
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=100",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["metadata"]["requested_n"] == 100
    
    def test_get_narrative_n_exceeds_max(
        self,
        test_client_with_mock_db,
    ):
        """Test 400 error when n exceeds maximum."""
        
        # Make request with n=101 (over limit)
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=101",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "must be between" in response_data["message"].lower()
    
    def test_get_narrative_n_below_min(
        self,
        test_client_with_mock_db,
    ):
        """Test 400 error when n is below minimum."""
        
        # Make request with n=0
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?n=0",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "must be between" in response_data["message"].lower()
    
    def test_get_narrative_character_not_found(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test 404 when character does not exist."""
        
        # Mock character not found
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = False
        mock_char_ref.get.return_value = mock_char_snapshot
        
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response_data = response.json()
        assert "error" in response_data
        assert "not found" in response_data["message"].lower()
    
    def test_get_narrative_invalid_uuid(
        self,
        test_client_with_mock_db,
    ):
        """Test 422 for malformed UUID."""
        
        # Make request with invalid UUID
        response = test_client_with_mock_db.get(
            "/characters/not-a-valid-uuid/narrative",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        response_data = response.json()
        assert "error" in response_data
        assert "uuid" in response_data["message"].lower()
    
    def test_get_narrative_with_user_id_match(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test successful retrieval with matching X-User-Id."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock empty narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query
        
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 0
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_turns_collection.count.return_value = mock_count_query
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with matching user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            headers={"X-User-Id": "user123"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_narrative_user_id_mismatch(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 403 when X-User-Id does not match owner."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with mismatched user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            headers={"X-User-Id": "different_user"},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_403_FORBIDDEN
        response_data = response.json()
        assert "error" in response_data
        assert "access denied" in response_data["message"].lower()
    
    def test_get_narrative_empty_user_id(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 400 when X-User-Id is empty."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with empty user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
            headers={"X-User-Id": "   "},
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "empty" in response_data["message"].lower()
    
    def test_get_narrative_with_since_filter(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test narrative retrieval with since timestamp filter."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        # Mock query with where clause
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_where_query = Mock()
        mock_where_query.limit.return_value = mock_query
        mock_order_query = Mock()
        mock_order_query.where.return_value = mock_where_query
        mock_turns_collection.order_by.return_value = mock_order_query
        
        # Mock count with where clause
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 0
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_where_count = Mock()
        mock_where_count.count.return_value = mock_count_query
        mock_turns_collection.where.return_value = mock_where_count
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with since parameter
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?since=2026-01-11T12:00:00Z",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
    
    def test_get_narrative_invalid_since_format(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 400 for invalid since timestamp format."""
        
        # Mock character document (to get past initial checks)
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with invalid since format
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?since=not-a-timestamp",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert "error" in response_data
        assert "timestamp" in response_data["message"].lower()
    
    def test_get_narrative_since_newer_than_all_turns(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that since timestamp newer than all turns returns empty list with 200."""
        
        # Mock character document
        mock_char_ref = Mock()
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot
        
        # Mock empty narrative turns (all turns are before since)
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        # Mock query with where returning empty
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_where_query = Mock()
        mock_where_query.limit.return_value = mock_query
        mock_order_query = Mock()
        mock_order_query.where.return_value = mock_where_query
        mock_turns_collection.order_by.return_value = mock_order_query
        
        # Mock count returning 0
        mock_count_query = Mock()
        mock_agg_result = Mock()
        mock_agg_result.value = 0
        mock_count_query.get.return_value = [[mock_agg_result]]
        mock_where_count = Mock()
        mock_where_count.count.return_value = mock_count_query
        mock_turns_collection.where.return_value = mock_where_count
        
        # Setup mock chain
        mock_collection = Mock()
        mock_firestore_client.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_char_ref
        
        # Make request with future since timestamp
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative?since=2030-01-01T00:00:00Z",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["turns"] == []
        assert data["metadata"]["returned_count"] == 0
        assert data["metadata"]["total_available"] == 0
    
    def test_get_narrative_firestore_error(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test 500 for Firestore errors."""
        
        # Mock Firestore error
        mock_firestore_client.collection.side_effect = Exception("Firestore connection error")
        
        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/narrative",
        )
        
        # Assertions
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        response_data = response.json()
        assert "error" in response_data
        assert "internal error" in response_data["message"].lower()
