/**
 * Agent后端API服务
 * 提供完整的Agent CRUD操作和管理功能
 */

import { AgentInfo, CreateAgentRequest } from './agentAPI';
import { agentRegistry } from './agentRegistry';
import agentBuildAPI from './agentBuildAPI'; // 导入agentBuildAPI

// 端口管理类
class PortManager {
  private readonly PORT_RANGE = { min: 5001, max: 5020 };
  private allocatedPorts = new Set<number>([8888]); // BaseApp占用端口8888

  /**
   * 分配一个可用端口
   */
  allocatePort(): number | null {
    for (let port = this.PORT_RANGE.min; port <= this.PORT_RANGE.max; port++) {
      if (!this.allocatedPorts.has(port)) {
        this.allocatedPorts.add(port);
        return port;
      }
    }
    return null;
  }

  /**
   * 释放端口
   */
  releasePort(port: number): void {
    this.allocatedPorts.delete(port);
  }

  /**
   * 检查端口是否已分配
   */
  isPortAllocated(port: number): boolean {
    return this.allocatedPorts.has(port);
  }

  /**
   * 获取已分配的端口列表
   */
  getAllocatedPorts(): number[] {
    return Array.from(this.allocatedPorts).sort();
  }
}

// 模拟数据库存储
class MockAgentDatabase {
  private agents = new Map<string, AgentInfo>();
  private userAgents = new Map<number, Set<string>>();

  constructor() {
    // 预置BaseApp Agent
    const baseappAgent: AgentInfo = {
      agent_id: 'baseapp',
      user_id: 1,
      port: 8888,
      name: 'BaseApp Chat Agent',
      type: 'baseapp',
      status: 'running',
      config: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };
    
    this.agents.set('baseapp', baseappAgent);
    this.userAgents.set(1, new Set(['baseapp']));
  }

  /**
   * 创建Agent
   */
  async createAgent(agent: AgentInfo): Promise<AgentInfo> {
    // 检查Agent ID是否已存在
    if (this.agents.has(agent.agent_id)) {
      throw new Error(`Agent with ID '${agent.agent_id}' already exists`);
    }

    // 保存Agent
    this.agents.set(agent.agent_id, agent);

    // 更新用户Agent映射
    if (!this.userAgents.has(agent.user_id)) {
      this.userAgents.set(agent.user_id, new Set());
    }
    this.userAgents.get(agent.user_id)!.add(agent.agent_id);

    return agent;
  }

  /**
   * 获取Agent信息
   */
  async getAgent(agentId: string): Promise<AgentInfo | null> {
    return this.agents.get(agentId) || null;
  }

  /**
   * 获取用户所有Agent
   */
  async getUserAgents(userId: number): Promise<AgentInfo[]> {
    const agentIds = this.userAgents.get(userId);
    if (!agentIds) return [];

    const agents: AgentInfo[] = [];
    for (const agentId of agentIds) {
      const agent = this.agents.get(agentId);
      if (agent) {
        agents.push(agent);
      }
    }

    return agents.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }

  /**
   * 获取所有Agent (Demo系统使用)
   */
  async getAllAgents(): Promise<AgentInfo[]> {
    const agents = Array.from(this.agents.values());
    return agents.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  }

  /**
   * 更新Agent
   */
  async updateAgent(agentId: string, updates: Partial<AgentInfo>): Promise<AgentInfo | null> {
    const agent = this.agents.get(agentId);
    if (!agent) return null;

    const updatedAgent = {
      ...agent,
      ...updates,
      updated_at: new Date().toISOString()
    };

    this.agents.set(agentId, updatedAgent);
    return updatedAgent;
  }

  /**
   * 删除Agent
   */
  async deleteAgent(agentId: string): Promise<boolean> {
    const agent = this.agents.get(agentId);
    if (!agent) return false;

    // 从用户Agent映射中移除
    const userAgentSet = this.userAgents.get(agent.user_id);
    if (userAgentSet) {
      userAgentSet.delete(agentId);
      if (userAgentSet.size === 0) {
        this.userAgents.delete(agent.user_id);
      }
    }

    // 删除Agent
    this.agents.delete(agentId);
    return true;
  }

  /**
   * 检查用户是否拥有Agent
   */
  async isUserOwner(agentId: string, userId: number): Promise<boolean> {
    const agent = this.agents.get(agentId);
    return agent ? agent.user_id === userId : false;
  }

  /**
   * 获取所有Agent统计
   */
  async getStats(): Promise<{ totalAgents: number; totalUsers: number; agentsByType: Record<string, number> }> {
    const agentsByType: Record<string, number> = {};
    
    for (const agent of this.agents.values()) {
      agentsByType[agent.type] = (agentsByType[agent.type] || 0) + 1;
    }

    return {
      totalAgents: this.agents.size,
      totalUsers: this.userAgents.size,
      agentsByType
    };
  }
}

/**
 * Agent后端API服务类
 */
export class AgentBackendAPI {
  private portManager = new PortManager();
  private database = new MockAgentDatabase();

  /**
   * 获取用户的所有Agent
   */
  async getUserAgents(userId: number): Promise<AgentInfo[]> {
    // Demo系统：返回所有Agent，不做用户筛选
    return this.database.getAllAgents();
    
    // 原有实现（生产环境使用）：
    // return this.database.getUserAgents(userId);
  }

  /**
   * 获取特定Agent信息
   */
  async getAgentInfo(agentId: string, userId?: number): Promise<AgentInfo | null> {
    const agent = await this.database.getAgent(agentId);
    
    // Demo系统暂时跳过权限检查
    // if (userId && agent && agent.user_id !== userId) {
    //   throw new Error('Access denied: User does not own this agent');
    // }
    
    return agent;
  }

