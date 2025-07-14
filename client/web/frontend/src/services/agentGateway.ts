/**
 * Agent API网关服务
 * 负责请求转发、路由解析和代理功能
 */

import axios, { AxiosRequestConfig, AxiosResponse } from 'axios';
import { agentRegistry } from './agentRegistry';

// 请求转发配置
interface ProxyConfig {
  userId: string;
  agentId: string;
  apiPath: string;
  method: string;
  data?: any;
  params?: any;
  headers?: Record<string, string>;
}

// 转发响应
interface ProxyResponse {
  success: boolean;
  data?: any;
  error?: string;
  status: number;
  headers?: Record<string, string>;
}

/**
 * Agent API网关类
 * 实现统一的API转发和代理功能
 */
export class AgentGateway {
  private timeout = 10000; // 10秒超时

  /**
   * 初始化网关服务
   */
  async initialize(): Promise<void> {
    await agentRegistry.initialize();
    console.log('Agent Gateway initialized');
  }

  /**
   * 核心转发方法
   * 解析路由并转发请求到对应的Agent后端
   */
  async forwardRequest(config: ProxyConfig): Promise<ProxyResponse> {
    try {
      // 1. 权限检查 (这里简化处理，实际应该验证JWT token)
      if (!this.checkPermission(config.userId, config.agentId)) {
        return {
          success: false,
          error: 'Forbidden: User does not have access to this agent',
          status: 403
        };
      }

      // 2. 查找Agent端口
      const agentPort = await agentRegistry.getAgentPort(config.agentId);
      if (!agentPort) {
        return {
          success: false,
          error: `Agent '${config.agentId}' not found`,
          status: 404
        };
      }

      // 3. 构造目标URL
      const targetUrl = `http://localhost:${agentPort}${config.apiPath}`;
      console.log(`[Gateway] Forwarding ${config.method} ${config.apiPath} -> ${targetUrl}`);

      // 4. 转发请求
      const axiosConfig: AxiosRequestConfig = {
        method: config.method.toLowerCase() as any,
        url: targetUrl,
        data: config.data,
        params: config.params,
        headers: {
          ...config.headers,
          'X-Forwarded-For': 'agent-gateway',
          'X-Agent-Id': config.agentId,
          'X-User-Id': config.userId
        },
        timeout: this.timeout,
        validateStatus: () => true // 接受所有状态码
      };

      const response = await axios(axiosConfig);

      // 5. 返回代理响应
      return {
        success: response.status >= 200 && response.status < 400,
        data: response.data,
        status: response.status,
        headers: this.filterResponseHeaders(response.headers)
      };

    } catch (error: any) {
      console.error('[Gateway] Forward request failed:', error.message);
      
      // 处理网络错误和超时
      if (error.code === 'ECONNREFUSED') {
        return {
          success: false,
          error: `Agent '${config.agentId}' is not running or unreachable`,
          status: 503
        };
      }
      
      if (error.code === 'ETIMEDOUT') {
        return {
          success: false,
          error: `Request to agent '${config.agentId}' timed out`,
          status: 408
        };
      }

      return {
        success: false,
        error: error.message || 'Internal gateway error',
        status: 500
      };
    }
  }

  /**
   * 解析API路径
   * 从完整路径中提取userId, agentId和API路径
   */
  parseApiPath(fullPath: string): { userId: string; agentId: string; apiPath: string } | null {
    // 匹配路径格式: /api/users/:userId/agents/:agentId/api/*
    const pathRegex = /^\/api\/users\/([^\/]+)\/agents\/([^\/]+)\/api(.*)$/;
    const match = fullPath.match(pathRegex);
    
    if (!match) {
      console.warn('[Gateway] Invalid API path format:', fullPath);
      return null;
    }

    return {
      userId: match[1],
      agentId: match[2],
      apiPath: match[3] || '/'
    };
  }

  /**
   * Express.js中间件
   * 可以直接集成到Express应用中
   */
  createExpressMiddleware() {
    return async (req: any, res: any, next: any) => {
      // 解析路径
      const pathInfo = this.parseApiPath(req.path);
      if (!pathInfo) {
        return res.status(400).json({ error: 'Invalid API path format' });
      }

      // 构造转发配置
      const proxyConfig: ProxyConfig = {
        userId: pathInfo.userId,
        agentId: pathInfo.agentId,
        apiPath: pathInfo.apiPath,
        method: req.method,
        data: req.body,
        params: req.query,
        headers: req.headers
      };

      // 转发请求
      const response = await this.forwardRequest(proxyConfig);

      // 设置响应头
      if (response.headers) {
        Object.entries(response.headers).forEach(([key, value]) => {
          res.set(key, value);
        });
      }

      // 返回响应
      res.status(response.status).json(response.data || { error: response.error });
    };
  }

  /**
   * 权限检查
   * 验证用户是否有权访问指定的Agent
   */
  private checkPermission(userId: string, agentId: string): boolean {
    // 简化的权限检查 - 实际应该验证JWT token和数据库权限
    // 这里暂时允许所有请求
    return true;
  }

  /**
   * 过滤响应头
   * 移除不应该转发的响应头
   */
  private filterResponseHeaders(headers: any): Record<string, string> {
    const filtered: Record<string, string> = {};
    const allowedHeaders = [
      'content-type',
      'content-length',
      'cache-control',
      'expires',
      'last-modified',
      'etag'
    ];

    Object.entries(headers).forEach(([key, value]: [string, any]) => {
      if (allowedHeaders.includes(key.toLowerCase()) && typeof value === 'string') {
        filtered[key] = value;
      }
    });

    return filtered;
  }

  /**
   * 健康检查
   * 检查所有Agent的运行状态
   */
  async healthCheck(): Promise<Record<string, any>> {
    const stats = await agentRegistry.getStats();
    
    return {
      gateway: {
        status: 'running',
        timestamp: new Date().toISOString(),
        timeout: this.timeout
      },
      registry: stats,
      agents: {
        total: stats.totalAgents,
        ports: stats.occupiedPorts
      }
    };
  }

  /**
   * 获取Agent状态
   */
  async getAgentStatus(agentId: string): Promise<any> {
    try {
      const agentPort = await agentRegistry.getAgentPort(agentId);
      if (!agentPort) {
        return { status: 'not_found', agentId };
      }

      // 尝试调用Agent的健康检查端点
      const response = await axios.get(`http://localhost:${agentPort}/health`, {
        timeout: 3000
      });

      return {
        status: 'running',
        agentId,
        port: agentPort,
        health: response.data
      };
    } catch (error: any) {
      return {
        status: 'error',
        agentId,
        error: error.message
      };
    }
  }
}

// 单例实例
export const agentGateway = new AgentGateway();