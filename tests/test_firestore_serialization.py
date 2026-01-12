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
Unit tests for Firestore serialization helpers.

Tests the conversion between Pydantic models and Firestore-friendly dicts,
including timestamp handling, optional field handling, and round-trip conversions.
"""

from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import Mock

from app.models import (
    CharacterDocument,
    CharacterIdentity,
    CombatState,
    CompletionState,
    Enemy,
    Health,
    NarrativeTurn,
    PlayerState,
    PointOfInterest,
    PointOfInterestSubcollection,
    Quest,
    QuestRewards,
    Status,
    # Serialization helpers
    character_from_firestore,
    character_to_firestore,
    datetime_from_firestore,
    datetime_to_firestore,
    narrative_turn_from_firestore,
    narrative_turn_to_firestore,
    poi_from_firestore,
    poi_to_firestore,
    to_firestore_dict,
)


class TestDatetimeConversion:
    """Test datetime conversion helpers."""
    
    def test_datetime_to_firestore_with_utc_datetime(self):
        """Test converting UTC datetime."""
        dt = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        result = datetime_to_firestore(dt)
        assert result == dt
        assert result.tzinfo == timezone.utc
    
    def test_datetime_to_firestore_with_naive_datetime(self):
        """Test converting naive datetime (assumes UTC)."""
        dt = datetime(2026, 1, 11, 12, 0, 0)
        result = datetime_to_firestore(dt)
        assert result.year == 2026
        assert result.tzinfo == timezone.utc
    
    def test_datetime_to_firestore_with_non_utc_timezone(self):
        """Test converting datetime with non-UTC timezone."""
        # Create a timezone offset of +5 hours
        tz_offset = timezone(timedelta(hours=5))
        dt = datetime(2026, 1, 11, 17, 0, 0, tzinfo=tz_offset)  # 5pm in +5
        result = datetime_to_firestore(dt)
        # Should be converted to UTC (12pm)
        assert result.hour == 12
        assert result.tzinfo == timezone.utc
    
    def test_datetime_to_firestore_with_iso_string_z_suffix(self):
        """Test converting ISO string with Z suffix."""
        iso_str = "2026-01-11T12:00:00Z"
        result = datetime_to_firestore(iso_str)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 11
        assert result.hour == 12
        assert result.tzinfo == timezone.utc
    
    def test_datetime_to_firestore_with_iso_string_offset(self):
        """Test converting ISO string with timezone offset."""
        iso_str = "2026-01-11T17:00:00+05:00"
        result = datetime_to_firestore(iso_str)
        # Should be converted to UTC (12pm)
        assert result.hour == 12
        assert result.tzinfo == timezone.utc
    
    def test_datetime_to_firestore_with_none(self):
        """Test that None is preserved."""
        result = datetime_to_firestore(None)
        assert result is None
    
    def test_datetime_from_firestore_with_datetime(self):
        """Test converting datetime object."""
        dt = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        result = datetime_from_firestore(dt)
        assert result == dt
    
    def test_datetime_from_firestore_with_naive_datetime(self):
        """Test converting naive datetime."""
        dt = datetime(2026, 1, 11, 12, 0, 0)
        result = datetime_from_firestore(dt)
        assert result.tzinfo == timezone.utc
    
    def test_datetime_from_firestore_with_iso_string(self):
        """Test converting ISO string."""
        iso_str = "2026-01-11T12:00:00Z"
        result = datetime_from_firestore(iso_str)
        assert result.year == 2026
        assert result.tzinfo == timezone.utc
    
    def test_datetime_from_firestore_with_timestamp_object(self):
        """Test converting Firestore Timestamp object."""
        # Mock a Firestore Timestamp
        mock_timestamp = Mock()
        dt = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        mock_timestamp.to_datetime.return_value = dt
        
        result = datetime_from_firestore(mock_timestamp)
        assert result == dt
        mock_timestamp.to_datetime.assert_called_once()
    
    def test_datetime_from_firestore_with_none(self):
        """Test that None is preserved."""
        result = datetime_from_firestore(None)
        assert result is None


class TestCharacterDocumentSerialization:
    """Test CharacterDocument serialization helpers."""
    
    def create_minimal_character(self) -> CharacterDocument:
        """Create a minimal valid CharacterDocument for testing."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={"strength": 10},
            location="test_location"
        )
        
        return CharacterDocument(
            character_id="test-char-id",
            owner_user_id="user_123",
            adventure_prompt="Test adventure prompt",
            player_state=player_state,
            world_pois_reference="world-v1",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        )
    
    def test_character_to_firestore_basic(self):
        """Test basic character serialization."""
        char = self.create_minimal_character()
        data = character_to_firestore(char)
        
        assert data['character_id'] == 'test-char-id'
        assert data['owner_user_id'] == 'user_123'
        assert data['schema_version'] == '1.0.0'
        assert 'player_state' in data
        assert 'created_at' in data
        assert 'updated_at' in data
    
    def test_character_to_firestore_nested_models(self):
        """Test that nested models are properly serialized."""
        char = self.create_minimal_character()
        data = character_to_firestore(char)
        
        # Check player_state structure
        player_state = data['player_state']
        assert 'identity' in player_state
        assert player_state['identity']['name'] == 'Test'
        assert player_state['identity']['class'] == 'Warrior'  # Using alias
        assert player_state['status'] == 'Healthy'
        assert player_state['health']['current'] == 100
        assert player_state['health']['max'] == 100
    
    def test_character_to_firestore_excludes_none(self):
        """Test that None values are excluded by default."""
        char = self.create_minimal_character()
        # active_quest and combat_state should be None by default
        data = character_to_firestore(char)
        
        # These fields should not be in the output when None
        assert 'active_quest' not in data
        assert 'combat_state' not in data
    
    def test_character_to_firestore_with_optional_fields(self):
        """Test serialization with optional fields populated."""
        char = self.create_minimal_character()
        char.active_quest = Quest(
            name="Test Quest",
            description="A test quest",
            requirements=["Complete objective"],
            rewards=QuestRewards(items=[], currency={"gold": 100}),
            completion_state="in_progress",
            updated_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc)
        )
        
        data = character_to_firestore(char)
        
        assert 'active_quest' in data
        assert data['active_quest']['name'] == 'Test Quest'
        assert data['active_quest']['completion_state'] == 'in_progress'
    
    def test_character_to_firestore_with_combat_state(self):
        """Test serialization with combat state."""
        char = self.create_minimal_character()
        enemy = Enemy(
            enemy_id="enemy_001",
            name="Test Enemy",
            health=Health(current=50, max=50),
            status_effects=[]
        )
        char.combat_state = CombatState(
            combat_id="combat_001",
            started_at=datetime(2026, 1, 11, 14, 0, 0, tzinfo=timezone.utc),
            enemies=[enemy]
        )
        
        data = character_to_firestore(char)
        
        assert 'combat_state' in data
        assert data['combat_state']['combat_id'] == 'combat_001'
        assert len(data['combat_state']['enemies']) == 1
    
    def test_character_from_firestore_basic(self):
        """Test basic character deserialization."""
        data = {
            'character_id': 'test-char-id',
            'owner_user_id': 'user_123',
            'adventure_prompt': 'Test adventure',
            'player_state': {
                'identity': {'name': 'Test', 'race': 'Human', 'class': 'Warrior'},
                'status': 'Healthy',
                'health': {'current': 100, 'max': 100},
                'stats': {'strength': 10},
                'location': 'test_location'
            },
            'world_pois_reference': 'world-v1',
            'narrative_turns_reference': 'narrative_turns',
            'schema_version': '1.0.0',
            'created_at': '2026-01-11T12:00:00Z',
            'updated_at': '2026-01-11T12:00:00Z'
        }
        
        char = character_from_firestore(data)
        
        assert char.character_id == 'test-char-id'
        assert char.owner_user_id == 'user_123'
        assert char.adventure_prompt == 'Test adventure'
        assert char.schema_version == '1.0.0'
        assert char.player_state.identity.name == 'Test'
        assert isinstance(char.created_at, datetime)
        assert isinstance(char.updated_at, datetime)
    
    def test_character_from_firestore_with_character_id_override(self):
        """Test deserialization with character_id override."""
        data = {
            'character_id': 'old-id',
            'owner_user_id': 'user_123',
            'adventure_prompt': 'Override test adventure',
            'player_state': {
                'identity': {'name': 'Test', 'race': 'Human', 'class': 'Warrior'},
                'status': 'Healthy',
                'health': {'current': 100, 'max': 100},
                'stats': {},
                'location': 'test'
            },
            'world_pois_reference': 'world-v1',
            'narrative_turns_reference': 'narrative_turns',
            'schema_version': '1.0.0',
            'created_at': '2026-01-11T12:00:00Z',
            'updated_at': '2026-01-11T12:00:00Z'
        }
        
        char = character_from_firestore(data, character_id='new-id')
        
        assert char.character_id == 'new-id'
    
    def test_character_roundtrip(self):
        """Test serialization round-trip."""
        original = self.create_minimal_character()
        
        # Serialize to Firestore format
        data = character_to_firestore(original)
        
        # Deserialize back to model
        restored = character_from_firestore(data)
        
        # Compare key fields
        assert restored.character_id == original.character_id
        assert restored.owner_user_id == original.owner_user_id
        assert restored.schema_version == original.schema_version
        assert restored.player_state.identity.name == original.player_state.identity.name
        assert restored.player_state.health.current == original.player_state.health.current
    
    def test_character_from_firestore_with_timestamps(self):
        """Test deserialization with Firestore Timestamp objects."""
        # Mock Firestore Timestamp objects
        mock_created = Mock()
        mock_updated = Mock()
        created_dt = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        updated_dt = datetime(2026, 1, 11, 13, 0, 0, tzinfo=timezone.utc)
        mock_created.to_datetime.return_value = created_dt
        mock_updated.to_datetime.return_value = updated_dt
        
        data = {
            'character_id': 'test-char-id',
            'owner_user_id': 'user_123',
            'adventure_prompt': 'Timestamp test adventure',
            'player_state': {
                'identity': {'name': 'Test', 'race': 'Human', 'class': 'Warrior'},
                'status': 'Healthy',
                'health': {'current': 100, 'max': 100},
                'stats': {},
                'location': 'test'
            },
            'world_pois_reference': 'world-v1',
            'narrative_turns_reference': 'narrative_turns',
            'schema_version': '1.0.0',
            'created_at': mock_created,
            'updated_at': mock_updated
        }
        
        char = character_from_firestore(data)
        
        assert char.created_at == created_dt
        assert char.updated_at == updated_dt


