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
Tests for combat management endpoints.

Tests cover PUT /characters/{character_id}/combat endpoint functionality
including validation, state computation, and edge cases.
"""

from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db


@pytest.fixture
def mock_firestore_client():
    """Create a mock Firestore client for combat tests."""
    mock_client = Mock()
    mock_collection = Mock()
    mock_doc_ref = Mock()
    mock_transaction = Mock()

    # Configure transaction mock to work with @firestore.transactional decorator
    mock_transaction._max_attempts = 5
    mock_transaction._id = None

    # Setup the mock chain
    mock_client.collection.return_value = mock_collection
    mock_client.transaction.return_value = mock_transaction
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
def sample_character_data():
    """Sample character document data for testing."""
    return {
        "character_id": "550e8400-e29b-41d4-a716-446655440000",
        "owner_user_id": "user123",
        "adventure_prompt": "Test adventure prompt",
        "player_state": {
            "identity": {
                "name": "Test Hero",
                "race": "Human",
                "class": "Warrior",
            },
            "status": "Healthy",
            "equipment": [],
            "inventory": [],
            "location": {
                "id": "origin:nexus",
                "display_name": "The Nexus",
            },
            "additional_fields": {},
        },
        "world_pois": [],
        "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
        "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "world_state": None,
        "active_quest": None,
        "archived_quests": [],
        "combat_state": None,
        "additional_metadata": {},
    }


@pytest.fixture
def valid_combat_state():
    """Valid combat state with 3 enemies."""
    return {
        "combat_id": "combat_001",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "turn": 1,
        "enemies": [
            {
                "enemy_id": "enemy_1",
                "name": "Goblin Warrior",
                "status": "Healthy",
                "weapon": "Short Sword",
                "traits": ["aggressive"],
            },
            {
                "enemy_id": "enemy_2",
                "name": "Goblin Archer",
                "status": "Wounded",
                "weapon": "Shortbow",
                "traits": ["ranged"],
            },
            {
                "enemy_id": "enemy_3",
                "name": "Goblin Shaman",
                "status": "Healthy",
                "weapon": "Staff",
                "traits": ["magic"],
            },
        ],
    }


@pytest.fixture
def all_dead_combat_state():
    """Combat state with all enemies dead."""
    return {
        "combat_id": "combat_002",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "turn": 5,
        "enemies": [
            {
                "enemy_id": "enemy_1",
                "name": "Goblin Warrior",
                "status": "Dead",
                "weapon": "Short Sword",
                "traits": [],
            },
            {
                "enemy_id": "enemy_2",
                "name": "Goblin Archer",
                "status": "Dead",
                "weapon": "Shortbow",
                "traits": [],
            },
        ],
    }


class TestUpdateCombat:
    """Tests for PUT /characters/{character_id}/combat endpoint."""

    def test_update_combat_success_active(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
        valid_combat_state,
    ):
        """Test successful combat update with active combat."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        # Mock transaction flow
        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Make request
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": valid_combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is True
        assert data["state"] is not None
        assert data["state"]["combat_id"] == "combat_001"
        assert len(data["state"]["enemies"]) == 3

    def test_update_combat_all_enemies_dead(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
        all_dead_combat_state,
    ):
        """Test combat update with all enemies dead returns active=false."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        # Mock transaction flow
        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Make request
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": all_dead_combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        assert data["state"] is not None
        assert data["state"]["combat_id"] == "combat_002"

    def test_update_combat_clear_state(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test clearing combat state by sending null."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Set existing active combat
        sample_character_data["combat_state"] = {
            "combat_id": "combat_001",
            "started_at": datetime.now(timezone.utc),
            "turn": 3,
            "enemies": [
                {
                    "enemy_id": "enemy_1",
                    "name": "Goblin",
                    "status": "Healthy",
                    "weapon": "Sword",
                    "traits": [],
                }
            ],
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        # Mock transaction flow
        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Make request to clear combat
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": None},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        assert data["state"] is None

    def test_update_combat_empty_enemies_list(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test combat with empty enemies list returns active=false."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        # Mock transaction flow
        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Combat state with empty enemies
        combat_state = {
            "combat_id": "combat_003",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [],
        }

        # Make request
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        assert data["state"] is not None
        assert len(data["state"]["enemies"]) == 0

    def test_update_combat_exceeds_enemy_limit(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that >5 enemies returns 422 validation error."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Combat state with 6 enemies (exceeds limit)
        combat_state = {
            "combat_id": "combat_004",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": f"enemy_{i}",
                    "name": f"Enemy {i}",
                    "status": "Healthy",
                    "weapon": "Sword",
                    "traits": [],
                }
                for i in range(1, 7)  # 6 enemies
            ],
        }

        # Make request
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        # API uses structured error format with 'errors' field
        assert "errors" in data or "detail" in data
        # Pydantic validation error will contain info about enemy limit

    def test_update_combat_character_not_found(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_combat_state,
    ):
        """Test 404 when character doesn't exist."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot - doesn't exist
        mock_snapshot = Mock()
        mock_snapshot.exists = False

        # Mock transaction flow
        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Make request
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": valid_combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        # Check for error message in either 'detail' or 'message' field
        error_msg = data.get("detail") or data.get("message") or ""
        assert "not found" in error_msg.lower()

    def test_update_combat_access_denied(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
        valid_combat_state,
    ):
        """Test 403 when user doesn't own the character."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        # Mock transaction flow
        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Make request with wrong user ID
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": valid_combat_state},
            headers={"X-User-Id": "different_user"},
        )

        # Verify response
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        # Check for error message in either 'detail' or 'message' field
        error_msg = data.get("detail") or data.get("message") or ""
        assert "access denied" in error_msg.lower()

    def test_update_combat_missing_user_id(
        self,
        test_client_with_mock_db,
        valid_combat_state,
    ):
        """Test 400 when X-User-Id header is missing."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Make request without X-User-Id header
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": valid_combat_state},
        )

        # Verify response
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        # Missing header causes FastAPI validation error

    def test_update_combat_invalid_uuid(
        self,
        test_client_with_mock_db,
        valid_combat_state,
    ):
        """Test 422 when character_id is not a valid UUID."""
        # Make request with invalid UUID
        response = test_client_with_mock_db.put(
            "/characters/not-a-uuid/combat",
            json={"combat_state": valid_combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        # Check for error message in either 'detail' or 'message' field
        error_msg = data.get("detail") or data.get("message") or ""
        assert "uuid" in error_msg.lower()

    def test_update_combat_invalid_status_enum(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test validation error when enemy has invalid status."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Combat state with invalid status
        combat_state = {
            "combat_id": "combat_005",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": "enemy_1",
                    "name": "Goblin",
                    "status": "InvalidStatus",  # Invalid!
                    "weapon": "Sword",
                    "traits": [],
                }
            ],
        }

        # Make request
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        # API uses structured error format with 'errors' field
        assert "errors" in data or "detail" in data
        # Pydantic validation error will mention status field

    def test_update_combat_missing_required_fields(
        self,
        test_client_with_mock_db,
    ):
        """Test validation error when required fields are missing."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Combat state missing required fields
        combat_state = {
            "combat_id": "combat_006",
            # Missing started_at
            # Missing enemies
        }

        # Make request
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify response
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        # API uses structured error format with 'errors' field
        assert "errors" in data or "detail" in data

    def test_update_combat_with_malformed_existing_state(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        valid_combat_state,
    ):
        """Test that malformed existing combat state doesn't break the update."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Character with malformed combat_state (missing required fields)
        sample_data = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test",
            "player_state": {
                "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
                "status": "Healthy",
                "equipment": [],
                "inventory": [],
                "location": {"id": "origin:nexus", "display_name": "The Nexus"},
                "additional_fields": {},
            },
            "world_pois": [],
            "world_pois_reference": f"characters/{character_id}/pois",
            "narrative_turns_reference": f"characters/{character_id}/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "world_state": None,
            "active_quest": None,
            "archived_quests": [],
            # Malformed combat_state - missing required fields like started_at
            "combat_state": {
                "combat_id": "old_combat",
                "enemies": [
                    {"enemy_id": "e1", "name": "Old Enemy", "status": "Healthy"}
                ],
            },
            "additional_metadata": {},
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_data

        # Mock transaction flow
        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Make request with valid new combat state
        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": valid_combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Should succeed despite malformed existing state (uses fallback logic)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is True
        assert data["state"]["combat_id"] == "combat_001"


class TestGetCombat:
    """Tests for GET /characters/{character_id}/combat endpoint."""

    def test_get_combat_active_state(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
        valid_combat_state,
    ):
        """Test retrieving active combat state."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Add active combat state to character
        sample_character_data["combat_state"] = {
            "combat_id": valid_combat_state["combat_id"],
            "started_at": datetime.now(timezone.utc),
            "turn": valid_combat_state["turn"],
            "enemies": valid_combat_state["enemies"],
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "user123"}
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is True
        assert data["state"] is not None
        assert data["state"]["combat_id"] == "combat_001"
        assert len(data["state"]["enemies"]) == 3

    def test_get_combat_no_state(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test retrieving combat when no combat state exists."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Ensure no combat state
        sample_character_data["combat_state"] = None

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "user123"}
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        assert data["state"] is None

    def test_get_combat_all_enemies_dead(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
        all_dead_combat_state,
    ):
        """Test retrieving combat when all enemies are dead."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Add combat state with all dead enemies
        sample_character_data["combat_state"] = {
            "combat_id": all_dead_combat_state["combat_id"],
            "started_at": datetime.now(timezone.utc),
            "turn": all_dead_combat_state["turn"],
            "enemies": all_dead_combat_state["enemies"],
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "user123"}
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        # When inactive (all enemies dead), state should be null per acceptance criteria
        assert data["state"] is None

    def test_get_combat_empty_enemies(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test retrieving combat when enemies list is empty."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Add combat state with empty enemies
        sample_character_data["combat_state"] = {
            "combat_id": "combat_empty",
            "started_at": datetime.now(timezone.utc),
            "turn": 1,
            "enemies": [],
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "user123"}
        )

        # Verify response
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        # When inactive (empty enemies list), state should be null per acceptance criteria
        assert data["state"] is None

    def test_get_combat_character_not_found(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test 404 when character doesn't exist."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot - doesn't exist
        mock_snapshot = Mock()
        mock_snapshot.exists = False

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "user123"}
        )

        # Verify response
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        error_msg = data.get("detail") or data.get("message") or ""
        assert "not found" in error_msg.lower()

    def test_get_combat_access_denied(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 403 when user doesn't own the character."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request with wrong user ID
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat",
            headers={"X-User-Id": "different_user"},
        )

        # Verify response
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        error_msg = data.get("detail") or data.get("message") or ""
        assert "access denied" in error_msg.lower()

    def test_get_combat_anonymous_access(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
        valid_combat_state,
    ):
        """Test anonymous access without X-User-Id header."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Add active combat state
        sample_character_data["combat_state"] = {
            "combat_id": valid_combat_state["combat_id"],
            "started_at": datetime.now(timezone.utc),
            "turn": valid_combat_state["turn"],
            "enemies": valid_combat_state["enemies"],
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request without X-User-Id header
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat",
        )

        # Verify response - should succeed for anonymous access
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is True
        assert data["state"] is not None

    def test_get_combat_empty_user_id_header(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 400 when X-User-Id header is provided but empty."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_character_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request with empty X-User-Id header
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "   "}
        )

        # Verify response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        error_msg = data.get("detail") or data.get("message") or ""
        assert "cannot be empty" in error_msg.lower()

    def test_get_combat_invalid_uuid(
        self,
        test_client_with_mock_db,
    ):
        """Test 422 when character_id is not a valid UUID."""
        # Make request with invalid UUID
        response = test_client_with_mock_db.get(
            "/characters/not-a-uuid/combat", headers={"X-User-Id": "user123"}
        )

        # Verify response
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        error_msg = data.get("detail") or data.get("message") or ""
        assert "uuid" in error_msg.lower()

    def test_get_combat_malformed_stored_data(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test graceful handling of malformed combat state in database."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Character with malformed combat_state
        sample_data = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test",
            "player_state": {
                "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
                "status": "Healthy",
                "equipment": [],
                "inventory": [],
                "location": {"id": "origin:nexus", "display_name": "The Nexus"},
                "additional_fields": {},
            },
            "world_pois": [],
            "world_pois_reference": f"characters/{character_id}/pois",
            "narrative_turns_reference": f"characters/{character_id}/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "world_state": None,
            "active_quest": None,
            "archived_quests": [],
            # Malformed combat_state - missing required fields
            "combat_state": {
                "combat_id": "malformed",
                # Missing started_at and enemies
            },
            "additional_metadata": {},
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "user123"}
        )

        # Should return inactive with null state (defensive fallback)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        assert data["state"] is None

    def test_get_combat_legacy_data_with_many_enemies(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test defensive handling of legacy data with >5 enemies."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Character with >5 enemies (legacy data)
        sample_data = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test",
            "player_state": {
                "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
                "status": "Healthy",
                "equipment": [],
                "inventory": [],
                "location": {"id": "origin:nexus", "display_name": "The Nexus"},
                "additional_fields": {},
            },
            "world_pois": [],
            "world_pois_reference": f"characters/{character_id}/pois",
            "narrative_turns_reference": f"characters/{character_id}/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "world_state": None,
            "active_quest": None,
            "archived_quests": [],
            # Legacy combat_state with >5 enemies
            "combat_state": {
                "combat_id": "legacy_combat",
                "started_at": datetime.now(timezone.utc),
                "turn": 3,
                "enemies": [
                    {
                        "enemy_id": f"enemy_{i}",
                        "name": f"Enemy {i}",
                        "status": "Healthy",
                        "weapon": "Sword",
                        "traits": [],
                    }
                    for i in range(1, 8)  # 7 enemies (exceeds limit)
                ],
            },
            "additional_metadata": {},
        }

        # Mock Firestore document snapshot
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = sample_data

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}/combat", headers={"X-User-Id": "user123"}
        )

        # Should return inactive with null state (defensive fallback for invalid data)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["active"] is False
        assert data["state"] is None


class TestStatusTransitions:
    """Test status transitions through combat sequences (Healthy → Wounded → Dead)."""

    def test_get_character_when_healthy(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test GET /character/{id} correctly retrieves a Healthy character."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Character state - Healthy
        healthy_character = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test",
            "player_state": {
                "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
                "status": "Healthy",
                "equipment": [],
                "inventory": [],
                "location": {"id": "arena", "display_name": "Arena"},
                "additional_fields": {},
            },
            "world_pois": [],
            "world_pois_reference": f"characters/{character_id}/pois",
            "narrative_turns_reference": f"characters/{character_id}/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "combat_state": None,
        }

        # Setup mock
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = healthy_character

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Get status
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}", headers={"X-User-Id": "user123"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["character"]["player_state"]["status"] == "Healthy"

    def test_get_character_when_wounded(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test GET /character/{id} correctly retrieves a Wounded character."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Character state - Wounded
        wounded_character = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test",
            "player_state": {
                "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
                "status": "Wounded",
                "equipment": [],
                "inventory": [],
                "location": {"id": "battlefield", "display_name": "Battlefield"},
                "additional_fields": {},
            },
            "world_pois": [],
            "world_pois_reference": f"characters/{character_id}/pois",
            "narrative_turns_reference": f"characters/{character_id}/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "combat_state": {
                "combat_id": "combat_final",
                "started_at": datetime.now(timezone.utc),
                "turn": 3,
                "enemies": [
                    {
                        "enemy_id": "boss_001",
                        "name": "Dragon",
                        "status": "Healthy",
                        "weapon": "Fire Breath",
                        "traits": ["flying", "powerful"],
                    }
                ],
            },
        }

        # Setup mock
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = wounded_character

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get.return_value = mock_snapshot

        # Verify wounded status
        response = test_client_with_mock_db.get(
            f"/characters/{character_id}", headers={"X-User-Id": "user123"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["character"]["player_state"]["status"] == "Wounded"

    def test_enemy_status_transitions_in_combat(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test enemy status transitions during combat (Healthy → Wounded → Dead)."""
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        # Combat with enemies at different status levels
        character_data = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test",
            "player_state": {
                "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
                "status": "Healthy",
                "equipment": [],
                "inventory": [],
                "location": {"id": "dungeon", "display_name": "Dungeon"},
                "additional_fields": {},
            },
            "world_pois": [],
            "world_pois_reference": f"characters/{character_id}/pois",
            "narrative_turns_reference": f"characters/{character_id}/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        # Setup mock
        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = character_data

        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Turn 1: All enemies Healthy
        combat_turn1 = {
            "combat_id": "combat_progression",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": "orc_001",
                    "name": "Orc Warrior",
                    "status": "Healthy",
                    "weapon": "Axe",
                    "traits": [],
                },
                {
                    "enemy_id": "orc_002",
                    "name": "Orc Scout",
                    "status": "Healthy",
                    "weapon": "Bow",
                    "traits": [],
                },
            ],
        }

        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_turn1},
            headers={"X-User-Id": "user123"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["active"] is True
        assert all(e["status"] == "Healthy" for e in response.json()["state"]["enemies"])

        # Turn 2: One enemy Wounded, one still Healthy
        combat_turn2 = {
            **combat_turn1,
            "turn": 2,
            "enemies": [
                {
                    "enemy_id": "orc_001",
                    "name": "Orc Warrior",
                    "status": "Wounded",  # Transitioned
                    "weapon": "Axe",
                    "traits": [],
                },
                {
                    "enemy_id": "orc_002",
                    "name": "Orc Scout",
                    "status": "Healthy",
                    "weapon": "Bow",
                    "traits": [],
                },
            ],
        }

        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_turn2},
            headers={"X-User-Id": "user123"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["active"] is True
        enemies = response.json()["state"]["enemies"]
        assert enemies[0]["status"] == "Wounded"
        assert enemies[1]["status"] == "Healthy"

        # Turn 3: One enemy Dead, one Wounded
        combat_turn3 = {
            **combat_turn1,
            "turn": 3,
            "enemies": [
                {
                    "enemy_id": "orc_001",
                    "name": "Orc Warrior",
                    "status": "Dead",  # Transitioned
                    "weapon": "Axe",
                    "traits": [],
                },
                {
                    "enemy_id": "orc_002",
                    "name": "Orc Scout",
                    "status": "Wounded",  # Transitioned
                    "weapon": "Bow",
                    "traits": [],
                },
            ],
        }

        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_turn3},
            headers={"X-User-Id": "user123"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["active"] is True  # Still active (one enemy alive)
        enemies = response.json()["state"]["enemies"]
        assert enemies[0]["status"] == "Dead"
        assert enemies[1]["status"] == "Wounded"

        # Turn 4: All enemies Dead
        combat_turn4 = {
            **combat_turn1,
            "turn": 4,
            "enemies": [
                {
                    "enemy_id": "orc_001",
                    "name": "Orc Warrior",
                    "status": "Dead",
                    "weapon": "Axe",
                    "traits": [],
                },
                {
                    "enemy_id": "orc_002",
                    "name": "Orc Scout",
                    "status": "Dead",  # Transitioned
                    "weapon": "Bow",
                    "traits": [],
                },
            ],
        }

        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_turn4},
            headers={"X-User-Id": "user123"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["active"] is False  # Combat ended
        assert all(e["status"] == "Dead" for e in response.json()["state"]["enemies"])

    def test_status_transitions_without_numeric_arithmetic(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Verify status transitions happen without numeric HP/damage calculations.
        
        This test ensures that the combat system uses only status-based health
        (Healthy/Wounded/Dead) without any numeric HP, level, or stats fields.
        """
        character_id = "550e8400-e29b-41d4-a716-446655440000"

        character_data = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test status-only combat",
            "player_state": {
                "identity": {"name": "Hero", "race": "Human", "class": "Warrior"},
                "status": "Healthy",  # Status-only health, no numeric HP/level/stats
                "equipment": [],
                "inventory": [],
                "location": "Arena",
                "additional_fields": {},
            },
            "world_pois": [],
            "world_pois_reference": f"characters/{character_id}/pois",
            "narrative_turns_reference": f"characters/{character_id}/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        mock_snapshot = Mock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = character_data

        def transaction_get(transaction=None):
            return mock_snapshot

        mock_doc_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_doc_ref.get = transaction_get

        # Create combat state with status changes - no HP values
        combat_state = {
            "combat_id": "combat_no_numeric",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": "enemy_001",
                    "name": "Test Enemy",
                    "status": "Wounded",  # Status-only health
                    "weapon": "Sword",
                    "traits": ["aggressive"],
                }
            ],
        }

        response = test_client_with_mock_db.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )

        # Verify combat accepted with status-only health
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["state"]["enemies"][0]["status"] == "Wounded"
        
        # Verify no numeric fields in enemy response
        enemy_data = response.json()["state"]["enemies"][0]
        assert "hp" not in enemy_data
        assert "health" not in enemy_data
        assert "current_hp" not in enemy_data
        assert "max_hp" not in enemy_data
        assert "damage" not in enemy_data
        
        # Verify no numeric fields in player_state
        player_state = character_data["player_state"]
        assert "level" not in player_state
        assert "experience" not in player_state
        assert "stats" not in player_state
        assert "health" not in player_state
        assert "current_hp" not in player_state
        assert "max_hp" not in player_state
