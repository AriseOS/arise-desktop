import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8888';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// API 服务
export const apiService = {
  // 发送消息
  async sendMessage(message, sessionId = null, userId = 'default-user') {
    try {
      const response = await api.post('/api/v1/chat/message', {
        message,
        session_id: sessionId,
        user_id: userId,
      });
      return response.data;
    } catch (error) {
      console.error('发送消息失败:', error);
      throw error;
    }
  },

  // 创建新会话
  async createSession(userId = 'default-user', title = '') {
    try {
      const response = await api.post('/api/v1/chat/session', {
        user_id: userId,
        title: title || '新对话',
      });
      return response.data;
    } catch (error) {
      console.error('创建会话失败:', error);
      throw error;
    }
  },

  // 获取会话列表
  async getSessions(userId = 'default-user') {
    try {
      const response = await api.get(`/api/v1/chat/sessions?user_id=${userId}`);
      return response.data;
    } catch (error) {
      console.error('获取会话列表失败:', error);
      throw error;
    }
  },

  // 获取会话历史
  async getSessionHistory(sessionId, limit = 50) {
    try {
      const response = await api.get(`/api/v1/chat/sessions/${sessionId}/history?limit=${limit}`);
      return response.data;
    } catch (error) {
      console.error('获取会话历史失败:', error);
      throw error;
    }
  },

  // 删除会话
  async deleteSession(sessionId, userId = 'default-user') {
    try {
      const response = await api.delete(`/api/v1/chat/sessions/${sessionId}?user_id=${userId}`);
      return response.data;
    } catch (error) {
      console.error('删除会话失败:', error);
      throw error;
    }
  },

  // 获取会话信息
  async getSessionInfo(sessionId) {
    try {
      const response = await api.get(`/api/v1/chat/sessions/${sessionId}`);
      return response.data;
    } catch (error) {
      console.error('获取会话信息失败:', error);
      throw error;
    }
  },
};

export default api;