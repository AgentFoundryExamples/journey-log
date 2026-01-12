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
Tests for narrative turn field validation and Firestore helpers.

Tests validation of field size limits, configuration settings,
and Firestore helper functions for narrative turns subcollection.
"""

from datetime import datetime, timezone
import uuid
import pytest
from pydantic import ValidationError
from unittest.mock import Mock, MagicMock, patch

from app.models import NarrativeTurn, narrative_turn_to_firestore
from app.config import Settings


class TestNarrativeTurnFieldValidation:
    """Test field size validation for NarrativeTurn model."""
    
    def test_user_action_within_limit(self):
        """Test that user_action within 8000 characters is valid."""
        user_action = "A" * 8000  # Exactly at limit
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            user_action=user_action,
            ai_response="Response",
            timestamp=datetime.now(timezone.utc)
        )
        assert len(turn.user_action) == 8000
    
    def test_user_action_exceeds_limit(self):
        """Test that user_action exceeding 8000 characters raises ValidationError."""
        user_action = "A" * 8001  # One character over limit
        with pytest.raises(ValidationError) as exc_info:
            NarrativeTurn(
                turn_id=str(uuid.uuid4()),
                user_action=user_action,
                ai_response="Response",
                timestamp=datetime.now(timezone.utc)
            )
        assert "user_action" in str(exc_info.value)
        assert "8000" in str(exc_info.value)
    
    def test_ai_response_within_limit(self):
        """Test that ai_response within 32000 characters is valid."""
        ai_response = "B" * 32000  # Exactly at limit
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            user_action="Action",
            ai_response=ai_response,
            timestamp=datetime.now(timezone.utc)
        )
        assert len(turn.ai_response) == 32000
    
    def test_ai_response_exceeds_limit(self):
        """Test that ai_response exceeding 32000 characters raises ValidationError."""
        ai_response = "B" * 32001  # One character over limit
        with pytest.raises(ValidationError) as exc_info:
            NarrativeTurn(
                turn_id=str(uuid.uuid4()),
                user_action="Action",
                ai_response=ai_response,
                timestamp=datetime.now(timezone.utc)
            )
        assert "ai_response" in str(exc_info.value)
        assert "32000" in str(exc_info.value)
    
    def test_both_fields_at_limit(self):
        """Test that both fields can be at their limits simultaneously."""
        user_action = "A" * 8000
        ai_response = "B" * 32000
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            user_action=user_action,
            ai_response=ai_response,
            timestamp=datetime.now(timezone.utc)
        )
        assert len(turn.user_action) == 8000
        assert len(turn.ai_response) == 32000
    
    def test_minimal_valid_turn(self):
        """Test creating a minimal valid narrative turn."""
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            user_action="I explore",
            ai_response="You see a path",
            timestamp=datetime.now(timezone.utc)
        )
        assert turn.user_action == "I explore"
        assert turn.ai_response == "You see a path"
        assert turn.turn_number is None  # Optional field
    
    def test_turn_with_all_fields(self):
        """Test creating a narrative turn with all optional fields."""
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            turn_number=5,
            user_action="I attack",
            ai_response="You deal damage",
            timestamp=datetime.now(timezone.utc),
            game_state_snapshot={"health": 100, "location": "dungeon"},
            metadata={"llm_model": "gpt-5.1", "tokens_used": 150}
        )
        assert turn.turn_number == 5
        assert turn.game_state_snapshot is not None
        assert turn.metadata is not None


class TestNarrativeTurnConfiguration:
    """Test configuration settings for narrative turns."""
    
    def test_default_configuration_values(self):
        """Test that default configuration values are correct."""
        settings = Settings()
        assert settings.narrative_turns_default_query_size == 10
        assert settings.narrative_turns_max_query_size == 100
        assert settings.narrative_turns_max_user_action_length == 8000
        assert settings.narrative_turns_max_ai_response_length == 32000
    
    def test_configuration_validation_min_values(self):
        """Test that configuration validates minimum values."""
        # Default query size must be >= 1
        with pytest.raises(ValidationError):
            Settings(narrative_turns_default_query_size=0)
        
        # Max query size must be >= 1
        with pytest.raises(ValidationError):
            Settings(narrative_turns_max_query_size=0)
    
    def test_configuration_validation_max_values(self):
        """Test that configuration validates maximum values."""
        # Default query size must be <= 100
        with pytest.raises(ValidationError):
            Settings(narrative_turns_default_query_size=101)
        
        # Max query size must be <= 1000
        with pytest.raises(ValidationError):
            Settings(narrative_turns_max_query_size=1001)
    
    def test_custom_configuration_values(self):
        """Test setting custom configuration values."""
        settings = Settings(
            narrative_turns_default_query_size=20,
            narrative_turns_max_query_size=200,
            narrative_turns_max_user_action_length=10000,
            narrative_turns_max_ai_response_length=40000
        )
        assert settings.narrative_turns_default_query_size == 20
        assert settings.narrative_turns_max_query_size == 200
        assert settings.narrative_turns_max_user_action_length == 10000
        assert settings.narrative_turns_max_ai_response_length == 40000


class TestNarrativeTurnFirestoreHelpers:
    """Test Firestore helper functions for narrative turns."""
    
    @patch('app.firestore.get_firestore_client')
    @patch('app.firestore.get_settings')
    def test_get_narrative_turns_collection(self, mock_settings, mock_client):
        """Test getting narrative turns collection reference."""
        from app.firestore import get_narrative_turns_collection
        
        # Setup mocks
        mock_settings_obj = Mock()
        mock_settings_obj.firestore_characters_collection = "characters"
        mock_settings.return_value = mock_settings_obj
        
        mock_client_obj = Mock()
        mock_collection = Mock()
        mock_document = Mock()
        mock_subcollection = Mock()
        
        mock_client_obj.collection.return_value = mock_collection
        mock_collection.document.return_value = mock_document
        mock_document.collection.return_value = mock_subcollection
        mock_client.return_value = mock_client_obj
        
        # Test
        character_id = str(uuid.uuid4())
        result = get_narrative_turns_collection(character_id)
        
        # Verify
        mock_client_obj.collection.assert_called_once_with("characters")
        mock_collection.document.assert_called_once_with(character_id)
        mock_document.collection.assert_called_once_with("narrative_turns")
        assert result == mock_subcollection
    
    @patch('app.firestore.get_narrative_turns_collection')
    def test_write_narrative_turn(self, mock_get_collection):
        """Test writing a narrative turn."""
        from app.firestore import write_narrative_turn
        
        # Setup mocks
        mock_collection = Mock()
        mock_doc_ref = Mock()
        mock_collection.document.return_value = mock_doc_ref
        mock_get_collection.return_value = mock_collection
        
        # Test data
        character_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        turn_data = {
            "turn_id": turn_id,
            "player_action": "I explore",
            "gm_response": "You see a path",
            "timestamp": datetime.now(timezone.utc)
        }
        
        # Test
        result = write_narrative_turn(character_id, turn_data, use_server_timestamp=False)
        
        # Verify
        mock_get_collection.assert_called_once_with(character_id)
        mock_collection.document.assert_called_once_with(turn_id)
        mock_doc_ref.set.assert_called_once()
        assert result == mock_doc_ref
    
    @patch('app.firestore.get_narrative_turns_collection')
    def test_write_narrative_turn_missing_turn_id(self, mock_get_collection):
        """Test that writing a turn without turn_id raises ValueError."""
        from app.firestore import write_narrative_turn
        
        character_id = str(uuid.uuid4())
        turn_data = {
            "player_action": "I explore",
            "gm_response": "You see a path"
        }
        
        with pytest.raises(ValueError) as exc_info:
            write_narrative_turn(character_id, turn_data)
        assert "turn_id" in str(exc_info.value)
    
    @patch('app.firestore.get_narrative_turns_collection')
    def test_write_narrative_turn_missing_timestamp_no_server_timestamp(self, mock_get_collection):
        """Test that writing a turn without timestamp when use_server_timestamp=False raises ValueError."""
        from app.firestore import write_narrative_turn
        
        character_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        turn_data = {
            "turn_id": turn_id,
            "player_action": "I explore",
            "gm_response": "You see a path"
            # Missing timestamp
        }
        
        with pytest.raises(ValueError) as exc_info:
            write_narrative_turn(character_id, turn_data, use_server_timestamp=False)
        assert "timestamp" in str(exc_info.value)
    
    @patch('app.firestore.get_narrative_turns_collection')
    @patch('app.firestore.get_settings')
    def test_query_narrative_turns_default_limit(self, mock_settings, mock_get_collection):
        """Test querying narrative turns with default limit."""
        from app.firestore import query_narrative_turns
        
        # Setup mocks
        mock_settings_obj = Mock()
        mock_settings_obj.narrative_turns_default_query_size = 10
        mock_settings_obj.narrative_turns_max_query_size = 100
        mock_settings.return_value = mock_settings_obj
        
        mock_collection = Mock()
        mock_query = Mock()
        mock_collection.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        
        # Create mock documents with distinct dictionaries using side_effect
        mock_doc1 = Mock()
        mock_doc1.to_dict.return_value = {"turn_number": 3, "player_action": "Action 3"}
        mock_doc2 = Mock()
        mock_doc2.to_dict.return_value = {"turn_number": 2, "player_action": "Action 2"}
        mock_doc3 = Mock()
        mock_doc3.to_dict.return_value = {"turn_number": 1, "player_action": "Action 1"}
        
        mock_query.stream.return_value = [mock_doc1, mock_doc2, mock_doc3]
        
        mock_get_collection.return_value = mock_collection
        
        # Test
        character_id = str(uuid.uuid4())
        result = query_narrative_turns(character_id)
        
        # Verify
        mock_collection.order_by.assert_called_once()
        mock_query.limit.assert_called_once_with(10)
        
        # Results should be reversed to oldest-first
        assert len(result) == 3
        assert result[0]["turn_number"] == 1
        assert result[1]["turn_number"] == 2
        assert result[2]["turn_number"] == 3
    
    @patch('app.firestore.get_narrative_turns_collection')
    @patch('app.firestore.get_settings')
    def test_query_narrative_turns_custom_limit(self, mock_settings, mock_get_collection):
        """Test querying narrative turns with custom limit."""
        from app.firestore import query_narrative_turns
        
        # Setup mocks
        mock_settings_obj = Mock()
        mock_settings_obj.narrative_turns_default_query_size = 10
        mock_settings_obj.narrative_turns_max_query_size = 100
        mock_settings.return_value = mock_settings_obj
        
        mock_collection = Mock()
        mock_query = Mock()
        mock_collection.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []
        
        mock_get_collection.return_value = mock_collection
        
        # Test with custom limit
        character_id = str(uuid.uuid4())
        query_narrative_turns(character_id, limit=25)
        
        # Verify custom limit was used
        mock_query.limit.assert_called_once_with(25)
    
    @patch('app.firestore.get_narrative_turns_collection')
    @patch('app.firestore.get_settings')
    def test_query_narrative_turns_enforces_max_limit(self, mock_settings, mock_get_collection):
        """Test that query enforces max limit from configuration."""
        from app.firestore import query_narrative_turns
        
        # Setup mocks
        mock_settings_obj = Mock()
        mock_settings_obj.narrative_turns_default_query_size = 10
        mock_settings_obj.narrative_turns_max_query_size = 100
        mock_settings.return_value = mock_settings_obj
        
        mock_collection = Mock()
        mock_query = Mock()
        mock_collection.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = []
        
        mock_get_collection.return_value = mock_collection
        
        # Test with limit exceeding max
        character_id = str(uuid.uuid4())
        query_narrative_turns(character_id, limit=500)
        
        # Verify max limit was enforced
        mock_query.limit.assert_called_once_with(100)
    
    @patch('app.firestore.get_narrative_turns_collection')
    def test_get_narrative_turn_by_id_exists(self, mock_get_collection):
        """Test getting a narrative turn by ID when it exists."""
        from app.firestore import get_narrative_turn_by_id
        
        # Setup mocks
        mock_collection = Mock()
        mock_doc_ref = Mock()
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = True
        mock_doc_snapshot.to_dict.return_value = {
            "turn_id": "turn_123",
            "player_action": "I explore"
        }
        mock_doc_ref.get.return_value = mock_doc_snapshot
        mock_collection.document.return_value = mock_doc_ref
        mock_get_collection.return_value = mock_collection
        
        # Test
        character_id = str(uuid.uuid4())
        turn_id = "turn_123"
        result = get_narrative_turn_by_id(character_id, turn_id)
        
        # Verify
        assert result is not None
        assert result["turn_id"] == "turn_123"
        mock_collection.document.assert_called_once_with(turn_id)
    
    @patch('app.firestore.get_narrative_turns_collection')
    def test_get_narrative_turn_by_id_not_exists(self, mock_get_collection):
        """Test getting a narrative turn by ID when it doesn't exist."""
        from app.firestore import get_narrative_turn_by_id
        
        # Setup mocks
        mock_collection = Mock()
        mock_doc_ref = Mock()
        mock_doc_snapshot = Mock()
        mock_doc_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_doc_snapshot
        mock_collection.document.return_value = mock_doc_ref
        mock_get_collection.return_value = mock_collection
        
        # Test
        character_id = str(uuid.uuid4())
        turn_id = "nonexistent"
        result = get_narrative_turn_by_id(character_id, turn_id)
        
        # Verify
        assert result is None
    
    @patch('app.firestore.get_narrative_turns_collection')
    def test_count_narrative_turns(self, mock_get_collection):
        """Test counting narrative turns using Firestore aggregation."""
        from app.firestore import count_narrative_turns
        
        # Setup mocks
        mock_collection = Mock()
        mock_count_query = Mock()
        mock_collection.count.return_value = mock_count_query
        
        # Mock the aggregation result structure
        # Firestore returns [[AggregationResult]] where AggregationResult has a value attribute
        mock_agg_result = Mock()
        mock_agg_result.value = 5
        mock_count_query.get.return_value = [[mock_agg_result]]
        
        mock_get_collection.return_value = mock_collection
        
        # Test
        character_id = str(uuid.uuid4())
        result = count_narrative_turns(character_id)
        
        # Verify
        assert result == 5
        mock_collection.count.assert_called_once()
        mock_count_query.get.assert_called_once()
    
    @patch('app.firestore.get_narrative_turns_collection')
    def test_count_narrative_turns_empty(self, mock_get_collection):
        """Test counting narrative turns for character with no turns."""
        from app.firestore import count_narrative_turns
        
        # Setup mocks
        mock_collection = Mock()
        mock_count_query = Mock()
        mock_collection.count.return_value = mock_count_query
        
        # Mock the aggregation result for empty collection
        mock_agg_result = Mock()
        mock_agg_result.value = 0
        mock_count_query.get.return_value = [[mock_agg_result]]
        
        mock_get_collection.return_value = mock_collection
        
        # Test
        character_id = str(uuid.uuid4())
        result = count_narrative_turns(character_id)
        
        # Verify
        assert result == 0


