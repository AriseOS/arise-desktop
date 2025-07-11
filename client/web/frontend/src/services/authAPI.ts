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

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: {
    id: number;
    username: string;
    email: string;
    full_name?: string;
    is_active: boolean;
    created_at: string;
  };
}

export interface UserResponse {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  created_at: string;
}

export const authAPI = {
  // 登录
  login: async (credentials: LoginRequest): Promise<AuthResponse> => {
    const response = await api.post('/api/login', credentials);
    return response.data;
  },

  // 注册
  register: async (userData: RegisterRequest): Promise<AuthResponse> => {
    const response = await api.post('/api/register', userData);
    return response.data;
  },

  // 获取当前用户信息
  getCurrentUser: async (): Promise<UserResponse> => {
    const response = await api.get('/api/me');
    return response.data;
  },

  // 退出登录
  logout: async (): Promise<void> => {
    // 清除本地token
    localStorage.removeItem('token');
  },
};