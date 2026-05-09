'use client';

import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import WorldExplorer from '@/components/world-explorer';
import AdminPanel from '@/components/admin-panel';
import EventLog from '@/components/event-log';
import WebSocketManager from '@/lib/websocket-manager';

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<'explorer' | 'admin' | 'logs'>('explorer');
  const [worldState, setWorldState] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocketManager('ws://localhost:8000/ws');

    ws.onMessage((data) => {
      if (data.type === 'world_state') {
        setWorldState(data.payload);
      } else if (data.type === 'event') {
        setEvents((prev) => [data.payload, ...prev.slice(0, 99)]);
      }
    });

    ws.onConnect(() => setConnected(true));
    ws.onDisconnect(() => setConnected(false));

    return () => ws.close();
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-accent/20 bg-card/40 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-gradient-to-br from-primary to-secondary" />
            <h1 className="text-2xl font-bold text-balance">AWE Engine Dashboard</h1>
          </div>
          <div className="flex items-center gap-3">
            <div className={`text-xs px-3 py-1 rounded-full ${
              connected 
                ? 'bg-green-500/20 text-green-400 border border-green-500/30' 
                : 'bg-red-500/20 text-red-400 border border-red-500/30'
            }`}>
              {connected ? 'Connected' : 'Disconnected'}
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="border-b border-accent/20 bg-card/20 backdrop-blur-md sticky top-16 z-40">
        <div className="max-w-7xl mx-auto px-4 flex gap-2 py-3">
          {(['explorer', 'admin', 'logs'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card/50 text-muted-foreground hover:text-foreground border border-accent/20'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {activeTab === 'explorer' && worldState && (
          <WorldExplorer worldState={worldState} />
        )}
        {activeTab === 'admin' && (
          <AdminPanel worldState={worldState} />
        )}
        {activeTab === 'logs' && (
          <EventLog events={events} />
        )}
      </main>
    </div>
  );
}