class TestNarrativeTurnEdgeCases:
    """Test edge cases for narrative turns."""
    
    def test_empty_user_action_invalid(self):
        """Test that empty user_action is invalid."""
        with pytest.raises(ValidationError):
            NarrativeTurn(
                turn_id=str(uuid.uuid4()),
                user_action="",
                ai_response="Response",
                timestamp=datetime.now(timezone.utc)
            )
    
    def test_empty_ai_response_invalid(self):
        """Test that empty ai_response is invalid."""
        with pytest.raises(ValidationError):
            NarrativeTurn(
                turn_id=str(uuid.uuid4()),
                user_action="Action",
                ai_response="",
                timestamp=datetime.now(timezone.utc)
            )
    
    def test_narrative_turn_serialization_preserves_limits(self):
        """Test that serialization preserves field lengths at limits."""
        user_action = "A" * 8000
        ai_response = "B" * 32000
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            user_action=user_action,
            ai_response=ai_response,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Serialize and check
        data = narrative_turn_to_firestore(turn)
        assert len(data["player_action"]) == 8000
        assert len(data["gm_response"]) == 32000
    
    def test_timestamp_in_future_accepted(self):
        """Test that future timestamps are accepted (as per edge case docs)."""
        future_time = datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            user_action="Action",
            ai_response="Response",
            timestamp=future_time
        )
        assert turn.timestamp == future_time
    
    def test_timestamp_in_past_accepted(self):
        """Test that past timestamps are accepted (for backfilling)."""
        past_time = datetime(2000, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        turn = NarrativeTurn(
            turn_id=str(uuid.uuid4()),
            user_action="Action",
            ai_response="Response",
            timestamp=past_time
        )
        assert turn.timestamp == past_time
