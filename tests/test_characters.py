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
        """Test that empty X-User-Id header is treated as no header."""
        
        # Mock Firestore document retrieval
        mock_doc_ref = mock_firestore_client.collection.return_value.document.return_value
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = sample_character_data
        mock_doc_ref.get.return_value = mock_doc_snapshot
        
        # Make request with empty user ID (should be treated as no verification)
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000",
            headers={"X-User-Id": "   "},
        )
        
        # Assertions - should succeed because empty string is ignored
        assert response.status_code == status.HTTP_200_OK
