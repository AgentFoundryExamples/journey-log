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
Unit tests for Pydantic models.

Tests validation, serialization, and edge cases for all character state models.
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models import (
    CharacterDocument,
    CharacterIdentity,
    CombatState,
    CombatStatus,
    CompletionState,
    Enemy,
    InventoryItem,
    NarrativeTurn,
    PlayerState,
    PointOfInterest,
    Quest,
    QuestRequirement,
    QuestReward,
    Status,
    Weapon,
)


class TestEnums:
    """Test enum validation."""
    
    def test_status_enum_values(self):
        """Test Status enum has correct values."""
        assert Status.HEALTHY.value == "Healthy"
        assert Status.WOUNDED.value == "Wounded"
        assert Status.DEAD.value == "Dead"
    
    def test_combat_status_enum_values(self):
        """Test CombatStatus enum has correct values."""
        assert CombatStatus.HEALTHY.value == "Healthy"
        assert CombatStatus.WOUNDED.value == "Wounded"
        assert CombatStatus.DEAD.value == "Dead"
    
    def test_completion_state_enum_values(self):
        """Test CompletionState enum has correct values."""
        assert CompletionState.NOT_STARTED.value == "NotStarted"
        assert CompletionState.IN_PROGRESS.value == "InProgress"
        assert CompletionState.COMPLETED.value == "Completed"
    
    def test_invalid_status_raises_error(self):
        """Test that invalid status values raise ValidationError."""
        with pytest.raises(ValidationError):
            PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status="InvalidStatus",
                health={"current": 100, "max": 100},
                stats={},
                location="test"
            )


class TestCharacterIdentity:
    """Test CharacterIdentity model."""
    
    def test_create_character_identity(self):
        """Test creating a valid CharacterIdentity."""
        identity = CharacterIdentity(
            name="Aragorn",
            race="Human",
            **{"class": "Ranger"}
        )
        assert identity.name == "Aragorn"
        assert identity.race == "Human"
        assert identity.character_class == "Ranger"
    
    def test_character_identity_forbids_extra_fields(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            CharacterIdentity(
                name="Aragorn",
                race="Human",
                **{"class": "Ranger"},
                extra_field="should fail"
            )


class TestWeapon:
    """Test Weapon model."""
    
    def test_weapon_with_string_special_effects(self):
        """Test weapon with simple string special effects."""
        weapon = Weapon(
            name="Anduril",
            damage="2d6",
            special_effects="Glows blue near enemies"
        )
        assert weapon.name == "Anduril"
        assert weapon.special_effects == "Glows blue near enemies"
    
    def test_weapon_with_dict_special_effects(self):
        """Test weapon with structured dict special effects."""
        weapon = Weapon(
            name="Flame Sword",
            damage=10,
            special_effects={"fire_damage": 5, "burn_chance": 0.3}
        )
        assert isinstance(weapon.special_effects, dict)
        assert weapon.special_effects["fire_damage"] == 5
    
    def test_weapon_without_special_effects(self):
        """Test weapon without special effects."""
        weapon = Weapon(name="Iron Sword", damage=5)
        assert weapon.special_effects is None


class TestInventoryItem:
    """Test InventoryItem model."""
    
    def test_inventory_item_with_string_effect(self):
        """Test item with string effect."""
        item = InventoryItem(
            name="Healing Potion",
            quantity=3,
            effect="Restores 50 HP"
        )
        assert item.name == "Healing Potion"
        assert item.quantity == 3
        assert item.effect == "Restores 50 HP"
    
    def test_inventory_item_with_dict_effect(self):
        """Test item with structured dict effect."""
        item = InventoryItem(
            name="Magic Ring",
            effect={"stat_bonus": {"wisdom": 2}, "passive": "invisible"}
        )
        assert isinstance(item.effect, dict)
        assert item.effect["stat_bonus"]["wisdom"] == 2
    
    def test_inventory_item_defaults(self):
        """Test item with default values."""
        item = InventoryItem(name="Rope")
        assert item.quantity == 1
        assert item.effect is None


class TestPlayerState:
    """Test PlayerState model."""
    
    def test_create_player_state(self):
        """Test creating a valid PlayerState."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Frodo", race="Hobbit", **{"class": "Burglar"}),
            status=Status.HEALTHY,
            level=5,
            experience=1000,
            health={"current": 80, "max": 100},
            stats={"strength": 10, "dexterity": 18},
            equipment=[],
            inventory=[],
            location="Rivendell",
            additional_fields={}
        )
        assert player_state.identity.name == "Frodo"
        assert player_state.status == Status.HEALTHY
        assert player_state.level == 5
    
    def test_player_state_with_location_dict(self):
        """Test PlayerState with structured location."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location={"world": "middle-earth", "region": "gondor", "coordinates": {"x": 100, "y": 200}}
        )
        assert isinstance(player_state.location, dict)
        assert player_state.location["world"] == "middle-earth"
    
    def test_player_state_empty_equipment_inventory(self):
        """Test PlayerState with empty equipment and inventory."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test"
        )
        assert player_state.equipment == []
        assert player_state.inventory == []
    
    def test_player_state_with_additional_fields(self):
        """Test PlayerState with additional_fields."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test",
            additional_fields={"custom_stat": "value"}
        )
        assert player_state.additional_fields["custom_stat"] == "value"


