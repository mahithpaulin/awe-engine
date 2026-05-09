"""
Step 5: The Structure Builder (Deterministic Engine)
=====================================================
The StructureBuilder is the final layer of the AWE Engine pipeline.

It receives a validated AIBlueprint and deterministically maps abstract
string identifiers (structure types, NPC roles) to concrete engine prefab
keys. The output is a RenderedChunk — a fully engine-ready object list that
can be sent directly to Unity, Godot, or any other game engine consumer.

This layer contains NO randomness beyond what is seeded by the blueprint's
chunk_seed, ensuring the same blueprint always produces the same world.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from .models import (
    AIBlueprint,
    NPCRole,
    RenderedChunk,
    RenderedObject,
    StructureBlueprint,
    WorldEvent,
    LayoutNode,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prefab registry
# ---------------------------------------------------------------------------

# Maps abstract structure_type keys → engine prefab paths.
# In production these paths would reference real asset bundles.
STRUCTURE_PREFAB_REGISTRY: dict[str, str] = {
    # Forest
    "ancient_tree":         "prefabs/nature/tree_ancient_oak",
    "wooden_shrine":        "prefabs/structures/shrine_wood",
    "campfire":             "prefabs/interactables/campfire_small",
    "log_pile":             "prefabs/props/log_pile_01",
    # Desert
    "desert_obelisk":       "prefabs/structures/obelisk_sandstone",
    "sand_dune_mound":      "prefabs/terrain/dune_mound_large",
    "buried_chest":         "prefabs/interactables/chest_buried",
    "ruined_arch":          "prefabs/ruins/arch_sandstone_crumbled",
    # Tundra
    "frozen_monolith":      "prefabs/structures/monolith_ice",
    "ice_pillar":           "prefabs/terrain/pillar_ice_01",
    "snow_mound":           "prefabs/terrain/mound_snow",
    "frost_shrine":         "prefabs/structures/shrine_frost",
    # Swamp
    "swamp_mushroom":       "prefabs/nature/mushroom_giant_swamp",
    "sunken_ruin":          "prefabs/ruins/wall_sunken_brick",
    "alchemy_station":      "prefabs/interactables/alchemy_station",
    "dead_tree":            "prefabs/nature/tree_dead_twisted",
    # Volcanic
    "lava_vent":            "prefabs/terrain/lava_vent_erupting",
    "forge_shrine":         "prefabs/structures/shrine_forge",
    "obsidian_pillar":      "prefabs/terrain/pillar_obsidian",
    "fire_geyser":          "prefabs/terrain/geyser_fire",
    # Ruins
    "temple_column":        "prefabs/ruins/column_marble_cracked",
    "artifact_pedestal":    "prefabs/interactables/pedestal_artifact",
    "crumbling_wall":       "prefabs/ruins/wall_stone_crumbled",
    "chest_rare":           "prefabs/interactables/chest_ornate",
    "chest_common":         "prefabs/interactables/chest_wood",
    # Ocean
    "coral_cluster":        "prefabs/nature/coral_cluster_large",
    "sunken_chest":         "prefabs/interactables/chest_sunken",
    "kelp_pillar":          "prefabs/nature/kelp_column",
    "anchor":               "prefabs/props/anchor_iron",
    # Plains
    "watchtower":           "prefabs/structures/watchtower_wood",
    "merchant_stall":       "prefabs/structures/stall_merchant",
    # Shared
    "bonfire":              "prefabs/interactables/bonfire_large",
    "healing_shrine":       "prefabs/interactables/shrine_healing",
    "gold_chest":           "prefabs/interactables/chest_gold",
}

# Maps abstract NPC role keys → engine NPC prefab paths.
NPC_PREFAB_REGISTRY: dict[str, str] = {
    # Wildlife
    "wolf_pack":            "prefabs/npcs/wolf_grey",
    "bear_guardian":        "prefabs/npcs/bear_grizzly",
    "giant_spider":         "prefabs/npcs/spider_giant",
    # Bandits
    "bandit_patrol":        "prefabs/npcs/bandit_swordsman",
    "bandit_archer":        "prefabs/npcs/bandit_archer",
    "bandit_captain":       "prefabs/npcs/bandit_captain",
    # Undead
    "skeleton_warrior":     "prefabs/npcs/skeleton_warrior",
    "zombie_horde":         "prefabs/npcs/zombie_basic",
    "wraith_patrol":        "prefabs/npcs/wraith",
    # Cultists
    "cultist_patrol":       "prefabs/npcs/cultist_robed",
    "cultist_mage":         "prefabs/npcs/cultist_mage",
    "cult_boss":            "prefabs/npcs/cultist_highpriest",
    # Guards / Neutral
    "town_guard":           "prefabs/npcs/guard_town",
    "patrol_guard":         "prefabs/npcs/guard_patrol",
    "guard_captain":        "prefabs/npcs/guard_captain",
    "merchant":             "prefabs/npcs/merchant_travelling",
    "wanderer":             "prefabs/npcs/npc_wanderer",
    "hermit":               "prefabs/npcs/npc_hermit",
    # Bosses
    "boss_golem":           "prefabs/npcs/boss_stone_golem",
    "boss_dragon":          "prefabs/npcs/boss_wyvern",
}

_FALLBACK_STRUCTURE_PREFAB = "prefabs/props/placeholder_cube"
_FALLBACK_NPC_PREFAB = "prefabs/npcs/placeholder_npc"


# FIXED: Added validation function to ensure all critical NPC roles have prefab entries
def _validate_npc_registry() -> dict[str, str]:
    """
    Ensure all common NPC roles have prefab entries.
    Returns a validated registry with missing entries logged as warnings.
    """
    # All NPC roles that should have entries
    required_roles = {
        # Wildlife
        "wolf_pack", "bear_guardian", "giant_spider",
        # Bandits
        "bandit_patrol", "bandit_archer", "bandit_captain",
        # Undead
        "skeleton_warrior", "zombie_horde", "wraith_patrol",
        # Cultists
        "cultist_patrol", "cultist_mage", "cult_boss",
        # Guards / Neutral
        "town_guard", "patrol_guard", "guard_captain",
        "merchant", "wanderer", "hermit",
        # Bosses
        "boss_golem", "boss_dragon",
    }
    
    registry = NPC_PREFAB_REGISTRY.copy()
    missing = required_roles - set(registry.keys())
    
    if missing:
        logger.warning(
            "NPC_PREFAB_REGISTRY missing %d entries: %s. "
            "These roles will use fallback prefabs at runtime.",
            len(missing), missing
        )
    
    return registry


# ---------------------------------------------------------------------------
# StructureBuilder
# ---------------------------------------------------------------------------

class StructureBuilder:
    """
    Converts a validated AIBlueprint into a RenderedChunk.

    The builder:
    1. Looks up every structure_type in STRUCTURE_PREFAB_REGISTRY.
    2. Computes a world-space position by combining the layout node's
       normalised position with the structure's local offset.
    3. Does the same for NPC roles using NPC_PREFAB_REGISTRY.
    4. Forwards WorldEvents verbatim (they are engine-side triggers).

    All positional arithmetic is seeded by the blueprint's chunk_seed so
    the same blueprint always produces identical object placement.

    Args:
        chunk_world_size: The real-world size of one chunk in world-units
                          (default 64.0). Used to scale normalised node
                          positions to absolute world coordinates.
        structure_registry: Override the default STRUCTURE_PREFAB_REGISTRY.
        npc_registry:       Override the default NPC_PREFAB_REGISTRY.
    """

    def __init__(
        self,
        chunk_world_size: float = 64.0,
        structure_registry: dict[str, str] | None = None,
        npc_registry: dict[str, str] | None = None,
    ) -> None:
        self.chunk_world_size = chunk_world_size
        self.structure_registry = structure_registry or STRUCTURE_PREFAB_REGISTRY
        # FIXED: Use validated NPC registry that logs missing entries
        self.npc_registry = npc_registry or _validate_npc_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, blueprint: AIBlueprint) -> RenderedChunk:
        """
        Transform a validated AIBlueprint into a RenderedChunk.

        Args:
            blueprint: A SafetyGate-validated AIBlueprint.

        Returns:
            A RenderedChunk containing all engine-ready objects, NPC spawns,
            and event triggers for this chunk.
        """
        rng = random.Random(blueprint.chunk_seed)

        # Index nodes by ID for O(1) lookup during structure placement
        node_index = {n.node_id: n for n in blueprint.layout_graph.nodes}

        rendered_objects = self._build_structures(
            blueprint.structures, node_index, blueprint.chunk_x, blueprint.chunk_y, rng
        )
        npc_spawns = self._build_npc_spawns(
            blueprint.npc_roles, node_index, blueprint.chunk_x, blueprint.chunk_y, rng
        )

        rendered = RenderedChunk(
            chunk_x=blueprint.chunk_x,
            chunk_y=blueprint.chunk_y,
            chunk_seed=blueprint.chunk_seed,
            theme=blueprint.chunk_theme,
            objects=rendered_objects,
            npc_spawns=npc_spawns,
            event_triggers=blueprint.events,
            ambient_notes=blueprint.ambient_notes,
        )

        logger.info(
            "Built RenderedChunk (%d,%d): %d objects, %d NPCs, %d events",
            blueprint.chunk_x, blueprint.chunk_y,
            len(rendered_objects), len(npc_spawns), len(blueprint.events),
        )

        return rendered

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_structures(
        self,
        structures: list[StructureBlueprint],
        node_index: dict[str, LayoutNode],
        chunk_x: int,
        chunk_y: int,
        rng: random.Random,
    ) -> list[RenderedObject]:
        """Map each StructureBlueprint to a RenderedObject with world coordinates."""
        objects: list[RenderedObject] = []

        for structure in structures:
            prefab = self.structure_registry.get(structure.structure_type)
            if prefab is None:
                logger.warning(
                    "Unknown structure_type '%s' — using fallback prefab",
                    structure.structure_type,
                )
                prefab = _FALLBACK_STRUCTURE_PREFAB

            world_pos = self._resolve_world_position(
                structure.node_id,
                structure.position_offset,
                node_index,
                chunk_x,
                chunk_y,
                rng,
            )

            metadata: dict[str, Any] = dict(structure.state)
            metadata["structure_type"] = structure.structure_type
            metadata["chunk_x"] = chunk_x
            metadata["chunk_y"] = chunk_y

            objects.append(RenderedObject(
                object_id=structure.structure_id,
                prefab_key=prefab,
                world_position=world_pos,
                metadata=metadata,
            ))

        return objects

    def _build_npc_spawns(
        self,
        npc_roles: list[NPCRole],
        node_index: dict[str, LayoutNode],
        chunk_x: int,
        chunk_y: int,
        rng: random.Random,
    ) -> list[RenderedObject]:
        """
        Map each NPCRole to one or more RenderedObjects (one per instance).

        When ``count > 1``, each instance is placed with a small random
        spread around the node's world position.
        """
        spawns: list[RenderedObject] = []

        for npc in npc_roles:
            prefab = self.npc_registry.get(npc.role)
            if prefab is None:
                logger.warning(
                    "Unknown NPC role '%s' — using fallback prefab",
                    npc.role,
                )
                prefab = _FALLBACK_NPC_PREFAB

            base_pos = self._resolve_world_position(
                npc.node_id,
                (0.0, 0.0, 0.0),
                node_index,
                chunk_x,
                chunk_y,
                rng,
            )

            for instance_idx in range(npc.count):
                # Spread instances within a 6-unit radius of the node centre
                spread_x = rng.uniform(-3.0, 3.0)
                spread_z = rng.uniform(-3.0, 3.0)

                instance_pos = (
                    base_pos[0] + spread_x,
                    base_pos[1],
                    base_pos[2] + spread_z,
                )

                spawns.append(RenderedObject(
                    object_id=f"{npc.npc_id}_inst{instance_idx}",
                    prefab_key=prefab,
                    world_position=instance_pos,
                    metadata={
                        "role": npc.role,
                        "faction": npc.faction.value,
                        "level": npc.level,
                        "instance_index": instance_idx,
                        "chunk_x": chunk_x,
                        "chunk_y": chunk_y,
                    },
                ))

        return spawns

    def _resolve_world_position(
        self,
        node_id: str,
        offset: tuple[float, float, float],
        node_index: dict[str, LayoutNode],
        chunk_x: int,
        chunk_y: int,
        rng: random.Random,
    ) -> tuple[float, float, float]:
        """
        Convert a (node_id + local offset) pair into absolute world coordinates.

        Layout nodes use normalised [0, 1] positions within the chunk square.
        We scale to world-units, then shift by the chunk's global origin.

        If the node_id is missing (AI hallucination), falls back to a random
        position within the chunk boundaries.
        """
        s = self.chunk_world_size
        chunk_origin_x = chunk_x * s
        chunk_origin_z = chunk_y * s

        node = node_index.get(node_id)
        if node is None:
            logger.warning("Node '%s' not found in blueprint; using fallback position", node_id)
            local_x = rng.uniform(0, s)
            local_z = rng.uniform(0, s)
        else:
            local_x = node.position[0] * s
            local_z = node.position[1] * s

        world_x = chunk_origin_x + local_x + offset[0]
        world_y = offset[1]
        world_z = chunk_origin_z + local_z + offset[2]

        return (round(world_x, 3), round(world_y, 3), round(world_z, 3))
