"""
Step 4: The AI World Designer — Gemini-Powered
===============================================
Translates RuleConstraints into creative AI JSON blueprints using
Google Gemini (via Replit AI Integrations proxy — no user API key needed).

Falls back to the deterministic mock when the Gemini env vars are absent,
so local dev always works without any configuration.

Public API:
  - build_system_prompt()   → static system instruction for the LLM
  - build_user_prompt()     → per-chunk JSON request
  - call_ai_mock()          → deterministic seeded mock (no network)
  - AIDesigner              → orchestrates prompt → Gemini/mock → SafetyGate
"""

from __future__ import annotations

import json
import logging
import os
import random
from typing import Any

from .models import (
    AIBlueprint,
    BiomeType,
    DifficultyLevel,
    FactionType,
    LayoutEdge,
    LayoutGraph,
    LayoutNode,
    NPCRole,
    RuleConstraints,
    StructureBlueprint,
    WorldEvent,
)
from .rule_engine import RuleEngine, ValidationResult, safety_gate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    """Static system prompt that primes Gemini as the AWE World Designer."""
    return (
        "You are the AWE World Designer — an elite procedural world generation AI "
        "for a multiplayer game engine.\n"
        "Your sole task is to produce valid JSON world blueprints for 2D/3D game chunks.\n\n"
        "STRICT RULES:\n"
        "1. Respond with ONLY a valid JSON object matching the blueprint schema. No prose.\n"
        "2. Never exceed the enemy_budget or structure_budget provided.\n"
        "3. The layout_graph MUST be fully connected (every node reachable from entrance).\n"
        "4. Include at least one exit node in the layout graph.\n"
        "5. Use only factions listed in allowed_factions.\n"
        "6. Do NOT use any structure type in forbidden_structure_types.\n"
        "7. Be creative and specific with chunk_theme and ambient_notes.\n"
        "8. All node positions use normalised [0.0, 1.0] coordinates.\n"
        "9. Output JSON must match exactly:\n"
        "   {chunk_x, chunk_y, chunk_seed, chunk_theme, biome, difficulty,\n"
        "    layout_graph: {nodes: [{node_id, label, is_entrance, is_exit, position:[x,y]}],\n"
        "                   edges: [{from_node, to_node, is_one_way, weight}]},\n"
        "    structures: [{structure_type, node_id, position_offset:[x,y,z], state:{}}],\n"
        "    npc_roles: [{role, faction, node_id, level, count}],\n"
        "    events: [{event_type, trigger_node, trigger_condition, payload:{}}],\n"
        "    ambient_notes}\n"
    )


def build_user_prompt(
    constraints: RuleConstraints,
    adjacent_chunk_themes: list[str] | None = None,
    player_behaviour_notes: str = "",
    player_count: int = 1,
) -> str:
    """Construct the per-chunk generation request from constraint budget."""
    payload: dict[str, Any] = {
        "chunk_coordinates": {"x": constraints.chunk_x, "y": constraints.chunk_y},
        "biome": constraints.biome.value,
        "difficulty": constraints.difficulty.name,
        "enemy_budget": constraints.max_enemy_count,
        "structure_budget": constraints.max_structure_count,
        "max_height_delta": constraints.max_height_delta,
        "min_exits": constraints.min_exit_count,
        "allowed_factions": [f.value for f in constraints.allowed_factions],
        "resource_budget": constraints.resource_budget,
        "forbidden_structure_types": constraints.forbidden_structure_types,
        "active_player_count": player_count,
    }
    if adjacent_chunk_themes:
        payload["adjacent_themes"] = adjacent_chunk_themes
    if player_behaviour_notes:
        payload["player_behaviour"] = player_behaviour_notes

    payload["task"] = (
        f"Generate a world chunk for {player_count} simultaneous player(s). "
        "Create a fully connected layout graph (3-6 nodes), place structures within budget, "
        "assign NPC roles to allowed factions, add 1-2 world events, "
        "and write an evocative chunk_theme and ambient_notes."
    )
    return json.dumps(payload, indent=2)


# ---------------------------------------------------------------------------
# Mock LLM (deterministic fallback)
# ---------------------------------------------------------------------------

