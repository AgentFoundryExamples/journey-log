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
Tests for context aggregation contract models and configuration.

Tests the schema/config groundwork for context aggregation endpoint:
- CharacterContextQuery validation
- ContextCapsMetadata structure
- Settings validators for context configuration
- Model serialization/deserialization
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.models import (
    CharacterContextQuery,
    CharacterContextResponse,
    CharacterIdentity,
    CombatEnvelope,
    CombatState,
    ContextCapsMetadata,
    EnemyState,
    Location,
    NarrativeContext,
    NarrativeTurn,
    PlayerState,
    Quest,
    QuestRewards,
    Status,
    WorldContextState,
    PointOfInterest,
)


class TestCharacterContextQuery:
    """Test CharacterContextQuery model validation."""

    def test_default_values(self):
        """Test default values for query parameters."""
        query = CharacterContextQuery()
        assert query.recent_n == 20
        assert query.include_pois is False

    def test_recent_n_min_validation(self):
        """Test recent_n minimum validation (must be >= 1)."""
        with pytest.raises(ValidationError) as exc_info:
            CharacterContextQuery(recent_n=0)
        assert "greater_than_equal" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            CharacterContextQuery(recent_n=-1)
        assert "greater_than_equal" in str(exc_info.value)

    def test_recent_n_valid_values(self):
        """Test recent_n accepts valid values."""
        query = CharacterContextQuery(recent_n=1)
        assert query.recent_n == 1

        query = CharacterContextQuery(recent_n=50)
        assert query.recent_n == 50

        query = CharacterContextQuery(recent_n=100)
        assert query.recent_n == 100

    def test_include_pois_values(self):
        """Test include_pois accepts boolean values."""
        query = CharacterContextQuery(include_pois=True)
        assert query.include_pois is True

        query = CharacterContextQuery(include_pois=False)
        assert query.include_pois is False

    def test_extra_fields_forbidden(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError) as exc_info:
            CharacterContextQuery(recent_n=10, extra_field="not allowed")
        assert "extra_forbidden" in str(exc_info.value).lower()


class TestContextCapsMetadata:
    """Test ContextCapsMetadata model structure."""

    def test_create_metadata(self):
        """Test creating metadata with all required fields."""
        metadata = ContextCapsMetadata(
            narrative_max_n=100,
            narrative_requested_n=20,
            pois_cap=3,
            pois_requested=True,
        )
        assert metadata.narrative_max_n == 100
        assert metadata.narrative_requested_n == 20
        assert metadata.pois_cap == 3
        assert metadata.pois_requested is True
        assert metadata.firestore_reads == "1 character doc + 1 narrative query + optional 1 POI query"

    def test_default_firestore_reads(self):
        """Test default firestore_reads field."""
        metadata = ContextCapsMetadata(
            narrative_max_n=100,
            narrative_requested_n=20,
            pois_cap=3,
            pois_requested=False,
        )
        assert "1 character doc" in metadata.firestore_reads
        assert "1 narrative query" in metadata.firestore_reads
        assert "optional 1 POI query" in metadata.firestore_reads

    def test_serialization(self):
        """Test metadata serialization."""
        metadata = ContextCapsMetadata(
            narrative_max_n=100,
            narrative_requested_n=20,
            pois_cap=3,
            pois_requested=True,
        )
        data = metadata.model_dump()
        assert data["narrative_max_n"] == 100
        assert data["narrative_requested_n"] == 20
        assert data["pois_cap"] == 3
        assert data["pois_requested"] is True
        assert "firestore_reads" in data


class TestNarrativeContext:
    """Test NarrativeContext model structure."""

    def test_create_empty_narrative(self):
        """Test creating narrative context with no turns."""
        narrative = NarrativeContext(
            turns=[],
            requested_n=20,
            max_n=100,
        )
        assert narrative.turns == []
        assert narrative.requested_n == 20
        assert narrative.max_n == 100

    def test_create_with_turns(self):
        """Test creating narrative context with turns."""
        turns = [
            NarrativeTurn(
                turn_id="turn1",
                user_action="test action",
                ai_response="test response",
                timestamp=datetime.now(timezone.utc),
            )
        ]
        narrative = NarrativeContext(
            turns=turns,
            requested_n=20,
            max_n=100,
        )
        assert len(narrative.turns) == 1
        assert narrative.requested_n == 20
        assert narrative.max_n == 100

    def test_serialization(self):
        """Test narrative context serialization."""
        narrative = NarrativeContext(
            turns=[],
            requested_n=20,
            max_n=100,
        )
        data = narrative.model_dump()
        assert data["turns"] == []
        assert data["requested_n"] == 20
        assert data["max_n"] == 100


class TestWorldContextState:
    """Test WorldContextState model structure."""

    def test_create_empty_world(self):
        """Test creating world context with no POIs."""
        world = WorldContextState(
            pois_sample=[],
            pois_cap=3,
            include_pois=False,
        )
        assert world.pois_sample == []
        assert world.pois_cap == 3
        assert world.include_pois is False

    def test_create_with_pois(self):
        """Test creating world context with POIs."""
        pois = [
            PointOfInterest(
                id="poi1",
                name="Test POI",
                description="A test location",
            )
        ]
        world = WorldContextState(
            pois_sample=pois,
            pois_cap=3,
            include_pois=True,
        )
        assert len(world.pois_sample) == 1
        assert world.pois_cap == 3
        assert world.include_pois is True

    def test_pois_cap_required(self):
        """Test that pois_cap is required."""
        with pytest.raises(ValidationError) as exc_info:
            WorldContextState(
                pois_sample=[],
                include_pois=False,
            )
        assert "pois_cap" in str(exc_info.value).lower()


