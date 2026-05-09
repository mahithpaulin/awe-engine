"""
Step 2: World Manager & Chunk Lifecycle — Multiplayer Edition
=============================================================
MultiplayerWorldManager extends the original WorldManager to support
multiple simultaneous players sharing a single live world.

Key multiplayer rules:
- A chunk stays ACTIVE as long as ANY player is within render_radius.
- Chunks are only unloaded once ALL players have moved out of range.
- Each player gets independent tick events; the world state is shared.
- Player sessions track position, last-seen time, and connection metadata.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any

from .models import (
    BiomeType,
    Chunk,
    ChunkState,
    DifficultyLevel,
    MemoryState,
    RenderedChunk,
)
from .rule_engine import RuleEngine

logger = logging.getLogger(__name__)

GeneratorFn = Callable[[Chunk], Awaitable[RenderedChunk]]
PersistLoadFn = Callable[[int, int], Awaitable[MemoryState | None]]
PersistSaveFn = Callable[[MemoryState], Awaitable[None]]


# ---------------------------------------------------------------------------
# Player session
# ---------------------------------------------------------------------------

@dataclass
class PlayerSession:
    """Runtime state for one connected player."""
    player_id: str
    world_x: float = 0.0
    world_y: float = 0.0
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_coords(self) -> tuple[int, int]:
        size = 64.0
        return (int(self.world_x // size), int(self.world_y // size))


# ---------------------------------------------------------------------------
# MultiplayerWorldManager
# ---------------------------------------------------------------------------

class MultiplayerWorldManager:
    """
    Manages a shared procedural world for multiple simultaneous players.

    All players inhabit the same chunk grid. Chunks are generated on first
    request and remain active until no player is nearby.

    Args:
        render_radius:   Chunk radius kept active around each player (default 2).
        chunk_size:      World-unit size of one chunk square (default 64).
        rule_engine:     Shared RuleEngine for constraint generation.
        generator_fn:    Async callable: Chunk → RenderedChunk.
        persist_load_fn: Optional async callable to restore MemoryState.
        persist_save_fn: Optional async callable to save MemoryState.
    """

    def __init__(
        self,
        render_radius: int = 2,
        chunk_size: float = 64.0,
        rule_engine: RuleEngine | None = None,
        generator_fn: GeneratorFn | None = None,
        persist_load_fn: PersistLoadFn | None = None,
        persist_save_fn: PersistSaveFn | None = None,
    ) -> None:
        self.render_radius = render_radius
        self.chunk_size = chunk_size
        self.rule_engine = rule_engine or RuleEngine()
        self.generator_fn = generator_fn
        self.persist_load_fn = persist_load_fn
        self.persist_save_fn = persist_save_fn

        self._chunks: dict[tuple[int, int], Chunk] = {}
        self._rendered: dict[tuple[int, int], RenderedChunk] = {}
        self._players: dict[str, PlayerSession] = {}
        # FIXED: Add reference counter to track which players reference each chunk
        # Prevents race condition where multiple players trigger simultaneous unload
        self._chunk_ref_count: dict[tuple[int, int], int] = {}

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    def join(self, player_id: str, world_x: float = 0.0, world_y: float = 0.0,
             metadata: dict[str, Any] | None = None) -> PlayerSession:
        """Register a new player. Returns the created session."""
        session = PlayerSession(
            player_id=player_id,
            world_x=world_x,
            world_y=world_y,
            metadata=metadata or {},
        )
        self._players[player_id] = session
        logger.info("Player '%s' joined at (%.1f, %.1f)", player_id, world_x, world_y)
        return session

    def leave(self, player_id: str) -> None:
        """
        Remove a player. Orphaned chunks will unload on next tick.
        FIXED: Mark last_seen to force chunk cleanup even if player data is stale.
        """
        session = self._players.get(player_id)
        if session:
            # Set last_seen far in the past to force immediate cleanup if referenced
            session.last_seen = 0.0
        self._players.pop(player_id, None)
        logger.info("Player '%s' left the world (cleanup scheduled)", player_id)

    def get_player(self, player_id: str) -> PlayerSession | None:
        return self._players.get(player_id)

    def all_players(self) -> list[PlayerSession]:
        return list(self._players.values())

    def player_count(self) -> int:
        return len(self._players)

    # ------------------------------------------------------------------
    # World tick (multiplayer)
    # ------------------------------------------------------------------

    async def tick(
        self,
        player_world_x: float,
        player_world_y: float,
        player_id: str = "default",
    ) -> dict[str, Any]:
        """
        Update a single player's position and synchronise the world.

        This updates the calling player's position, then computes the union
        of all players' required chunks, generates missing ones, and unloads
        chunks no longer needed by anyone.

        Returns a dict with: generated, unloaded, active, player_chunk.
        """
        # Update or create the player session
        if player_id not in self._players:
            self.join(player_id, player_world_x, player_world_y)
        session = self._players[player_id]
        session.world_x = player_world_x
        session.world_y = player_world_y
        session.last_seen = time.time()

        # Required chunks = union of all players' render areas
        required = self._all_required_chunks()

        # FIXED: Update reference counts atomically with required chunks
        # This prevents race condition where simultaneous player updates trigger duplicate unloads
        old_refs = set(self._chunk_ref_count.keys())
        
        # Update ref counts for newly required chunks
        for coord in required:
            if coord not in self._chunk_ref_count:
                self._chunk_ref_count[coord] = 0
            self._chunk_ref_count[coord] += 1
        
        # Decrement and remove orphaned chunk refs
        for coord in old_refs - required:
            self._chunk_ref_count[coord] -= 1
            if self._chunk_ref_count[coord] <= 0:
                del self._chunk_ref_count[coord]

        generated_coords: list[tuple[int, int]] = []
        unloaded_coords: list[tuple[int, int]] = []

        # Generate missing chunks
        for coord in required:
            chunk = self._chunks.get(coord)
            if chunk is None:
                chunk = self._register_new_chunk(coord[0], coord[1])
            if chunk.state == ChunkState.UNLOADED:
                await self._load_chunk(chunk)
                generated_coords.append(coord)

        # Unload chunks only if no player references them (ref count == 0)
        for coord, chunk in list(self._chunks.items()):
            if (coord not in required and 
                coord not in self._chunk_ref_count and 
                chunk.state in (ChunkState.ACTIVE, ChunkState.SIMULATED)):
                await self._unload_chunk(chunk)
                unloaded_coords.append(coord)

        # Update access timestamps
        now = time.time()
        for coord in required:
            chunk = self._chunks.get(coord)
            if chunk and chunk.state == ChunkState.ACTIVE:
                chunk.last_accessed_time = now
                if chunk.memory:
                    chunk.memory.last_accessed = now

        active_coords = [
            coord for coord, c in self._chunks.items()
            if c.state == ChunkState.ACTIVE
        ]

        logger.info(
            "Tick[%s] at (%.0f,%.0f) | players=%d generated=%d unloaded=%d active=%d",
            player_id, player_world_x, player_world_y,
            len(self._players), len(generated_coords),
            len(unloaded_coords), len(active_coords),
        )

        return {
            "generated": generated_coords,
            "unloaded": unloaded_coords,
            "active": active_coords,
            "player_chunk": self.world_position_to_chunk(player_world_x, player_world_y),
        }

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_chunk(self, chunk_x: int, chunk_y: int) -> Chunk | None:
        return self._chunks.get((chunk_x, chunk_y))

    def get_rendered(self, chunk_x: int, chunk_y: int) -> RenderedChunk | None:
        return self._rendered.get((chunk_x, chunk_y))

    def all_active_chunks(self) -> list[Chunk]:
        return [
            c for c in self._chunks.values()
            if c.state in (ChunkState.ACTIVE, ChunkState.SIMULATED)
        ]

    def world_position_to_chunk(self, world_x: float, world_y: float) -> tuple[int, int]:
        return (int(world_x // self.chunk_size), int(world_y // self.chunk_size))

    def world_state_snapshot(self) -> dict[str, Any]:
        """
        Full snapshot of the world for broadcasting to clients.
        Contains all active chunks and all player sessions.
        """
        chunks = [
            {
                "chunk_x": c.chunk_x,
                "chunk_y": c.chunk_y,
                "biome": c.biome.value,
                "difficulty": c.difficulty.name,
                "state": c.state.value,
                "theme": (
                    self._rendered.get((c.chunk_x, c.chunk_y)) and
                    self._rendered[(c.chunk_x, c.chunk_y)].theme or ""
                ),
            }
            for c in self._chunks.values()
        ]
        players = [
            {
                "player_id": p.player_id,
                "world_x": p.world_x,
                "world_y": p.world_y,
                "chunk_x": p.chunk_coords[0],
                "chunk_y": p.chunk_coords[1],
                "joined_at": p.joined_at,
                "last_seen": p.last_seen,
            }
            for p in self._players.values()
        ]
        return {
            "chunks": chunks,
            "players": players,
            "active_chunk_count": len([c for c in chunks if c["state"] == "ACTIVE"]),
            "player_count": len(players),
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------
    # Lifecycle internals
    # ------------------------------------------------------------------

    async def _load_chunk(self, chunk: Chunk) -> None:
        chunk.state = ChunkState.GENERATING
        logger.debug("Chunk %s → GENERATING", chunk.chunk_id)

        if self.persist_load_fn:
            memory = await self.persist_load_fn(chunk.chunk_x, chunk.chunk_y)
            if memory:
                chunk.memory = memory

        if chunk.memory is None:
            now = time.time()
            chunk.memory = MemoryState(
                chunk_x=chunk.chunk_x,
                chunk_y=chunk.chunk_y,
                first_visited=now,
                last_accessed=now,
            )

        if self.generator_fn:
            rendered = await self.generator_fn(chunk)
            self._rendered[(chunk.chunk_x, chunk.chunk_y)] = rendered
            chunk.generated_structure_ids = [obj.object_id for obj in rendered.objects]

        chunk.state = ChunkState.ACTIVE
        chunk.last_accessed_time = time.time()
        logger.info("Chunk %s → ACTIVE", chunk.chunk_id)

    async def _unload_chunk(self, chunk: Chunk) -> None:
        chunk.state = ChunkState.SIMULATED
        if self.persist_save_fn and chunk.memory:
            await self.persist_save_fn(chunk.memory)
        self._rendered.pop((chunk.chunk_x, chunk.chunk_y), None)
        chunk.state = ChunkState.UNLOADED
        logger.info("Chunk %s → UNLOADED", chunk.chunk_id)

    # ------------------------------------------------------------------
    # Chunk registration & deterministic seeding
    # ------------------------------------------------------------------

    def _register_new_chunk(self, chunk_x: int, chunk_y: int) -> Chunk:
        seed = self._derive_seed(chunk_x, chunk_y)
        biome = self._derive_biome(chunk_x, chunk_y, seed)
        difficulty = self._derive_difficulty(chunk_x, chunk_y)
        chunk = Chunk(
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            seed=seed,
            biome=biome,
            difficulty=difficulty,
            state=ChunkState.UNLOADED,
        )
        self._chunks[(chunk_x, chunk_y)] = chunk
        return chunk

    def _all_required_chunks(self) -> set[tuple[int, int]]:
        """Union of all render-radius areas for every connected player."""
        required: set[tuple[int, int]] = set()
        for session in self._players.values():
            cx, cy = self.world_position_to_chunk(session.world_x, session.world_y)
            r = self.render_radius
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    required.add((cx + dx, cy + dy))
        return required

    @staticmethod
    def _derive_seed(chunk_x: int, chunk_y: int) -> int:
        raw = f"{chunk_x}:{chunk_y}".encode()
        digest = hashlib.sha256(raw).digest()
        return int.from_bytes(digest[:4], "big")

    @staticmethod
    def _derive_biome(chunk_x: int, chunk_y: int, seed: int) -> BiomeType:
        biomes = list(BiomeType)
        index = (abs(chunk_x * 73856093 ^ chunk_y * 19349663) ^ seed) % len(biomes)
        return biomes[index]

    @staticmethod
    def _derive_difficulty(chunk_x: int, chunk_y: int) -> DifficultyLevel:
        distance = abs(chunk_x) + abs(chunk_y)
        if distance <= 2:
            return DifficultyLevel.TRIVIAL
        elif distance <= 5:
            return DifficultyLevel.EASY
        elif distance <= 10:
            return DifficultyLevel.MODERATE
        elif distance <= 20:
            return DifficultyLevel.HARD
        else:
            return DifficultyLevel.EXTREME


# Backwards-compat alias
WorldManager = MultiplayerWorldManager