  /**
   * 创建新Agent
   */
  async createAgent(userId: number, agentData: CreateAgentRequest): Promise<AgentInfo> {
    // 分配端口
    const port = this.portManager.allocatePort();
    if (!port) {
      throw new Error('No available ports for new agent');
    }

    // 生成唯一Agent ID
    const agentId = `agent_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // 创建Agent对象
    const agent: AgentInfo = {
      agent_id: agentId,
      user_id: userId,
      port,
      name: agentData.name,
      type: agentData.type,
      status: 'stopped', // 新创建的Agent默认为停止状态
      config: agentData.config || {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    try {
      // 保存到数据库
      const createdAgent = await this.database.createAgent(agent);
      
      // 同步到Agent注册表
      await agentRegistry.initialize();
      // 这里应该调用 agentRegistry.addAgent() 方法，但目前注册表是只读的
      
      console.log(`[AgentBackendAPI] Created new agent: ${agentId} on port ${port}`);
      return createdAgent;
      
    } catch (error) {
      // 如果创建失败，释放端口
      this.portManager.releasePort(port);
      throw error;
    }
  }

  /**
   * 启动Agent
   */
  async startAgent(agentId: string, userId: number): Promise<void> {
    // Demo系统暂时跳过权限检查
    // if (!(await this.database.isUserOwner(agentId, userId))) {
    //   throw new Error('Access denied: User does not own this agent');
    // }
    if (agentId === 'browser-session-test-workflow') {
      console.log(`[AgentBackendAPI] Started agent: ${agentId}`);
      // 在这里调用workflow的execute接口
      await agentBuildAPI.executeWorkflow('browser-session-test-workflow');
      return;
    }

    const agent = await this.database.getAgent(agentId);
    if (!agent) {
      throw new Error('Agent not found');
    }

    if (agent.status === 'running') {
      throw new Error('Agent is already running');
    }

    // 更新状态为运行中
    await this.database.updateAgent(agentId, { status: 'running' });
    
    // 这里应该实际启动Agent进程
    // 暂时只是更新状态
    console.log(`[AgentBackendAPI] Started agent: ${agentId} on port ${agent.port}`);
  }

  /**
   * 停止Agent
   */
  async stopAgent(agentId: string, userId: number): Promise<void> {
    // Demo系统暂时跳过权限检查
    // if (!(await this.database.isUserOwner(agentId, userId))) {
    //   throw new Error('Access denied: User does not own this agent');
    // }

    const agent = await this.database.getAgent(agentId);
    if (!agent) {
      throw new Error('Agent not found');
    }

    if (agent.status === 'stopped') {
      throw new Error('Agent is already stopped');
    }

    // BaseApp不允许停止
    if (agent.agent_id === 'baseapp') {
      throw new Error('BaseApp cannot be stopped');
    }

    // 更新状态为停止
    await this.database.updateAgent(agentId, { status: 'stopped' });
    
    // 这里应该实际停止Agent进程
    console.log(`[AgentBackendAPI] Stopped agent: ${agentId}`);
  }

  /**
   * 删除Agent
   */
  async deleteAgent(agentId: string, userId: number): Promise<void> {
    // Demo系统暂时跳过权限检查
    // if (!(await this.database.isUserOwner(agentId, userId))) {
    //   throw new Error('Access denied: User does not own this agent');
    // }

    const agent = await this.database.getAgent(agentId);
    if (!agent) {
      throw new Error('Agent not found');
    }

    // BaseApp不允许删除
    if (agent.agent_id === 'baseapp') {
      throw new Error('BaseApp cannot be deleted');
    }

    // 如果Agent正在运行，先停止
    if (agent.status === 'running') {
      await this.stopAgent(agentId, userId);
    }

    // 释放端口
    this.portManager.releasePort(agent.port);

    // 删除Agent
    const success = await this.database.deleteAgent(agentId);
    if (!success) {
      throw new Error('Failed to delete agent');
    }

    console.log(`[AgentBackendAPI] Deleted agent: ${agentId}, released port: ${agent.port}`);
  }

  /**
   * 更新Agent配置
   */
  async updateAgent(agentId: string, userId: number, updates: Partial<Pick<AgentInfo, 'name' | 'config'>>): Promise<AgentInfo> {
    // Demo系统暂时跳过权限检查
    // if (!(await this.database.isUserOwner(agentId, userId))) {
    //   throw new Error('Access denied: User does not own this agent');
    // }

    const updatedAgent = await this.database.updateAgent(agentId, updates);
    if (!updatedAgent) {
      throw new Error('Agent not found');
    }

    return updatedAgent;
  }

  /**
   * 获取Agent状态
   */
  async getAgentStatus(agentId: string): Promise<{ status: string; port?: number; health?: any }> {
    const agent = await this.database.getAgent(agentId);
    if (!agent) {
      return { status: 'not_found' };
    }

    // 这里可以添加实际的健康检查逻辑
    return {
      status: agent.status,
      port: agent.port,
      health: { timestamp: new Date().toISOString() }
    };
  }

  /**
   * 获取系统统计信息
   */
  async getSystemStats(): Promise<any> {
    const dbStats = await this.database.getStats();
    const allocatedPorts = this.portManager.getAllocatedPorts();
    
    return {
      ...dbStats,
      portUsage: {
        allocated: allocatedPorts,
        available: Array.from({ length: 20 }, (_, i) => 5001 + i).filter(p => !allocatedPorts.includes(p)),
        total: 20
      }
    };
  }
}

// 单例实例
export const agentBackendAPI = new AgentBackendAPI();