def call_ai_mock(
    system_prompt: str,
    user_prompt: str,
    constraints: RuleConstraints,
) -> dict[str, Any]:
    """
    Deterministic mock LLM — used when Gemini env vars are not set.
    Same (x,y) always produces the same blueprint (seeded RNG).
    """
    rng = random.Random(
        abs(constraints.chunk_x * 2654435761 ^ constraints.chunk_y * 2246822519)
    )

    theme_prefixes = {
        BiomeType.FOREST:   ["overgrown", "ancient", "cursed", "sunlit"],
        BiomeType.DESERT:   ["scorched", "buried", "endless", "forgotten"],
        BiomeType.TUNDRA:   ["frozen", "blizzard-swept", "glacial", "desolate"],
        BiomeType.SWAMP:    ["fetid", "mist-shrouded", "rotting", "dark"],
        BiomeType.VOLCANIC: ["molten", "ashen", "erupting", "smouldering"],
        BiomeType.RUINS:    ["crumbling", "haunted", "ancient", "overgrown"],
        BiomeType.OCEAN:    ["storm-lashed", "sunken", "coral-choked", "tidal"],
        BiomeType.PLAINS:   ["windswept", "golden", "battle-scarred", "endless"],
    }
    theme_suffixes = {
        BiomeType.FOREST:   ["grove", "canopy", "hollow", "sanctuary"],
        BiomeType.DESERT:   ["dunes", "necropolis", "oasis", "wastes"],
        BiomeType.TUNDRA:   ["tundra", "ice-field", "glacier", "permafrost"],
        BiomeType.SWAMP:    ["bayou", "morass", "bog", "mire"],
        BiomeType.VOLCANIC: ["caldera", "lava field", "forge", "pyre"],
        BiomeType.RUINS:    ["citadel", "temple", "catacombs", "arena"],
        BiomeType.OCEAN:    ["reef", "shipwreck", "trench", "atoll"],
        BiomeType.PLAINS:   ["battlefield", "homestead", "crossroads", "expanse"],
    }
    prefix = rng.choice(theme_prefixes[constraints.biome])
    suffix = rng.choice(theme_suffixes[constraints.biome])
    theme = f"{prefix} {suffix} of chunk ({constraints.chunk_x},{constraints.chunk_y})"

    node_count = rng.randint(3, min(6, constraints.max_structure_count))
    nodes = []
    for i in range(node_count):
        nodes.append({
            "node_id": f"node_{i}",
            "label": f"Area {i}",
            "is_entrance": i == 0,
            "is_exit": i == node_count - 1,
            "position": [round(rng.uniform(0.05, 0.95), 2), round(rng.uniform(0.05, 0.95), 2)],
        })

    edges = []
    for i in range(node_count - 1):
        edges.append({
            "from_node": f"node_{i}",
            "to_node": f"node_{i + 1}",
            "is_one_way": False,
            "weight": round(rng.uniform(0.5, 2.0), 1),
        })
    if node_count >= 4 and rng.random() < 0.5:
        a, b = rng.sample(range(node_count), 2)
        edges.append({"from_node": f"node_{a}", "to_node": f"node_{b}",
                      "is_one_way": rng.random() < 0.3, "weight": 1.0})

    structure_pool = {
        BiomeType.FOREST:   ["ancient_tree", "wooden_shrine", "campfire", "log_pile", "chest_common"],
        BiomeType.DESERT:   ["desert_obelisk", "sand_dune_mound", "buried_chest", "ruined_arch"],
        BiomeType.TUNDRA:   ["frozen_monolith", "ice_pillar", "snow_mound", "frost_shrine"],
        BiomeType.SWAMP:    ["swamp_mushroom", "sunken_ruin", "alchemy_station", "dead_tree"],
        BiomeType.VOLCANIC: ["lava_vent", "forge_shrine", "obsidian_pillar", "fire_geyser"],
        BiomeType.RUINS:    ["temple_column", "artifact_pedestal", "crumbling_wall", "chest_rare"],
        BiomeType.OCEAN:    ["coral_cluster", "sunken_chest", "kelp_pillar", "anchor"],
        BiomeType.PLAINS:   ["watchtower", "campfire", "merchant_stall", "chest_common"],
    }
    pool = structure_pool[constraints.biome]
    structures = []
    for _ in range(rng.randint(1, constraints.max_structure_count)):
        structures.append({
            "structure_type": rng.choice(pool),
            "node_id": f"node_{rng.randint(0, node_count - 1)}",
            "position_offset": [round(rng.uniform(-5, 5), 1), 0.0, round(rng.uniform(-5, 5), 1)],
            "state": {},
        })

    npc_role_pool = {
        FactionType.WILDLIFE:  ["wolf_pack", "bear_guardian", "giant_spider"],
        FactionType.BANDITS:   ["bandit_patrol", "bandit_archer", "bandit_captain"],
        FactionType.UNDEAD:    ["skeleton_warrior", "zombie_horde", "wraith_patrol"],
        FactionType.CULTISTS:  ["cultist_patrol", "cultist_mage", "cult_boss"],
        FactionType.GUARDS:    ["town_guard", "patrol_guard", "guard_captain"],
        FactionType.NEUTRAL:   ["merchant", "wanderer", "hermit"],
    }
    npc_list = []
    if constraints.max_enemy_count > 0 and constraints.allowed_factions:
        non_neutral = [f for f in constraints.allowed_factions if f != FactionType.NEUTRAL]
        faction = rng.choice(non_neutral) if non_neutral else rng.choice(constraints.allowed_factions)
        roles = npc_role_pool.get(faction, ["patrol_guard"])
        # FIXED: Cap NPC level to reasonable progression bounds (max ~30 for EXTREME difficulty)
        base_level = constraints.difficulty.value * 5
        level_variance = rng.randint(-2, 2)
        capped_level = max(1, min(30, base_level + level_variance))
        
        npc_list.append({
            "role": rng.choice(roles),
            "faction": faction.value,
            "node_id": f"node_{rng.randint(0, node_count - 1)}",
            "level": capped_level,
            "count": rng.randint(1, min(constraints.max_enemy_count, 5)),
        })

    ambient_pool = [
        "Wind howls through cracked stone.",
        "The air smells of ash and something older.",
        "Distant drums echo between the trees.",
        "A thick fog clings to the ground.",
        "Bioluminescent spores drift lazily in the dark.",
    ]

    return {
        "chunk_x": constraints.chunk_x,
        "chunk_y": constraints.chunk_y,
        "chunk_seed": abs(constraints.chunk_x * 1000003 ^ constraints.chunk_y * 999983),
        "chunk_theme": theme,
        "biome": constraints.biome.value,
        "difficulty": constraints.difficulty.value,
        "layout_graph": {"nodes": nodes, "edges": edges},
        "structures": structures,
        "npc_roles": npc_list,
        "events": [{"event_type": "ambush", "trigger_node": "node_0",
                    "trigger_condition": "on_enter", "payload": {"intensity": "medium"}}],
        "ambient_notes": rng.choice(ambient_pool),
    }