class TestNarrativeTurnSerialization:
    """Test NarrativeTurn serialization helpers."""
    
    def test_narrative_turn_to_firestore_basic(self):
        """Test basic narrative turn serialization."""
        turn = NarrativeTurn(
            turn_id="turn_001",
            turn_number=1,
            player_action="I draw my sword",
            gm_response="You draw your sword",
            timestamp=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        )
        
        data = narrative_turn_to_firestore(turn)
        
        assert data['turn_id'] == 'turn_001'
        assert data['turn_number'] == 1
        assert data['player_action'] == 'I draw my sword'
        assert data['gm_response'] == 'You draw your sword'
        assert 'timestamp' in data
    
    def test_narrative_turn_to_firestore_with_metadata(self):
        """Test serialization with optional metadata."""
        turn = NarrativeTurn(
            turn_id="turn_002",
            player_action="test",
            gm_response="test",
            timestamp=datetime.now(timezone.utc),
            game_state_snapshot={"location": "Cave", "health": 100},
            metadata={"response_time_ms": 1250, "llm_model": "gpt-5.1"}
        )
        
        data = narrative_turn_to_firestore(turn)
        
        assert 'game_state_snapshot' in data
        assert data['game_state_snapshot']['location'] == 'Cave'
        assert 'metadata' in data
        assert data['metadata']['llm_model'] == 'gpt-5.1'
    
    def test_narrative_turn_from_firestore_basic(self):
        """Test basic narrative turn deserialization."""
        data = {
            'turn_id': 'turn_001',
            'turn_number': 1,
            'player_action': 'test action',
            'gm_response': 'test response',
            'timestamp': '2026-01-11T12:00:00Z'
        }
        
        turn = narrative_turn_from_firestore(data)
        
        assert turn.turn_id == 'turn_001'
        assert turn.turn_number == 1
        assert isinstance(turn.timestamp, datetime)
    
    def test_narrative_turn_from_firestore_with_id_override(self):
        """Test deserialization with turn_id override."""
        data = {
            'turn_id': 'old-id',
            'player_action': 'test',
            'gm_response': 'test',
            'timestamp': '2026-01-11T12:00:00Z'
        }
        
        turn = narrative_turn_from_firestore(data, turn_id='new-id')
        
        assert turn.turn_id == 'new-id'
    
    def test_narrative_turn_roundtrip(self):
        """Test narrative turn serialization round-trip."""
        original = NarrativeTurn(
            turn_id="turn_003",
            turn_number=3,
            player_action="test action",
            gm_response="test response",
            timestamp=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
            game_state_snapshot={"test": "data"}
        )
        
        # Serialize
        data = narrative_turn_to_firestore(original)
        
        # Deserialize
        restored = narrative_turn_from_firestore(data)
        
        assert restored.turn_id == original.turn_id
        assert restored.turn_number == original.turn_number
        assert restored.user_action == original.user_action
        assert restored.ai_response == original.ai_response


