type MessageHandler = (data: any) => void;
type EventHandler = () => void;

export default class WebSocketManager {
  private ws: WebSocket | null = null;
  private url: string;
  private messageHandlers: Set<MessageHandler> = new Set();
  private connectHandlers: Set<EventHandler> = new Set();
  private disconnectHandlers: Set<EventHandler> = new Set();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;

  constructor(url: string) {
    this.url = url;
    this.connect();
  }

  private connect() {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('[v0] WebSocket connected');
        this.reconnectAttempts = 0;
        this.connectHandlers.forEach((handler) => handler());
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.messageHandlers.forEach((handler) => handler(data));
        } catch (err) {
          console.error('[v0] Failed to parse message:', err);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[v0] WebSocket error:', error);
      };

      this.ws.onclose = () => {
        console.log('[v0] WebSocket disconnected');
        this.disconnectHandlers.forEach((handler) => handler());
        this.attemptReconnect();
      };
    } catch (err) {
      console.error('[v0] Failed to create WebSocket:', err);
      this.attemptReconnect();
    }
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(
        `[v0] Reconnecting in ${this.reconnectDelay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
      );
      setTimeout(() => this.connect(), this.reconnectDelay);
    }
  }

  onMessage(handler: MessageHandler) {
    this.messageHandlers.add(handler);
  }

  onConnect(handler: EventHandler) {
    this.connectHandlers.add(handler);
  }

  onDisconnect(handler: EventHandler) {
    this.disconnectHandlers.add(handler);
  }

  send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.warn('[v0] WebSocket not connected, message not sent');
    }
  }

  close() {
    this.ws?.close();
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
