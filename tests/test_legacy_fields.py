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
Tests for backward compatibility with legacy numeric health/stat fields.

These tests verify that legacy documents containing deprecated numeric fields
(level, experience, stats, current_hp, max_hp, etc.) can be successfully
deserialized without errors, and that these fields are ignored/stripped.
"""

from datetime import datetime, timezone

import pytest

from app.models import (
    CharacterDocument,
    CharacterIdentity,
    Status,
    character_from_firestore,
)


class TestLegacyFieldBackwardCompatibility:
    """Test backward compatibility with legacy numeric health/stat fields."""

    def test_deserialize_document_with_legacy_level_experience_stats(self):
        """Test that documents with legacy level/experience/stats deserialize correctly."""
        # Simulate a Firestore document with legacy numeric fields
        legacy_data = {
            "character_id": "test-char-123",
            "owner_user_id": "user_456",
            "adventure_prompt": "A brave warrior's tale",
            "player_state": {
                "identity": {
                    "name": "Test Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
                # Legacy fields that should be stripped
                "level": 10,
                "experience": 5000,
                "stats": {
                    "strength": 18,
                    "dexterity": 14,
                    "constitution": 16,
                },
                # Current fields
                "equipment": [],
                "inventory": [],
                "location": "Town Square",
                "additional_fields": {},
            },
            "world_pois_reference": "world-v1",
            "narrative_turns_reference": "narrative_turns",
            "schema_version": "1.0.0",
            "created_at": "2026-01-11T12:00:00Z",
            "updated_at": "2026-01-11T12:00:00Z",
        }

        # Deserialize the document
        character = character_from_firestore(legacy_data)

        # Verify the character was deserialized successfully
        assert character.character_id == "test-char-123"
        assert character.player_state.status == Status.HEALTHY
        assert character.player_state.identity.name == "Test Hero"

        # Verify legacy fields were stripped (no attributes exist)
        assert not hasattr(character.player_state, "level")
        assert not hasattr(character.player_state, "experience")
        assert not hasattr(character.player_state, "stats")

    def test_deserialize_document_with_legacy_hp_fields(self):
        """Test that documents with legacy HP-style fields deserialize correctly."""
        legacy_data = {
            "character_id": "test-char-789",
            "owner_user_id": "user_101",
            "adventure_prompt": "An epic quest",
            "player_state": {
                "identity": {
                    "name": "Warrior",
                    "race": "Dwarf",
                    "class": "Fighter",
                },
                "status": "Wounded",
                # Legacy HP-style fields
                "current_hp": 45,
                "max_hp": 100,
                "current_health": 45,
                "max_health": 100,
                "health": {"current": 45, "max": 100},
                # Current fields
                "equipment": [],
                "inventory": [],
                "location": "Dungeon",
                "additional_fields": {},
            },
            "world_pois_reference": "world-v1",
            "narrative_turns_reference": "narrative_turns",
            "schema_version": "1.0.0",
            "created_at": "2026-01-11T12:00:00Z",
            "updated_at": "2026-01-11T12:00:00Z",
        }

        # Deserialize the document
        character = character_from_firestore(legacy_data)

        # Verify the character was deserialized successfully
        assert character.character_id == "test-char-789"
        assert character.player_state.status == Status.WOUNDED
        assert character.player_state.identity.name == "Warrior"

        # Verify legacy HP fields were stripped
        assert not hasattr(character.player_state, "current_hp")
        assert not hasattr(character.player_state, "max_hp")
        assert not hasattr(character.player_state, "current_health")
        assert not hasattr(character.player_state, "max_health")
        assert not hasattr(character.player_state, "health")

    def test_deserialize_document_with_mixed_legacy_and_current_fields(self):
        """Test that documents with both legacy and current fields work correctly."""
        mixed_data = {
            "character_id": "test-char-456",
            "owner_user_id": "user_789",
            "adventure_prompt": "A mixed legacy document",
            "player_state": {
                "identity": {
                    "name": "Mixed",
                    "race": "Elf",
                    "class": "Ranger",
                },
                "status": "Healthy",
                # Mix of legacy and current fields
                "level": 5,
                "experience": 1000,
                "stats": {"agility": 20},
                "equipment": [{"name": "Bow", "damage": "1d8"}],
                "inventory": [{"name": "Arrow", "quantity": 20}],
                "location": "Forest",
                "additional_fields": {"custom": "value"},
            },
            "world_pois_reference": "world-v1",
            "narrative_turns_reference": "narrative_turns",
            "schema_version": "1.0.0",
            "created_at": "2026-01-11T12:00:00Z",
            "updated_at": "2026-01-11T12:00:00Z",
        }

        # Deserialize the document
        character = character_from_firestore(mixed_data)

        # Verify the character was deserialized successfully
        assert character.character_id == "test-char-456"
        assert character.player_state.status == Status.HEALTHY

        # Verify current fields are preserved
        assert len(character.player_state.equipment) == 1
        assert character.player_state.equipment[0].name == "Bow"
        assert len(character.player_state.inventory) == 1
        assert character.player_state.inventory[0].name == "Arrow"
        assert character.player_state.location == "Forest"
        assert character.player_state.additional_fields["custom"] == "value"

        # Verify legacy fields were stripped
        assert not hasattr(character.player_state, "level")
        assert not hasattr(character.player_state, "experience")
        assert not hasattr(character.player_state, "stats")

    def test_status_validation_still_enforced(self):
        """Test that status validation is still enforced despite legacy field stripping."""
        # Missing status should raise ValidationError
        with pytest.raises(Exception):  # Will be ValidationError from Pydantic
            legacy_data = {
                "character_id": "test-char-999",
                "owner_user_id": "user_999",
                "adventure_prompt": "Missing status",
                "player_state": {
                    "identity": {
                        "name": "Test",
                        "race": "Human",
                        "class": "Warrior",
                    },
                    # Missing status field - should fail validation
                    "equipment": [],
                    "inventory": [],
                    "location": "Test",
                    "additional_fields": {},
                },
                "world_pois_reference": "world-v1",
                "narrative_turns_reference": "narrative_turns",
                "schema_version": "1.0.0",
                "created_at": "2026-01-11T12:00:00Z",
                "updated_at": "2026-01-11T12:00:00Z",
            }
            character_from_firestore(legacy_data)

    def test_invalid_status_raises_error(self):
        """Test that invalid status values are rejected despite legacy field stripping."""
        with pytest.raises(Exception):  # Will be ValidationError from Pydantic
            legacy_data = {
                "character_id": "test-char-888",
                "owner_user_id": "user_888",
                "adventure_prompt": "Invalid status",
                "player_state": {
                    "identity": {
                        "name": "Test",
                        "race": "Human",
                        "class": "Warrior",
                    },
                    "status": "InvalidStatus",  # Invalid status
                    "level": 10,  # Legacy field
                    "equipment": [],
                    "inventory": [],
                    "location": "Test",
                    "additional_fields": {},
                },
                "world_pois_reference": "world-v1",
                "narrative_turns_reference": "narrative_turns",
                "schema_version": "1.0.0",
                "created_at": "2026-01-11T12:00:00Z",
                "updated_at": "2026-01-11T12:00:00Z",
            }
            character_from_firestore(legacy_data)

    def test_legacy_fields_not_repersisted_after_roundtrip(self):
        """Test that stripped legacy fields are never persisted back to storage."""
        from app.models import character_to_firestore

        # Simulate a Firestore document with legacy fields
        legacy_data = {
            "character_id": "test-char-roundtrip",
            "owner_user_id": "user_roundtrip",
            "adventure_prompt": "Roundtrip test",
            "player_state": {
                "identity": {
                    "name": "Roundtrip Hero",
                    "race": "Human",
                    "class": "Warrior",
                },
                "status": "Healthy",
                # Legacy fields that should NOT be in output
                "level": 10,
                "experience": 5000,
                "stats": {"strength": 18},
                "current_hp": 100,
                "max_hp": 100,
                # Current fields
                "equipment": [],
                "inventory": [],
                "location": "Test Town",
                "additional_fields": {},
            },
            "world_pois_reference": "world-v1",
            "narrative_turns_reference": "narrative_turns",
            "schema_version": "1.0.0",
            "created_at": "2026-01-11T12:00:00Z",
            "updated_at": "2026-01-11T12:00:00Z",
        }

        # Deserialize the document (strips legacy fields)
        character = character_from_firestore(legacy_data)

        # Re-serialize the document
        serialized_data = character_to_firestore(character)

        # Verify legacy fields are NOT present in the serialized output
        assert "player_state" in serialized_data
        player_state = serialized_data["player_state"]

        # Assert that none of the legacy numeric fields are in the output
        assert "level" not in player_state, "level field should not be persisted"
        assert "experience" not in player_state, "experience field should not be persisted"
        assert "stats" not in player_state, "stats field should not be persisted"
        assert "current_hp" not in player_state, "current_hp field should not be persisted"
        assert "max_hp" not in player_state, "max_hp field should not be persisted"
        assert "current_health" not in player_state, "current_health field should not be persisted"
        assert "max_health" not in player_state, "max_health field should not be persisted"
        assert "health" not in player_state, "health field should not be persisted"

        # Verify that current fields are still present
        assert "identity" in player_state
        assert "status" in player_state
        assert player_state["status"] == "Healthy"
        assert "equipment" in player_state
        assert "inventory" in player_state
        assert "location" in player_state
