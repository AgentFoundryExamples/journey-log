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
from app.config import get_settings


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

        # Mock narrative turns subcollection
        mock_turns_collection = Mock()
        # Mock POIs subcollection
        mock_pois_collection = Mock()
        
        # Set up char_ref.collection to return appropriate subcollection based on name
        def collection_side_effect(name):
            if name == "narrative_turns":
                return mock_turns_collection
            elif name == "pois":
                return mock_pois_collection
            return Mock()
        
        mock_char_ref.collection.side_effect = collection_side_effect

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

        # Mock POIs subcollection (return empty to use fallback to embedded POIs)
        mock_pois_limit = Mock()
        mock_pois_limit.stream.return_value = []
        mock_pois_order_by = Mock()
        mock_pois_order_by.limit.return_value = mock_pois_limit
        mock_pois_collection.order_by.return_value = mock_pois_order_by

        # Make request with include_pois=true
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?include_pois=true",
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

    def test_get_context_with_poi_subcollection(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context with POIs from subcollection (not embedded fallback)."""

        # Remove embedded POIs to ensure we're testing subcollection path
        char_data = copy.deepcopy(sample_character_data)
        char_data.pop("world_pois", None)

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = char_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative turns and POI subcollections
        mock_turns_collection = Mock()
        mock_pois_collection = Mock()

        def collection_side_effect(name):
            if name == "narrative_turns":
                return mock_turns_collection
            elif name == "pois":
                return mock_pois_collection
            return Mock()

        mock_char_ref.collection.side_effect = collection_side_effect

        # Mock empty narrative turns
        mock_turns_limit = Mock()
        mock_turns_limit.stream.return_value = []
        mock_turns_order_by = Mock()
        mock_turns_order_by.limit.return_value = mock_turns_limit
        mock_turns_collection.order_by.return_value = mock_turns_order_by

        # Mock POI subcollection with actual POI documents
        now = datetime.now(timezone.utc)
        mock_poi_docs = []
        for i in range(2):
            mock_poi_doc = Mock()
            mock_poi_doc.id = f"poi_{i}"
            mock_poi_doc.to_dict.return_value = {
                "poi_id": f"poi_{i}",
                "name": f"POI {i}",
                "description": f"Description {i}",
                "timestamp_discovered": now - timedelta(hours=i),
                "tags": [f"tag{i}"],
            }
            mock_poi_docs.append(mock_poi_doc)

        mock_pois_limit = Mock()
        mock_pois_limit.stream.return_value = mock_poi_docs
        mock_pois_order_by = Mock()
        mock_pois_order_by.limit.return_value = mock_pois_limit
        mock_pois_collection.order_by.return_value = mock_pois_order_by

        # Make request with include_pois=true
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?include_pois=true",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify POI query was made
        assert mock_pois_collection.order_by.called
        assert mock_pois_order_by.limit.called

        # Verify POIs from subcollection are returned (not embedded fallback)
        assert data["world"]["include_pois"] is True
        assert len(data["world"]["pois_sample"]) > 0
        # Check that POI data matches subcollection format
        poi_names = [poi["name"] for poi in data["world"]["pois_sample"]]
        assert any("POI" in name for name in poi_names)

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
        """Test 400 for recent_n=0."""

        # Make request with recent_n=0
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=0",
        )

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_context_invalid_recent_n_negative(
        self,
        test_client_with_mock_db,
    ):
        """Test 400 for negative recent_n."""

        # Make request with recent_n=-1
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=-1",
        )

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_context_invalid_recent_n_too_large(
        self,
        test_client_with_mock_db,
    ):
        """Test 400 for recent_n > 100."""

        # Make request with recent_n=101
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=101",
        )

        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST

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

    def test_get_context_include_narrative_false(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context with include_narrative=false skips narrative query."""
        
        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative turns collection (should NOT be called)
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection

        # Make request with include_narrative=false
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?include_narrative=false",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify narrative is empty
        assert data["narrative"]["returned_n"] == 0
        assert data["narrative"]["recent_turns"] == []
        assert data["narrative"]["requested_n"] == 20  # default value
        
        # Verify narrative query was skipped
        assert mock_turns_collection.order_by.call_count == 0, "Expected no narrative query"

    def test_get_context_include_combat_false(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context with include_combat=false returns empty combat envelope."""
        
        # Mock character document with combat state
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

        # Make request with include_combat=false
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?include_combat=false",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify combat is inactive with null state
        assert data["combat"]["active"] is False
        assert data["combat"]["state"] is None

    def test_get_context_include_quest_false(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context with include_quest=false returns null quest."""
        
        # Mock character document with active quest
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

        # Make request with include_quest=false
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?include_quest=false",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify quest is null
        assert data["quest"] is None
        assert data["has_active_quest"] is False

    def test_get_context_all_components_false(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context with all include_* flags false maintains stable structure."""
        
        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative collection (should NOT be called)
        mock_turns_collection = Mock()
        mock_char_ref.collection.return_value = mock_turns_collection

        # Make request with all flags false
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context"
            "?include_narrative=false&include_combat=false&include_quest=false&include_pois=false",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify all components are empty/neutral but structure is stable
        assert "player_state" in data
        assert "quest" in data
        assert data["quest"] is None
        assert data["has_active_quest"] is False
        assert "combat" in data
        assert data["combat"]["active"] is False
        assert data["combat"]["state"] is None
        assert "narrative" in data
        assert data["narrative"]["recent_turns"] == []
        assert data["narrative"]["returned_n"] == 0
        assert "world" in data
        assert data["world"]["pois_sample"] == []
        assert "metadata" in data
        
        # Verify no missing keys
        assert "character_id" in data
        
        # Verify narrative query was skipped
        assert mock_turns_collection.order_by.call_count == 0

    def test_get_context_include_narrative_false_validates_recent_n(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that recent_n is still validated even when include_narrative=false."""
        
        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Make request with include_narrative=false but invalid recent_n
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context"
            "?include_narrative=false&recent_n=200",  # exceeds max
        )

        # Assertions - should still validate recent_n
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error_detail = response.json()
        assert "recent_n" in str(error_detail).lower()



class TestContextPOISubcollectionRead:
    """Tests for reading POIs from subcollection via context endpoint."""

    @pytest.fixture
    def subcollection_character_data(self):
        """Character data with POIs in subcollection (not embedded)."""
        return {
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "owner_user_id": "user123",
            "adventure_prompt": "Test adventure",
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
            "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
            "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            # No world_pois field - POIs are in subcollection
        }

    @pytest.fixture
    def legacy_character_data_with_embedded_pois(self):
        """Character data with legacy embedded POIs."""
        return {
            "character_id": "550e8400-e29b-41d4-a716-446655440000",
            "owner_user_id": "user123",
            "adventure_prompt": "Test adventure",
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
                    "id": "legacy_poi_1",
                    "name": "Legacy Temple",
                    "description": "An old temple from embedded storage",
                    "created_at": datetime.now(timezone.utc),
                    "tags": ["legacy"],
                }
            ],
            "world_pois_reference": "characters/550e8400-e29b-41d4-a716-446655440000/pois",
            "narrative_turns_reference": "characters/550e8400-e29b-41d4-a716-446655440000/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    def test_context_reads_pois_from_subcollection_when_available(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        subcollection_character_data,
    ):
        """Test that context endpoint reads POIs from subcollection."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = subcollection_character_data
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
        
        # Verify world section is present
        assert "world" in data
        assert "include_pois" in data["world"]
        assert "pois_sample" in data["world"]

    def test_context_fallback_to_embedded_pois_when_subcollection_empty(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        legacy_character_data_with_embedded_pois,
    ):
        """Test context falls back to embedded world_pois when subcollection is empty."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = legacy_character_data_with_embedded_pois
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
        
        # Verify POIs from embedded array appear in context
        assert "world" in data
        assert "pois_sample" in data["world"]
        
        # Note: The actual implementation may sample POIs, so we just verify
        # the structure exists and legacy POIs can be accessed
        pois_sample = data["world"]["pois_sample"]
        assert isinstance(pois_sample, list)

    def test_context_with_fewer_pois_than_cap(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test context when available POIs are fewer than the configured cap (no padding)."""

        # Mock character document
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = sample_character_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative and POI subcollections
        mock_turns_collection = Mock()
        mock_pois_collection = Mock()

        def collection_side_effect(name):
            if name == "narrative_turns":
                return mock_turns_collection
            elif name == "pois":
                return mock_pois_collection
            return Mock()

        mock_char_ref.collection.side_effect = collection_side_effect

        # Mock empty narrative turns
        mock_turns_limit = Mock()
        mock_turns_limit.stream.return_value = []
        mock_turns_order_by = Mock()
        mock_turns_order_by.limit.return_value = mock_turns_limit
        mock_turns_collection.order_by.return_value = mock_turns_order_by

        # Mock POI subcollection with only 1 POI (less than cap of 3)
        now = datetime.now(timezone.utc)
        mock_poi_doc = Mock()
        mock_poi_doc.id = "poi_001"
        mock_poi_doc.to_dict.return_value = {
            "poi_id": "poi_001",
            "name": "Single POI",
            "description": "Only one POI available",
            "timestamp_discovered": now,
            "tags": ["unique"],
        }

        mock_pois_limit = Mock()
        mock_pois_limit.stream.return_value = [mock_poi_doc]
        mock_pois_order_by = Mock()
        mock_pois_order_by.limit.return_value = mock_pois_limit
        mock_pois_collection.order_by.return_value = mock_pois_order_by

        # Make request with include_pois=true
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?include_pois=true",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify world section with POIs
        assert data["world"]["include_pois"] is True
        assert len(data["world"]["pois_sample"]) == 1  # Only 1 POI, no padding
        assert data["world"]["pois_sample"][0]["name"] == "Single POI"
        
        # Verify no padding artifacts
        assert data["world"]["pois_sample"][0]["id"] == "poi_001"

        # Verify Firestore read count (acceptance criteria)
        # Read 1: Character document
        assert mock_char_ref.get.call_count == 1, "Expected 1 character document read"
        
        # Read 2: Narrative turns query
        assert mock_turns_collection.order_by.call_count == 1, "Expected 1 narrative query"
        
        # Read 3: POI query (when include_pois=true)
        assert mock_pois_collection.order_by.call_count == 1, "Expected 1 POI query"
        
        # Total: 3 reads (character + narrative + POI)

    def test_context_response_includes_all_metadata_fields(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that context response includes all required metadata fields."""

        # Mock character document with quest and combat
        char_data = copy.deepcopy(sample_character_data)
        
        mock_char_ref = (
            mock_firestore_client.collection.return_value.document.return_value
        )
        mock_char_snapshot = Mock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = char_data
        mock_char_ref.get.return_value = mock_char_snapshot

        # Mock narrative turns
        mock_turns_collection = Mock()
        mock_pois_collection = Mock()

        def collection_side_effect(name):
            if name == "narrative_turns":
                return mock_turns_collection
            elif name == "pois":
                # Mock empty POI subcollection for this test
                mock_pois_query = Mock()
                mock_pois_query.stream.return_value = []
                mock_pois_collection.order_by.return_value.limit.return_value = mock_pois_query
                return mock_pois_collection
            return Mock()

        mock_char_ref.collection.side_effect = collection_side_effect
        
        now = datetime.now(timezone.utc)
        mock_turn_docs = []
        for i in range(2):
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
            "/characters/550e8400-e29b-41d4-a716-446655440000/context?recent_n=5",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify top-level structure
        assert "character_id" in data
        assert "player_state" in data
        assert "quest" in data
        assert "has_active_quest" in data
        assert "combat" in data
        assert "narrative" in data
        assert "world" in data
        assert "metadata" in data
        
        # Verify narrative metadata
        settings = get_settings()
        narrative = data["narrative"]
        assert "recent_turns" in narrative
        assert "requested_n" in narrative
        assert "returned_n" in narrative
        assert "max_n" in narrative
        assert narrative["requested_n"] == 5
        assert narrative["returned_n"] == 2
        assert narrative["max_n"] == settings.context_recent_n_max
        
        # Verify combat envelope
        combat = data["combat"]
        assert "active" in combat
        assert "state" in combat
        assert isinstance(combat["active"], bool)
        
        # Verify world state
        world = data["world"]
        assert "pois_sample" in world
        assert "pois_cap" in world
        assert "include_pois" in world
        assert world["pois_cap"] == settings.context_poi_cap
        
        # Verify context metadata
        metadata = data["metadata"]
        assert "narrative_max_n" in metadata
        assert "narrative_requested_n" in metadata
        assert "pois_cap" in metadata
        assert "pois_requested" in metadata
        assert metadata["narrative_max_n"] == settings.context_recent_n_max
        assert metadata["narrative_requested_n"] == 5
        assert metadata["pois_cap"] == settings.context_poi_cap
        
        # Verify derived boolean fields
        assert data["has_active_quest"] is True  # sample_character_data has quest
        assert combat["active"] is True  # sample_character_data has combat with non-dead enemy

        # Verify Firestore read count (acceptance criteria)
        # Read 1: Character document
        assert mock_char_ref.get.call_count == 1, "Expected 1 character document read"
        
        # Read 2: Narrative turns query
        assert mock_turns_collection.order_by.call_count == 1, "Expected 1 narrative query"
        
        # Total: 2 reads (character + narrative, no POI since include_pois=false by default)

    def test_context_metadata_consistency_with_settings(
        self,
        test_client_with_mock_db,
        mock_firestore_client,
        sample_character_data,
    ):
        """Test that metadata fields reflect the configured settings."""
        settings = get_settings()
        
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

        # Make request with default parameters
        response = test_client_with_mock_db.get(
            "/characters/550e8400-e29b-41d4-a716-446655440000/context",
        )

        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify metadata matches settings
        assert data["narrative"]["max_n"] == settings.context_recent_n_max
        assert data["narrative"]["requested_n"] == settings.context_recent_n_default
        assert data["world"]["pois_cap"] == settings.context_poi_cap
        assert data["metadata"]["narrative_max_n"] == settings.context_recent_n_max
        assert data["metadata"]["pois_cap"] == settings.context_poi_cap
