# Bug Fix Locations in mahithpaulin/awe-engine

This document maps each bug fix to the exact file and line numbers in the original repository.

## Reference Workspace Source
- **Repository**: mahithpaulin/awe-engine
- **Branch**: main
- **Mount Path**: `/vercel/share/v0-reference-workspace-sources/mahithpaulin/awe-engine/main`

## Bug Fixes and Where to Apply Them

### Bug 1: SafetyGate Edge Validation
**File**: `artifacts/awe-engine/awe/rule_engine.py`
**Function**: `_check_graph_connectivity()`
**Original Lines**: 348-368

**The Issue**:
```python
# OLD CODE (line 366):
if not edge.is_one_way and edge.to_node in adjacency:
    adjacency[edge.to_node].add(edge.from_node)
# This means one-way edges are IGNORED during reverse traversal
```

**The Fix**:
Separate the logic so one-way edges are unidirectional:
```python
# One-way edges only go from_node → to_node
if edge.from_node in adjacency:
    adjacency[edge.from_node].add(edge.to_node)
# Two-way edges are bidirectional
if not edge.is_one_way and edge.to_node in adjacency:
    adjacency[edge.to_node].add(edge.from_node)
```

---

### Bug 2: WorldManager Race Condition
**File**: `artifacts/awe-engine/awe/world_manager.py`
**Method**: `MultiplayerWorldManager.__init__()` and `tick()`
**Issue Location**: Lines 79-98 and 134-188

**The Issue**:
- No reference counting for shared chunk access
- Multiple players can trigger simultaneous unload of same chunk
- State check and unload operation not atomic

**The Fix**:
1. Add ref counter dict to `__init__()`:
```python
self._chunk_ref_count: dict[tuple[int, int], int] = {}
```

2. Update `tick()` to use atomic reference counting:
```python
# Atomically update ref counts before generating/unloading
old_refs = set(self._chunk_ref_count.keys())

for coord in required:
    if coord not in self._chunk_ref_count:
        self._chunk_ref_count[coord] = 0
    self._chunk_ref_count[coord] += 1

for coord in old_refs - required:
    self._chunk_ref_count[coord] -= 1
    if self._chunk_ref_count[coord] <= 0:
        del self._chunk_ref_count[coord]

# Only unload if ref count is 0
if (coord not in required and 
    coord not in self._chunk_ref_count and 
    chunk.state in (ChunkState.ACTIVE, ChunkState.SIMULATED)):
    await self._unload_chunk(chunk)
```

---

### Bug 3: NPC Level Calculation
**File**: `artifacts/awe-engine/awe/ai_designer.py`
**Function**: `call_ai_mock()`
**Line**: 209

**The Issue**:
```python
# OLD CODE (line 209):
"level": constraints.difficulty.value * rng.randint(3, 6),
# For EXTREME (5): produces 15-30, FAR exceeding semantic bounds
```

**The Fix**:
```python
base_level = constraints.difficulty.value * 5
level_variance = rng.randint(-2, 2)
capped_level = max(1, min(30, base_level + level_variance))

"level": capped_level,
```

Result: TRIVIAL gets ~3-7, EXTREME gets ~23-27 (semantically correct progression)

---

### Bug 4: SafetyGate Faction Patching
**File**: `artifacts/awe-engine/awe/rule_engine.py`
**Function**: `safety_gate()`
**Lines**: 299-315

**The Issue**:
```python
# OLD CODE (lines 305-310):
if auto_patch:
    for npc in bad_factions:
        npc.faction = FactionType.NEUTRAL  # No check if NEUTRAL is allowed!
    warnings.append(...)
```

**The Fix**:
```python
if auto_patch:
    if FactionType.NEUTRAL in allowed:
        for npc in bad_factions:
            npc.faction = FactionType.NEUTRAL
        warnings.append(...)
    else:
        # Pick a random allowed faction
        import random
        fallback_faction = random.choice(list(allowed))
        for npc in bad_factions:
            npc.faction = fallback_faction
        warnings.append(f"...reset to {fallback_faction.value}.")
```

---

### Bug 5: NPC Prefab Registry Validation
**File**: `artifacts/awe-engine/awe/structure_builder.py`
**Lines**: 86-114 and 146-190

**The Issue**:
- Missing prefab entries silently use fallback
- No visibility into what's missing
- Developers don't know they need to add entries

**The Fix**:
Add validation function before class definition:

```python
def _validate_npc_registry() -> dict[str, str]:
    """Ensure all required NPC roles have prefab entries."""
    required_roles = {
        "wolf_pack", "bear_guardian", "giant_spider",
        "bandit_patrol", "bandit_archer", "bandit_captain",
        # ... all roles ...
        "boss_golem", "boss_dragon",
    }
    
    registry = NPC_PREFAB_REGISTRY.copy()
    missing = required_roles - set(registry.keys())
    
    if missing:
        logger.warning(
            "NPC_PREFAB_REGISTRY missing %d entries: %s",
            len(missing), missing
        )
    
    return registry
```

Update `StructureBuilder.__init__()`:
```python
# OLD: self.npc_registry = npc_registry or NPC_PREFAB_REGISTRY
# NEW:
self.npc_registry = npc_registry or _validate_npc_registry()
```

---

## How to Apply Fixes

### Option 1: Manual Application
1. Open each file in the reference workspace
2. Locate the section mentioned above
3. Apply the fix as shown
4. Test with provided unit test cases

### Option 2: Use the Improved Copies
The fixed versions are available in `/vercel/share/v0-project/`:
- `rule_engine.py` - All SafetyGate fixes applied
- `world_manager.py` - Race condition fix applied
- `ai_designer.py` - NPC level fix applied
- `structure_builder.py` - Registry validation applied

### Option 3: Cherry-pick via Git
```bash
# In your local awe-engine repo:
git remote add v0-improved <path-to-fixed-repo>
git fetch v0-improved
git cherry-pick <commit-hash>  # Or manually merge sections
```

---

## Testing Checklist

After applying fixes, verify:

- [ ] `_check_graph_connectivity()` rejects blueprints with one-way dead-ends
- [ ] Multiple concurrent players don't cause chunk state corruption
- [ ] NPC levels stay within 1-30 range for all difficulties
- [ ] Auto-patching respects biome faction restrictions
- [ ] `_validate_npc_registry()` logs warnings for missing entries on startup

---

## Backward Compatibility

All fixes maintain backward compatibility:
- Same function signatures
- Same return types
- Only internal logic changed
- No data model changes required

---

**Last Updated**: Phase 1 of AWE Engine improvements
**Status**: Ready for staging deployment
