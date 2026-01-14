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
Tests for status validation and error messages across all APIs.

Verifies that:
1. Invalid status strings produce clear 422 errors with allowed values
2. All endpoints reject unknown status strings deterministically
3. No numeric health fields are exposed in API responses
4. Legacy numeric fields are handled gracefully without persisting
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.models import Status


@pytest.fixture
def test_client_with_mock_db():
    """Create a test client with mocked Firestore for validation tests."""
    mock_db = MagicMock()
    with patch("app.dependencies.get_firestore_client", return_value=mock_db):
        client = TestClient(app)
        yield client, mock_db


class TestStatusValidationInCombatEndpoints:
    """Test status validation in combat-related endpoints."""
    
    def test_update_combat_invalid_enemy_status_returns_422_with_clear_message(
        self, test_client_with_mock_db
    ):
        """Test that invalid enemy status returns 422 with clear error listing allowed values."""
        client, _ = test_client_with_mock_db
        character_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Combat state with invalid enemy status
        combat_state = {
            "combat_id": "combat_001",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": "enemy_1",
                    "name": "Goblin",
                    "status": "Injured",  # Invalid - should be Healthy/Wounded/Dead
                    "weapon": "Sword",
                    "traits": [],
                }
            ],
        }
        
        response = client.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )
        
        # Verify 422 status code
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Verify error contains information about the field and allowed values
        data = response.json()
        assert "errors" in data
        assert len(data["errors"]) == 1
        error = data["errors"][0]
        
        # Verify the precise location of the validation error
        expected_loc = ("body", "combat_state", "enemies", 0, "status")
        assert tuple(error["loc"]) == expected_loc
        
        # Verify the error message and type for enum validation
        assert error["type"] == "enum"
        assert "Input should be 'Healthy', 'Wounded' or 'Dead'" in error["msg"]
    
    def test_update_combat_multiple_invalid_statuses(
        self, test_client_with_mock_db
    ):
        """Test validation with multiple enemies having invalid statuses."""
        client, _ = test_client_with_mock_db
        character_id = "550e8400-e29b-41d4-a716-446655440000"
        
        combat_state = {
            "combat_id": "combat_002",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": "enemy_1",
                    "name": "Goblin",
                    "status": "Hurt",  # Invalid
                    "weapon": "Sword",
                    "traits": [],
                },
                {
                    "enemy_id": "enemy_2",
                    "name": "Orc",
                    "status": "Alive",  # Invalid
                    "weapon": "Axe",
                    "traits": [],
                },
            ],
        }
        
        response = client.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )
        
        # Should return 422 with validation errors (may include multiple errors)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert "errors" in data or "detail" in data
    
    def test_update_combat_valid_statuses_accepted(
        self, test_client_with_mock_db
    ):
        """Test that all valid Status enum values are accepted."""
        client, mock_db = test_client_with_mock_db
        character_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Mock Firestore to return a valid character
        mock_char_snapshot = MagicMock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = {
            "owner_user_id": "user123",
            "combat_state": None,
        }
        mock_db.collection.return_value.document.return_value.get.return_value = (
            mock_char_snapshot
        )
        
        # Test each valid status value
        for status_value in ["Healthy", "Wounded", "Dead"]:
            combat_state = {
                "combat_id": f"combat_{status_value}",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "turn": 1,
                "enemies": [
                    {
                        "enemy_id": "enemy_1",
                        "name": "Test Enemy",
                        "status": status_value,
                        "weapon": "Sword",
                        "traits": [],
                    }
                ],
            }
            
            response = client.put(
                f"/characters/{character_id}/combat",
                json={"combat_state": combat_state},
                headers={"X-User-Id": "user123"},
            )
            
            # Should succeed (200) or fail with Firestore error, but not validation error
            assert response.status_code != status.HTTP_422_UNPROCESSABLE_ENTITY, (
                f"Valid status '{status_value}' should not return 422"
            )