class TestPointOfInterestSerialization:
    """Test PointOfInterestSubcollection serialization helpers."""
    
    def test_poi_to_firestore_basic(self):
        """Test basic POI serialization."""
        poi = PointOfInterestSubcollection(
            poi_id="poi_123",
            name="Hidden Temple",
            description="An ancient temple"
        )
        
        data = poi_to_firestore(poi)
        
        assert data['poi_id'] == 'poi_123'
        assert data['name'] == 'Hidden Temple'
        assert data['description'] == 'An ancient temple'
    
    def test_poi_to_firestore_with_optional_fields(self):
        """Test POI serialization with optional fields."""
        poi = PointOfInterestSubcollection(
            poi_id="poi_124",
            name="Dragon's Lair",
            description="A dangerous cave",
            type="dungeon",
            timestamp_discovered=datetime(2026, 1, 10, 15, 30, 0, tzinfo=timezone.utc),
            last_visited=datetime(2026, 1, 10, 16, 0, 0, tzinfo=timezone.utc),
            visited=True,
            notes="Found a magical artifact here."
        )
        
        data = poi_to_firestore(poi)
        
        assert data['type'] == 'dungeon'
        assert data['visited'] is True
        assert data['notes'] == 'Found a magical artifact here.'
        assert 'timestamp_discovered' in data
        assert 'last_visited' in data
    
    def test_poi_to_firestore_excludes_none(self):
        """Test that None optional fields are excluded."""
        poi = PointOfInterestSubcollection(
            poi_id="poi_125",
            name="Unknown Location",
            description="Not yet visited"
        )
        
        data = poi_to_firestore(poi)
        
        # Optional fields should not be present
        assert 'type' not in data
        assert 'timestamp_discovered' not in data
        assert 'last_visited' not in data
        assert 'notes' not in data
    
    def test_poi_from_firestore_basic(self):
        """Test basic POI deserialization."""
        data = {
            'poi_id': 'poi_123',
            'name': 'Hidden Temple',
            'description': 'An ancient temple'
        }
        
        poi = poi_from_firestore(data)
        
        assert poi.poi_id == 'poi_123'
        assert poi.name == 'Hidden Temple'
        assert poi.description == 'An ancient temple'
    
    def test_poi_from_firestore_with_timestamps(self):
        """Test POI deserialization with timestamps."""
        data = {
            'poi_id': 'poi_124',
            'name': 'Test POI',
            'description': 'Test',
            'timestamp_discovered': '2026-01-10T15:30:00Z',
            'last_visited': '2026-01-10T16:00:00Z'
        }
        
        poi = poi_from_firestore(data)
        
        assert isinstance(poi.timestamp_discovered, datetime)
        assert isinstance(poi.last_visited, datetime)
    
    def test_poi_from_firestore_with_id_override(self):
        """Test deserialization with poi_id override."""
        data = {
            'poi_id': 'old-id',
            'name': 'Test',
            'description': 'Test'
        }
        
        poi = poi_from_firestore(data, poi_id='new-id')
        
        assert poi.poi_id == 'new-id'
    
    def test_poi_roundtrip(self):
        """Test POI serialization round-trip."""
        original = PointOfInterestSubcollection(
            poi_id="poi_126",
            name="Test Location",
            description="Test description",
            type="landmark",
            visited=True,
            timestamp_discovered=datetime(2026, 1, 10, 15, 30, 0, tzinfo=timezone.utc)
        )
        
        # Serialize
        data = poi_to_firestore(original)
        
        # Deserialize
        restored = poi_from_firestore(data)
        
        assert restored.poi_id == original.poi_id
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.type == original.type
        assert restored.visited == original.visited


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_to_firestore_dict_with_empty_lists(self):
        """Test that empty lists are handled properly."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test",
            equipment=[],
            inventory=[]
        )
        
        data = to_firestore_dict(player_state)
        
        # Empty lists should be included
        assert 'equipment' in data
        assert data['equipment'] == []
        assert 'inventory' in data
        assert data['inventory'] == []
    
    def test_character_from_firestore_missing_optional_fields(self):
        """Test that missing optional fields default to None."""
        data = {
            'character_id': 'test-id',
            'owner_user_id': 'user_123',
            'adventure_prompt': 'Missing optional fields test',
            'player_state': {
                'identity': {'name': 'Test', 'race': 'Human', 'class': 'Warrior'},
                'status': 'Healthy',
                'health': {'current': 100, 'max': 100},
                'stats': {},
                'location': 'test'
            },
            'world_pois_reference': 'world',
            'narrative_turns_reference': 'narrative_turns',
            'schema_version': '1.0.0',
            'created_at': '2026-01-11T12:00:00Z',
            'updated_at': '2026-01-11T12:00:00Z'
            # Note: active_quest, combat_state, world_state are missing
        }
        
        char = character_from_firestore(data)
        
        assert char.active_quest is None
        assert char.combat_state is None
        assert char.world_state is None
    
    def test_narrative_turn_without_turn_number(self):
        """Test narrative turn without optional turn_number."""
        turn = NarrativeTurn(
            turn_id="turn_004",
            player_action="test",
            gm_response="test",
            timestamp=datetime.now(timezone.utc)
            # turn_number is optional
        )
        
        data = narrative_turn_to_firestore(turn)
        
        # turn_number should not be in output if None
        assert 'turn_number' not in data
    
    def test_datetime_to_firestore_invalid_type(self):
        """Test that invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Cannot convert"):
            datetime_to_firestore(12345)
    
    def test_datetime_from_firestore_invalid_type(self):
        """Test that invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Cannot convert"):
            datetime_from_firestore(12345)