class TestCombatEnvelope:
    """Test CombatEnvelope model structure."""

    def test_inactive_combat(self):
        """Test inactive combat state."""
        combat = CombatEnvelope(
            active=False,
            state=None,
        )
        assert combat.active is False
        assert combat.state is None

    def test_active_combat(self):
        """Test active combat state."""
        combat_state = CombatState(
            combat_id="combat1",
            started_at=datetime.now(timezone.utc),
            turn=1,
            enemies=[
                EnemyState(
                    enemy_id="enemy1",
                    name="Orc",
                    status=Status.HEALTHY,
                )
            ],
        )
        combat = CombatEnvelope(
            active=True,
            state=combat_state,
        )
        assert combat.active is True
        assert combat.state is not None
        assert combat.state.combat_id == "combat1"


class TestCharacterContextResponse:
    """Test CharacterContextResponse model structure."""

    def test_complete_response(self):
        """Test creating a complete context response."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            location=Location(id="loc1", display_name="Test Location"),
        )
        quest = Quest(
            name="Test Quest",
            description="A test quest",
            requirements=[],
            rewards=QuestRewards(items=[], currency={}, experience=100),
            completion_state="in_progress",
            updated_at=datetime.now(timezone.utc),
        )
        combat = CombatEnvelope(active=False, state=None)
        narrative = NarrativeContext(turns=[], requested_n=20, max_n=100)
        world = WorldContextState(pois_sample=[], pois_cap=3, include_pois=False)
        metadata = ContextCapsMetadata(
            narrative_max_n=100,
            narrative_requested_n=20,
            pois_cap=3,
            pois_requested=False,
        )

        response = CharacterContextResponse(
            character_id="char123",
            player_state=player_state,
            quest=quest,
            has_active_quest=True,
            combat=combat,
            narrative=narrative,
            world=world,
            metadata=metadata,
        )

        assert response.character_id == "char123"
        assert response.has_active_quest is True
        assert response.quest is not None
        assert response.combat.active is False
        assert response.narrative.max_n == 100
        assert response.world.pois_cap == 3
        assert response.metadata.narrative_max_n == 100

    def test_no_quest_response(self):
        """Test response with no active quest."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            location=Location(id="loc1", display_name="Test Location"),
        )
        combat = CombatEnvelope(active=False, state=None)
        narrative = NarrativeContext(turns=[], requested_n=20, max_n=100)
        world = WorldContextState(pois_sample=[], pois_cap=3, include_pois=False)
        metadata = ContextCapsMetadata(
            narrative_max_n=100,
            narrative_requested_n=20,
            pois_cap=3,
            pois_requested=False,
        )

        response = CharacterContextResponse(
            character_id="char123",
            player_state=player_state,
            quest=None,
            has_active_quest=False,
            combat=combat,
            narrative=narrative,
            world=world,
            metadata=metadata,
        )

        assert response.has_active_quest is False
        assert response.quest is None


class TestSettingsValidation:
    """Test Settings model validation for context configuration."""

    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings()
        assert settings.context_recent_n_default == 20
        assert settings.context_recent_n_max == 100
        assert settings.context_poi_cap == 3

    def test_context_defaults_validation(self):
        """Test that context_recent_n_default cannot exceed context_recent_n_max."""
        # When default exceeds the field constraint (le=100), field validation fails first
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                context_recent_n_default=150,
                context_recent_n_max=100,
            )
        assert "less_than_equal" in str(exc_info.value).lower()

        # When default exceeds max but both are within bounds, model validator catches it
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                context_recent_n_default=60,
                context_recent_n_max=50,
            )
        assert "cannot exceed" in str(exc_info.value).lower()

    def test_context_defaults_equal_allowed(self):
        """Test that context_recent_n_default can equal context_recent_n_max."""
        settings = Settings(
            context_recent_n_default=50,
            context_recent_n_max=50,
        )
        assert settings.context_recent_n_default == 50
        assert settings.context_recent_n_max == 50

    def test_context_min_validation(self):
        """Test minimum validation for context settings."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(context_recent_n_default=0)
        assert "greater_than_equal" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Settings(context_recent_n_max=0)
        assert "greater_than_equal" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Settings(context_poi_cap=0)
        assert "greater_than_equal" in str(exc_info.value)

    def test_context_max_validation(self):
        """Test maximum validation for context settings."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(context_recent_n_default=101)
        assert "less_than_equal" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Settings(context_recent_n_max=1001)
        assert "less_than_equal" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            Settings(context_poi_cap=21)
        assert "less_than_equal" in str(exc_info.value)

    def test_custom_context_values(self):
        """Test setting custom context values."""
        settings = Settings(
            context_recent_n_default=30,
            context_recent_n_max=150,
            context_poi_cap=5,
        )
        assert settings.context_recent_n_default == 30
        assert settings.context_recent_n_max == 150
        assert settings.context_poi_cap == 5