class TestStatusValidationInListCharactersEndpoint:
    """Test that list characters endpoint only returns status fields."""
    
    def test_list_characters_returns_only_status_no_numeric_fields(
        self, test_client_with_mock_db
    ):
        """Test that list_characters returns only status, not numeric health fields."""
        client, mock_db = test_client_with_mock_db
        
        # Mock Firestore to return characters
        mock_query = MagicMock()
        mock_doc1 = MagicMock()
        mock_doc1.id = "char1"
        mock_doc1.to_dict.return_value = {
            "owner_user_id": "user123",
            "player_state": {
                "identity": {
                    "name": "Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
            },
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_query.stream.return_value = [mock_doc1]
        mock_db.collection.return_value.where.return_value.order_by.return_value = (
            mock_query
        )
        
        response = client.get(
            "/characters",
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify response structure
        assert "characters" in data
        assert len(data["characters"]) == 1
        
        character = data["characters"][0]
        
        # Verify status field is present
        assert "status" in character
        assert character["status"] in ["Healthy", "Wounded", "Dead"]
        
        # Verify NO numeric health/stat fields
        assert "level" not in character
        assert "experience" not in character
        assert "stats" not in character
        assert "health" not in character
        assert "hp" not in character
        assert "current_hp" not in character
        assert "max_hp" not in character


class TestLegacyNumericFieldHandling:
    """Test that legacy numeric fields are handled gracefully without persisting."""
    
    def test_get_character_with_legacy_fields_returns_only_status(
        self, test_client_with_mock_db
    ):
        """Test that characters with legacy numeric fields return only status."""
        client, mock_db = test_client_with_mock_db
        character_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Mock Firestore to return character with legacy fields
        mock_char_snapshot = MagicMock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test adventure",
            "player_state": {
                "identity": {
                    "name": "Legacy Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Wounded",
                # Legacy numeric fields that should be stripped
                "level": 10,
                "experience": 5000,
                "stats": {"strength": 18},
                "current_hp": 50,
                "max_hp": 100,
                "equipment": [],
                "inventory": [],
                "location": "Town",
                "additional_fields": {},
            },
            "world_pois_reference": "world",
            "narrative_turns_reference": "narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_db.collection.return_value.document.return_value.get.return_value = (
            mock_char_snapshot
        )
        
        response = client.get(
            f"/characters/{character_id}",
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify character structure
        assert "character" in data
        character = data["character"]
        
        # Verify player_state has status
        assert "player_state" in character
        player_state = character["player_state"]
        assert "status" in player_state
        assert player_state["status"] == "Wounded"
        
        # Verify NO legacy numeric fields in response
        assert "level" not in player_state
        assert "experience" not in player_state
        assert "stats" not in player_state
        assert "current_hp" not in player_state
        assert "max_hp" not in player_state
        assert "health" not in player_state


class TestStatusEnumValues:
    """Test that Status enum values are correctly defined."""
    
    def test_status_enum_values_are_correct(self):
        """Test that Status enum has the exact expected string values."""
        expected_values = {"Healthy", "Wounded", "Dead"}
        actual_values = {s.value for s in Status}
        assert actual_values == expected_values


class TestNoNumericDefaultsOrFallbacks:
    """Test that no defaults or fallbacks based on numeric HP/XP exist."""
    
    def test_create_character_uses_status_not_hp(
        self, test_client_with_mock_db
    ):
        """Test that character creation uses Status enum, not HP-based defaults."""
        client, mock_db = test_client_with_mock_db
        
        # Mock Firestore for character creation
        mock_transaction = MagicMock()
        mock_db.transaction.return_value = mock_transaction
        mock_collection = MagicMock()
        mock_db.collection.return_value = mock_collection
        
        # Mock the query to return no existing characters
        mock_query = MagicMock()
        mock_query.stream.return_value = []
        mock_collection.where.return_value.where.return_value.where.return_value.limit.return_value = (
            mock_query
        )
        
        # Mock document creation
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref
        
        # Mock the created document read-back
        mock_created_doc = MagicMock()
        mock_created_doc.exists = True
        mock_created_doc.to_dict.return_value = {
            "character_id": "new-char-id",
            "owner_user_id": "user123",
            "adventure_prompt": "Test adventure",
            "player_state": {
                "identity": {
                    "name": "New Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",  # Default status
                "equipment": [],
                "inventory": [],
                "location": {
                    "id": "origin:nexus",
                    "display_name": "The Nexus",
                },
                "additional_fields": {},
            },
            "world_pois_reference": "characters/new-char-id/pois",
            "narrative_turns_reference": "characters/new-char-id/narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        mock_doc_ref.get.return_value = mock_created_doc
        
        response = client.post(
            "/characters",
            json={
                "name": "New Hero",
                "race": "Human",
                "class": "Warrior",
                "adventure_prompt": "Test adventure",
            },
            headers={"X-User-Id": "user123"},
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        
        # Verify the created character has status, not numeric fields
        assert "character" in data
        character = data["character"]
        player_state = character["player_state"]
        
        assert "status" in player_state
        assert player_state["status"] == "Healthy"
        
        # Verify NO numeric health fields
        assert "level" not in player_state
        assert "experience" not in player_state
        assert "hp" not in player_state
        assert "health" not in player_state


class TestLegacyFieldPersistence:
    """Test that legacy numeric fields are not persisted back to Firestore."""
    
    def test_legacy_fields_not_repersisted_on_update(
        self, test_client_with_mock_db
    ):
        """Verify that legacy fields are stripped and NOT written back to Firestore."""
        client, mock_db = test_client_with_mock_db
        character_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Mock Firestore to return character with legacy fields
        mock_char_snapshot = MagicMock()
        mock_char_snapshot.exists = True
        mock_char_snapshot.to_dict.return_value = {
            "character_id": character_id,
            "owner_user_id": "user123",
            "adventure_prompt": "Test adventure",
            "player_state": {
                "identity": {
                    "name": "Legacy Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
                # Legacy fields that should NOT be persisted
                "level": 10,
                "experience": 5000,
                "stats": {"strength": 18},
                "current_hp": 100,
                "max_hp": 100,
                "equipment": [],
                "inventory": [],
                "location": "Town",
                "additional_fields": {},
            },
            "world_pois_reference": "world",
            "narrative_turns_reference": "narrative_turns",
            "schema_version": "1.0.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        
        # Mock transaction for combat update
        mock_transaction = MagicMock()
        mock_db.transaction.return_value = mock_transaction
        mock_db.collection.return_value.document.return_value.get.return_value = (
            mock_char_snapshot
        )
        
        # Track the data written to Firestore
        written_data = {}
        
        def mock_update(ref, data):
            written_data.update(data)
        
        mock_transaction.update = mock_update
        
        # Update combat state
        combat_state = {
            "combat_id": "combat_001",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
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
        
        response = client.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )
        
        # Should succeed
        assert response.status_code == status.HTTP_200_OK
        
        # Verify that written data does NOT contain legacy numeric fields
        # The update should only contain combat_state and updated_at
        assert "combat_state" in written_data
        assert "updated_at" in written_data
        
        # Verify legacy fields are NOT in the written data
        # Since we're updating at the document level, these shouldn't appear
        assert "player_state" not in written_data or (
            isinstance(written_data.get("player_state"), dict) and
            "level" not in written_data["player_state"] and
            "experience" not in written_data["player_state"] and
            "stats" not in written_data["player_state"] and
            "current_hp" not in written_data["player_state"] and
            "max_hp" not in written_data["player_state"]
        )


class TestMissingStatusField:
    """Test that missing status field produces actionable validation errors."""
    
    def test_combat_enemy_missing_status_field_returns_422(
        self, test_client_with_mock_db
    ):
        """Test that enemy without status field produces validation error."""
        client, _ = test_client_with_mock_db
        character_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Combat state with enemy missing status field
        combat_state = {
            "combat_id": "combat_001",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "turn": 1,
            "enemies": [
                {
                    "enemy_id": "enemy_1",
                    "name": "Goblin",
                    # Missing "status" field entirely
                    "weapon": "Sword",
                    "traits": [],
                }
            ],
        }
        
        response = client.put(
            f"/characters/{character_id}/combat",
            json={"combat_state": combat_state},
            headers={"X-User-Id": "user123"},
        )
        
        # Should return 422 validation error
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        data = response.json()
        assert "errors" in data
        assert len(data["errors"]) >= 1
        
        # Verify at least one error mentions the missing status field
        error_locations = [tuple(error["loc"]) for error in data["errors"]]
        # The error location should point to the enemy's status field
        expected_loc = ("body", "combat_state", "enemies", 0, "status")
        assert expected_loc in error_locations
        
        # Verify it's a "missing" type error
        missing_errors = [e for e in data["errors"] if e["type"] == "missing"]
        assert len(missing_errors) >= 1
