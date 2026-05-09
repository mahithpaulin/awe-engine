'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function AdminPanel({ worldState }: { worldState: any }) {
  const [spawnChunkX, setSpawnChunkX] = useState('0');
  const [spawnChunkY, setSpawnChunkY] = useState('0');
  const [spawning, setSpawning] = useState(false);
  const [playerCount, setPlayerCount] = useState('1');
  const [simulating, setSimulating] = useState(false);

  const handleSpawnChunk = async () => {
    setSpawning(true);
    try {
      const response = await fetch('/api/chunks/spawn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chunk_x: parseInt(spawnChunkX),
          chunk_y: parseInt(spawnChunkY),
        }),
      });
      if (response.ok) {
        console.log('[v0] Chunk spawned successfully');
      }
    } catch (err) {
      console.error('[v0] Failed to spawn chunk:', err);
    } finally {
      setSpawning(false);
    }
  };

  const handleStartSimulation = async () => {
    setSimulating(true);
    try {
      const response = await fetch('/api/simulation/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          player_count: parseInt(playerCount),
        }),
      });
      if (response.ok) {
        console.log('[v0] Simulation started');
      }
    } catch (err) {
      console.error('[v0] Failed to start simulation:', err);
    } finally {
      setSimulating(false);
    }
  };

  return (
    <div className="grid gap-6 md:grid-cols-2">
      {/* Chunk Spawner */}
      <Card className="glass-card p-6">
        <h3 className="text-lg font-bold mb-4">Manual Chunk Spawn</h3>
        <div className="space-y-4">
          <div className="grid gap-3">
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Chunk X</label>
              <Input
                type="number"
                value={spawnChunkX}
                onChange={(e) => setSpawnChunkX(e.target.value)}
                placeholder="0"
                className="bg-input border-accent/30"
              />
            </div>
            <div>
              <label className="text-sm text-muted-foreground mb-2 block">Chunk Y</label>
              <Input
                type="number"
                value={spawnChunkY}
                onChange={(e) => setSpawnChunkY(e.target.value)}
                placeholder="0"
                className="bg-input border-accent/30"
              />
            </div>
          </div>
          <Button
            onClick={handleSpawnChunk}
            disabled={spawning}
            className="w-full bg-primary hover:bg-primary/80 text-primary-foreground"
          >
            {spawning ? 'Spawning...' : 'Spawn Chunk'}
          </Button>
        </div>
      </Card>

      {/* Multiplayer Simulation */}
      <Card className="glass-card p-6">
        <h3 className="text-lg font-bold mb-4">Multiplayer Testbed</h3>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-muted-foreground mb-2 block">Number of Players</label>
            <Input
              type="number"
              min="1"
              max="10"
              value={playerCount}
              onChange={(e) => setPlayerCount(e.target.value)}
              className="bg-input border-accent/30"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Simulate concurrent players moving through the world and testing chunk loading/unloading behavior.
          </p>
          <Button
            onClick={handleStartSimulation}
            disabled={simulating}
            className="w-full bg-secondary hover:bg-secondary/80 text-secondary-foreground"
          >
            {simulating ? 'Starting...' : 'Start Simulation'}
          </Button>
        </div>
      </Card>

      {/* Performance Metrics */}
      <Card className="glass-card p-6 md:col-span-2">
        <h3 className="text-lg font-bold mb-4">Performance Metrics</h3>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="text-center">
            <div className="text-3xl font-bold text-primary">{worldState?.active_chunk_count || 0}</div>
            <div className="text-xs text-muted-foreground mt-1">Active Chunks</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-secondary">{worldState?.player_count || 0}</div>
            <div className="text-xs text-muted-foreground mt-1">Connected Players</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-accent">
              {worldState?.chunks?.length || 0}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Total Chunks</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-green-400">
              {worldState?.timestamp ? new Date(worldState.timestamp * 1000).toLocaleTimeString() : 'N/A'}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Last Update</div>
          </div>
        </div>
      </Card>

      {/* Blueprint Editor Preview */}
      <Card className="glass-card p-6 md:col-span-2">
        <h3 className="text-lg font-bold mb-4">Blueprint Inspector</h3>
        <p className="text-sm text-muted-foreground mb-4">
          View and validate generated blueprints from the AI designer. Check rule constraints, safety gate results, and structure placement.
        </p>
        <div className="bg-card/50 border border-accent/20 rounded p-4 min-h-[200px] font-mono text-xs">
          <div className="text-muted-foreground">
            Blueprint validation results will appear here when chunks are generated.
          </div>
        </div>
      </Card>
    </div>
  );
}
