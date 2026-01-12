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
    Enemy,
    EnemyState,
    Health,
    InventoryItem,
    Location,
    NarrativeTurn,
    PlayerState,
    PointOfInterest,
    PointOfInterestSubcollection,
    Quest,
    QuestArchiveEntry,
    QuestRewards,
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
    
    def test_combat_status_is_alias(self):
        """Test that CombatStatus is an alias for Status."""
        assert CombatStatus is Status
    
    def test_invalid_status_raises_error(self):
        """Test that invalid status values raise ValidationError."""
        with pytest.raises(ValidationError):
            PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status="InvalidStatus",
                health=Health(current=100, max=100),
                stats={},
                location="test"
            )


class TestHealth:
    """Test Health model."""
    
    def test_create_valid_health(self):
        """Test creating valid Health."""
        health = Health(current=50, max=100)
        assert health.current == 50
        assert health.max == 100
    
    def test_health_current_equals_max(self):
        """Test Health when current equals max."""
        health = Health(current=100, max=100)
        assert health.current == 100
        assert health.max == 100
    
    def test_health_current_exceeds_max_raises_error(self):
        """Test that current > max raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Health(current=150, max=100)
        assert "current health cannot be greater than max health" in str(exc_info.value)
    
    def test_health_negative_current_raises_error(self):
        """Test that negative current raises ValidationError."""
        with pytest.raises(ValidationError):
            Health(current=-10, max=100)
    
    def test_health_negative_max_raises_error(self):
        """Test that negative max raises ValidationError."""
        with pytest.raises(ValidationError):
            Health(current=50, max=-100)
    
    def test_health_zero_values_allowed(self):
        """Test that zero values are allowed."""
        health = Health(current=0, max=0)
        assert health.current == 0
        assert health.max == 0


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
            health=Health(current=80, max=100),
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
            health=Health(current=100, max=100),
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
            health=Health(current=100, max=100),
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
            health=Health(current=100, max=100),
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
    
    def test_narrative_turn_with_metadata(self):
        """Test NarrativeTurn with optional metadata."""
        turn = NarrativeTurn(
            turn_id="turn_003",
            player_action="test",
            gm_response="test",
            timestamp=datetime.now(timezone.utc),
            game_state_snapshot={"location": "Cave", "health": 100},
            metadata={"response_time_ms": 1250, "llm_model": "gpt-5.1"}
        )
        assert turn.metadata["llm_model"] == "gpt-5.1"


class TestPointOfInterest:
    """Test PointOfInterest model (embedded in character documents)."""
    
    def test_create_poi_minimal(self):
        """Test creating a minimal PointOfInterest."""
        poi = PointOfInterest(
            id="poi_123",
            name="Hidden Temple",
            description="An ancient temple"
        )
        assert poi.id == "poi_123"
        assert poi.name == "Hidden Temple"
        assert poi.description == "An ancient temple"
        assert poi.created_at is None
        assert poi.tags is None
    
    def test_poi_with_all_fields(self):
        """Test POI with all fields populated."""
        created_time = datetime.now(timezone.utc)
        poi = PointOfInterest(
            id="poi_124",
            name="Dragon's Lair",
            description="A dangerous cave",
            created_at=created_time,
            tags=["dungeon", "dangerous", "treasure"]
        )
        assert poi.created_at == created_time
        assert len(poi.tags) == 3
        assert "dungeon" in poi.tags


class TestPointOfInterestSubcollection:
    """Test PointOfInterestSubcollection model (stored in subcollections)."""
    
    def test_create_poi_subcollection(self):
        """Test creating a PointOfInterestSubcollection."""
        poi = PointOfInterestSubcollection(
            poi_id="poi_123",
            name="Hidden Temple",
            description="An ancient temple"
        )
        assert poi.poi_id == "poi_123"
        assert poi.name == "Hidden Temple"
    
    def test_poi_subcollection_with_optional_timestamps(self):
        """Test POI subcollection with optional timestamp fields."""
        poi = PointOfInterestSubcollection(
            poi_id="poi_124",
            name="Dragon's Lair",
            description="A dangerous cave",
            timestamp_discovered=datetime.now(timezone.utc),
            last_visited=datetime.now(timezone.utc),
            visited=True
        )
        assert poi.timestamp_discovered is not None
        assert poi.last_visited is not None
        assert poi.visited is True


class TestQuestModels:
    """Test Quest-related models."""
    
    def test_quest_rewards_with_items(self):
        """Test QuestRewards with items."""
        rewards = QuestRewards(
            items=["Magic Sword", "Health Potion"],
            currency={"gold": 100},
            experience=500
        )
        assert len(rewards.items) == 2
        assert rewards.currency["gold"] == 100
        assert rewards.experience == 500
    
    def test_quest_rewards_empty_arrays_allowed(self):
        """Test that QuestRewards allows empty arrays."""
        rewards = QuestRewards(
            items=[],
            currency={},
            experience=None
        )
        assert rewards.items == []
        assert rewards.currency == {}
        assert rewards.experience is None
    
    def test_quest_rewards_negative_experience_rejected(self):
        """Test that negative experience is rejected."""
        with pytest.raises(ValidationError):
            QuestRewards(
                items=[],
                currency={},
                experience=-100
            )
    
    def test_quest_rewards_negative_currency_rejected(self):
        """Test that negative currency values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QuestRewards(
                items=[],
                currency={"gold": -50},
                experience=0
            )
        assert "cannot be negative" in str(exc_info.value)
    
    def test_quest_rewards_empty_currency_key_rejected(self):
        """Test that empty currency keys are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QuestRewards(
                items=[],
                currency={"": 100},
                experience=0
            )
        assert "cannot be empty" in str(exc_info.value)
    
    def test_create_quest(self):
        """Test creating a complete Quest."""
        from datetime import datetime, timezone
        quest = Quest(
            name="Destroy the Ring",
            description="Take the Ring to Mount Doom",
            requirements=["Reach Rivendell", "Form Fellowship", "Reach Mordor"],
            rewards=QuestRewards(
                items=["Ring of Power"],
                currency={"gold": 1000},
                experience=5000
            ),
            completion_state="in_progress",
            updated_at=datetime.now(timezone.utc)
        )
        assert quest.name == "Destroy the Ring"
        assert quest.completion_state == "in_progress"
        assert len(quest.requirements) == 3
    
    def test_quest_completion_state_validation(self):
        """Test that invalid completion states are rejected."""
        from datetime import datetime, timezone
        with pytest.raises(ValidationError) as exc_info:
            Quest(
                name="Test Quest",
                description="Test",
                requirements=[],
                rewards=QuestRewards(items=[], currency={}),
                completion_state="invalid_state",
                updated_at=datetime.now(timezone.utc)
            )
        # Check for Literal validation error message
        error_str = str(exc_info.value)
        assert "completion_state" in error_str
        assert ("not_started" in error_str or "in_progress" in error_str or "completed" in error_str)
    
    def test_quest_archive_entry(self):
        """Test creating a QuestArchiveEntry."""
        from datetime import datetime, timezone
        quest = Quest(
            name="Completed Quest",
            description="A quest that was completed",
            requirements=["Do something"],
            rewards=QuestRewards(items=[], currency={"gold": 50}),
            completion_state="completed",
            updated_at=datetime.now(timezone.utc)
        )
        cleared_time = datetime.now(timezone.utc)
        entry = QuestArchiveEntry(quest=quest, cleared_at=cleared_time)
        assert entry.quest.name == "Completed Quest"
        assert entry.cleared_at == cleared_time


class TestCombatState:
    """Test CombatState model."""
    
    def test_create_combat_state(self):
        """Test creating a CombatState with new EnemyState schema."""
        enemy = EnemyState(
            enemy_id="orc_001",
            name="Orc Warrior",
            status=Status.WOUNDED,
            weapon="Rusty Axe",
            traits=["aggressive", "armored"]
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
        assert combat.enemies[0].status == Status.WOUNDED
    
    def test_combat_is_active_property(self):
        """Test is_active property for active combat."""
        enemy = EnemyState(
            enemy_id="orc_001",
            name="Orc Warrior",
            status=Status.HEALTHY
        )
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            enemies=[enemy]
        )
        assert combat.is_active is True
    
    def test_combat_is_not_active_with_dead_enemies(self):
        """Test is_active property when all enemies are dead."""
        enemy = EnemyState(
            enemy_id="orc_001",
            name="Orc Warrior",
            status=Status.DEAD
        )
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            enemies=[enemy]
        )
        assert combat.is_active is False
    
    def test_combat_is_not_active_with_empty_enemies(self):
        """Test is_active property when enemies list is empty."""
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            enemies=[]
        )
        assert combat.is_active is False
    
    def test_combat_max_5_enemies_validation(self):
        """Test that combat validates maximum 5 enemies."""
        enemies = [
            EnemyState(enemy_id=f"enemy_{i}", name=f"Enemy {i}", status=Status.HEALTHY)
            for i in range(6)
        ]
        with pytest.raises(ValidationError) as exc_info:
            CombatState(
                combat_id="combat_123",
                started_at="2026-01-11T14:30:00Z",
                enemies=enemies
            )
        assert "more than 5 enemies" in str(exc_info.value).lower()
    
    def test_combat_exactly_5_enemies_allowed(self):
        """Test that exactly 5 enemies is allowed."""
        enemies = [
            EnemyState(enemy_id=f"enemy_{i}", name=f"Enemy {i}", status=Status.HEALTHY)
            for i in range(5)
        ]
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            enemies=enemies
        )
        assert len(combat.enemies) == 5
        assert combat.is_active is True
    
    def test_combat_is_active_with_mixed_statuses(self):
        """Test is_active with mixed enemy statuses."""
        enemies = [
            EnemyState(enemy_id="enemy_1", name="Dead Enemy", status=Status.DEAD),
            EnemyState(enemy_id="enemy_2", name="Alive Enemy", status=Status.WOUNDED),
        ]
        combat = CombatState(
            combat_id="combat_123",
            started_at="2026-01-11T14:30:00Z",
            enemies=enemies
        )
        # Should be active because at least one enemy is not dead
        assert combat.is_active is True


class TestEnemyState:
    """Test EnemyState model."""
    
    def test_create_enemy_state_minimal(self):
        """Test creating an EnemyState with minimal required fields."""
        enemy = EnemyState(
            enemy_id="goblin_001",
            name="Goblin Scout",
            status=Status.HEALTHY
        )
        assert enemy.enemy_id == "goblin_001"
        assert enemy.name == "Goblin Scout"
        assert enemy.status == Status.HEALTHY
        assert enemy.weapon is None
        assert enemy.traits == []
        assert enemy.metadata is None
    
    def test_create_enemy_state_with_all_fields(self):
        """Test creating an EnemyState with all optional fields."""
        enemy = EnemyState(
            enemy_id="dragon_001",
            name="Ancient Red Dragon",
            status=Status.WOUNDED,
            weapon="Flame Breath",
            traits=["flying", "fire_resist", "legendary"],
            metadata={"difficulty": "very_hard", "loot_tier": 5}
        )
        assert enemy.enemy_id == "dragon_001"
        assert enemy.name == "Ancient Red Dragon"
        assert enemy.status == Status.WOUNDED
        assert enemy.weapon == "Flame Breath"
        assert len(enemy.traits) == 3
        assert enemy.metadata["difficulty"] == "very_hard"
    
    def test_enemy_state_status_enum_validation(self):
        """Test that invalid status values are rejected."""
        with pytest.raises(ValidationError):
            EnemyState(
                enemy_id="test_001",
                name="Test Enemy",
                status="Invalid"
            )


class TestCharacterDocument:
    """Test CharacterDocument aggregate model."""
    
    def test_create_character_document(self):
        """Test creating a complete CharacterDocument."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Aragorn", race="Human", **{"class": "Ranger"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={"strength": 18},
            location="Rivendell"
        )
        
        doc = CharacterDocument(
            character_id="550e8400-e29b-41d4-a716-446655440000",
            owner_user_id="user_123",
            adventure_prompt="A ranger from the North seeking to reclaim the throne of Gondor",
            player_state=player_state,
            world_pois_reference="middle-earth-v1",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            additional_metadata={"character_name": "Aragorn"}
        )
        
        assert doc.character_id == "550e8400-e29b-41d4-a716-446655440000"
        assert doc.owner_user_id == "user_123"
        assert doc.adventure_prompt == "A ranger from the North seeking to reclaim the throne of Gondor"
        assert doc.schema_version == "1.0.0"
        assert doc.player_state.identity.name == "Aragorn"
    
    def test_character_document_optional_fields_none(self):
        """Test CharacterDocument with optional fields as None."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="A simple test adventure",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            active_quest=None,
            combat_state=None
        )
        
        assert doc.active_quest is None
        assert doc.combat_state is None
        assert doc.world_state is None
    
    def test_character_document_with_active_quest(self):
        """Test CharacterDocument with active quest."""
        from datetime import datetime, timezone
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        quest = Quest(
            name="Test Quest",
            description="A test quest",
            requirements=["Kill 10 orcs"],
            rewards=QuestRewards(items=[], currency={"gold": 100}),
            completion_state="in_progress",
            updated_at=datetime.now(timezone.utc)
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="Embark on a quest to save the kingdom",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z",
            active_quest=quest
        )
        
        assert doc.active_quest is not None
        assert doc.active_quest.name == "Test Quest"
    
    def test_character_document_with_combat_state(self):
        """Test CharacterDocument with active combat."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        enemy = EnemyState(
            enemy_id="enemy_001",
            name="Test Enemy",
            status=Status.HEALTHY
        )
        
        combat = CombatState(
            combat_id="combat_001",
            started_at="2026-01-11T14:30:00Z",
            enemies=[enemy]
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="Battle your way through the dungeon",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
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
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="An epic adventure awaits",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
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
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        with pytest.raises(ValidationError):
            CharacterDocument(
                character_id="test-id",
                owner_user_id="user_123",
                adventure_prompt="Test adventure",
                player_state=player_state,
                world_pois_reference="world",
                narrative_turns_reference="narrative_turns",
                schema_version="1.0.0",
                created_at="2026-01-11T12:00:00Z",
                updated_at="2026-01-11T12:00:00Z",
                extra_forbidden_field="should fail"
            )
    
    def test_character_document_with_world_pois(self):
        """Test CharacterDocument with embedded world_pois."""
        from datetime import datetime, timezone
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        pois = [
            PointOfInterest(
                id="poi_001",
                name="Hidden Cave",
                description="A mysterious cave",
                created_at=datetime.now(timezone.utc),
                tags=["dungeon", "secret"]
            ),
            PointOfInterest(
                id="poi_002",
                name="Ancient Ruins",
                description="Old ruins",
                tags=["landmark"]
            )
        ]
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="Explore the world",
            player_state=player_state,
            world_pois=pois,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z"
        )
        
        assert len(doc.world_pois) == 2
        assert doc.world_pois[0].name == "Hidden Cave"
        assert len(doc.world_pois[0].tags) == 2
    
    def test_character_document_with_archived_quests(self):
        """Test CharacterDocument with archived quests."""
        from datetime import datetime, timezone
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        archived = [
            QuestArchiveEntry(
                quest=Quest(
                    name="Old Quest",
                    description="Completed quest",
                    requirements=["Defeat boss"],
                    rewards=QuestRewards(items=["Legendary Sword"], currency={"gold": 500}),
                    completion_state="completed",
                    updated_at=datetime.now(timezone.utc)
                ),
                cleared_at=datetime.now(timezone.utc)
            )
        ]
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="Complete many quests",
            player_state=player_state,
            archived_quests=archived,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z"
        )
        
        assert len(doc.archived_quests) == 1
        assert doc.archived_quests[0].quest.name == "Old Quest"
    
    def test_character_document_world_pois_cap_validation(self):
        """Test that world_pois cap (200) is enforced."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        # Create 201 POIs to exceed the cap
        pois = [
            PointOfInterest(
                id=f"poi_{i:03d}",
                name=f"POI {i}",
                description=f"Description {i}"
            )
            for i in range(201)
        ]
        
        with pytest.raises(ValidationError) as exc_info:
            CharacterDocument(
                character_id="test-id",
                owner_user_id="user_123",
                adventure_prompt="Too many POIs",
                player_state=player_state,
                world_pois=pois,
                world_pois_reference="world",
                narrative_turns_reference="narrative_turns",
                schema_version="1.0.0",
                created_at="2026-01-11T12:00:00Z",
                updated_at="2026-01-11T12:00:00Z"
            )
        assert "world_pois cannot exceed 200" in str(exc_info.value)
    
    def test_character_document_archived_quests_cap_validation(self):
        """Test that archived_quests cap (50) is enforced."""
        from datetime import datetime, timezone
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        # Create 51 archived quests to exceed the cap
        archived = [
            QuestArchiveEntry(
                quest=Quest(
                    name=f"Quest {i}",
                    description=f"Quest {i} description",
                    requirements=[],
                    rewards=QuestRewards(items=[], currency={}),
                    completion_state="completed",
                    updated_at=datetime.now(timezone.utc)
                ),
                cleared_at=datetime.now(timezone.utc)
            )
            for i in range(51)
        ]
        
        with pytest.raises(ValidationError) as exc_info:
            CharacterDocument(
                character_id="test-id",
                owner_user_id="user_123",
                adventure_prompt="Too many archived quests",
                player_state=player_state,
                archived_quests=archived,
                world_pois_reference="world",
                narrative_turns_reference="narrative_turns",
                schema_version="1.0.0",
                created_at="2026-01-11T12:00:00Z",
                updated_at="2026-01-11T12:00:00Z"
            )
        assert "archived_quests cannot exceed 50" in str(exc_info.value)


class TestEdgeCases:
    """Test edge cases and validation errors."""
    
    def test_enum_validation_clear_error(self):
        """Test that invalid completion state values produce clear errors."""
        from datetime import datetime, timezone
        with pytest.raises(ValidationError) as exc_info:
            Quest(
                name="Test",
                description="Test",
                requirements=[],
                rewards=QuestRewards(items=[], currency={}),
                completion_state="InvalidState",
                updated_at=datetime.now(timezone.utc)
            )
        
        # Verify the error message mentions the invalid value
        assert "InvalidState" in str(exc_info.value)
    
    def test_empty_equipment_list_allowed(self):
        """Test that empty equipment list is allowed."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
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
            health=Health(current=100, max=100),
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


