import React, { useEffect, useState, useCallback } from 'react';
import { useParams, Navigate, useNavigate } from 'react-router-dom';
import { Layout, Spin, Alert, Button, Typography } from 'antd';
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import BaseAppPage from './BaseAppPage';
import { agentService, AgentInfo } from '../services/agentAPI';

const { Header, Content } = Layout;
const { Title } = Typography;

// 使用统一的AgentInfo接口
type AgentConfig = AgentInfo;

const AgentContainer: React.FC = () => {
  const { userId, agentId } = useParams<{ userId: string; agentId: string }>();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  
  const [agentConfig, setAgentConfig] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 获取Agent配置信息
  const fetchAgentConfig = useCallback(async () => {
    if (!userId || !agentId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      // 调用真实的Agent API获取配置
      const agentInfo = await agentService.getAgentInfo(userId, agentId);
      setAgentConfig(agentInfo);
      console.log('[AgentContainer] Loaded agent config:', agentInfo);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      console.error('[AgentContainer] Failed to load agent config:', errorMessage);
    } finally {
      setLoading(false);
    }
  }, [userId, agentId]);

  useEffect(() => {
    fetchAgentConfig();
  }, [fetchAgentConfig]);

  // 权限检查：确保用户只能访问自己的Agent
  if (user && userId !== user.id?.toString()) {
    return <Navigate to="/dashboard" replace />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (loading) {
    return (
      <Layout className="min-h-screen">
        <Content className="flex items-center justify-center">
          <Spin size="large" />
        </Content>
      </Layout>
    );
  }

  if (error || !agentConfig) {
    return (
      <Layout className="min-h-screen">
        <Header className="bg-white shadow-sm flex items-center justify-between px-6">
          <div className="flex items-center">
            <Button 
              type="text" 
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/dashboard')}
              className="mr-4"
            >
              Back to Dashboard
            </Button>
            <Title level={4} className="m-0">Agent Error</Title>
          </div>
        </Header>
        <Content className="flex items-center justify-center p-6">
          <div className="max-w-md w-full">
            <Alert
              message="Agent Loading Failed"
              description={error || `Could not load agent ${agentId}`}
              type="error"
              action={
                <Button 
                  type="primary" 
                  icon={<ReloadOutlined />}
                  onClick={fetchAgentConfig}
                >
                  Retry
                </Button>
              }
            />
          </div>
        </Content>
      </Layout>
    );
  }

  // 渲染不同类型的Agent
  const renderAgentContent = () => {
    switch (agentConfig.type) {
      case 'baseapp':
        // 对于baseapp类型，直接渲染BaseAppPage组件
        return <BaseAppPage />;
      
      case 'custom':
        // 对于自定义Agent，显示占位符界面
        // 实际实现时可以动态加载Agent的前端代码
        return (
          <div className="flex items-center justify-center h-full bg-gray-50">
            <div className="text-center">
              <Alert
                message="Custom Agent Interface"
                description={
                  <div>
                    <p>Agent ID: {agentConfig.agent_id}</p>
                    <p>Port: {agentConfig.port}</p>
                    <p>This is a placeholder for custom agent frontend.</p>
                    <p>In production, this would load the agent's custom UI.</p>
                  </div>
                }
                type="info"
                className="mb-4"
              />
              <Button 
                type="primary" 
                onClick={() => window.open(`http://localhost:${agentConfig.port}`, '_blank')}
              >
                Open Agent Interface in New Tab
              </Button>
            </div>
          </div>
        );
      
      default:
        return (
          <div className="flex items-center justify-center h-full">
            <Alert
              message="Unknown Agent Type"
              description={`Agent type "${agentConfig.type}" is not supported`}
              type="error"
            />
          </div>
        );
    }
  };

  return (
    <Layout className="min-h-screen">
      <Header className="bg-white shadow-sm flex items-center justify-between px-6">
        <div className="flex items-center">
          <Button 
            type="text" 
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/dashboard')}
            className="mr-4"
          >
            Back to Dashboard
          </Button>
          <Title level={4} className="m-0">{agentConfig.name}</Title>
          <div className="ml-4 flex items-center space-x-2">
            <span className={`px-2 py-1 rounded text-xs font-medium ${
              agentConfig.status === 'running' 
                ? 'bg-green-100 text-green-800' 
                : agentConfig.status === 'error'
                ? 'bg-red-100 text-red-800'
                : 'bg-gray-100 text-gray-800'
            }`}>
              {agentConfig.status.toUpperCase()}
            </span>
            <span className="text-sm text-gray-500">
              Port: {agentConfig.port}
            </span>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <Button 
            type="text" 
            icon={<ReloadOutlined />}
            onClick={fetchAgentConfig}
          >
            Refresh
          </Button>
        </div>
      </Header>
      
      <Content className="flex-1">
        {renderAgentContent()}
      </Content>
    </Layout>
  );
};

export default AgentContainer;