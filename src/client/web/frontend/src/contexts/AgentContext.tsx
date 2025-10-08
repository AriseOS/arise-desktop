/**
 * Agent上下文提供器
 * 为组件提供当前Agent和用户的信息，支持新的统一路由系统
 */

import React, { createContext, useContext, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { createBaseAppService } from '../services/baseappAPI';

interface AgentContextValue {
  userId: string | null;
  agentId: string | null;
  baseappService: ReturnType<typeof createBaseAppService> | null;
  isNewRouting: boolean;
}

const AgentContext = createContext<AgentContextValue>({
  userId: null,
  agentId: null,
  baseappService: null,
  isNewRouting: false
});

interface AgentProviderProps {
  children: React.ReactNode;
  forceNewRouting?: boolean; // 强制使用新路由（用于测试）
}

export const AgentProvider: React.FC<AgentProviderProps> = ({ 
  children, 
  forceNewRouting = false 
}) => {
  const { userId: routeUserId, agentId: routeAgentId } = useParams<{ 
    userId: string; 
    agentId: string; 
  }>();
  const { user } = useSelector((state: RootState) => state.auth);
  const [baseappService, setBaseappService] = useState<ReturnType<typeof createBaseAppService> | null>(null);

  // 确定是否使用新的路由系统
  const isNewRouting = forceNewRouting || (!!routeUserId && !!routeAgentId);
  const userId = isNewRouting ? routeUserId : user?.id?.toString() || null;
  const agentId = isNewRouting ? routeAgentId : 'baseapp';

  useEffect(() => {
    if (userId) {
      // 根据路由情况创建相应的BaseApp服务实例
      const service = createBaseAppService(userId, isNewRouting);
      setBaseappService(service);
      
      console.log('[AgentContext] Initialized BaseApp service:', {
        userId,
        agentId,
        isNewRouting,
        serviceType: isNewRouting ? 'unified-routing' : 'legacy-direct'
      });
    } else {
      setBaseappService(null);
    }
  }, [userId, agentId, isNewRouting]);

  const contextValue: AgentContextValue = {
    userId,
    agentId,
    baseappService,
    isNewRouting
  };

  return (
    <AgentContext.Provider value={contextValue}>
      {children}
    </AgentContext.Provider>
  );
};

export const useAgent = () => {
  const context = useContext(AgentContext);
  if (!context) {
    throw new Error('useAgent must be used within an AgentProvider');
  }
  return context;
};

export default AgentContext;