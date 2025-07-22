// WebSocket 服务类
export class WebSocketService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 3000;
  private url: string;
  private onMessageCallback?: (data: any) => void;
  private onErrorCallback?: (error: any) => void;
  private onCloseCallback?: () => void;

  constructor(url: string) {
    this.url = url;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
          console.log(`✅ WebSocket 连接已建立: ${this.url}`);
          this.reconnectAttempts = 0;
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (this.onMessageCallback) {
              this.onMessageCallback(data);
            }
          } catch (error) {
            console.error('解析 WebSocket 消息失败:', error);
          }
        };

        this.ws.onerror = (error) => {
          console.error(`❌ WebSocket 错误: ${this.url}`, error);
          if (this.onErrorCallback) {
            this.onErrorCallback(error);
          }
          reject(error);
        };

        this.ws.onclose = () => {
          console.log(`🔌 WebSocket 连接已关闭: ${this.url}`);
          if (this.onCloseCallback) {
            this.onCloseCallback();
          }
          this.attemptReconnect();
        };

      } catch (error) {
        reject(error);
      }
    });
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.warn('WebSocket 未连接，无法发送消息');
    }
  }

  onMessage(callback: (data: any) => void) {
    this.onMessageCallback = callback;
  }

  onError(callback: (error: any) => void) {
    this.onErrorCallback = callback;
  }

  onClose(callback: () => void) {
    this.onCloseCallback = callback;
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`🔄 尝试重连 WebSocket (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        this.connect().catch(error => {
          console.error('重连失败:', error);
        });
      }, this.reconnectInterval);
    } else {
      console.error('❌ WebSocket 重连失败，已达到最大重试次数');
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// 构建进度 WebSocket 服务
export class BuildProgressWebSocket extends WebSocketService {
  constructor(buildId: string) {
    const wsUrl = `ws://localhost:8000/ws/agents/build/${buildId}`;
    super(wsUrl);
  }

  sendPing() {
    this.send({ action: 'ping' });
  }
}

// Agent 对话 WebSocket 服务  
export class AgentChatWebSocket extends WebSocketService {
  constructor(agentId: string) {
    const wsUrl = `ws://localhost:8000/ws/agents/${agentId}/chat`;
    super(wsUrl);
  }

  sendMessage(message: string) {
    this.send({
      type: 'chat',
      message: message,
      timestamp: new Date().toISOString()
    });
  }
}