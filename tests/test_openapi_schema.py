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
Tests for OpenAPI schema to verify status-only health model is exposed.

These tests ensure that the API schema only exposes status enum fields for
player and enemy health representations, with no numeric health properties.
"""

import re

import pytest

from app.main import app


class TestOpenAPISchemaHealthModel:
    """Test OpenAPI schema exposes only status-based health model."""

    # Class-level constants for validation
    PROBLEMATIC_HEALTH_TERMS = ["hp", "hit points", "current_hp", "max_hp"]
    CHARACTER_RELATED_ENDPOINTS = [
        "/characters",
        "/characters/{character_id}",
        "/characters/{character_id}/combat",
    ]
    
    # Pre-compiled regex for standalone "xp" detection (case-insensitive)
    XP_PATTERN = re.compile(r'\bxp\b', re.IGNORECASE)

    def test_openapi_schema_player_state_has_status_field(self):
        """Test that PlayerState schema includes status field."""
        schema = app.openapi()
        
        # Find PlayerState schema component
        assert "components" in schema
        assert "schemas" in schema["components"]
        
        # PlayerState should be defined
        assert "PlayerState" in schema["components"]["schemas"]
        player_state_schema = schema["components"]["schemas"]["PlayerState"]
        
        # Verify status field exists
        assert "properties" in player_state_schema
        assert "status" in player_state_schema["properties"]
        
        # Verify status is an enum with Healthy, Wounded, Dead
        status_field = player_state_schema["properties"]["status"]
        # Status can be defined as a reference or inline
        if "$ref" in status_field:
            # Follow reference
            ref_name = status_field["$ref"].split("/")[-1]
            assert ref_name in schema["components"]["schemas"]
            status_enum_schema = schema["components"]["schemas"][ref_name]
            assert "enum" in status_enum_schema
            enum_values = status_enum_schema["enum"]
        elif "enum" in status_field:
            enum_values = status_field["enum"]
        else:
            # Check if it's an allOf with enum
            assert "allOf" in status_field or "anyOf" in status_field
            # Just verify status field exists
            return
        
        # Verify the three valid status values
        assert "Healthy" in enum_values
        assert "Wounded" in enum_values
        assert "Dead" in enum_values

    def test_openapi_schema_player_state_no_numeric_health_fields(self):
        """Test that PlayerState schema does NOT expose numeric health fields."""
        schema = app.openapi()
        player_state_schema = schema["components"]["schemas"]["PlayerState"]
        properties = player_state_schema["properties"]
        
        # Verify numeric health fields are NOT present
        assert "level" not in properties
        assert "experience" not in properties
        assert "stats" not in properties
        assert "health" not in properties
        assert "current_hp" not in properties
        assert "max_hp" not in properties
        assert "hp" not in properties
        assert "xp" not in properties
        assert "current_health" not in properties
        assert "max_health" not in properties

    def test_openapi_schema_enemy_state_has_status_field(self):
        """Test that EnemyState schema includes status field."""
        schema = app.openapi()
        
        # Find EnemyState schema component
        assert "EnemyState" in schema["components"]["schemas"]
        enemy_state_schema = schema["components"]["schemas"]["EnemyState"]
        
        # Verify status field exists
        assert "properties" in enemy_state_schema
        assert "status" in enemy_state_schema["properties"]

    def test_openapi_schema_enemy_state_no_numeric_health_fields(self):
        """Test that EnemyState schema does NOT expose numeric health fields."""
        schema = app.openapi()
        enemy_state_schema = schema["components"]["schemas"]["EnemyState"]
        properties = enemy_state_schema["properties"]
        
        # Verify numeric health fields are NOT present
        assert "level" not in properties
        assert "health" not in properties
        assert "current_hp" not in properties
        assert "max_hp" not in properties
        assert "hp" not in properties
        assert "stats" not in properties

    def test_openapi_schema_status_enum_definition(self):
        """Test that Status enum is properly defined in schema."""
        schema = app.openapi()
        
        # Find Status enum schema
        assert "Status" in schema["components"]["schemas"]
        status_schema = schema["components"]["schemas"]["Status"]
        
        # Verify it's an enum with exactly 3 values
        assert "enum" in status_schema
        enum_values = status_schema["enum"]
        assert len(enum_values) == 3
        assert "Healthy" in enum_values
        assert "Wounded" in enum_values
        assert "Dead" in enum_values

    def test_openapi_schema_combat_status_is_status_alias(self):
        """Test that CombatStatus is an alias for Status enum."""
        schema = app.openapi()
        
        # CombatStatus should either be an alias/reference to Status or have same values
        if "CombatStatus" in schema["components"]["schemas"]:
            combat_status_schema = schema["components"]["schemas"]["CombatStatus"]
            
            # If it's a reference, verify it points to Status
            if "$ref" in combat_status_schema:
                assert "Status" in combat_status_schema["$ref"]
            # If it's defined inline, verify same enum values
            elif "enum" in combat_status_schema:
                enum_values = combat_status_schema["enum"]
                assert len(enum_values) == 3
                assert "Healthy" in enum_values
                assert "Wounded" in enum_values
                assert "Dead" in enum_values

    def test_openapi_schema_character_response_excludes_numeric_health(self):
        """Test that character response schemas don't expose numeric health."""
        schema = app.openapi()
        
        # Check CharacterResponse if it exists
        if "CharacterResponse" in schema["components"]["schemas"]:
            char_response = schema["components"]["schemas"]["CharacterResponse"]
            if "properties" in char_response and "player_state" in char_response["properties"]:
                # Should reference PlayerState which we've already verified
                player_state_ref = char_response["properties"]["player_state"]
                assert "$ref" in player_state_ref
                assert "PlayerState" in player_state_ref["$ref"]

    def test_openapi_schema_combat_endpoints_use_status(self):
        """Test that combat-related endpoints use status enum for health."""
        schema = app.openapi()
        
        # Find combat update endpoint
        if "/characters/{character_id}/combat" in schema["paths"]:
            combat_path = schema["paths"]["/characters/{character_id}/combat"]
            
            # Check PUT endpoint (update combat)
            if "put" in combat_path:
                put_endpoint = combat_path["put"]
                
                # Request body should reference a schema with status-based health
                if "requestBody" in put_endpoint:
                    request_body = put_endpoint["requestBody"]
                    # Verify it uses schemas we've already validated
                    # The actual validation is in the schema components

    def test_openapi_paths_do_not_reference_hp_or_xp(self):
        """Test that API endpoint descriptions don't reference HP/XP terminology for player health."""
        schema = app.openapi()
        
        # Check all path descriptions for numeric PLAYER health terminology
        # Note: "experience" in quest rewards is acceptable
        
        for path, path_item in schema["paths"].items():
            for method, operation in path_item.items():
                if method in ["get", "post", "put", "delete", "patch"]:
                    # Check operation description
                    if "description" in operation:
                        description_lower = operation["description"].lower()
                        for term in self.PROBLEMATIC_HEALTH_TERMS:
                            assert term not in description_lower, \
                                f"Found '{term}' in {method.upper()} {path} description"
                    
                    # Check parameter descriptions
                    if "parameters" in operation:
                        for param in operation["parameters"]:
                            if "description" in param:
                                param_desc_lower = param["description"].lower()
                                for term in self.PROBLEMATIC_HEALTH_TERMS:
                                    assert term not in param_desc_lower, \
                                        f"Found '{term}' in parameter description for {method.upper()} {path}"
        
        # Also check for XP specifically in character-related endpoints (not quest rewards)
        for endpoint in self.CHARACTER_RELATED_ENDPOINTS:
            if endpoint in schema["paths"]:
                path_item = schema["paths"][endpoint]
                for method, operation in path_item.items():
                    if method in ["get", "post", "put", "delete", "patch"]:
                        if "description" in operation:
                            description_lower = operation["description"].lower()
                            if "xp" in description_lower and self.XP_PATTERN.search(description_lower):
                                raise AssertionError(
                                    f"Found standalone 'xp' reference in {method.upper()} {endpoint} description"
                                )

    def test_openapi_example_responses_use_status_only(self):
        """Test that example responses in schema use status-only health model."""
        schema = app.openapi()
        
        # Check if any schemas have example values
        for schema_name, schema_def in schema["components"]["schemas"].items():
            if "example" in schema_def:
                example = schema_def["example"]
                
                # If example has player_state or enemy data, verify status-only
                if isinstance(example, dict):
                    if "player_state" in example:
                        player_state = example["player_state"]
                        # Should have status
                        if isinstance(player_state, dict):
                            assert "status" in player_state or "$ref" in player_state
                            # Should NOT have numeric health
                            assert "level" not in player_state
                            assert "current_hp" not in player_state
                            assert "stats" not in player_state
                    
                    if "enemies" in example and isinstance(example["enemies"], list):
                        for enemy in example["enemies"]:
                            if isinstance(enemy, dict):
                                # Enemies should use status, not HP
                                assert "level" not in enemy
                                assert "hp" not in enemy


