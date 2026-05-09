# AWE Engine - Improved Version

This is an enhanced version of the AWE Engine with critical bug fixes and a modern React admin dashboard.

## What's Fixed

### Backend Bugs Fixed

1. **SafetyGate Edge Validation (rule_engine.py)**
   - Fixed graph connectivity check that was treating one-way edges as bidirectional
   - Now properly validates that one-way edges don't create unreachable nodes
   - Prevents invalid blueprints from passing validation

2. **WorldManager Race Condition (world_manager.py)**
   - Added reference counter mechanism for chunk lifecycle management
   - Prevents simultaneous unload attempts from multiple players
   - Ensures chunks only unload when ALL players have moved out of range
   - Atomic reference counting prevents state inconsistency

3. **NPC Level Calculation (ai_designer.py)**
   - Fixed NPC level overflow for high difficulties
   - Changed from `difficulty * random(3, 6)` to capped `max(1, min(30, difficulty * 5 + variance))`
   - Ensures semantic correctness for progression scaling

4. **SafetyGate Faction Patching (rule_engine.py)**
   - Added validation that NEUTRAL is allowed before patching hostile factions
   - Falls back to random allowed faction if NEUTRAL is forbidden
   - Prevents creating invalid blueprints during auto-patch

5. **NPC Prefab Registry Validation (structure_builder.py)**
   - Added `_validate_npc_registry()` function to detect missing prefab entries
   - Logs warnings at startup for any missing entries
   - Gracefully falls back to placeholder prefabs at runtime

## New React Dashboard

A modern admin interface for monitoring and testing the AWE Engine:

### Features

- **World Explorer**: Interactive chunk grid visualization
  - Real-time chunk state display with biome colors
  - Difficulty indicators
  - Click to view chunk details
  - Live player positions
  - Performance metrics

- **Admin Panel**: Control and testing tools
  - Manual chunk spawning at specific coordinates
  - Multiplayer simulation testbed (1-10 concurrent players)
  - Performance metrics dashboard
  - Blueprint inspector

- **Event Log**: Real-time system events
  - Filter by event type
  - Timestamp tracking
  - Event data inspection
  - Up to 100 events in memory

- **Real-time WebSocket**: Live updates
  - Automatic reconnection with exponential backoff
  - Handles connection loss gracefully
  - Type-safe message handling

### Design

- **Dark Tech Aesthetic**: Matches modern game dev tools
- **Cyan/Teal Accents**: Primary color scheme for high visibility
- **Glass Morphism**: Frosted glass cards with backdrop blur
- **Responsive Grid**: Works on desktop, tablet, and mobile
- **Performance Optimized**: Uses client-side state management

## Tech Stack

- **Frontend**: React 19 + TypeScript
- **Styling**: Tailwind CSS with custom dark theme
- **State**: Client-side with WebSocket sync
- **Components**: shadcn/ui
- **API**: WebSocket for real-time updates

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.8+ (for backend)

### Backend Setup

```bash
cd artifacts/awe-engine
pip install -r requirements.txt
python main.py
```

### Frontend Setup

```bash
cd /vercel/share/v0-project
pnpm install
pnpm dev
```

The dashboard will be available at `http://localhost:3000`

## API Endpoints

### WebSocket

- `ws://localhost:8000/ws` - Main WebSocket connection for real-time updates

### REST API (to be implemented)

- `POST /api/chunks/spawn` - Manually spawn a chunk
- `POST /api/simulation/start` - Start multiplayer simulation
- `GET /api/world/state` - Get current world state
- `GET /api/blueprints/:id` - View blueprint details

## File Structure

```
├── app/
│   ├── globals.css          # Dark tech theme
│   ├── layout.tsx           # Root layout
│   └── page.tsx             # Dashboard page
├── components/
│   ├── world-explorer.tsx   # Chunk grid visualization
│   ├── admin-panel.tsx      # Control panel
│   └── event-log.tsx        # Event stream
├── lib/
│   └── websocket-manager.ts # WebSocket client with reconnect logic
└── rule_engine.py           # Fixed SafetyGate validation
```

## Future Improvements

- [ ] Blueprint editor with visual graph layout
- [ ] Real-time performance profiling
- [ ] Chunk generation history and replay
- [ ] Custom rule engine testing
- [ ] Export/import world states
- [ ] Multi-world management

## Known Limitations

- WebSocket connection assumes localhost during development
- Event log limited to 100 most recent events
- Chunk grid visual representation maxes at ~1000 chunks for performance
- Admin simulation currently supports up to 10 concurrent players

## Support

For issues or questions about the improvements, refer to:
- Bug fixes: Check inline comments in fixed Python files
- Frontend: See component documentation in React files
- Architecture: Review the plan document for design decisions
