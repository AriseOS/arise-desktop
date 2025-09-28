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
import { RootState } from '../store';
import { logout } from '../store/authSlice';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { agentBuildAPI } from '../services/agentBuildAPI';
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

  // 创建一个示例工作流数据用于测试
  const sampleWorkflowData = {
    steps: [
      // 开始节点
      {
        id: 'start',
        name: '开始',
        type: 'start',
        description: '分页商品爬取工作流开始'
      },
      // 步骤1: 初始化全局变量
      {
        id: 'init-global-vars',
        name: '初始化全局变量',
        type: 'text_agent',
        description: '初始化分页循环和数据收集所需的变量'
      },
      // 步骤2: 打开浏览器会话
      {
        id: 'init-browser',
        name: '初始化浏览器',
        type: 'tool_agent',
        description: '创建浏览器会话用于后续页面访问'
      },
      // 步骤3: 外层循环 - 遍历所有页面
      {
        id: 'page-iteration-loop',
        name: '页面遍历循环',
        type: 'loop',
        description: '遍历多个列表页面',
        data: {
          condition: '{{current_page}} <= {{max_pages}} && {{has_next_page}} == true'
        }
      },
      // 步骤3.1: 构建当前页URL
      {
        id: 'build-page-url',
        name: '构建当前页URL',
        type: 'text_agent',
        description: '根据页码构建完整的列表页URL'
      },
      // 步骤3.2: 打开列表页
      {
        id: 'open-list-page',
        name: '打开商品列表页',
        type: 'tool_agent',
        description: '导航到当前列表页'
      },
      // 步骤3.3: 提取商品URL列表
      {
        id: 'extract-product-urls',
        name: '提取商品链接',
        type: 'scraper_agent',
        description: '从列表页提取所有商品的详情页链接'
      },
      // 步骤3.4: 初始化商品循环变量
      {
        id: 'init-product-loop-vars',
        name: '初始化商品循环变量',
        type: 'text_agent',
        description: '为内层商品循环准备变量'
      },
      // 步骤3.5: 内层循环 - 遍历当前页商品
      {
        id: 'product-iteration-loop',
        name: '商品数据收集循环',
        type: 'loop',
        description: '遍历当前页的所有商品并收集数据',
        data: {
          condition: '{{product_index}} < {{total_products_in_page}}'
        }
      },
      // 步骤3.5.1: 获取当前商品信息
      {
        id: 'get-current-product',
        name: '获取当前商品',
        type: 'text_agent',
        description: '从列表中获取当前索引的商品'
      },
      // 步骤3.5.2: 打开商品详情页
      {
        id: 'open-product-page',
        name: '打开商品详情页',
        type: 'tool_agent',
        description: '导航到商品详情页'
      },
      // 步骤3.5.3: 提取商品详细数据
      {
        id: 'extract-product-details',
        name: '提取商品详情',
        type: 'scraper_agent',
        description: '从商品详情页提取完整数据'
      },
      // 步骤3.5.4: 添加到总数据集
      {
        id: 'append-product-data',
        name: '保存商品数据',
        type: 'text_agent',
        description: '将提取的数据添加到总集合'
      },
      // 步骤3.5.5: 商品索引递增
      {
        id: 'increment-product-index',
        name: '更新商品索引',
        type: 'text_agent',
        description: '移动到下一个商品'
      },
      // 步骤3.6: 检查是否有下一页
      {
        id: 'check-next-page',
        name: '检查下一页',
        type: 'scraper_agent',
        description: '检查列表页是否有下一页'
      },
      // 步骤3.7: 更新页码和下一页标志
      {
        id: 'update-page-vars',
        name: '更新页面变量',
        type: 'text_agent',
        description: '准备下一轮页面循环'
      },
      // 步骤4: 生成数据分析报告
      {
        id: 'generate-report',
        name: '生成分析报告',
        type: 'text_agent',
        description: '基于收集的数据生成详细分析报告'
      },
      // 步骤5: 保存结果（可选）
      {
        id: 'save-results',
        name: '保存数据和报告',
        type: 'code_agent',
        description: '将收集的数据保存到文件'
      },
      // 步骤6: 最终输出
      {
        id: 'final-output',
        name: '整理最终输出',
        type: 'text_agent',
        description: '准备工作流的最终输出'
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
      { from: 'start', to: 'init-global-vars' },
      { from: 'init-global-vars', to: 'init-browser' },
      { from: 'init-browser', to: 'page-iteration-loop' },
      { from: 'page-iteration-loop', to: 'build-page-url' },
      { from: 'page-iteration-loop', to: 'end' },
      { from: 'build-page-url', to: 'open-list-page' },
      { from: 'open-list-page', to: 'extract-product-urls' },
      { from: 'extract-product-urls', to: 'init-product-loop-vars' },
      { from: 'init-product-loop-vars', to: 'product-iteration-loop' },
      { from: 'product-iteration-loop', to: 'check-next-page' },
      { from: 'product-iteration-loop', to: 'get-current-product' },
      { from: 'get-current-product', to: 'open-product-page' },
      { from: 'open-product-page', to: 'extract-product-details' },
      { from: 'extract-product-details', to: 'append-product-data' },
      { from: 'append-product-data', to: 'increment-product-index' },
      { from: 'increment-product-index', to: 'product-iteration-loop' },
      { from: 'check-next-page', to: 'update-page-vars' },
      { from: 'update-page-vars', to: 'page-iteration-loop' },
      { from: 'page-iteration-loop', to: 'generate-report' },
      { from: 'generate-report', to: 'save-results' },
      { from: 'save-results', to: 'final-output' },
      { from: 'final-output', to: 'end' }
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
          <LanguageSwitcher />
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
                <div className="flex items-center">
                  <RobotOutlined className="mr-2 text-green-600" />
                  {t('workspace.workflow')}
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