class TestNarrativeTurn:
    """Test NarrativeTurn model."""
    
    def test_create_narrative_turn_with_datetime(self):
        """Test creating a NarrativeTurn with datetime."""
        turn = NarrativeTurn(
            turn_id="turn_001",
            turn_number=1,
            player_action="I draw my sword",
            gm_response="You draw your sword",
            timestamp=datetime.now(timezone.utc)
        )
        assert turn.turn_id == "turn_001"
        assert isinstance(turn.timestamp, datetime)
    
    def test_create_narrative_turn_with_string_timestamp(self):
        """Test creating a NarrativeTurn with ISO string timestamp."""
        turn = NarrativeTurn(
            turn_id="turn_002",
            player_action="I approach the door",
            gm_response="The door creaks open",
            timestamp="2026-01-11T12:00:00Z"
        )
        assert turn.timestamp == "2026-01-11T12:00:00Z"
    
    def test_narrative_turn_with_metadata(self):
        """Test NarrativeTurn with optional metadata."""
        turn = NarrativeTurn(
            turn_id="turn_003",
            player_action="test",
            gm_response="test",
            timestamp="2026-01-11T12:00:00Z",
            game_state_snapshot={"location": "Cave", "health": 100},
            metadata={"response_time_ms": 1250, "llm_model": "gpt-5.1"}
        )
        assert turn.metadata["llm_model"] == "gpt-5.1"


class TestPointOfInterest:
    """Test PointOfInterest model."""
    
    def test_create_poi(self):
        """Test creating a PointOfInterest."""
        poi = PointOfInterest(
            poi_id="poi_123",
            name="Hidden Temple",
            description="An ancient temple"
        )
        assert poi.id == "poi_123"
        assert poi.name == "Hidden Temple"
    
    def test_poi_with_optional_timestamps(self):
        """Test POI with optional timestamp fields."""
        poi = PointOfInterest(
            poi_id="poi_124",
            name="Dragon's Lair",
            description="A dangerous cave",
            discovered_at="2026-01-10T15:30:00Z",
            visited_at="2026-01-10T16:00:00Z",
            visited=True
        )
        assert poi.timestamp_discovered == "2026-01-10T15:30:00Z"
        assert poi.last_visited == "2026-01-10T16:00:00Z"
        assert poi.visited is True


class TestQuestModels:
    """Test Quest-related models."""
    
    def test_quest_requirement_with_string_details(self):
        """Test QuestRequirement with string details."""
        req = QuestRequirement(
            type="kill",
            details="Defeat 10 orcs"
        )
        assert req.type == "kill"
        assert req.details == "Defeat 10 orcs"
    
    def test_quest_requirement_with_dict_details(self):
        """Test QuestRequirement with dict details."""
        req = QuestRequirement(
            type="collect",
            details={"item": "Ancient Artifact", "quantity": 1}
        )
        assert isinstance(req.details, dict)
    
    def test_quest_reward_with_dict_details(self):
        """Test QuestReward with dict details."""
        reward = QuestReward(
            type="item",
            details={"name": "Magic Sword", "rarity": "legendary"}
        )
        assert reward.type == "item"
        assert isinstance(reward.details, dict)
    
    def test_create_quest(self):
        """Test creating a complete Quest."""
        quest = Quest(
            quest_id="quest_001",
            title="Destroy the Ring",
            description="Take the Ring to Mount Doom",
            completion_state=CompletionState.IN_PROGRESS,
            objectives=[
                {"id": "obj_001", "description": "Reach Rivendell", "completed": True}
            ],
            requirements=[
                QuestRequirement(type="visit", details="Mount Doom")
            ],
            rewards=[
                QuestReward(type="experience", details="1000 XP")
            ],
            started_at="2026-01-11T12:00:00Z"
        )
        assert quest.quest_id == "quest_001"
        assert quest.completion_state == CompletionState.IN_PROGRESS
        assert len(quest.objectives) == 1


class TestCombatState:
    """Test CombatState model."""
    
    def test_create_combat_state(self):
        """Test creating a CombatState."""
        enemy = Enemy(
            enemy_id="orc_001",
            name="Orc Warrior",
            health={"current": 25, "max": 50},
            status_effects=["poisoned"]
        )
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            turn=3,
            enemies=[enemy]
        )
        assert combat.combat_id == "combat_123"
        assert len(combat.enemies) == 1
        assert combat.turn == 3
    
    def test_combat_is_active_property(self):
        """Test is_active property for active combat."""
        enemy = Enemy(
            enemy_id="orc_001",
            name="Orc Warrior",
            health={"current": 25, "max": 50},
            status_effects=[]
        )
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            enemies=[enemy]
        )
        assert combat.is_active is True
    
    def test_combat_is_not_active_with_dead_enemies(self):
        """Test is_active property when all enemies are dead."""
        enemy = Enemy(
            enemy_id="orc_001",
            name="Orc Warrior",
            health={"current": 0, "max": 50},
            status_effects=[]
        )
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            enemies=[enemy]
        )
        assert combat.is_active is False