class TestCharacterIdentityValidation:
    """Test CharacterIdentity validation rules."""
    
    def test_name_length_validation_min(self):
        """Test that name must be at least 1 character."""
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="", race="Human", **{"class": "Warrior"})
        assert "at least 1 character" in str(exc_info.value)
    
    def test_name_length_validation_max(self):
        """Test that name cannot exceed 64 characters."""
        long_name = "A" * 65
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name=long_name, race="Human", **{"class": "Warrior"})
        assert "at most 64 characters" in str(exc_info.value)
    
    def test_race_length_validation_min(self):
        """Test that race must be at least 1 character."""
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="Test", race="", **{"class": "Warrior"})
        assert "at least 1 character" in str(exc_info.value)
    
    def test_race_length_validation_max(self):
        """Test that race cannot exceed 64 characters."""
        long_race = "A" * 65
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="Test", race=long_race, **{"class": "Warrior"})
        assert "at most 64 characters" in str(exc_info.value)
    
    def test_class_length_validation_min(self):
        """Test that class must be at least 1 character."""
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="Test", race="Human", **{"class": ""})
        assert "at least 1 character" in str(exc_info.value)
    
    def test_class_length_validation_max(self):
        """Test that class cannot exceed 64 characters."""
        long_class = "A" * 65
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="Test", race="Human", **{"class": long_class})
        assert "at most 64 characters" in str(exc_info.value)
    
    def test_whitespace_normalization(self):
        """Test that whitespace is normalized in identity fields."""
        identity = CharacterIdentity(
            name="  Test   Hero  ",
            race="  Human  ",
            **{"class": "  Warrior   "}
        )
        assert identity.name == "Test Hero"
        assert identity.race == "Human"
        assert identity.character_class == "Warrior"
    
    def test_whitespace_only_fails_validation(self):
        """Test that whitespace-only fields fail validation after normalization."""
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="   ", race="Human", **{"class": "Warrior"})
        assert "name cannot be empty or only whitespace" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="Test", race="   ", **{"class": "Warrior"})
        assert "race cannot be empty or only whitespace" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            CharacterIdentity(name="Test", race="Human", **{"class": "   "})
        assert "character_class cannot be empty or only whitespace" in str(exc_info.value)
    
    def test_valid_identity_at_bounds(self):
        """Test valid identity fields at boundary lengths."""
        # Single character
        identity = CharacterIdentity(name="A", race="B", **{"class": "C"})
        assert identity.name == "A"
        
        # 64 characters exactly
        name_64 = "A" * 64
        identity = CharacterIdentity(name=name_64, race="Human", **{"class": "Warrior"})
        assert len(identity.name) == 64


