/**
 * Agent注册表服务
 * 负责Agent与端口的映射管理、内存缓存和数据库操作
 */

// Agent信息接口
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

// 端口分配信息接口
export interface PortAllocation {
  port: number;
  agent_id?: string;
  allocated_at?: string;
  status: 'available' | 'allocated';
}

// Agent会话信息接口
export interface AgentSession {
  session_id: string;
  agent_id: string;
  user_id: number;
  title?: string;
  created_at: string;
  updated_at: string;
}

/**
 * Agent注册表内存缓存
 * 提供高性能的端口查找服务
 */
class AgentRegistryCache {
  private agentPortMap = new Map<string, number>();           // agentId -> port
  private portAgentMap = new Map<number, string>();           // port -> agentId
  private userAgentsMap = new Map<number, Set<string>>();     // userId -> agentIds[]
  private initialized = false;

  /**
   * 初始化缓存 - 从数据库加载数据
   */
  async initialize(): Promise<void> {
    if (this.initialized) return;

    try {
      // 这里应该调用数据库API加载所有Agent数据
      // 模拟数据库调用
      const agents = await this.loadAgentsFromDB();
      
      for (const agent of agents) {
        this.addToCache(agent);
      }
      
      this.initialized = true;
      console.log(`Agent Registry Cache initialized with ${agents.length} agents`);
    } catch (error) {
      console.error('Failed to initialize Agent Registry Cache:', error);
      throw error;
    }
  }

  /**
   * 添加Agent到缓存
   */
  addToCache(agent: AgentInfo): void {
    this.agentPortMap.set(agent.agent_id, agent.port);
    this.portAgentMap.set(agent.port, agent.agent_id);
    
    if (!this.userAgentsMap.has(agent.user_id)) {
      this.userAgentsMap.set(agent.user_id, new Set());
    }
    this.userAgentsMap.get(agent.user_id)!.add(agent.agent_id);
  }

  /**
   * 从缓存移除Agent
   */
  removeFromCache(agentId: string): void {
    const port = this.agentPortMap.get(agentId);
    if (port) {
      this.agentPortMap.delete(agentId);
      this.portAgentMap.delete(port);
    }

    // 从用户Agent集合中移除
    for (const [userId, agentIds] of this.userAgentsMap.entries()) {
      if (agentIds.has(agentId)) {
        agentIds.delete(agentId);
        if (agentIds.size === 0) {
          this.userAgentsMap.delete(userId);
        }
        break;
      }
    }
  }

  /**
   * 获取Agent对应的端口
   */
  getAgentPort(agentId: string): number | undefined {
    return this.agentPortMap.get(agentId);
  }

  /**
   * 获取端口对应的Agent
   */
  getPortAgent(port: number): string | undefined {
    return this.portAgentMap.get(port);
  }

  /**
   * 获取用户所有Agent ID
   */
  getUserAgents(userId: number): string[] {
    const agentIds = this.userAgentsMap.get(userId);
    return agentIds ? Array.from(agentIds) : [];
  }

  /**
   * 检查端口是否已被占用
   */
  isPortOccupied(port: number): boolean {
    return this.portAgentMap.has(port);
  }

  /**
   * 模拟从数据库加载Agent数据
   * 实际实现时应该调用真实的数据库API
   */
  private async loadAgentsFromDB(): Promise<AgentInfo[]> {
    // 模拟数据 - 实际应该从数据库查询
    return [
      {
        agent_id: 'baseapp',
        user_id: 1,
        port: 8888,
        name: 'BaseApp Chat Agent',
        type: 'baseapp',
        status: 'running',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ];
  }

  /**
   * 获取缓存统计信息
   */
  getStats() {
    return {
      totalAgents: this.agentPortMap.size,
      totalUsers: this.userAgentsMap.size,
      occupiedPorts: Array.from(this.portAgentMap.keys()).sort()
    };
  }
}

/**
 * Agent注册表服务
 * 提供Agent管理的完整功能
 */
export class AgentRegistryService {
  private cache = new AgentRegistryCache();
  private portRange = { min: 5001, max: 5020 }; // 开发阶段端口范围