# ---------------------------------------------------------------------------
# Gemini live call
# ---------------------------------------------------------------------------

def _is_gemini_available() -> bool:
    return bool(
        os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")
        and os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY")
    )


async def call_gemini_live(
    system_prompt: str,
    user_prompt: str,
    constraints: RuleConstraints,
) -> dict[str, Any]:
    """
    Call Gemini via Replit AI Integrations proxy.

    Uses gemini-2.5-flash with JSON response mode to guarantee structured output.
    Falls back to mock if the env vars are unexpectedly missing at call time.
    """
    import google.generativeai as genai

    base_url = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL", "")
    api_key = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY", "dummy")

    genai.configure(
        api_key=api_key,
        client_options={"api_endpoint": base_url} if base_url else {},
    )

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            max_output_tokens=8192,
        ),
    )

    logger.info(
        "Calling Gemini for chunk (%d,%d)…",
        constraints.chunk_x, constraints.chunk_y,
    )

    response = await model.generate_content_async(user_prompt)
    raw = response.text.strip()

    # Strip markdown code fences if the model wraps despite JSON mode
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned invalid JSON: %s\nRaw: %s", exc, raw[:500])
        logger.warning("Falling back to mock for chunk (%d,%d)", constraints.chunk_x, constraints.chunk_y)
        return call_ai_mock(system_prompt, user_prompt, constraints)


# ---------------------------------------------------------------------------
# AIDesigner orchestrator
# ---------------------------------------------------------------------------

class AIDesigner:
    """
    Orchestrates the full AI generation pipeline for a single chunk.

    Pipeline:
    1. Build system + user prompts from RuleConstraints.
    2. Call Gemini (live) or mock depending on env var availability.
    3. Parse raw JSON into AIBlueprint.
    4. Run SafetyGate with auto-patch.
    5. Return validated blueprint.

    Args:
        rule_engine:  Shared RuleEngine instance.
        use_mock:     Force mock mode regardless of env vars (for testing).
    """

    def __init__(
        self,
        rule_engine: RuleEngine | None = None,
        use_mock: bool = False,
    ) -> None:
        self.rule_engine = rule_engine or RuleEngine()
        self.use_mock = use_mock

    @property
    def is_live(self) -> bool:
        """True when Gemini is available and mock is not forced."""
        return not self.use_mock and _is_gemini_available()

    async def generate_blueprint(
        self,
        constraints: RuleConstraints,
        adjacent_chunk_themes: list[str] | None = None,
        player_behaviour_notes: str = "",
        player_count: int = 1,
    ) -> tuple[AIBlueprint, ValidationResult]:
        """
        Run the full AI generation + validation pipeline.

        Returns (validated AIBlueprint, ValidationResult).
        Raises ValueError on hard SafetyGate failures.
        """
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(
            constraints,
            adjacent_chunk_themes=adjacent_chunk_themes,
            player_behaviour_notes=player_behaviour_notes,
            player_count=player_count,
        )

        raw_json = await self._call_llm(system_prompt, user_prompt, constraints)

        try:
            blueprint = AIBlueprint.model_validate(raw_json)
        except Exception as exc:
            raise ValueError(
                f"AI returned JSON that failed schema validation: {exc}"
            ) from exc

        result = safety_gate(blueprint, constraints, auto_patch=True)

        if not result.valid:
            raise ValueError(
                f"Blueprint for chunk ({constraints.chunk_x},{constraints.chunk_y}) "
                f"failed SafetyGate: {result.errors}"
            )

        logger.info(
            "Blueprint %s accepted [mode=%s] — warnings: %s",
            result.blueprint.blueprint_id,
            "live" if self.is_live else "mock",
            result.warnings or "none",
        )

        return result.blueprint, result

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        constraints: RuleConstraints,
    ) -> dict[str, Any]:
        if self.is_live:
            return await call_gemini_live(system_prompt, user_prompt, constraints)
        return call_ai_mock(system_prompt, user_prompt, constraints)
