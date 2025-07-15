import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器：添加认证token
api.interceptors.request.use(
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

// 响应拦截器：处理401错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Agent 构建相关接口类型定义
export interface AgentBuildRequest {
  description: string;
  agent_name?: string;
}

export interface AgentBuildResponse {
  build_id: string;
  status: string;
  message: string;
}

export interface BuildStatusResponse {
  build_id: string;
  status: string;
  current_step?: string;
  progress_message?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface AgentInfo {
  agent_id: string;
  name: string;
  description: string;
  capabilities: string[];
  workflow_data: any;
  cost_analysis: string;
  created_at: string;
}

export interface AgentListItem {
  agent_id: string;
  name: string;
  description: string;
  cost_analysis: string;
  created_at: string;
}

export interface WorkflowResponse {
  agent_id: string;
  workflow: any;
  metadata: {
    name: string;
    description: string;
    capabilities: string[];
    cost_analysis: string;
  };
}

export const agentBuildAPI = {
  // 开始构建 Agent
  buildAgent: async (request: AgentBuildRequest): Promise<AgentBuildResponse> => {
    const response = await api.post('/api/agents/build', request);
    return response.data;
  },

  // 获取构建状态
  getBuildStatus: async (buildId: string): Promise<BuildStatusResponse> => {
    const response = await api.get(`/api/agents/build/${buildId}/status`);
    return response.data;
  },

  // 获取 Agent 信息
  getAgentInfo: async (agentId: string): Promise<AgentInfo> => {
    const response = await api.get(`/api/agents/${agentId}`);
    return response.data;
  },

  // 列出用户的所有 Agent
  listUserAgents: async (): Promise<AgentListItem[]> => {
    const response = await api.get('/api/agents');
    return response.data;
  },

  // 获取 Agent 工作流
  getAgentWorkflow: async (agentId: string): Promise<WorkflowResponse> => {
    const response = await api.get(`/api/agents/${agentId}/workflow`);
    return response.data;
  },
};