  /**
   * 初始化服务
   */
  async initialize(): Promise<void> {
    await this.cache.initialize();
  }

  /**
   * 获取Agent端口
   */
  async getAgentPort(agentId: string): Promise<number | null> {
    await this.ensureInitialized();
    const port = this.cache.getAgentPort(agentId);
    return port || null;
  }

  /**
   * 获取Agent完整信息
   */
  async getAgentInfo(agentId: string): Promise<AgentInfo | null> {
    await this.ensureInitialized();
    
    // 实际实现时应该查询数据库
    // 这里暂时返回模拟数据
    const port = this.cache.getAgentPort(agentId);
    if (!port) return null;

    return {
      agent_id: agentId,
      user_id: 1, // 临时数据
      port,
      name: agentId === 'baseapp' ? 'BaseApp Chat Agent' : `Agent ${agentId}`,
      type: agentId === 'baseapp' ? 'baseapp' : 'custom',
      status: 'running',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };
  }

  /**
   * 获取用户所有Agent
   */
  async getUserAgents(userId: number): Promise<AgentInfo[]> {
    await this.ensureInitialized();
    
    const agentIds = this.cache.getUserAgents(userId);
    const agents: AgentInfo[] = [];
    
    for (const agentId of agentIds) {
      const agent = await this.getAgentInfo(agentId);
      if (agent) {
        agents.push(agent);
      }
    }
    
    return agents;
  }

  /**
   * 分配可用端口
   */
  async allocatePort(): Promise<number | null> {
    await this.ensureInitialized();
    
    for (let port = this.portRange.min; port <= this.portRange.max; port++) {
      if (!this.cache.isPortOccupied(port)) {
        return port;
      }
    }
    
    return null; // 没有可用端口
  }

  /**
   * 创建新Agent
   */
  async createAgent(userId: number, name: string, type: 'baseapp' | 'custom', config?: Record<string, any>): Promise<AgentInfo | null> {
    await this.ensureInitialized();
    
    // 分配端口
    const port = await this.allocatePort();
    if (!port) {
      throw new Error('No available ports');
    }
    
    // 生成Agent ID
    const agentId = `agent_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    const agent: AgentInfo = {
      agent_id: agentId,
      user_id: userId,
      port,
      name,
      type,
      status: 'stopped', // 新创建的Agent默认为停止状态
      config,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };
    
    // 添加到缓存
    this.cache.addToCache(agent);
    
    // 实际实现时应该保存到数据库
    console.log('Created new agent:', agent);
    
    return agent;
  }

  /**
   * 删除Agent
   */
  async deleteAgent(agentId: string): Promise<boolean> {
    await this.ensureInitialized();
    
    const agent = await this.getAgentInfo(agentId);
    if (!agent) return false;
    
    // 从缓存移除
    this.cache.removeFromCache(agentId);
    
    // 实际实现时应该从数据库删除
    console.log('Deleted agent:', agentId);
    
    return true;
  }

  /**
   * 更新Agent状态
   */
  async updateAgentStatus(agentId: string, status: 'running' | 'stopped' | 'error'): Promise<boolean> {
    await this.ensureInitialized();
    
    const agent = await this.getAgentInfo(agentId);
    if (!agent) return false;
    
    // 实际实现时应该更新数据库
    console.log(`Updated agent ${agentId} status to ${status}`);
    
    return true;
  }

  /**
   * 确保服务已初始化
   */
  private async ensureInitialized(): Promise<void> {
    await this.cache.initialize();
  }

  /**
   * 获取服务统计信息
   */
  async getStats() {
    await this.ensureInitialized();
    return this.cache.getStats();
  }
}

// 单例实例
export const agentRegistry = new AgentRegistryService();