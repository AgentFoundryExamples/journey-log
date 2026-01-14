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
Tests for GET /characters/{character_id}/context endpoint.

Tests cover context aggregation, derived fields, query parameters,
and edge cases.
"""

import copy
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db


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
def mock_firestore_client():
    """Create a mock Firestore client."""
    mock_client = Mock()
    mock_collection = Mock()
    mock_client.collection.return_value = mock_collection
    return mock_client


@pytest.fixture
def sample_character_data():
    """Sample character document data with all sections populated."""
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
            "equipment": [],
            "inventory": [],
            "location": {
                "id": "origin:nexus",
                "display_name": "The Nexus",
            },
            "additional_fields": {},
        },
        "world_pois": [
            {
                "id": "poi1",
                "name": "Ancient Temple",
                "description": "A mysterious temple",
                "created_at": datetime.now(timezone.utc),
                "tags": ["dungeon"],
            },
            {
                "id": "poi2",
                "name": "Dragon's Lair",
                "description": "A dangerous cave",
                "created_at": datetime.now(timezone.utc),
                "tags": ["boss"],
            },
            {
                "id": "poi3",
                "name": "Enchanted Forest",
                "description": "A magical forest",
                "created_at": datetime.now(timezone.utc),
                "tags": ["exploration"],
            },
        ],
        "active_quest": {
            "name": "Slay the Dragon",
            "description": "Defeat the ancient dragon",
            "requirements": ["Reach level 10", "Get dragon-slaying sword"],
            "rewards": {
                "items": ["Dragon Scale"],
                "currency": {"gold": 1000},
            },
            "completion_state": "in_progress",
            "updated_at": datetime.now(timezone.utc),
        },
        "combat_state": {
            "combat_id": "combat_001",
            "started_at": datetime.now(timezone.utc),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": "goblin_001",
                    "name": "Goblin Scout",
                    "status": "Wounded",
                    "weapon": "Dagger",
                    "traits": ["sneaky"],
                }
            ],
        },
        "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
        "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


class TestGetCharacterContext:
    """Tests for GET /characters/{character_id}/context endpoint."""

    def test_get_context_success_with_all_data(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test successful context aggregation with all data present."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection

        # Create 3 sample turns
        now = datetime.now(timezone.utc)
        mock_turn_docs = []
        for i in range(3):
            mock_doc = Mock()
            mock_doc.id = f"turn_{i}"
            mock_doc.to_dict.return_value = {
                "turn_id": f"turn_{i}",
                "player_action": f"Action {i}",
                "gm_response": f"Response {i}",
                "timestamp": now - timedelta(minutes=10 - i),
            }
            mock_turn_docs.append(mock_doc)

        mock_limit = Mock()
        mock_limit.stream.return_value = list(reversed(mock_turn_docs))
        mock_order_by = Mock()
        mock_order_by.limit.return_value = mock_limit
        mock_turns_collection.order_by.return_value = mock_order_by

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Check structure
        assert "character_id" in data
        assert "player_state" in data
        assert "quest" in data
        assert "combat" in data
        assert "narrative" in data
        assert "world" in data
        assert "has_active_quest" in data

        # Check derived fields
        assert data["has_active_quest"] is True
        assert data["combat"]["active"] is True  # Enemy is Wounded, not Dead
        assert data["combat"]["state"] is not None

        # Check narrative metadata
        assert data["narrative"]["requested_n"] == 20  # default
        assert data["narrative"]["returned_n"] == 3
        assert data["narrative"]["max_n"] == 100
        assert len(data["narrative"]["recent_turns"]) == 3

        # Check world POIs included
        assert data["world"]["include_pois"] is True
        assert len(data["world"]["pois_sample"]) > 0

        # Verify Firestore read count: 2 reads (1 character doc + 1 narrative query)
        # 1. Character document read
        assert mock_char_ref.get.call_count == 1
        # 2. Narrative turns query
        assert mock_turns_collection.order_by.called
        assert mock_order_by.limit.called

        # Verify correct query parameters for narrative turns
        from google.cloud import firestore
        mock_turns_collection.order_by.assert_called_once_with(
            "timestamp", direction=firestore.Query.DESCENDING
        )
        mock_order_by.limit.assert_called_once_with(20)  # default recent_n

    def test_get_context_no_active_quest(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context when character has no active quest."""

        # Remove active quest
        char_data = copy.deepcopy(sample_character_data)
        char_data["active_quest"] = None

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = char_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock empty narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["has_active_quest"] is False
        assert data["quest"] is None

    def test_get_context_no_combat(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context when character is not in combat."""

        # Remove combat state
        char_data = copy.deepcopy(sample_character_data)
        char_data["combat_state"] = None

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = char_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock empty narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["combat"]["active"] is False
        assert data["combat"]["state"] is None

    def test_get_context_combat_all_enemies_dead(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context when all enemies are dead (combat inactive)."""

        # Set all enemies to Dead
        char_data = copy.deepcopy(sample_character_data)
        char_data["combat_state"]["enemies"][0]["status"] = "Dead"

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = char_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock empty narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["combat"]["active"] is False
        assert data["combat"]["state"] is None  # State omitted when inactive

    def test_get_context_with_recent_n_parameter(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context with custom recent_n parameter."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        mock_limit = Mock()
        mock_limit.stream.return_value = []
        mock_order_by = Mock()
        mock_order_by.limit.return_value = mock_limit
        mock_turns_collection.order_by.return_value = mock_order_by

        # Make request with recent_n=5
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=5",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["narrative"]["requested_n"] == 5
        assert data["narrative"]["max_n"] == 100

        # Verify correct limit parameter passed to Firestore query
        mock_order_by.limit.assert_called_once_with(5)

    def test_get_context_with_include_pois_false(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context with include_pois=false."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
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

        # Make request with include_pois=false
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?include_pois=false",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["world"]["include_pois"] is False
        assert data["world"]["pois_sample"] == []

    def test_get_context_empty_narrative(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context when character has no narrative turns."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
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

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["narrative"]["returned_n"] == 0
        assert data["narrative"]["recent_turns"] == []

    def test_get_context_empty_pois(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context when character has no POIs."""

        # Remove POIs
        char_data = copy.deepcopy(sample_character_data)
        char_data["world_pois"] = []

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = char_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock empty narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        mock_query = Mock()
        mock_query.stream.return_value = []
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["world"]["pois_sample"] == []

    def test_get_context_character_not_found(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
    ):
        """Test 404 when character does not exist."""

        # Mock character not found
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = False
        mock_char_ref.get.return_value = mock_char_snapshot

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_context_invalid_uuid(
        self,
        test_client_with_mock_db,
    ):
        """Test 422 for invalid character UUID."""

        # Make request with invalid UUID
        response = test_client_with_mock_db.get(
            "/characters/invalid-uuid/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_context_user_verification(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context retrieval with user ID verification."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
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

        # Make request with matching user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
            headers={"X-User-Id": "user123"},
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK

    def test_get_context_user_mismatch(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 403 when user ID does not match character owner."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Make request with mismatched user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
            headers={"X-User-Id": "wrong_user"},
        )

        # Assertions
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_context_empty_user_id(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test 400 for empty X-User-Id header."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Make request with empty user ID
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
            headers={"X-User-Id": "   "},
        )

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_context_invalid_recent_n_zero(
        self,
        test_client_with_mock_db,
    ):
        """Test 422 for recent_n=0."""

        # Make request with recent_n=0
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=0",
        )

        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_context_invalid_recent_n_negative(
        self,
        test_client_with_mock_db,
    ):
        """Test 422 for negative recent_n."""

        # Make request with recent_n=-1
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=-1",
        )

        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_context_invalid_recent_n_too_large(
        self,
        test_client_with_mock_db,
    ):
        """Test 422 for recent_n > 100."""

        # Make request with recent_n=101
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=101",
        )

        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_context_narrative_ordering(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that narrative turns are returned in oldest-to-newest order."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative turns with clear timestamps
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection

        now = datetime.now(timezone.utc)
        mock_turn_docs = []
        for i in range(3):
            mock_doc = Mock()
            mock_doc.id = f"turn_{i}"
            mock_doc.to_dict.return_value = {
                "turn_id": f"turn_{i}",
                "player_action": f"Action {i}",
                "gm_response": f"Response {i}",
                "timestamp": now + timedelta(minutes=i),
            }
            mock_turn_docs.append(mock_doc)

        mock_query = Mock()
        # Query returns DESC (newest first), endpoint should reverse
        mock_query.stream.return_value = list(reversed(mock_turn_docs))
        mock_turns_collection.order_by.return_value.limit.return_value = mock_query

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify oldest-to-newest ordering
        turns = data["narrative"]["recent_turns"]
        assert len(turns) == 3
        assert turns[0]["player_action"] == "Action 0"  # Oldest
        assert turns[1]["player_action"] == "Action 1"
        assert turns[2]["player_action"] == "Action 2"  # Newest

    def test_get_context_firestore_read_count(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that context aggregation uses exactly 2 Firestore reads as documented."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative turns
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection
        
        mock_limit = Mock()
        mock_limit.stream.return_value = []
        mock_order_by = Mock()
        mock_order_by.limit.return_value = mock_limit
        mock_turns_collection.order_by.return_value = mock_order_by

        # Make request
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK

        # Verify exactly 2 Firestore reads as documented in README:
        # Read 1: Character document (includes quest, combat, POIs)
        assert mock_char_ref.get.call_count == 1, "Expected 1 character document read"
        
        # Read 2: Narrative turns subcollection query
        assert mock_turns_collection.order_by.call_count == 1, "Expected 1 narrative query"
        assert mock_limit.stream.call_count == 1, "Expected 1 stream operation"

        # Total: 2 Firestore read operations
        # This validates the performance claim in README.md
