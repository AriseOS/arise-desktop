import React, { useState, useRef, useEffect } from 'react';
import { Layout, Card, Typography, Button, Input, Space, Avatar, Dropdown, Tag, message } from 'antd';
import { 
  UserOutlined, 
  LogoutOutlined, 
  RobotOutlined, 
  PlayCircleOutlined, 
  StopOutlined,
  SendOutlined,
  LoadingOutlined
} from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import agentService from '../services/agentAPI';
import { agentBuildAPI } from '../services/agentBuildAPI'; // 导入agentBuildAPI
import { createBaseAppService } from '../services/baseappAPI';
import type { AgentInfo } from '../services/agentAPI';
import { logout } from '../store/authSlice';
import { RootState } from '../store';
import { BuildProgressWebSocket } from '../services/websocketService';
import WorkflowVisualization from '../components/WorkflowVisualization';

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const WorkspacePage: React.FC = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useSelector((state: RootState) => state.auth);
  const { t } = useTranslation();
  
  // 从导航状态获取数据
  const locationState = (location.state as any) || {};
  const buildId = locationState.buildId;
  const initialPrompt = locationState.initialPrompt || '';
  
  // 状态管理
  const [userInput, setUserInput] = useState(initialPrompt);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentBuildId, setCurrentBuildId] = useState<string | null>(buildId || null);
  const [buildStatus, setBuildStatus] = useState<string>('building');
  const [agentInfo, setAgentInfo] = useState<any>(null);
  const [agentLogs, setAgentLogs] = useState<Array<{id: string, timestamp: Date, message: string, type: 'info' | 'success' | 'error'}>>([]);
  const [workflowData, setWorkflowData] = useState<any>(null);
  const [websocket, setWebsocket] = useState<BuildProgressWebSocket | null>(null);

  const agentLogsRef = useRef<HTMLDivElement>(null);

  // WebSocket 连接管理
  useEffect(() => {
    if (!currentBuildId) return;

    // 创建 WebSocket 连接
    const ws = new BuildProgressWebSocket(currentBuildId);
    
    // 设置消息处理
    ws.onMessage((data) => {
      console.log('收到 WebSocket 消息:', data);
      
      if (data.type === 'progress_update') {
        // 添加进度日志
        const newLog = {
          id: Date.now().toString(),
          timestamp: new Date(data.timestamp),
          message: `📊 [${data.step?.toUpperCase()}] ${data.message}`,
          type: 'info' as const
        };
        
        setAgentLogs(prev => {
          // 避免重复日志
          const lastLog = prev[prev.length - 1];
          if (lastLog && lastLog.message === newLog.message) {
            return prev;
          }
          return [...prev, newLog];
        });

        // 更新构建状态
        if (data.step === 'completed') {
          setBuildStatus('completed');
          setIsGenerating(false);
          setAgentLogs(prev => [...prev, {
            id: Date.now().toString(),
            timestamp: new Date(),
            message: '✅ [COMPLETED] Agent 构建完成！',
            type: 'success'
          }]);
        } else if (data.step === 'failed') {
          setBuildStatus('failed');
          setIsGenerating(false);
          setAgentLogs(prev => [...prev, {
            id: Date.now().toString(),
            timestamp: new Date(),
            message: `❌ [ERROR] 构建失败`,
            type: 'error'
          }]);
        }
      }
    });

    ws.onError((error) => {
      console.error('WebSocket 错误:', error);
      setAgentLogs(prev => [...prev, {
        id: Date.now().toString(),
        timestamp: new Date(),
        message: '❌ [ERROR] 实时连接中断',
        type: 'error'
      }]);
    });

    ws.onClose(() => {
      console.log('WebSocket 连接已关闭');
    });

    // 建立连接
    ws.connect().then(() => {
      setWebsocket(ws);
      setIsGenerating(true);
      
      // 发送心跳
      const heartbeat = setInterval(() => {
        if (ws.isConnected()) {
          ws.sendPing();
        }
      }, 30000);

      return () => clearInterval(heartbeat);
    }).catch((error) => {
      console.error('WebSocket 连接失败:', error);
      message.error('实时连接建立失败，请刷新页面重试');
    });

    // 清理函数
    return () => {
      if (ws) {
        ws.disconnect();
      }
    };
  }, [currentBuildId]);

  // 初始化日志
  useEffect(() => {
    if (currentBuildId) {
      setAgentLogs([{
        id: '1',
        timestamp: new Date(),
        message: '🎯 [STARTED] Agent 构建已启动',
        type: 'info'
      }]);
    } else {
      // 显示欢迎信息
      setAgentLogs([{
        id: '1',
        timestamp: new Date(),
        message: '👋 [WELCOME] 欢迎来到 Agent 工作台！描述您的需求开始构建 Agent',
        type: 'info'
      }]);
    }
  }, [currentBuildId]);

  // 自动滚动日志
  useEffect(() => {
    if (agentLogsRef.current) {
      agentLogsRef.current.scrollTop = agentLogsRef.current.scrollHeight;
    }
  }, [agentLogs]);

  const handleLogout = () => {
    dispatch(logout());
  };

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: t('nav.profile'),
    },
    {
      key: 'home',
      icon: <RobotOutlined />,
      label: t('nav.home'),
      onClick: () => navigate('/'),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: t('nav.logout'),
      onClick: handleLogout,
    },
  ];

  const handleStartGeneration = async () => {
    if (!userInput.trim()) return;
    
    setIsGenerating(true);
    setAgentLogs([]); // 清除之前的日志
    
    try {
      // 调用 Agent 构建 API
      const result = await agentBuildAPI.buildAgent({
        description: userInput.trim(),
        agent_name: undefined
      });

      setCurrentBuildId(result.build_id);
      setBuildStatus('building');
      
      message.success('Agent 构建已启动');
      
    } catch (error: any) {
      console.error('启动构建失败:', error);
      message.error(error.response?.data?.detail || '启动构建失败');
      setIsGenerating(false);
    }
  };

  const handleStopGeneration = () => {
    setIsGenerating(false);
    setAgentLogs(prev => [...prev, {
      id: Date.now().toString(),
      timestamp: new Date(),
      message: '⏹️ [STOPPED] 用户停止了构建过程',
      type: 'info'
    }]);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleStartGeneration();
    }
  };

  const handleExecuteWorkflow = async () => {
    if (!user) return;
    
    // 检查是否有构建完成的Agent
    // todo： 演示的时候直接调用了写死的agent
    // if (!currentBuildId || !agentInfo) {
    //   message.error('请先构建一个Agent');
    //   return;
    // }
    
    try {
      // 调用agentService的startAgent接口启动Agent
      await agentService.startAgent(user.id.toString(), "browser-session-test-workflow");
      message.success('Agent已成功启动');
    } catch (error: any) {
      console.error('启动Agent出错:', error);
      if (error.message && error.message.includes('Network Error')) {
        message.error('连接服务失败，请确保后端服务正在运行');
      } else {
        message.error('启动Agent失败，请查看控制台了解详情');
      }
    }
  };

  // 创建一个示例工作流数据用于测试
  const sampleWorkflowData = {
    steps: [
      // 开始节点
      {
        id: 'start',
        name: '开始',
        type: 'start',
        description: '浏览器会话共享测试工作流开始'
      },
      // 步骤1: 从example.com获取标题
      {
        id: 'get-example-title',
        name: '获取Example.com标题',
        type: 'scraper_agent',
        description: '提取example.com的页面标题'
      },
      // 步骤2: 从百度获取热点话题
      {
        id: 'get-baidu-hot',
        name: '获取百度热点话题',
        type: 'scraper_agent',
        description: '提取百度热搜或主要链接'
      },
      // 步骤3: 汇总结果
      {
        id: 'summarize-results',
        name: '汇总结果',
        type: 'text_agent',
        description: '汇总来自两个网站的数据'
      },
      // 步骤4: 准备最终输出
      {
        id: 'prepare-output',
        name: '准备最终输出',
        type: 'variable',
        description: '组织最终输出结构'
      },
      // 结束节点
      {
        id: 'end',
        name: '结束',
        type: 'end',
        description: '工作流结束节点'
      }
    ],
    connections: [
      { from: 'start', to: 'get-example-title' },
      { from: 'get-example-title', to: 'get-baidu-hot' },
      { from: 'get-baidu-hot', to: 'summarize-results' },
      { from: 'summarize-results', to: 'prepare-output' },
      { from: 'prepare-output', to: 'end' }
    ]
  };

  // 临时使用示例数据来展示可视化效果
  const displayWorkflowData = workflowData || sampleWorkflowData;

  return (
    <Layout className="min-h-screen bg-gray-50">
      {/* Header */}
      <Header className="bg-white shadow-sm flex items-center justify-between px-6">
        <div className="flex items-center">
          <Title level={3} className="m-0 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            {t('workspace.title')}
          </Title>
        </div>
        
        <div className="flex items-center space-x-4">
          {user ? (
            <Space>
              <Text className="text-gray-600">
                {t('workspace.welcome').replace('{username}', user.username || user.full_name || 'User')}
              </Text>
              <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
                <Avatar 
                  icon={<UserOutlined />} 
                  className="cursor-pointer bg-gradient-to-r from-blue-500 to-purple-500"
                />
              </Dropdown>
            </Space>
          ) : (
            <Button type="primary" onClick={() => navigate('/login')}>
              {t('common.login')}
            </Button>
          )}
        </div>
      </Header>

      <Content className="p-6">
        <div className="h-full grid grid-cols-12 gap-4">
          {/* 左侧面板：Agent 输出和对话 */}
          <div className="col-span-3 space-y-4">
            {/* Agent 输出日志 */}
            <Card 
              title={
                <div className="flex items-center">
                  <RobotOutlined className="mr-2 text-blue-600" />
                  {t('workspace.agentOutput')}
                  {isGenerating && (
                    <Tag color="processing" className="ml-2">
                      <LoadingOutlined className="mr-1" />
                      {t('workspace.running')}
                    </Tag>
                  )}
                </div>
              }
              className="flex-1"
              bodyStyle={{ padding: 0, height: '300px', overflow: 'hidden' }}
            >
              <div 
                ref={agentLogsRef}
                className="h-full overflow-y-auto p-4 bg-gray-900 text-gray-100 font-mono text-sm"
                style={{ minHeight: '300px' }}
              >
                {agentLogs.map(log => (
                  <div key={log.id} className="mb-2">
                    <div className="text-gray-400 text-xs">
                      {log.timestamp.toLocaleTimeString()}
                    </div>
                    <div className={`
                      ${log.type === 'error' ? 'text-red-400' : 
                        log.type === 'success' ? 'text-green-400' : 'text-gray-200'}
                    `}>
                      {log.message}
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* 用户对话区 */}
            <Card 
              title={
                <div className="flex items-center">
                  <SendOutlined className="mr-2 text-purple-600" />
                  {t('workspace.dialog')}
                </div>
              }
            >
              <div className="space-y-4">
                <div>
                  <Text className="text-sm text-gray-600 block mb-2">
                    {t('workspace.userRequirement')}
                  </Text>
                  <TextArea
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder={t('workspace.placeholder')}
                    autoSize={{ minRows: 3, maxRows: 6 }}
                    className="resize-none"
                  />
                </div>
                
                <div className="flex justify-between items-center">
                  <Text className="text-xs text-gray-500">
                    {t('workspace.quickKey', { key: navigator.platform.includes('Mac') ? 'Cmd' : 'Ctrl' })}
                  </Text>
                  
                  <Space>
                    {isGenerating ? (
                      <Button
                        danger
                        icon={<StopOutlined />}
                        onClick={handleStopGeneration}
                      >
                        {t('workspace.stop')}
                      </Button>
                    ) : (
                      <Button
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        onClick={handleStartGeneration}
                        disabled={!userInput.trim()}
                      >
                        {t('workspace.startGenerate')}
                      </Button>
                    )}
                  </Space>
                </div>
              </div>
            </Card>
          </div>

          {/* 中间面板：工作流展示 */}
          <div className="col-span-6">
            <Card 
              title={
                <div className="flex items-center justify-between w-full">
                  <div className="flex items-center">
                    <RobotOutlined className="mr-2 text-green-600" />
                    {t('workspace.workflow')}
                  </div>
                  <Button 
                    type="primary" 
                    icon={<PlayCircleOutlined />}
                    onClick={handleExecuteWorkflow}
                  >
                    执行工作流
                  </Button>
                </div>
              }
              className="h-full"
              bodyStyle={{ height: 'calc(100vh - 200px)' }}
            >
              <div className="h-full flex items-center justify-center bg-gray-50 rounded-lg">
                {displayWorkflowData ? (
                  <div className="bg-white rounded-lg shadow-sm border border-gray-200 h-full w-full">
                    <WorkflowVisualization workflowData={displayWorkflowData} />
                  </div>
                ) : (
                  <div className="text-center text-gray-500">
                    <RobotOutlined className="text-4xl mb-4" />
                    <Title level={4} className="text-gray-400">
                      {t('workspace.waitingToBuild')}
                    </Title>
                    <Paragraph className="text-gray-400">
                      {t('workspace.buildProcess')}
                    </Paragraph>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* 右侧面板：预览区 */}
          <div className="col-span-3">
            <Card 
              title={
                <div className="flex items-center">
                  <RobotOutlined className="mr-2 text-orange-600" />
                  Agent 对话预览
                </div>
              }
              className="h-full"
              bodyStyle={{ height: 'calc(100vh - 200px)' }}
            >
              <div className="h-full flex items-center justify-center bg-gray-50 rounded-lg">
                {agentInfo ? (
                  <div className="text-center w-full">
                    <Title level={4}>与 Agent 对话</Title>
                    {/* TODO: 实现 Agent 对话组件 */}
                    <div className="bg-white rounded-lg p-4 shadow-sm">
                      <Text>Agent 对话界面将在这里显示</Text>
                    </div>
                  </div>
                ) : (
                  <div className="text-center text-gray-500">
                    <RobotOutlined className="text-4xl mb-4" />
                    <Title level={4} className="text-gray-400">
                      {t('workspace.previewArea')}
                    </Title>
                    <Paragraph className="text-gray-400">
                      Agent 构建完成后，您可以在这里与 Agent 进行对话测试
                    </Paragraph>
                  </div>
                )}
              </div>
            </Card>
          </div>
        </div>
      </Content>
    </Layout>
  );
};

export default WorkspacePage;