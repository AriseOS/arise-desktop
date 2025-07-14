import axios from 'axios';
import { agentGateway } from './agentGateway';
import { agentBackendAPI } from './agentBackendAPI';

// Agent管理API服务
export interface AgentInfo {
  agent_id: string;
  user_id: number;
  port: number;
  name: string;
  type: 'baseapp' | 'custom';
  status: 'running' | 'stopped' | 'error';
  config?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRequest {
  name: string;
  type: 'baseapp' | 'custom';
  config?: Record<string, any>;
}

const AGENT_API_BASE = import.meta.env.VITE_AGENT_API_URL || 'http://localhost:8000/api';

const agentAPI = axios.create({
  baseURL: AGENT_API_BASE,
  timeout: 10000,
});

// 请求拦截器：添加认证token
agentAPI.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：处理错误
agentAPI.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token过期，重定向到登录页
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

/**
 * Agent管理API
 */
export const agentService = {
  // 获取用户的所有Agent
  async getUserAgents(userId: string): Promise<AgentInfo[]> {
    try {
      return await agentBackendAPI.getUserAgents(parseInt(userId));
    } catch (error) {
      console.error('[AgentAPI] getUserAgents failed:', error);
      throw error;
    }
  },

  // 获取特定Agent信息
  async getAgentInfo(userId: string, agentId: string): Promise<AgentInfo> {
    try {
      const agent = await agentBackendAPI.getAgentInfo(agentId, parseInt(userId));
      if (!agent) {
        throw new Error(`Agent '${agentId}' not found`);
      }
      return agent;
    } catch (error) {
      console.error('[AgentAPI] getAgentInfo failed:', error);
      throw error;
    }
  },

  // 创建新Agent
  async createAgent(userId: string, agentData: CreateAgentRequest): Promise<AgentInfo> {
    try {
      return await agentBackendAPI.createAgent(parseInt(userId), agentData);
    } catch (error) {
      console.error('[AgentAPI] createAgent failed:', error);
      throw error;
    }
  },

  // 启动Agent
  async startAgent(userId: string, agentId: string): Promise<void> {
    try {
      await agentBackendAPI.startAgent(agentId, parseInt(userId));
    } catch (error) {
      console.error('[AgentAPI] startAgent failed:', error);
      throw error;
    }
  },

  // 停止Agent
  async stopAgent(userId: string, agentId: string): Promise<void> {
    try {
      await agentBackendAPI.stopAgent(agentId, parseInt(userId));
    } catch (error) {
      console.error('[AgentAPI] stopAgent failed:', error);
      throw error;
    }
  },

  // 删除Agent
  async deleteAgent(userId: string, agentId: string): Promise<void> {
    try {
      await agentBackendAPI.deleteAgent(agentId, parseInt(userId));
    } catch (error) {
      console.error('[AgentAPI] deleteAgent failed:', error);
      throw error;
    }
  },

  // 更新Agent
  async updateAgent(userId: string, agentId: string, updates: Partial<Pick<AgentInfo, 'name' | 'config'>>): Promise<AgentInfo> {
    try {
      return await agentBackendAPI.updateAgent(agentId, parseInt(userId), updates);
    } catch (error) {
      console.error('[AgentAPI] updateAgent failed:', error);
      throw error;
    }
  },

  // 代理Agent API请求 - 使用新的网关转发机制
  async proxyAgentRequest(
    userId: string, 
    agentId: string, 
    path: string, 
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
    data?: any,
    params?: any
  ): Promise<any> {
    // 确保网关已初始化
    await agentGateway.initialize();
    
    // 使用网关转发请求
    const response = await agentGateway.forwardRequest({
      userId,
      agentId,
      apiPath: path.startsWith('/') ? path : `/${path}`,
      method,
      data,
      params
    });
    
    if (!response.success) {
      throw new Error(response.error || 'Agent request failed');
    }
    
    return response.data;
  },

  // 获取Agent状态
  async getAgentStatus(agentId: string): Promise<any> {
    try {
      return await agentBackendAPI.getAgentStatus(agentId);
    } catch (error) {
      console.error('[AgentAPI] getAgentStatus failed:', error);
      throw error;
    }
  },

  // 网关健康检查
  async getGatewayHealth(): Promise<any> {
    await agentGateway.initialize();
    return agentGateway.healthCheck();
  },

  // 获取系统统计信息
  async getSystemStats(): Promise<any> {
    try {
      return await agentBackendAPI.getSystemStats();
    } catch (error) {
      console.error('[AgentAPI] getSystemStats failed:', error);
      throw error;
    }
  }
};

/**
 * Agent专属API代理
 * 用于在统一路由下访问Agent的后端API
 */
export class AgentAPIProxy {
  constructor(private userId: string, private agentId: string) {}

  async get(path: string, params?: any) {
    return agentService.proxyAgentRequest(this.userId, this.agentId, path, 'GET', undefined, params);
  }

  async post(path: string, data: any, params?: any) {
    return agentService.proxyAgentRequest(this.userId, this.agentId, path, 'POST', data, params);
  }

  async put(path: string, data: any, params?: any) {
    return agentService.proxyAgentRequest(this.userId, this.agentId, path, 'PUT', data, params);
  }

  async delete(path: string, params?: any) {
    return agentService.proxyAgentRequest(this.userId, this.agentId, path, 'DELETE', undefined, params);
  }
}

/**
 * 创建BaseApp专用的API代理
 * 用于兼容现有的BaseApp服务调用
 */
export const createBaseAppAPIProxy = (userId: string, agentId: string = 'baseapp') => {
  const proxy = new AgentAPIProxy(userId, agentId);
  
  return {
    // BaseApp特定的API方法
    sendMessage: (data: any) => proxy.post('/api/v1/chat/message', data),
    createSession: (data: any) => proxy.post('/api/v1/chat/session', data),
    getSessions: (params: any) => proxy.get('/api/v1/chat/sessions', params),
    getSessionHistory: (sessionId: string, params: any) => proxy.get(`/api/v1/chat/sessions/${sessionId}/history`, params),
    deleteSession: (sessionId: string, params: any) => proxy.delete(`/api/v1/chat/sessions/${sessionId}`, params),
    getSessionInfo: (sessionId: string) => proxy.get(`/api/v1/chat/sessions/${sessionId}`),
    healthCheck: () => proxy.get('/health'),
    
    // 通用代理方法
    get: proxy.get.bind(proxy),
    post: proxy.post.bind(proxy),
    put: proxy.put.bind(proxy),
    delete: proxy.delete.bind(proxy)
  };
};

export default agentService;