class TestAdventurePromptValidation:
    """Test adventure_prompt validation rules."""
    
    def test_adventure_prompt_required(self):
        """Test that adventure_prompt is required."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        with pytest.raises(ValidationError) as exc_info:
            CharacterDocument(
                character_id="test-id",
                owner_user_id="user_123",
                # adventure_prompt missing
                player_state=player_state,
                world_pois_reference="world",
                narrative_turns_reference="narrative_turns",
                schema_version="1.0.0",
                created_at="2026-01-11T12:00:00Z",
                updated_at="2026-01-11T12:00:00Z"
            )
        assert "adventure_prompt" in str(exc_info.value)
    
    def test_adventure_prompt_empty_string(self):
        """Test that adventure_prompt cannot be empty."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        with pytest.raises(ValidationError) as exc_info:
            CharacterDocument(
                character_id="test-id",
                owner_user_id="user_123",
                adventure_prompt="",
                player_state=player_state,
                world_pois_reference="world",
                narrative_turns_reference="narrative_turns",
                schema_version="1.0.0",
                created_at="2026-01-11T12:00:00Z",
                updated_at="2026-01-11T12:00:00Z"
            )
        assert "at least 1 character" in str(exc_info.value)
    
    def test_adventure_prompt_whitespace_only(self):
        """Test that adventure_prompt cannot be only whitespace."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        with pytest.raises(ValidationError) as exc_info:
            CharacterDocument(
                character_id="test-id",
                owner_user_id="user_123",
                adventure_prompt="   ",
                player_state=player_state,
                world_pois_reference="world",
                narrative_turns_reference="narrative_turns",
                schema_version="1.0.0",
                created_at="2026-01-11T12:00:00Z",
                updated_at="2026-01-11T12:00:00Z"
            )
        assert "cannot be empty or only whitespace" in str(exc_info.value)
    
    def test_adventure_prompt_whitespace_normalization(self):
        """Test that adventure_prompt whitespace is normalized."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="  A   brave   warrior   sets   out  ",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z"
        )
        
        assert doc.adventure_prompt == "A brave warrior sets out"
    
    def test_adventure_prompt_valid(self):
        """Test valid adventure_prompt."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="A brave warrior sets out to save the kingdom from darkness",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z"
        )
        
        assert doc.adventure_prompt == "A brave warrior sets out to save the kingdom from darkness"


class TestLocationModel:
    """Test Location model."""
    
    def test_create_location(self):
        """Test creating a Location."""
        location = Location(id="origin:nexus", display_name="The Nexus")
        assert location.id == "origin:nexus"
        assert location.display_name == "The Nexus"
    
    def test_location_forbids_extra_fields(self):
        """Test that Location forbids extra fields."""
        with pytest.raises(ValidationError):
            Location(id="test", display_name="Test", extra_field="should fail")
    
    def test_location_id_empty_fails(self):
        """Test that empty id fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            Location(id="", display_name="Test")
        assert "at least 1 character" in str(exc_info.value)
    
    def test_location_display_name_empty_fails(self):
        """Test that empty display_name fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            Location(id="test", display_name="")
        assert "at least 1 character" in str(exc_info.value)
    
    def test_location_id_whitespace_only_fails(self):
        """Test that whitespace-only id fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            Location(id="   ", display_name="Test")
        assert "id cannot be empty or only whitespace" in str(exc_info.value)
    
    def test_location_display_name_whitespace_only_fails(self):
        """Test that whitespace-only display_name fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            Location(id="test", display_name="   ")
        assert "display_name cannot be empty or only whitespace" in str(exc_info.value)
    
    def test_location_in_player_state(self):
        """Test using Location in PlayerState."""
        location = Location(id="town:rivendell", display_name="Rivendell")
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Elf", **{"class": "Ranger"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location=location
        )
        assert isinstance(player_state.location, Location)
        assert player_state.location.id == "town:rivendell"
        assert player_state.location.display_name == "Rivendell"
    
    def test_location_backward_compatibility_string(self):
        """Test that PlayerState still accepts location as string."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="Test Location"
        )
        assert player_state.location == "Test Location"
    
    def test_location_backward_compatibility_dict(self):
        """Test that PlayerState still accepts location as dict."""
        location_dict = {"world": "middle-earth", "region": "gondor"}
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location=location_dict
        )
        assert player_state.location == location_dict
    
    def test_location_string_empty_fails(self):
        """Test that empty string location fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status=Status.HEALTHY,
                health=Health(current=100, max=100),
                stats={},
                location=""
            )
        assert "location string cannot be empty" in str(exc_info.value)
    
    def test_location_string_whitespace_only_fails(self):
        """Test that whitespace-only string location fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status=Status.HEALTHY,
                health=Health(current=100, max=100),
                stats={},
                location="   "
            )
        assert "location string cannot be empty" in str(exc_info.value)
    
    def test_location_dict_empty_fails(self):
        """Test that empty dict location fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status=Status.HEALTHY,
                health=Health(current=100, max=100),
                stats={},
                location={}
            )
        assert "location dict cannot be empty" in str(exc_info.value)
    
    def test_location_dict_with_id_but_no_display_name_fails(self):
        """Test that location dict with id but no display_name fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status=Status.HEALTHY,
                health=Health(current=100, max=100),
                stats={},
                location={"id": "origin:nexus"}
            )
        assert "must have both non-empty fields" in str(exc_info.value)
    
    def test_location_dict_with_display_name_but_no_id_fails(self):
        """Test that location dict with display_name but no id fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status=Status.HEALTHY,
                health=Health(current=100, max=100),
                stats={},
                location={"display_name": "The Nexus"}
            )
        assert "must have both non-empty fields" in str(exc_info.value)


class TestWorldState:
    """Test world_state field."""
    
    def test_world_state_optional(self):
        """Test that world_state is optional."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="Test adventure",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z"
        )
        
        assert doc.world_state is None
    
    def test_world_state_with_data(self):
        """Test world_state with data."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            location="test"
        )
        
        world_state = {
            "time_of_day": "morning",
            "weather": "sunny",
            "factions": {
                "kingdom": "friendly",
                "orcs": "hostile"
            },
            "global_events": ["dragon_awakened"]
        }
        
        doc = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_123",
            adventure_prompt="Test adventure",
            player_state=player_state,
            world_state=world_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at="2026-01-11T12:00:00Z",
            updated_at="2026-01-11T12:00:00Z"
        )
        
        assert doc.world_state is not None
        assert doc.world_state["time_of_day"] == "morning"
        assert doc.world_state["weather"] == "sunny"
        assert "dragon_awakened" in doc.world_state["global_events"]
