'use client';

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useState } from 'react';

export default function EventLog({ events }: { events: any[] }) {
  const [filter, setFilter] = useState<string | null>(null);

  const eventTypes = ['chunk_generated', 'chunk_unloaded', 'player_joined', 'player_left', 'validation'];
  const filteredEvents = filter ? events.filter((e) => e.type === filter) : events;

  const getEventColor = (type: string) => {
    const colors: Record<string, string> = {
      chunk_generated: 'bg-green-500/20 text-green-400 border-green-500/30',
      chunk_unloaded: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
      player_joined: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
      player_left: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
      validation: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
    };
    return colors[type] || 'bg-muted/20 text-muted-foreground border-muted/30';
  };

  return (
    <div className="space-y-6">
      {/* Filters */}
      <Card className="glass-card p-6">
        <h3 className="text-lg font-bold mb-4">Event Filters</h3>
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={() => setFilter(null)}
            variant={filter === null ? 'default' : 'outline'}
            className={`text-xs ${
              filter === null
                ? 'bg-primary text-primary-foreground'
                : 'bg-card/50 border-accent/20 text-muted-foreground hover:text-foreground'
            }`}
          >
            All Events
          </Button>
          {eventTypes.map((type) => (
            <Button
              key={type}
              onClick={() => setFilter(type)}
              variant={filter === type ? 'default' : 'outline'}
              className={`text-xs ${
                filter === type
                  ? 'bg-accent text-accent-foreground'
                  : 'bg-card/50 border-accent/20 text-muted-foreground hover:text-foreground'
              }`}
            >
              {type.replace(/_/g, ' ')}
            </Button>
          ))}
        </div>
      </Card>

      {/* Events List */}
      <Card className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold">Real-time Events</h3>
          <div className="text-xs text-muted-foreground">{filteredEvents.length} events</div>
        </div>

        <div className="space-y-2 max-h-[600px] overflow-y-auto">
          {filteredEvents.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              {filter ? `No ${filter.replace(/_/g, ' ')} events yet` : 'No events yet'}
            </div>
          ) : (
            filteredEvents.map((event, idx) => (
              <div key={idx} className="flex items-start gap-3 p-3 rounded border border-accent/10 bg-card/30">
                <div className={`text-xs px-2 py-1 rounded border ${getEventColor(event.type)} whitespace-nowrap`}>
                  {event.type.replace(/_/g, ' ')}
                </div>
                <div className="flex-1 text-sm">
                  <div className="text-foreground">{event.message || 'Event occurred'}</div>
                  {event.data && (
                    <div className="text-xs text-muted-foreground mt-1 font-mono">
                      {JSON.stringify(event.data, null, 2)}
                    </div>
                  )}
                </div>
                <div className="text-xs text-muted-foreground whitespace-nowrap">
                  {event.timestamp
                    ? new Date(event.timestamp * 1000).toLocaleTimeString()
                    : 'now'}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
