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
Comprehensive serialization round-trip tests for Journey Log models.

This module validates that CharacterDocument, NarrativeTurn, and PointOfInterest
instances can be serialized to Firestore-compatible dictionaries and deserialized
back to equivalent model instances without data loss.

The tests ensure:
- All required fields survive serialization
- Optional fields (None/missing) are handled correctly
- Timestamps preserve timezone information (UTC)
- Schema versions are maintained
- Arrays (empty and populated) round-trip correctly
- Complex nested structures remain intact

To extend these tests when schemas evolve:
1. Add new fixture methods for the new schema variations
2. Add corresponding round-trip test methods
3. Test both forward compatibility (old -> new) and backward compatibility (new -> old)
4. Document schema changes in docs/SCHEMA.md

See docs/SCHEMA.md for the canonical schema definition.
"""

from datetime import datetime, timezone, timedelta
import pytest
from unittest.mock import Mock

from app.models import (
    CharacterDocument,
    CharacterIdentity,
    CombatState,
    EnemyState,
    Health,
    InventoryItem,
    NarrativeTurn,
    PlayerState,
    PointOfInterestSubcollection,
    Quest,
    QuestRewards,
    Status,
    Weapon,
    # Serialization helpers
    character_from_firestore,
    character_to_firestore,
    narrative_turn_from_firestore,
    narrative_turn_to_firestore,
    poi_from_firestore,
    poi_to_firestore,
)


# ==============================================================================
# Fixtures: CharacterDocument Test Data
# ==============================================================================


@pytest.fixture
def base_player_state():
    """Create a basic PlayerState for use in character fixtures."""
    return PlayerState(
        identity=CharacterIdentity(
            name="Test Hero",
            race="Human",
            **{"class": "Warrior"}
        ),
        status=Status.HEALTHY,
        level=5,
        experience=1000,
        health=Health(current=80, max=100),
        stats={
            "strength": 16,
            "dexterity": 12,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 11,
            "charisma": 13
        },
        equipment=[
            Weapon(name="Iron Sword", damage="1d8", special_effects="Sharp blade"),
            Weapon(name="Wooden Shield", damage=2)
        ],
        inventory=[
            InventoryItem(name="Healing Potion", quantity=3, effect="Restores 50 HP"),
            InventoryItem(name="Rope", quantity=1)
        ],
        location="Village Square",
        additional_fields={"custom_stat": "test_value"}
    )


@pytest.fixture
def character_healthy(base_player_state):
    """Fixture: Healthy character with no quest or combat."""
    return CharacterDocument(
        character_id="char-healthy-001",
        owner_user_id="user_001",
        adventure_prompt="Begin your journey as a brave hero seeking glory and adventure",
        player_state=base_player_state,
        world_pois_reference="world-v1",
        narrative_turns_reference="narrative_turns",
        schema_version="1.0.0",
        created_at=datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        active_quest=None,
        combat_state=None,
        additional_metadata={
            "character_name": "Test Hero",
            "tags": ["test", "fixture"]
        }
    )


@pytest.fixture
def character_wounded_with_quest(base_player_state):
    """Fixture: Wounded character with an in-progress quest."""
    # Create a new PlayerState to avoid mutating the shared fixture
    player_state = PlayerState(
        identity=base_player_state.identity,
        status=Status.WOUNDED,
        level=base_player_state.level,
        experience=base_player_state.experience,
        health=Health(current=30, max=100),
        stats=base_player_state.stats,
        equipment=base_player_state.equipment,
        inventory=base_player_state.inventory,
        location=base_player_state.location,
        additional_fields=base_player_state.additional_fields
    )
    
    quest = Quest(
        name="Defeat the Dragon",
        description="Slay the dragon terrorizing the village",
        requirements=[
            "Find the dragon's lair",
            "Defeat the dragon",
            "Collect dragon scale"
        ],
        rewards=QuestRewards(
            items=["Dragon Slayer Sword"],
            currency={"gold": 500},
            experience=1000
        ),
        completion_state="in_progress",
        updated_at=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
    )
    
    return CharacterDocument(
        character_id="char-wounded-002",
        owner_user_id="user_002",
        adventure_prompt="Wounded but not defeated, continue the quest to slay the dragon",
        player_state=player_state,
        world_pois_reference="world-v1",
        narrative_turns_reference="narrative_turns",
        schema_version="1.0.0",
        created_at=datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc),
        active_quest=quest,
        combat_state=None,
        additional_metadata={"character_name": "Wounded Hero"}
    )


@pytest.fixture
def character_in_combat_multiple_enemies(base_player_state):
    """Fixture: Character in combat with multiple enemies."""
    enemy1 = EnemyState(
        enemy_id="orc_001",
        name="Orc Warrior",
        status=Status.WOUNDED,
        weapon="Rusty Axe",
        traits=["poisoned", "weakened"]
    )
    
    enemy2 = EnemyState(
        enemy_id="orc_002",
        name="Orc Archer",
        status=Status.HEALTHY,
        weapon="Short Bow",
        traits=["ranged"]
    )
    
    enemy3 = EnemyState(
        enemy_id="orc_boss",
        name="Orc Chieftain",
        status=Status.WOUNDED,
        weapon="Great Sword",
        traits=["enraged", "leader"]
    )
    
    combat = CombatState(
        combat_id="combat_123",
        started_at=datetime(2026, 1, 11, 14, 30, 0, tzinfo=timezone.utc),
        turn=5,
        enemies=[enemy1, enemy2, enemy3],
        player_conditions={
            "status_effects": ["blessed", "haste"],
            "temporary_buffs": ["shield_of_valor", "warrior's_fury"]
        }
    )
    
    return CharacterDocument(
        character_id="char-combat-003",
        owner_user_id="user_003",
        adventure_prompt="Fight your way through waves of enemies in an epic battle",
        player_state=base_player_state,
        world_pois_reference="world-v1",
        narrative_turns_reference="narrative_turns",
        schema_version="1.0.0",
        created_at=datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 11, 14, 30, 0, tzinfo=timezone.utc),
        active_quest=None,
        combat_state=combat,
        additional_metadata={"character_name": "Battle Hero"}
    )


@pytest.fixture
def character_dead_completed_quest(base_player_state):
    """Fixture: Dead character with completed quest."""
    base_player_state.status = Status.DEAD
    base_player_state.health = Health(current=0, max=100)
    
    quest = Quest(
        name="Retrieve the Artifact",
        description="Find the ancient artifact in the ruins",
        requirements=[
            "Visit Ancient Ruins",
            "Find the artifact"
        ],
        rewards=QuestRewards(
            items=["Ancient Artifact"],
            currency={},
            experience=500
        ),
        completion_state="completed",
        updated_at=datetime(2026, 1, 11, 18, 0, 0, tzinfo=timezone.utc)
    )
    
    return CharacterDocument(
        character_id="char-dead-004",
        owner_user_id="user_004",
        adventure_prompt="A heroic quest that ended in tragedy but not in vain",
        player_state=base_player_state,
        world_pois_reference="world-v1",
        narrative_turns_reference="narrative_turns",
        schema_version="1.0.0",
        created_at=datetime(2026, 1, 9, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 11, 18, 0, 0, tzinfo=timezone.utc),
        active_quest=quest,
        combat_state=None,
        additional_metadata={"character_name": "Fallen Hero", "death_timestamp": "2026-01-11T18:00:00Z"}
    )


@pytest.fixture
def character_empty_arrays():
    """Fixture: Character with explicitly empty arrays."""
    player_state = PlayerState(
        identity=CharacterIdentity(name="Empty", race="Elf", **{"class": "Mage"}),
        status=Status.HEALTHY,
        health=Health(current=50, max=50),
        stats={},
        equipment=[],
        inventory=[],
        location="Nowhere"
    )
    
    quest = Quest(
        name="Empty Quest",
        description="A quest with no requirements",
        requirements=[],
        rewards=QuestRewards(items=[], currency={}, experience=None),
        completion_state="not_started",
        updated_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc)
    )
    
    return CharacterDocument(
        character_id="char-empty-005",
        owner_user_id="user_005",
        adventure_prompt="Start fresh with no equipment or objectives",
        player_state=player_state,
        world_pois_reference="world-v1",
        narrative_turns_reference="narrative_turns",
        schema_version="1.0.0",
        created_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
        active_quest=quest,
        combat_state=None,
        additional_metadata={}
    )


@pytest.fixture
def character_future_schema():
    """Fixture: Character with a future schema version (for testing compatibility)."""
    player_state = PlayerState(
        identity=CharacterIdentity(name="Future", race="Android", **{"class": "Hacker"}),
        status=Status.HEALTHY,
        health=Health(current=100, max=100),
        stats={"cyber": 20},
        location="Cyberspace"
    )
    
    return CharacterDocument(
        character_id="char-future-006",
        owner_user_id="user_006",
        adventure_prompt="Hack the system and break the simulation",
        player_state=player_state,
        world_pois_reference="world-v2",
        narrative_turns_reference="narrative_turns",
        schema_version="2.0.0",  # Future schema version
        created_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
        active_quest=None,
        combat_state=None,
        additional_metadata={"future_field": "test"}
    )


# ==============================================================================
# Fixtures: NarrativeTurn Test Data
# ==============================================================================


@pytest.fixture
def narrative_turn_basic():
    """Fixture: Basic narrative turn with minimal fields."""
    return NarrativeTurn(
        turn_id="turn_001",
        turn_number=1,
        player_action="I draw my sword",
        gm_response="You draw your sword, the blade gleams in the moonlight",
        timestamp=datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
    )


@pytest.fixture
def narrative_turn_with_metadata():
    """Fixture: Narrative turn with full metadata."""
    return NarrativeTurn(
        turn_id="turn_002",
        turn_number=10,
        player_action="I attempt to negotiate with the dragon",
        gm_response="The dragon considers your words carefully, smoke curling from its nostrils",
        timestamp=datetime(2026, 1, 11, 14, 30, 0, tzinfo=timezone.utc),
        game_state_snapshot={
            "location": "Dragon's Lair",
            "health": 75,
            "active_effects": ["intimidation"],
            "nearby_npcs": ["Dragon", "Kobold Minion"]
        },
        metadata={
            "response_time_ms": 1850,
            "llm_model": "gpt-5.1",
            "tokens_used": 245,
            "temperature": 0.7,
            "dice_rolls": [{"type": "d20", "result": 18, "modifier": 3}]
        }
    )


@pytest.fixture
def narrative_turn_no_turn_number():
    """Fixture: Narrative turn without optional turn_number."""
    return NarrativeTurn(
        turn_id="turn_003",
        player_action="I rest at the campfire",
        gm_response="You settle in for the night, the fire crackling softly",
        timestamp=datetime(2026, 1, 11, 20, 0, 0, tzinfo=timezone.utc),
        game_state_snapshot={"location": "Forest Clearing", "time": "night"}
    )


@pytest.fixture
def narrative_turn_different_timezone():
    """Fixture: Narrative turn with non-UTC timezone that should convert to UTC."""
    # Create a timestamp with +5 hours offset
    tz_offset = timezone(timedelta(hours=5))
    return NarrativeTurn(
        turn_id="turn_004",
        turn_number=15,
        player_action="I wake up at dawn",
        gm_response="The sun rises over the eastern mountains",
        timestamp=datetime(2026, 1, 12, 11, 0, 0, tzinfo=tz_offset)  # 11am +5 = 6am UTC
    )


# ==============================================================================
# Fixtures: PointOfInterest Test Data
# ==============================================================================


@pytest.fixture
def poi_minimal():
    """Fixture: Minimal POI with required fields only."""
    return PointOfInterestSubcollection(
        poi_id="poi_001",
        name="Hidden Cave",
        description="A dark cave entrance behind a waterfall"
    )


@pytest.fixture
def poi_full_details():
    """Fixture: POI with all optional fields populated."""
    return PointOfInterestSubcollection(
        poi_id="poi_002",
        name="Dragon's Lair",
        description="A massive cave system filled with treasure and danger",
        type="dungeon",
        location={
            "world": "middle-earth",
            "region": "lonely-mountain",
            "coordinates": {"x": 250, "y": 300, "z": 50}
        },
        timestamp_discovered=datetime(2026, 1, 10, 15, 30, 0, tzinfo=timezone.utc),
        last_visited=datetime(2026, 1, 11, 14, 30, 0, tzinfo=timezone.utc),
        visited=True,
        notes="Found magical artifact here. Beware of dragon!",
        metadata={
            "difficulty": "very_hard",
            "recommended_level": 15,
            "rewards": ["Dragon Hoard", "Ancient Tome"],
            "quest_related": True,
            "quest_id": "quest_001"
        }
    )


@pytest.fixture
def poi_discovered_not_visited():
    """Fixture: POI that has been discovered but not yet visited."""
    return PointOfInterestSubcollection(
        poi_id="poi_003",
        name="Ancient Ruins",
        description="Crumbling stone structures from a lost civilization",
        type="ruins",
        timestamp_discovered=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
        visited=False,
        notes="Looks interesting, should explore later"
    )


@pytest.fixture
def poi_visited_no_discovery_time():
    """Fixture: POI marked as visited but no discovery timestamp (edge case)."""
    return PointOfInterestSubcollection(
        poi_id="poi_004",
        name="Village Inn",
        description="A cozy inn with warm beds and hot meals",
        type="town",
        visited=True,
        last_visited=datetime(2026, 1, 11, 18, 0, 0, tzinfo=timezone.utc)
    )


# ==============================================================================
# CharacterDocument Round-Trip Tests
# ==============================================================================


class TestCharacterDocumentRoundTrip:
    """Test CharacterDocument serialization round-trips."""
    
    def test_healthy_character_roundtrip(self, character_healthy):
        """Test round-trip for healthy character with no quest or combat."""
        # Serialize
        data = character_to_firestore(character_healthy)
        
        # Verify serialization included expected fields
        assert data['character_id'] == 'char-healthy-001'
        assert data['schema_version'] == '1.0.0'
        assert 'active_quest' not in data  # None values excluded
        assert 'combat_state' not in data  # None values excluded
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify all core fields match
        assert restored.character_id == character_healthy.character_id
        assert restored.owner_user_id == character_healthy.owner_user_id
        assert restored.schema_version == character_healthy.schema_version
        assert restored.world_pois_reference == character_healthy.world_pois_reference
        assert restored.narrative_turns_reference == character_healthy.narrative_turns_reference
        assert restored.created_at == character_healthy.created_at
        assert restored.updated_at == character_healthy.updated_at
        assert restored.active_quest is None
        assert restored.combat_state is None
        
        # Verify player state identity
        assert restored.player_state.identity.name == character_healthy.player_state.identity.name
        assert restored.player_state.identity.race == character_healthy.player_state.identity.race
        assert restored.player_state.identity.character_class == character_healthy.player_state.identity.character_class
        
        # Verify player state core attributes
        assert restored.player_state.status == character_healthy.player_state.status
        assert restored.player_state.level == character_healthy.player_state.level
        assert restored.player_state.experience == character_healthy.player_state.experience
        assert restored.player_state.health.current == character_healthy.player_state.health.current
        assert restored.player_state.health.max == character_healthy.player_state.health.max
        assert restored.player_state.location == character_healthy.player_state.location
        
        # Verify stats dictionary
        assert restored.player_state.stats == character_healthy.player_state.stats
        
        # Verify equipment array
        assert len(restored.player_state.equipment) == len(character_healthy.player_state.equipment)
        for i, equipment in enumerate(restored.player_state.equipment):
            orig_equipment = character_healthy.player_state.equipment[i]
            assert equipment.name == orig_equipment.name
            assert equipment.damage == orig_equipment.damage
            assert equipment.special_effects == orig_equipment.special_effects
        
        # Verify inventory array
        assert len(restored.player_state.inventory) == len(character_healthy.player_state.inventory)
        for i, item in enumerate(restored.player_state.inventory):
            orig_item = character_healthy.player_state.inventory[i]
            assert item.name == orig_item.name
            assert item.quantity == orig_item.quantity
            assert item.effect == orig_item.effect
        
        # Verify additional fields and metadata
        assert restored.player_state.additional_fields == character_healthy.player_state.additional_fields
        assert restored.additional_metadata == character_healthy.additional_metadata
    
    def test_wounded_character_with_quest_roundtrip(self, character_wounded_with_quest):
        """Test round-trip for wounded character with in-progress quest."""
        # Serialize
        data = character_to_firestore(character_wounded_with_quest)
        
        # Verify quest is included
        assert 'active_quest' in data
        assert data['active_quest']['name'] == 'Defeat the Dragon'
        assert data['active_quest']['completion_state'] == 'in_progress'
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify character state
        assert restored.character_id == character_wounded_with_quest.character_id
        assert restored.player_state.status == Status.WOUNDED
        assert restored.player_state.health.current == 30
        
        # Verify quest details
        assert restored.active_quest is not None
        assert restored.active_quest.name == character_wounded_with_quest.active_quest.name
        assert restored.active_quest.completion_state == "in_progress"
        assert len(restored.active_quest.requirements) == 3
        assert len(restored.active_quest.rewards.items) == 1
        
        # Verify quest timestamp
        assert restored.active_quest.updated_at == character_wounded_with_quest.active_quest.updated_at
    
    def test_character_in_combat_multiple_enemies_roundtrip(self, character_in_combat_multiple_enemies):
        """Test round-trip for character in combat with multiple enemies."""
        # Serialize
        data = character_to_firestore(character_in_combat_multiple_enemies)
        
        # Verify combat state is included
        assert 'combat_state' in data
        assert len(data['combat_state']['enemies']) == 3
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify combat state
        assert restored.combat_state is not None
        assert restored.combat_state.combat_id == character_in_combat_multiple_enemies.combat_state.combat_id
        assert restored.combat_state.turn == 5
        assert len(restored.combat_state.enemies) == 3
        
        # Verify enemy details
        enemy1 = restored.combat_state.enemies[0]
        assert enemy1.enemy_id == "orc_001"
        assert enemy1.name == "Orc Warrior"
        assert enemy1.status == Status.WOUNDED
        assert enemy1.weapon == "Rusty Axe"
        assert len(enemy1.traits) == 2
        assert "poisoned" in enemy1.traits
        
        # Verify combat timestamp
        assert restored.combat_state.started_at == character_in_combat_multiple_enemies.combat_state.started_at
        
        # Verify player conditions
        assert restored.combat_state.player_conditions is not None
        assert len(restored.combat_state.player_conditions['status_effects']) == 2
        assert "blessed" in restored.combat_state.player_conditions['status_effects']
    
    def test_dead_character_completed_quest_roundtrip(self, character_dead_completed_quest):
        """Test round-trip for dead character with completed quest."""
        # Serialize
        data = character_to_firestore(character_dead_completed_quest)
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify character is dead
        assert restored.player_state.status == Status.DEAD
        assert restored.player_state.health.current == 0
        
        # Verify quest is completed
        assert restored.active_quest is not None
        assert restored.active_quest.completion_state == "completed"
    
    def test_character_empty_arrays_roundtrip(self, character_empty_arrays):
        """Test round-trip for character with empty arrays."""
        # Serialize
        data = character_to_firestore(character_empty_arrays)
        
        # Verify empty arrays are included in serialization
        assert 'player_state' in data
        assert 'equipment' in data['player_state']
        assert data['player_state']['equipment'] == []
        assert 'inventory' in data['player_state']
        assert data['player_state']['inventory'] == []
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify empty arrays survive round-trip
        assert restored.player_state.equipment == []
        assert restored.player_state.inventory == []
        assert restored.active_quest is not None
        assert restored.active_quest.requirements == []
        assert restored.active_quest.rewards.items == []
        assert restored.active_quest.rewards.currency == {}
    
    def test_character_future_schema_version_roundtrip(self, character_future_schema):
        """Test round-trip for character with future schema version."""
        # Serialize
        data = character_to_firestore(character_future_schema)
        
        # Verify future schema version is preserved
        assert data['schema_version'] == '2.0.0'
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify schema version survives round-trip
        assert restored.schema_version == '2.0.0'
        assert restored.character_id == character_future_schema.character_id
        assert restored.world_pois_reference == "world-v2"
    
    def test_character_equipment_and_inventory_roundtrip(self, character_healthy):
        """Test that equipment and inventory items round-trip correctly."""
        # Serialize
        data = character_to_firestore(character_healthy)
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify equipment
        assert len(restored.player_state.equipment) == 2
        assert restored.player_state.equipment[0].name == "Iron Sword"
        assert restored.player_state.equipment[0].damage == "1d8"
        assert restored.player_state.equipment[0].special_effects == "Sharp blade"
        assert restored.player_state.equipment[1].name == "Wooden Shield"
        assert restored.player_state.equipment[1].special_effects is None
        
        # Verify inventory
        assert len(restored.player_state.inventory) == 2
        assert restored.player_state.inventory[0].name == "Healing Potion"
        assert restored.player_state.inventory[0].quantity == 3
        assert restored.player_state.inventory[0].effect == "Restores 50 HP"
        assert restored.player_state.inventory[1].quantity == 1
    
    def test_character_additional_metadata_roundtrip(self, character_healthy):
        """Test that additional_metadata survives round-trip."""
        # Serialize
        data = character_to_firestore(character_healthy)
        
        # Deserialize
        restored = character_from_firestore(data)
        
        # Verify additional_metadata
        assert restored.additional_metadata['character_name'] == "Test Hero"
        assert "test" in restored.additional_metadata['tags']
        assert "fixture" in restored.additional_metadata['tags']


# ==============================================================================
# NarrativeTurn Round-Trip Tests
# ==============================================================================


class TestNarrativeTurnRoundTrip:
    """Test NarrativeTurn serialization round-trips."""
    
    def test_basic_narrative_turn_roundtrip(self, narrative_turn_basic):
        """Test round-trip for basic narrative turn."""
        # Serialize
        data = narrative_turn_to_firestore(narrative_turn_basic)
        
        # Verify aliases are used
        assert 'player_action' in data
        assert 'gm_response' in data
        
        # Deserialize
        restored = narrative_turn_from_firestore(data)
        
        # Verify all fields match
        assert restored.turn_id == narrative_turn_basic.turn_id
        assert restored.turn_number == narrative_turn_basic.turn_number
        assert restored.user_action == narrative_turn_basic.user_action
        assert restored.ai_response == narrative_turn_basic.ai_response
        assert restored.timestamp == narrative_turn_basic.timestamp
    
    def test_narrative_turn_with_metadata_roundtrip(self, narrative_turn_with_metadata):
        """Test round-trip for narrative turn with full metadata."""
        # Serialize
        data = narrative_turn_to_firestore(narrative_turn_with_metadata)
        
        # Deserialize
        restored = narrative_turn_from_firestore(data)
        
        # Verify main fields
        assert restored.turn_id == narrative_turn_with_metadata.turn_id
        assert restored.turn_number == narrative_turn_with_metadata.turn_number
        
        # Verify game_state_snapshot
        assert restored.game_state_snapshot is not None
        assert restored.game_state_snapshot['location'] == "Dragon's Lair"
        assert restored.game_state_snapshot['health'] == 75
        assert "intimidation" in restored.game_state_snapshot['active_effects']
        
        # Verify metadata
        assert restored.metadata is not None
        assert restored.metadata['llm_model'] == "gpt-5.1"
        assert restored.metadata['tokens_used'] == 245
        assert restored.metadata['response_time_ms'] == 1850
    
    def test_narrative_turn_no_turn_number_roundtrip(self, narrative_turn_no_turn_number):
        """Test round-trip for narrative turn without turn_number."""
        # Serialize
        data = narrative_turn_to_firestore(narrative_turn_no_turn_number)
        
        # Verify turn_number is not in serialized data (None excluded)
        assert 'turn_number' not in data
        
        # Deserialize
        restored = narrative_turn_from_firestore(data)
        
        # Verify turn_number is None
        assert restored.turn_number is None
        assert restored.turn_id == narrative_turn_no_turn_number.turn_id
        assert restored.game_state_snapshot is not None
    
    def test_narrative_turn_timestamp_preservation(self, narrative_turn_basic):
        """Test that timestamps preserve timezone information (UTC)."""
        # Serialize
        data = narrative_turn_to_firestore(narrative_turn_basic)
        
        # Deserialize
        restored = narrative_turn_from_firestore(data)
        
        # Verify timestamp is timezone-aware and in UTC
        assert restored.timestamp.tzinfo is not None
        assert restored.timestamp.tzinfo == timezone.utc
        assert restored.timestamp == narrative_turn_basic.timestamp
    
    def test_narrative_turn_timezone_conversion(self, narrative_turn_different_timezone):
        """Test that non-UTC timezones are converted to UTC during round-trip."""
        # Original timestamp is 11am +5 = 6am UTC
        original_utc = narrative_turn_different_timezone.timestamp.astimezone(timezone.utc)
        
        # Serialize
        data = narrative_turn_to_firestore(narrative_turn_different_timezone)
        
        # Deserialize
        restored = narrative_turn_from_firestore(data)
        
        # Verify timestamp is in UTC and represents the same moment in time
        assert restored.timestamp.tzinfo == timezone.utc
        assert restored.timestamp == original_utc
        assert restored.timestamp.hour == 6  # 11am +5 = 6am UTC


# ==============================================================================
# PointOfInterest Round-Trip Tests
# ==============================================================================


class TestPointOfInterestRoundTrip:
    """Test PointOfInterest serialization round-trips."""
    
    def test_minimal_poi_roundtrip(self, poi_minimal):
        """Test round-trip for minimal POI with only required fields."""
        # Serialize
        data = poi_to_firestore(poi_minimal)
        
        # Verify only required fields are present
        assert 'poi_id' in data
        assert 'name' in data
        assert 'description' in data
        assert 'type' not in data  # Optional, None excluded
        assert 'timestamp_discovered' not in data  # Optional, None excluded
        
        # Deserialize
        restored = poi_from_firestore(data)
        
        # Verify all fields match
        assert restored.poi_id == poi_minimal.poi_id
        assert restored.name == poi_minimal.name
        assert restored.description == poi_minimal.description
        assert restored.type is None
        assert restored.timestamp_discovered is None
        assert restored.last_visited is None
        assert restored.visited is False
        assert restored.notes is None
    
    def test_full_poi_roundtrip(self, poi_full_details):
        """Test round-trip for POI with all fields populated."""
        # Serialize
        data = poi_to_firestore(poi_full_details)
        
        # Deserialize
        restored = poi_from_firestore(data)
        
        # Verify all fields match
        assert restored.poi_id == poi_full_details.poi_id
        assert restored.name == poi_full_details.name
        assert restored.description == poi_full_details.description
        assert restored.type == poi_full_details.type
        assert restored.visited == poi_full_details.visited
        assert restored.notes == poi_full_details.notes
        
        # Verify location structure
        assert restored.location is not None
        assert restored.location['world'] == "middle-earth"
        assert restored.location['region'] == "lonely-mountain"
        assert restored.location['coordinates']['x'] == 250
        
        # Verify timestamps
        assert restored.timestamp_discovered == poi_full_details.timestamp_discovered
        assert restored.last_visited == poi_full_details.last_visited
        
        # Verify metadata
        assert restored.metadata is not None
        assert restored.metadata['difficulty'] == "very_hard"
        assert restored.metadata['recommended_level'] == 15
    
    def test_poi_discovered_not_visited_roundtrip(self, poi_discovered_not_visited):
        """Test round-trip for POI that is discovered but not visited."""
        # Serialize
        data = poi_to_firestore(poi_discovered_not_visited)
        
        # Deserialize
        restored = poi_from_firestore(data)
        
        # Verify discovery and visit status
        assert restored.timestamp_discovered is not None
        assert restored.timestamp_discovered == poi_discovered_not_visited.timestamp_discovered
        assert restored.visited is False
        assert restored.last_visited is None
        assert restored.notes == "Looks interesting, should explore later"
    
    def test_poi_visited_no_discovery_time_roundtrip(self, poi_visited_no_discovery_time):
        """Test round-trip for POI marked as visited without discovery timestamp."""
        # Serialize
        data = poi_to_firestore(poi_visited_no_discovery_time)
        
        # Deserialize
        restored = poi_from_firestore(data)
        
        # Verify edge case handling
        assert restored.visited is True
        assert restored.last_visited is not None
        assert restored.timestamp_discovered is None  # Edge case: visited but no discovery time
    
    def test_poi_timestamp_preservation(self, poi_full_details):
        """Test that POI timestamps preserve timezone information."""
        # Serialize
        data = poi_to_firestore(poi_full_details)
        
        # Deserialize
        restored = poi_from_firestore(data)
        
        # Verify timestamps are timezone-aware and in UTC
        assert restored.timestamp_discovered.tzinfo is not None
        assert restored.timestamp_discovered.tzinfo == timezone.utc
        assert restored.last_visited.tzinfo is not None
        assert restored.last_visited.tzinfo == timezone.utc


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestRoundTripEdgeCases:
    """Test edge cases in serialization round-trips."""
    
    def test_empty_vs_none_arrays(self):
        """Verify that empty arrays are preserved, not treated as None."""
        player_state = PlayerState(
            identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
            status=Status.HEALTHY,
            health=Health(current=100, max=100),
            stats={},
            equipment=[],  # Empty array
            inventory=[],  # Empty array
            location="test"
        )
        
        char = CharacterDocument(
            character_id="test-id",
            owner_user_id="user_001",
            adventure_prompt="Test empty arrays",
            player_state=player_state,
            world_pois_reference="world",
            narrative_turns_reference="narrative_turns",
            schema_version="1.0.0",
            created_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc)
        )
        
        # Round-trip
        data = character_to_firestore(char)
        restored = character_from_firestore(data)
        
        # Empty arrays should be preserved
        assert restored.player_state.equipment == []
        assert restored.player_state.inventory == []
        assert restored.player_state.equipment is not None
    
    def test_schema_version_increment_handling(self):
        """Test handling of different schema versions."""
        versions_to_test = ["1.0.0", "1.1.0", "2.0.0", "10.5.3"]
        
        for version in versions_to_test:
            player_state = PlayerState(
                identity=CharacterIdentity(name="Test", race="Human", **{"class": "Warrior"}),
                status=Status.HEALTHY,
                health=Health(current=100, max=100),
                stats={},
                location="test"
            )
            
            char = CharacterDocument(
                character_id=f"test-{version}",
                owner_user_id="user_001",
                adventure_prompt="Test schema version handling",
                player_state=player_state,
                world_pois_reference="world",
                narrative_turns_reference="narrative_turns",
                schema_version=version,
                created_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 11, 10, 0, 0, tzinfo=timezone.utc)
            )
            
            # Round-trip
            data = character_to_firestore(char)
            restored = character_from_firestore(data)
            
            # Schema version should be preserved exactly
            assert restored.schema_version == version
    
    def test_timestamp_timezone_aware_equality(self):
        """Test that timestamps with different timezone representations are equal."""
        # Create same moment in time with different timezone representations
        utc_time = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        offset_time = datetime(2026, 1, 11, 17, 0, 0, tzinfo=timezone(timedelta(hours=5)))
        
        # Create two identical turns with different timezone representations
        turn_utc = NarrativeTurn(
            turn_id="turn_utc",
            player_action="test",
            gm_response="test",
            timestamp=utc_time
        )
        
        turn_offset = NarrativeTurn(
            turn_id="turn_offset",
            player_action="test",
            gm_response="test",
            timestamp=offset_time
        )
        
        # Round-trip both
        data_utc = narrative_turn_to_firestore(turn_utc)
        data_offset = narrative_turn_to_firestore(turn_offset)
        
        restored_utc = narrative_turn_from_firestore(data_utc)
        restored_offset = narrative_turn_from_firestore(data_offset)
        
        # Both should be in UTC and equal
        assert restored_utc.timestamp.tzinfo == timezone.utc
        assert restored_offset.timestamp.tzinfo == timezone.utc
        assert restored_utc.timestamp == restored_offset.timestamp
    
    def test_multiple_entries_in_arrays(self, character_in_combat_multiple_enemies):
        """Test that arrays with multiple entries round-trip correctly."""
        # Round-trip
        data = character_to_firestore(character_in_combat_multiple_enemies)
        restored = character_from_firestore(data)
        
        # Verify multiple enemies
        assert len(restored.combat_state.enemies) == 3
        assert all(isinstance(enemy, EnemyState) for enemy in restored.combat_state.enemies)
        
        # Verify each enemy's traits array (replacing old status_effects)
        assert len(restored.combat_state.enemies[0].traits) == 2
        assert len(restored.combat_state.enemies[1].traits) == 1
        assert len(restored.combat_state.enemies[2].traits) == 2
    
    def test_narrative_turn_ordering_metadata(self):
        """Test that turn_number metadata is preserved for ordering."""
        turns = []
        for i in range(5):
            turn = NarrativeTurn(
                turn_id=f"turn_{i:03d}",
                turn_number=i + 1,
                player_action=f"Action {i+1}",
                gm_response=f"Response {i+1}",
                timestamp=datetime(2026, 1, 11, 12, i, 0, tzinfo=timezone.utc)
            )
            turns.append(turn)
        
        # Round-trip all turns
        for turn in turns:
            data = narrative_turn_to_firestore(turn)
            restored = narrative_turn_from_firestore(data)
            
            # Verify turn_number is preserved for ordering
            assert restored.turn_number == turn.turn_number
            
            # Verify timestamp is preserved for time-based ordering
            assert restored.timestamp == turn.timestamp
    
    def test_firestore_timestamp_mock_roundtrip(self):
        """Test round-trip with mocked Firestore Timestamp objects."""
        # Create a mock Firestore Timestamp
        mock_timestamp = Mock()
        dt = datetime(2026, 1, 11, 12, 0, 0, tzinfo=timezone.utc)
        mock_timestamp.to_datetime.return_value = dt
        
        # Create data dict with Firestore Timestamp
        data = {
            'turn_id': 'turn_mock',
            'player_action': 'test',
            'gm_response': 'test',
            'timestamp': mock_timestamp
        }
        
        # Deserialize
        restored = narrative_turn_from_firestore(data)
        
        # Verify timestamp was converted correctly
        assert restored.timestamp == dt
        assert restored.timestamp.tzinfo == timezone.utc
        mock_timestamp.to_datetime.assert_called_once()
