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
Journey Log API Service

A FastAPI-based service for managing journey logs.
"""

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

__version__ = "0.1.0"

__all__ = [
    "CharacterDocument",
    "CharacterIdentity",
    "CombatState",
    "CombatStatus",
    "CompletionState",
    "Enemy",
    "InventoryItem",
    "NarrativeTurn",
    "PlayerState",
    "PointOfInterest",
    "Quest",
    "QuestRequirement",
    "QuestReward",
    "Status",
    "Weapon",
]
