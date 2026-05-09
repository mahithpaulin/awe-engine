"""
Step 3: The Rule Engine & Safety Gate
======================================
The RuleEngine generates constraint budgets from raw chunk parameters.
The SafetyGate validates incoming AI blueprints against those constraints,
ensuring the AI can never produce game-breaking or physically impossible output.

This is the critical correctness layer between the AI and the game world.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .models import (
    AIBlueprint,
    BiomeType,
    ChunkState,
    DifficultyLevel,
    FactionType,
    NPCRole,
    RuleConstraints,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Biome configuration tables
# ---------------------------------------------------------------------------

_BIOME_FACTION_MAP: dict[BiomeType, list[FactionType]] = {
    BiomeType.FOREST:   [FactionType.WILDLIFE, FactionType.BANDITS, FactionType.NEUTRAL],
    BiomeType.DESERT:   [FactionType.BANDITS, FactionType.UNDEAD, FactionType.NEUTRAL],
    BiomeType.TUNDRA:   [FactionType.WILDLIFE, FactionType.NEUTRAL],
    BiomeType.SWAMP:    [FactionType.UNDEAD, FactionType.CULTISTS, FactionType.WILDLIFE],
    BiomeType.VOLCANIC: [FactionType.CULTISTS, FactionType.WILDLIFE],
    BiomeType.RUINS:    [FactionType.UNDEAD, FactionType.BANDITS, FactionType.CULTISTS],
    BiomeType.OCEAN:    [FactionType.WILDLIFE, FactionType.NEUTRAL],
    BiomeType.PLAINS:   [FactionType.GUARDS, FactionType.BANDITS, FactionType.NEUTRAL],
}

_BIOME_FORBIDDEN_STRUCTURES: dict[BiomeType, list[str]] = {
    BiomeType.TUNDRA:   ["desert_obelisk", "lava_vent"],
    BiomeType.VOLCANIC: ["ice_pillar", "water_fountain"],
    BiomeType.OCEAN:    ["campfire", "wooden_tower"],
    BiomeType.DESERT:   ["ice_pillar", "swamp_mushroom"],
    BiomeType.SWAMP:    ["desert_obelisk", "ice_pillar"],
    BiomeType.FOREST:   ["lava_vent"],
    BiomeType.RUINS:    [],
    BiomeType.PLAINS:   ["lava_vent", "ice_pillar"],
}


@dataclass
class ValidationResult:
    """
    Result produced by the SafetyGate after inspecting a blueprint.

    Attributes:
        valid:     Whether the blueprint passed all checks.
        blueprint: The (potentially patched) blueprint.
        errors:    Hard violations that caused rejection.
        warnings:  Soft violations that were auto-corrected.
    """
    valid: bool
    blueprint: AIBlueprint
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------

class RuleEngine:
    """
    Derives a RuleConstraints budget from chunk coordinates and world parameters.

    The engine applies three rule categories:
    - Physical rules  : terrain height, walkability
    - Gameplay rules  : enemy/resource budgets, exit guarantees
    - Narrative rules : biome/faction consistency
    """

    # Base enemy counts indexed by DifficultyLevel value (1-5)
    _BASE_ENEMY_BY_DIFFICULTY: dict[int, int] = {1: 2, 2: 5, 3: 10, 4: 18, 5: 30}

    # Base structure counts indexed by DifficultyLevel value
    _BASE_STRUCTURES_BY_DIFFICULTY: dict[int, int] = {1: 5, 2: 8, 3: 12, 4: 16, 5: 20}

    # Height delta (world-units) allowed per difficulty
    _MAX_HEIGHT_BY_DIFFICULTY: dict[int, float] = {
        1: 2.0, 2: 4.0, 3: 6.0, 4: 8.0, 5: 12.0
    }

    def generate_constraints(
        self,
        chunk_x: int,
        chunk_y: int,
        biome: BiomeType,
        difficulty: DifficultyLevel,
        adjacent_difficulties: list[DifficultyLevel] | None = None,
    ) -> RuleConstraints:
        """
        Produce a RuleConstraints object for the specified chunk parameters.

        Difficulty is influenced by adjacent chunks to ensure smooth world
        transitions — a chunk surrounded by hard chunks cannot be trivial.

        Args:
            chunk_x:              X grid coordinate of the target chunk.
            chunk_y:              Y grid coordinate of the target chunk.
            biome:                Biome type for the chunk.
            difficulty:           Nominal difficulty level.
            adjacent_difficulties: Difficulty levels of neighbouring chunks
                                   (used to clamp the effective difficulty).

        Returns:
            A fully populated RuleConstraints object.
        """
        effective_difficulty = self._resolve_effective_difficulty(
            difficulty, adjacent_difficulties or []
        )

        d = effective_difficulty.value
        enemy_budget = self._BASE_ENEMY_BY_DIFFICULTY[d]
        structure_budget = self._BASE_STRUCTURES_BY_DIFFICULTY[d]
        max_height = self._MAX_HEIGHT_BY_DIFFICULTY[d]

        resource_budget = self._build_resource_budget(biome, effective_difficulty)

        logger.debug(
            "Generated constraints for chunk (%d,%d): difficulty=%s, enemies=%d",
            chunk_x, chunk_y, effective_difficulty.name, enemy_budget,
        )

        return RuleConstraints(
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            biome=biome,
            difficulty=effective_difficulty,
            max_enemy_count=enemy_budget,
            max_structure_count=structure_budget,
            max_height_delta=max_height,
            min_exit_count=1,
            allowed_factions=_BIOME_FACTION_MAP[biome],
            resource_budget=resource_budget,
            forbidden_structure_types=_BIOME_FORBIDDEN_STRUCTURES.get(biome, []),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_effective_difficulty(
        self,
        nominal: DifficultyLevel,
        adjacent: list[DifficultyLevel],
    ) -> DifficultyLevel:
        """
        Clamp difficulty so it stays within ±1 of the average of adjacent chunks.

        Prevents jarring difficulty spikes (e.g. a trivial chunk surrounded
        by extreme ones) that would break world-feel.
        """
        if not adjacent:
            return nominal

        avg = sum(d.value for d in adjacent) / len(adjacent)
        clamped = max(1, min(5, round(avg)))
        # Allow at most ±1 deviation from clamped average
        final_value = max(clamped - 1, min(clamped + 1, nominal.value))
        return DifficultyLevel(final_value)

    def _build_resource_budget(
        self,
        biome: BiomeType,
        difficulty: DifficultyLevel,
    ) -> dict[str, int]:
        """
        Derive per-resource caps from biome and difficulty.

        Higher difficulty = fewer healing resources, more loot potential.
        """
        d = difficulty.value
        base_healing = max(0, 3 - d)
        base_gold = d

        biome_bonus: dict[str, dict[str, int]] = {
            BiomeType.RUINS:    {"gold_chests": 1, "artifact_pedestals": 1},
            BiomeType.SWAMP:    {"alchemy_stations": 1},
            BiomeType.VOLCANIC: {"forge_shrines": 1},
        }

        budget: dict[str, int] = {
            "healing_shrines": base_healing,
            "gold_chests": base_gold,
        }
        budget.update(biome_bonus.get(biome, {}))
        return budget


# ---------------------------------------------------------------------------
# SafetyGate
# ---------------------------------------------------------------------------

def safety_gate(
    blueprint: AIBlueprint,
    constraints: RuleConstraints,
    *,
    auto_patch: bool = True,
) -> ValidationResult:
    """
    Validate an AI-generated blueprint against a RuleConstraints budget.

    The gate checks:
    1. Coordinate match          — blueprint targets the correct chunk.
    2. Graph connectivity        — all nodes reachable from any entrance.
    3. Exit guarantee            — at least one exit node exists.
    4. Enemy budget              — total hostile NPC count within limit.
    5. Structure budget          — total structures within limit.
    6. Faction consistency       — only allowed factions appear.
    7. Forbidden structures      — prohibited types are absent.

    When ``auto_patch=True`` (default), soft violations are corrected
    in-place and logged as warnings. Hard violations (coordinate mismatch,
    disconnected graph) cause immediate rejection.

    Args:
        blueprint:   The AIBlueprint to inspect.
        constraints: The RuleConstraints budget from RuleEngine.
        auto_patch:  If True, attempt to fix soft violations automatically.

    Returns:
        A ValidationResult containing the (possibly patched) blueprint,
        a validity flag, and lists of errors and warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ---- Hard check 1: coordinate match ----
    if blueprint.chunk_x != constraints.chunk_x or blueprint.chunk_y != constraints.chunk_y:
        errors.append(
            f"Blueprint chunk ({blueprint.chunk_x},{blueprint.chunk_y}) does not match "
            f"expected chunk ({constraints.chunk_x},{constraints.chunk_y})"
        )

    # ---- Hard check 2: graph connectivity (BFS from first entrance) ----
    graph_error = _check_graph_connectivity(blueprint)
    if graph_error:
        errors.append(graph_error)

    # ---- Hard check 3: exit guarantee ----
    exit_nodes = [n for n in blueprint.layout_graph.nodes if n.is_exit]
    if len(exit_nodes) < constraints.min_exit_count:
        errors.append(
            f"Blueprint has {len(exit_nodes)} exit(s); minimum required is "
            f"{constraints.min_exit_count}"
        )

    if errors:
        logger.warning("SafetyGate rejected blueprint %s: %s", blueprint.blueprint_id, errors)
        return ValidationResult(valid=False, blueprint=blueprint, errors=errors, warnings=warnings)

    # ---- Soft check 4: enemy budget ----
    total_enemies = sum(
        npc.count for npc in blueprint.npc_roles
        if _is_hostile_role(npc)
    )
    if total_enemies > constraints.max_enemy_count:
        if auto_patch:
            blueprint = _patch_enemy_count(blueprint, constraints.max_enemy_count)
            warnings.append(
                f"Enemy count {total_enemies} exceeded budget {constraints.max_enemy_count}; "
                "excess NPCs trimmed."
            )
        else:
            errors.append(
                f"Enemy count {total_enemies} exceeds budget {constraints.max_enemy_count}"
            )

    # ---- Soft check 5: structure budget ----
    if len(blueprint.structures) > constraints.max_structure_count:
        if auto_patch:
            trimmed = len(blueprint.structures) - constraints.max_structure_count
            blueprint.structures = blueprint.structures[: constraints.max_structure_count]
            warnings.append(
                f"Structure count exceeded budget {constraints.max_structure_count}; "
                f"{trimmed} structure(s) removed."
            )
        else:
            errors.append(
                f"Structure count {len(blueprint.structures)} exceeds budget "
                f"{constraints.max_structure_count}"
            )

    # ---- Soft check 6: faction consistency ----
    allowed = set(constraints.allowed_factions)
    bad_factions = [
        npc for npc in blueprint.npc_roles if npc.faction not in allowed
    ]
    if bad_factions:
        if auto_patch:
            # FIXED: Check if NEUTRAL is allowed before patching
            if FactionType.NEUTRAL in allowed:
                for npc in bad_factions:
                    npc.faction = FactionType.NEUTRAL
                warnings.append(
                    f"{len(bad_factions)} NPC(s) had disallowed factions; reset to NEUTRAL."
                )
            else:
                # Pick a random allowed faction instead
                import random
                fallback_faction = random.choice(list(allowed))
                for npc in bad_factions:
                    npc.faction = fallback_faction
                warnings.append(
                    f"{len(bad_factions)} NPC(s) had disallowed factions; reset to {fallback_faction.value}."
                )
        else:
            errors.append(
                f"Disallowed factions found: "
                f"{[n.faction for n in bad_factions]}"
            )

    # ---- Soft check 7: forbidden structure types ----
    forbidden = set(constraints.forbidden_structure_types)
    bad_structures = [s for s in blueprint.structures if s.structure_type in forbidden]
    if bad_structures:
        if auto_patch:
            blueprint.structures = [
                s for s in blueprint.structures if s.structure_type not in forbidden
            ]
            warnings.append(
                f"{len(bad_structures)} forbidden structure(s) removed: "
                f"{[s.structure_type for s in bad_structures]}"
            )
        else:
            errors.append(
                f"Forbidden structure types present: "
                f"{[s.structure_type for s in bad_structures]}"
            )

    valid = len(errors) == 0
    if warnings:
        logger.info(
            "SafetyGate patched blueprint %s — warnings: %s",
            blueprint.blueprint_id, warnings,
        )
    return ValidationResult(valid=valid, blueprint=blueprint, errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# Safety Gate internals
# ---------------------------------------------------------------------------

def _check_graph_connectivity(blueprint: AIBlueprint) -> str | None:
    """
    BFS from all entrance nodes; returns an error string if any node is
    unreachable (i.e. the graph is disconnected). Returns None on success.
    
    FIXED: Now properly validates one-way edges. A one-way edge can only be
    traversed in the direction it points, preventing unreachable nodes.
    """
    nodes = blueprint.layout_graph.nodes
    edges = blueprint.layout_graph.edges

    if not nodes:
        return "Layout graph has no nodes"

    node_ids = {n.node_id for n in nodes}

    # Build adjacency respecting one-way edge directionality
    adjacency: dict[str, set[str]] = {nid: set() for nid in node_ids}
    for edge in edges:
        # One-way edges only go from_node → to_node
        if edge.from_node in adjacency:
            adjacency[edge.from_node].add(edge.to_node)
        # Two-way edges are bidirectional
        if not edge.is_one_way and edge.to_node in adjacency:
            adjacency[edge.to_node].add(edge.from_node)

    # BFS from first node (or first entrance)
    entrances = [n.node_id for n in nodes if n.is_entrance] or [nodes[0].node_id]
    visited: set[str] = set()
    queue = list(entrances)
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(adjacency.get(current, set()) - visited)

    unreachable = node_ids - visited
    if unreachable:
        return f"Layout graph is disconnected; unreachable nodes: {unreachable}"
    return None


def _is_hostile_role(npc: NPCRole) -> bool:
    """Return True if an NPC role is considered combat-hostile."""
    hostile_keywords = {"boss", "patrol", "guard", "bandit", "undead", "golem", "cultist"}
    return any(kw in npc.role.lower() for kw in hostile_keywords)


def _patch_enemy_count(blueprint: AIBlueprint, max_count: int) -> AIBlueprint:
    """
    Reduce enemy NPC counts until the total hostile count is within budget.

    Prioritises keeping bosses and reducing patrol/grunt counts first.
    """
    total = sum(npc.count for npc in blueprint.npc_roles if _is_hostile_role(npc))
    excess = total - max_count

    # Sort: non-bosses first (reduce grunts before bosses)
    hostile_npcs = sorted(
        [npc for npc in blueprint.npc_roles if _is_hostile_role(npc)],
        key=lambda n: ("boss" not in n.role.lower()),
        reverse=True,
    )

    for npc in hostile_npcs:
        if excess <= 0:
            break
        reduction = min(npc.count, excess)
        npc.count -= reduction
        excess -= reduction

    # Remove zero-count NPCs
    blueprint.npc_roles = [n for n in blueprint.npc_roles if n.count > 0]
    return blueprint