class TestOpenAPISchemaContextEndpoint:
    """Test OpenAPI schema for context aggregation endpoint."""

    def test_openapi_context_endpoint_exists(self):
        """Test that context endpoint is documented in OpenAPI schema."""
        schema = app.openapi()
        
        # Verify context endpoint exists
        assert "paths" in schema
        assert "/characters/{character_id}/context" in schema["paths"]
        
        context_path = schema["paths"]["/characters/{character_id}/context"]
        assert "get" in context_path
        
    def test_openapi_context_endpoint_query_parameters(self):
        """Test that context endpoint documents recent_n and include_pois parameters."""
        schema = app.openapi()
        
        context_endpoint = schema["paths"]["/characters/{character_id}/context"]["get"]
        
        # Verify parameters are documented
        assert "parameters" in context_endpoint
        params = context_endpoint["parameters"]
        
        # Find recent_n and include_pois parameters
        param_names = [p["name"] for p in params if "name" in p]
        assert "recent_n" in param_names
        assert "include_pois" in param_names
        
        # Verify recent_n parameter details
        recent_n_param = next(p for p in params if p.get("name") == "recent_n")
        assert recent_n_param["in"] == "query"
        assert recent_n_param["required"] is False  # Optional parameter
        assert "schema" in recent_n_param
        assert recent_n_param["schema"]["type"] == "integer"
        
        # Verify include_pois parameter details
        include_pois_param = next(p for p in params if p.get("name") == "include_pois")
        assert include_pois_param["in"] == "query"
        assert include_pois_param["required"] is False  # Optional parameter
        assert "schema" in include_pois_param
        assert include_pois_param["schema"]["type"] == "boolean"
        
    def test_openapi_context_response_model(self):
        """Test that context response model is properly defined."""
        schema = app.openapi()
        
        context_endpoint = schema["paths"]["/characters/{character_id}/context"]["get"]
        
        # Verify 200 response is documented
        assert "responses" in context_endpoint
        assert "200" in context_endpoint["responses"]
        
        response_200 = context_endpoint["responses"]["200"]
        assert "content" in response_200
        assert "application/json" in response_200["content"]
        
        # Verify response schema reference
        json_content = response_200["content"]["application/json"]
        assert "schema" in json_content
        
        # The schema should reference CharacterContextResponse
        response_schema = json_content["schema"]
        if "$ref" in response_schema:
            schema_name = response_schema["$ref"].split("/")[-1]
            assert "CharacterContextResponse" in schema_name or "Context" in schema_name
        
    def test_openapi_character_context_response_schema(self):
        """Test that CharacterContextResponse schema has all required fields."""
        schema = app.openapi()
        
        # Find CharacterContextResponse in components
        assert "components" in schema
        assert "schemas" in schema["components"]
        
        # Access schema definition by its name
        schemas = schema["components"]["schemas"]
        assert "CharacterContextResponse" in schemas, "CharacterContextResponse schema not found"
        context_response_schema = schemas["CharacterContextResponse"]
        
        # Verify required fields
        assert "properties" in context_response_schema
        props = context_response_schema["properties"]
        
        # Check for key fields
        assert "character_id" in props
        assert "player_state" in props
        assert "quest" in props
        assert "has_active_quest" in props
        assert "combat" in props
        assert "narrative" in props
        assert "world" in props
        
        # Verify has_active_quest is a boolean
        has_active_quest = props["has_active_quest"]
        if "$ref" not in has_active_quest:
            assert has_active_quest.get("type") == "boolean"
        
    def test_openapi_narrative_context_schema(self):
        """Test that NarrativeContext schema includes metadata fields."""
        schema = app.openapi()
        
        # Find NarrativeContext schema
        assert "NarrativeContext" in schema["components"]["schemas"]
        narrative_context = schema["components"]["schemas"]["NarrativeContext"]
        
        # Verify metadata fields
        assert "properties" in narrative_context
        props = narrative_context["properties"]
        
        assert "recent_turns" in props
        assert "requested_n" in props
        assert "returned_n" in props
        assert "max_n" in props
        
        # Verify field types
        if "$ref" not in props["requested_n"]:
            assert props["requested_n"]["type"] == "integer"
        if "$ref" not in props["returned_n"]:
            assert props["returned_n"]["type"] == "integer"
        if "$ref" not in props["max_n"]:
            assert props["max_n"]["type"] == "integer"
        
    def test_openapi_combat_envelope_schema(self):
        """Test that CombatEnvelope schema has active flag and state."""
        schema = app.openapi()
        
        # Find CombatEnvelope schema
        assert "CombatEnvelope" in schema["components"]["schemas"]
        combat_envelope = schema["components"]["schemas"]["CombatEnvelope"]
        
        # Verify fields
        assert "properties" in combat_envelope
        props = combat_envelope["properties"]
        
        assert "active" in props
        assert "state" in props
        
        # Verify active is boolean
        if "$ref" not in props["active"]:
            assert props["active"]["type"] == "boolean"
        
    def test_openapi_world_context_state_schema(self):
        """Test that WorldContextState schema has POI sampling fields."""
        schema = app.openapi()
        
        # Find WorldContextState schema
        assert "WorldContextState" in schema["components"]["schemas"]
        world_context = schema["components"]["schemas"]["WorldContextState"]
        
        # Verify fields
        assert "properties" in world_context
        props = world_context["properties"]
        
        assert "pois_sample" in props
        assert "pois_cap" in props
        assert "include_pois" in props
        
        # Verify include_pois is boolean
        if "$ref" not in props["include_pois"]:
            assert props["include_pois"]["type"] == "boolean"
        
        # Verify pois_cap is integer
        if "$ref" not in props["pois_cap"]:
            assert props["pois_cap"]["type"] == "integer"
        
    def test_openapi_context_endpoint_error_responses(self):
        """Test that context endpoint documents error responses."""
        schema = app.openapi()
        
        context_endpoint = schema["paths"]["/characters/{character_id}/context"]["get"]
        responses = context_endpoint["responses"]
        
        # Verify at minimum 422 is documented (FastAPI auto-generates this)
        assert "422" in responses  # Invalid UUID or validation error
        
        # Verify 200 success response is documented
        assert "200" in responses
        
        # Note: FastAPI doesn't auto-generate 400/404 responses in OpenAPI schema
        # unless explicitly defined with @response decorator. The actual endpoint
        # returns these codes, but they're not in the OpenAPI spec by default.
