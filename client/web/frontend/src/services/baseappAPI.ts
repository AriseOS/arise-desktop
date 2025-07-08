import axios from 'axios';

const BASEAPP_API_URL = process.env.REACT_APP_BASEAPP_API_URL || 'http://localhost:8888';

const baseappAPI = axios.create({
  baseURL: BASEAPP_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器：添加认证token（如果需要）
baseappAPI.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器：处理错误
baseappAPI.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('BaseApp API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// 类型定义
export interface BaseAppChatRequest {
  message: string;
  session_id?: string;
  user_id: string;
}

export interface BaseAppChatResponse {
  success: boolean;
  response: string;
  session_id: string;
  user_id: string;
  timestamp: string;
  message_id?: string;
}

export interface BaseAppSessionRequest {
  user_id: string;
  title?: string;
}

export interface BaseAppSessionInfo {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface BaseAppSessionListResponse {
  sessions: BaseAppSessionInfo[];
  total: number;
}

export interface BaseAppMessage {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: string;
}

export interface BaseAppSessionHistoryResponse {
  session_id: string;
  messages: BaseAppMessage[];
  total: number;
}

export interface BaseAppOperationResponse {
  success: boolean;
  message: string;
  timestamp: string;
}

export const baseappService = {
  // 发送消息
  sendMessage: async (data: BaseAppChatRequest): Promise<BaseAppChatResponse> => {
    const response = await baseappAPI.post('/api/v1/chat/message', data);
    return response.data;
  },

  // 创建新会话
  createSession: async (data: BaseAppSessionRequest): Promise<BaseAppSessionInfo> => {
    const response = await baseappAPI.post('/api/v1/chat/session', data);
    return response.data;
  },

  // 获取会话列表
  getSessions: async (userId: string): Promise<BaseAppSessionListResponse> => {
    const response = await baseappAPI.get(`/api/v1/chat/sessions?user_id=${userId}`);
    return response.data;
  },

  // 获取会话历史
  getSessionHistory: async (sessionId: string, limit: number = 50): Promise<BaseAppSessionHistoryResponse> => {
    const response = await baseappAPI.get(`/api/v1/chat/sessions/${sessionId}/history?limit=${limit}`);
    return response.data;
  },

  // 删除会话
  deleteSession: async (sessionId: string, userId: string): Promise<BaseAppOperationResponse> => {
    const response = await baseappAPI.delete(`/api/v1/chat/sessions/${sessionId}?user_id=${userId}`);
    return response.data;
  },

  // 获取会话信息
  getSessionInfo: async (sessionId: string): Promise<BaseAppSessionInfo> => {
    const response = await baseappAPI.get(`/api/v1/chat/sessions/${sessionId}`);
    return response.data;
  },

  // 健康检查
  healthCheck: async (): Promise<{ status: string; service: string; version: string }> => {
    const response = await baseappAPI.get('/health');
    return response.data;
  },
};