class TestCharacterDocument:
    """Test CharacterDocument aggregate model."""
    
    def test_create_character_document(self):
        """Test creating a complete CharacterDocument."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Aragorn", race="Human", **{"class": "Ranger"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={"strength": 18},
            location="Rivendell"
        )
        
        doc = CharacterDocument(
            character_id="550e8400-e29b-41d4-a716-446655440000",
            owner_user_id="user_123",
            player_state=player_state,
            world_pois_reference="middle-earth-v1",
            schema_version=1,
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            additional_metadata={"character_name": "Aragorn"}
        )
        
        assert doc.character_id == "550e8400-e29b-41d4-a716-446655440000"
        assert doc.owner_user_id == "user_123"
        assert doc.schema_version == 1
        assert doc.player_state.identity.name == "Aragorn"
    
    def test_character_document_optional_fields_none(self):
        """Test CharacterDocument with optional fields as None."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test"
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            player_state=player_state,
            world_pois_reference="world",
            schema_version=1,
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            active_quest=None,
            combat_state=None
        )
        
        assert doc.active_quest is None
        assert doc.combat_state is None
    
    def test_character_document_with_active_quest(self):
        """Test CharacterDocument with active quest."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test"
        )
        
        quest = Quest(
            quest_id="quest_001",
            title="Test Quest",
            description="A test quest",
            completion_state=CompletionState.IN_PROGRESS
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            player_state=player_state,
            world_pois_reference="world",
            schema_version=1,
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            active_quest=quest
        )
        
        assert doc.active_quest is not None
        assert doc.active_quest.quest_id == "quest_001"
    
    def test_character_document_with_combat_state(self):
        """Test CharacterDocument with active combat."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test"
        )
        
        enemy = Enemy(
            enemy_id="enemy_001",
            name="Test Enemy",
            health={"current": 50, "max": 50},
            status_effects=[]
        )
        
        combat = CombatState(
            combat_id="combat_001",
            started_at="2026-01-11T14:30:00Z",
            enemies=[enemy]
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            player_state=player_state,
            world_pois_reference="world",
            schema_version=1,
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            combat_state=combat
        )
        
        assert doc.combat_state is not None
        assert doc.combat_state.combat_id == "combat_001"
    
    def test_character_document_additional_metadata(self):
        """Test CharacterDocument with additional_metadata."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test"
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            player_state=player_state,
            world_pois_reference="world",
            schema_version=1,
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            additional_metadata={
                "character_name": "Test Character",
                "tags": ["test", "demo"],
                "custom_field": "custom_value"
            }
        )
        
        assert doc.additional_metadata["character_name"] == "Test Character"
        assert "test" in doc.additional_metadata["tags"]
    
    def test_character_document_forbids_extra_fields(self):
        """Test that CharacterDocument forbids extra fields."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test"
        )
        
        with pytest.raises(ValidationError):
            CharacterDocument(
                character_id="test-id",
                owner_user_id="user_123",
                player_state=player_state,
                world_pois_reference="world",
                schema_version=1,
                created_at="2026-01-11T12:00:00Z",
                updated_at="2026-01-11T12:00:00Z",
                extra_forbidden_field="should fail"
            )


class TestEdgeCases:
    """Test edge cases and validation errors."""
    
    def test_enum_validation_clear_error(self):
        """Test that invalid enum values produce clear errors."""
        with pytest.raises(ValidationError) as exc_info:
            Quest(
                quest_id="test",
                title="Test",
                description="Test",
                completion_state="InvalidState"
            )
        
        # Verify the error message mentions the invalid value
        assert "InvalidState" in str(exc_info.value)
    
    def test_empty_equipment_list_allowed(self):
        """Test that empty equipment list is allowed."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test",
            equipment=[]
        )
        assert player_state.equipment == []
    
    def test_additional_metadata_arbitrary_keys(self):
        """Test that additional_metadata accepts arbitrary keys."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health={"current": 100, "max": 100},
            stats={},
            location="test",
            additional_fields={
                "key1": "value1",
                "key2": 123,
                "key3": {"nested": "data"},
                "key4": ["list", "of", "items"]
            }
        )
        assert player_state.additional_fields["key1"] == "value1"
        assert player_state.additional_fields["key2"] == 123
        assert isinstance(player_state.additional_fields["key3"], dict)
        assert isinstance(player_state.additional_fields["key4"], list)
