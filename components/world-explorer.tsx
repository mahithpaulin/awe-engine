'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';

interface Chunk {
  chunk_x: number;
  chunk_y: number;
  biome: string;
  difficulty: string;
  state: string;
  theme: string;
}

interface WorldState {
  chunks: Chunk[];
  players: any[];
  active_chunk_count: number;
  player_count: number;
  timestamp: number;
}

const BIOME_COLORS: Record<string, string> = {
  forest: 'from-green-900 to-green-700',
  desert: 'from-yellow-900 to-yellow-700',
  tundra: 'from-blue-900 to-blue-700',
  swamp: 'from-purple-900 to-purple-700',
  volcanic: 'from-red-900 to-red-700',
  ruins: 'from-gray-900 to-gray-700',
  ocean: 'from-cyan-900 to-cyan-700',
  plains: 'from-amber-900 to-amber-700',
};

const DIFFICULTY_COLORS: Record<string, string> = {
  TRIVIAL: 'text-green-400',
  EASY: 'text-blue-400',
  MODERATE: 'text-yellow-400',
  HARD: 'text-orange-400',
  EXTREME: 'text-red-400',
};

export default function WorldExplorer({ worldState }: { worldState: WorldState }) {
  const [selectedChunk, setSelectedChunk] = useState<Chunk | null>(null);

  const getChunkGrid = () => {
    if (!worldState?.chunks) return [];
    
    const xs = worldState.chunks.map((c) => c.chunk_x);
    const ys = worldState.chunks.map((c) => c.chunk_y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const chunkMap = new Map(worldState.chunks.map((c) => [`${c.chunk_x},${c.chunk_y}`, c]));

    const grid = [];
    for (let y = maxY; y >= minY; y--) {
      const row = [];
      for (let x = minX; x <= maxX; x++) {
        const chunk = chunkMap.get(`${x},${y}`);
        row.push({ x, y, chunk });
      }
      grid.push(row);
    }
    return grid;
  };

  const grid = getChunkGrid();

  return (
    <div className="grid gap-6 md:grid-cols-3">
      {/* World Grid Visualization */}
      <div className="md:col-span-2">
        <Card className="glass-card p-6">
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-primary animate-pulse" />
            World Chunks
          </h2>

          <div className="space-y-4">
            {/* Grid */}
            <div className="overflow-auto">
              <div className="inline-block">
                {grid.map((row, rowIdx) => (
                  <div key={rowIdx} className="flex gap-2">
                    {row.map((cell, colIdx) => (
                      <div
                        key={`${cell.x},${cell.y}`}
                        onClick={() => setSelectedChunk(cell.chunk || null)}
                        className={`w-16 h-16 rounded border-2 transition-all cursor-pointer flex flex-col items-center justify-center text-xs font-medium ${
                          cell.chunk
                            ? `bg-gradient-to-br ${BIOME_COLORS[cell.chunk.biome] || 'from-gray-800 to-gray-700'} border-accent/40 hover:border-accent`
                            : 'bg-card/40 border-border/50 opacity-30'
                        } ${
                          selectedChunk?.chunk_x === cell.x && selectedChunk?.chunk_y === cell.y
                            ? 'ring-2 ring-primary'
                            : ''
                        }`}
                      >
                        {cell.chunk && (
                          <>
                            <div className="font-bold">{cell.chunk.chunk_x},{cell.chunk.chunk_y}</div>
                            <div className={`text-xs ${DIFFICULTY_COLORS[cell.chunk.difficulty]}`}>
                              {cell.chunk.difficulty[0]}
                            </div>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-3 pt-4 border-t border-accent/20">
              <div className="text-center">
                <div className="text-2xl font-bold text-primary">{worldState.active_chunk_count}</div>
                <div className="text-xs text-muted-foreground">Active Chunks</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-secondary">{worldState.player_count}</div>
                <div className="text-xs text-muted-foreground">Players</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-accent">{worldState.chunks.length}</div>
                <div className="text-xs text-muted-foreground">Total Chunks</div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Chunk Details Panel */}
      <div>
        <Card className="glass-card p-6 sticky top-32">
          <h3 className="text-lg font-bold mb-4">Chunk Details</h3>
          {selectedChunk ? (
            <div className="space-y-3 text-sm">
              <div>
                <div className="text-muted-foreground">Coordinates</div>
                <div className="font-mono font-bold">{selectedChunk.chunk_x}, {selectedChunk.chunk_y}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Biome</div>
                <div className="font-bold capitalize">{selectedChunk.biome}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Difficulty</div>
                <div className={`font-bold ${DIFFICULTY_COLORS[selectedChunk.difficulty]}`}>
                  {selectedChunk.difficulty}
                </div>
              </div>
              <div>
                <div className="text-muted-foreground">State</div>
                <div className="font-mono text-xs bg-card/50 p-2 rounded border border-accent/20">
                  {selectedChunk.state}
                </div>
              </div>
              {selectedChunk.theme && (
                <div>
                  <div className="text-muted-foreground">Theme</div>
                  <div className="text-xs">{selectedChunk.theme}</div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Select a chunk to view details
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
