import React, { useState, useRef, useEffect } from 'react';
import { Layout, Card, Typography, Button, Input, Space, Avatar, Dropdown, Tag, Select, message } from 'antd';
import { 
  UserOutlined, 
  LogoutOutlined, 
  RobotOutlined, 
  PlayCircleOutlined, 
  StopOutlined,
  MobileOutlined,
  DesktopOutlined,
  CodeOutlined,
  ThunderboltOutlined,
  SendOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  LoadingOutlined
} from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { RootState } from '../store';
import { logout } from '../store/authSlice';
import LanguageSwitcher from '../components/LanguageSwitcher';
import { agentBuildAPI } from '../services/agentBuildAPI';

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

const WorkspacePage: React.FC = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useSelector((state: RootState) => state.auth);
  const { t } = useTranslation();
  
  // Get data from navigation state
  const locationState = (location.state as any) || {};
  const buildId = locationState.buildId;
  const initialPrompt = locationState.initialPrompt || 'Create an Excel Q&A Agent that can validate uploaded Excel files and answer questions about proper Excel formatting. The agent should check for correct headers, data types, required fields, and provide helpful guidance on Excel best practices.';
  
  // State management
  const [userInput, setUserInput] = useState(initialPrompt);
  const [isGenerating, setIsGenerating] = useState(false);
  const [targetPlatform, setTargetPlatform] = useState<'frontend' | 'android'>('frontend');
  const [currentBuildId, setCurrentBuildId] = useState<string | null>(buildId || null);
  const [buildStatus, setBuildStatus] = useState<string>('building');
  const [agentInfo, setAgentInfo] = useState<any>(null);
  const [agentLogs, setAgentLogs] = useState<Array<{id: string, timestamp: Date, message: string, type: 'info' | 'success' | 'error'}>>([]);

  // 监控构建进度
  useEffect(() => {
    if (!currentBuildId) return;

    const pollBuildStatus = async () => {
      try {
        const status = await agentBuildAPI.getBuildStatus(currentBuildId);
        setBuildStatus(status.status);
        
        // 添加日志
        const newLog = {
          id: Date.now().toString(),
          timestamp: new Date(),
          message: `📊 [${status.current_step?.toUpperCase()}] ${status.progress_message}`,
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

        if (status.status === 'completed') {
          // 构建完成，获取Agent信息
          const buildSession = await agentBuildAPI.getBuildStatus(currentBuildId);
          if (buildSession.status === 'completed') {
            // 这里需要从构建结果中获取agent_id
            // 暂时使用模拟数据
            setAgentInfo({
              name: 'Generated Agent',
              description: initialPrompt,
              capabilities: ['文本处理', '问答交互']
            });
          }
          return; // 停止轮询
        }
        
        if (status.status === 'failed') {
          setAgentLogs(prev => [...prev, {
            id: Date.now().toString(),
            timestamp: new Date(),
            message: `❌ [ERROR] ${status.error_message}`,
            type: 'error'
          }]);
          return; // 停止轮询
        }

        // 继续轮询
        setTimeout(pollBuildStatus, 2000);
        
      } catch (error) {
        console.error('获取构建状态失败:', error);
        setAgentLogs(prev => [...prev, {
          id: Date.now().toString(),
          timestamp: new Date(),
          message: '❌ [ERROR] 获取构建状态失败',
          type: 'error'
        }]);
      }
    };

    // 开始轮询
    if (buildStatus === 'building') {
      pollBuildStatus();
    }
  }, [currentBuildId, buildStatus, initialPrompt]);

  // 初始化日志（仅在有buildId时）
  useEffect(() => {
    if (currentBuildId) {
      setAgentLogs([{
        id: '1',
        timestamp: new Date(),
        message: '🎯 [STARTED] Agent 构建已启动',
        type: 'info'
      }]);
    } else {
      // 如果没有buildId，显示默认演示日志
      setAgentLogs([
        {
          id: '1',
          timestamp: new Date(Date.now() - 300000),
          message: '🎯 [REQUIREMENT ANALYSIS] User wants: Excel Q&A Agent for form validation and guidance',
          type: 'info'
        },
        {
          id: '2',
          timestamp: new Date(Date.now() - 240000),
          message: '🧠 [THINKING] This requires Excel parsing, validation, and Q&A capabilities',
          type: 'info'
        },
        {
          id: '3',
          timestamp: new Date(Date.now() - 180000),
          message: '🏗️ [ARCHITECTURE] Designing multi-component system: FileHandler + Validator + KnowledgeBase',
          type: 'info'
        },
        {
          id: '4',
          timestamp: new Date(Date.now() - 120000),
          message: '🧪 [TESTING] Running validation tests with sample Excel files',
          type: 'info'
        },
        {
          id: '5',
          timestamp: new Date(Date.now() - 60000),
          message: '✅ [SUCCESS] Excel Q&A Agent built successfully! Ready for deployment.',
          type: 'success'
        }
      ]);
    }
  }, [currentBuildId]);
  const [workflowSteps, setWorkflowSteps] = useState<Array<{id: string, title: string, status: 'pending' | 'running' | 'completed' | 'error', description: string}>>([
    // 添加一些演示workflow步骤
    { id: '1', title: 'Requirement Analysis', status: 'completed' as const, description: 'Analyzing Excel Q&A Agent requirements' },
    { id: '2', title: 'Excel Schema Design', status: 'completed' as const, description: 'Designing Excel validation schema' },
    { id: '3', title: 'Q&A Engine Setup', status: 'completed' as const, description: 'Building knowledge base and Q&A system' },
    { id: '4', title: 'Agent Integration', status: 'completed' as const, description: 'Integrating all components and testing' }
  ]);
  
  // Workflow display states
  const [workflowZoom, setWorkflowZoom] = useState(1);
  const [workflowPosition, setWorkflowPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const workflowRef = useRef<HTMLDivElement>(null);
  
  const agentLogsRef = useRef<HTMLDivElement>(null);

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
      icon: <DesktopOutlined />,
      label: t('nav.backToHome'),
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
    setAgentLogs([]); // Clear previous logs
    
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
      return;
    }
    
    // 实际构建过程将通过轮询API状态来更新
    // useEffect 会处理构建进度的显示
  };
      {
        message: "🎯 [REQUIREMENT ANALYSIS] User wants: Excel Q&A Agent for form validation and guidance",
        type: 'info' as const,
        delay: 500
      },
      {
        message: "🤔 [THINKING] This requires: 1) Excel parsing 2) Schema validation 3) Q&A capability 4) User guidance",
        type: 'info' as const,
        delay: 1200
      },
      {
        message: "📋 [ANALYSIS] Key use cases: Upload template → Validate submissions → Answer formatting questions",
        type: 'info' as const,
        delay: 1800
      },
      {
        message: "🏗️ [ARCHITECTURE] Designing multi-component system: FileHandler + Validator + KnowledgeBase + ChatEngine",
        type: 'info' as const,
        delay: 2400
      },
      {
        message: "⚙️ [IMPLEMENTATION] Setting up Excel parser with pandas/openpyxl for file processing",
        type: 'info' as const,
        delay: 3000
      },
      {
        message: "🔍 [VALIDATION] Building schema validator: check headers, data types, required fields, format rules",
        type: 'info' as const,
        delay: 3600
      },
      {
        message: "🧠 [KNOWLEDGE BASE] Creating Q&A database with Excel best practices and common formatting issues",
        type: 'info' as const,
        delay: 4200
      },
      {
        message: "💬 [CHAT ENGINE] Implementing NLP interface for natural language Q&A about Excel formatting",
        type: 'info' as const,
        delay: 4800
      },
      {
        message: "🔗 [INTEGRATION] Connecting all components: Upload → Parse → Validate → Store → Query → Response",
        type: 'info' as const,
        delay: 5400
      },
      {
        message: "🧪 [TESTING] Running validation tests with sample Excel files and edge cases",
        type: 'info' as const,
        delay: 6000
      },
      {
        message: "✅ [SUCCESS] Excel Q&A Agent built successfully! Ready for deployment and user testing.",
        type: 'success' as const,
        delay: 6600
      }
    ];

    // Mock workflow steps for Excel Q&A Agent
    const mockSteps = [
      { id: '1', title: 'Requirement Analysis', status: 'running' as const, description: 'Analyzing Excel Q&A Agent requirements' },
      { id: '2', title: 'Excel Schema Design', status: 'pending' as const, description: 'Designing Excel validation schema' },
      { id: '3', title: 'Q&A Engine Setup', status: 'pending' as const, description: 'Building knowledge base and Q&A system' },
      { id: '4', title: 'Agent Integration', status: 'pending' as const, description: 'Integrating all components and testing' }
    ];
    setWorkflowSteps(mockSteps);
    
    // Execute building steps with realistic timing
    let currentStep = 0;
    
    const executeStep = async (step: typeof buildingSteps[0]) => {
      await new Promise(resolve => setTimeout(resolve, step.delay));
      setAgentLogs(prev => [...prev, {
        id: (Date.now() + Math.random()).toString(),
        timestamp: new Date(),
        message: step.message,
        type: step.type
      }]);
      
      // Update workflow step status
      if (currentStep < mockSteps.length) {
        setWorkflowSteps(prev => prev.map((s, i) => {
          if (i === currentStep) {
            return { ...s, status: 'completed' as const };
          } else if (i === currentStep + 1) {
            return { ...s, status: 'running' as const };
          }
          return s;
        }));
        currentStep++;
      }
    };
    
    // Execute all steps
    for (const step of buildingSteps) {
      await executeStep(step);
    }
    
    // Mark final step as completed
    setWorkflowSteps(prev => prev.map(s => ({ ...s, status: 'completed' as const })));
    setIsGenerating(false);
  };

  const handleStopGeneration = () => {
    setIsGenerating(false);
    setAgentLogs(prev => [...prev, {
      id: Date.now().toString(),
      timestamp: new Date(),
      message: t('workspace.generationStopped'),
      type: 'info'
    }]);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleStartGeneration();
    }
  };

  // Workflow zoom and pan handlers
  const handleZoomIn = () => {
    setWorkflowZoom(prev => Math.min(prev + 0.2, 3));
  };

  const handleZoomOut = () => {
    setWorkflowZoom(prev => Math.max(prev - 0.2, 0.3));
  };

  const handleResetView = () => {
    setWorkflowZoom(1);
    setWorkflowPosition({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({
      x: e.clientX - workflowPosition.x,
      y: e.clientY - workflowPosition.y
    });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setWorkflowPosition({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Auto-scroll agent logs
  useEffect(() => {
    if (agentLogsRef.current) {
      agentLogsRef.current.scrollTop = agentLogsRef.current.scrollHeight;
    }
  }, [agentLogs]);

  return (
    <Layout className="min-h-screen bg-gray-50">
      {/* Header */}
      <Header className="bg-white shadow-sm flex items-center justify-between px-6 border-0">
        <div className="flex items-center space-x-4">
          <Title level={3} className="m-0 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            ami.dev
          </Title>
          <Tag color="blue" className="ml-4">{t('workspace.title')}</Tag>
        </div>
        
        <div className="flex items-center space-x-4">
          <LanguageSwitcher />
          
          <Space>
            <Text className="text-gray-600">{t('home.welcome').replace('{username}', user?.username || 'User')}</Text>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Avatar 
                icon={<UserOutlined />} 
                className="cursor-pointer bg-gradient-to-r from-blue-500 to-purple-500"
              />
            </Dropdown>
          </Space>
        </div>
      </Header>

      {/* Main Content */}
      <Content className="p-4 h-[calc(100vh-64px)]">
        <div className="h-full grid grid-cols-12 gap-4">
          
          {/* Left Panel - Agent Output & User Dialog */}
          <div className="col-span-3 flex flex-col h-full gap-4">
            
            {/* Agent Output */}
            <Card 
              title={
                <Space>
                  <RobotOutlined className="text-green-600" />
                  <span>{t('workspace.agentOutput')}</span>
                  {isGenerating && <Tag color="processing">{t('workspace.running')}</Tag>}
                </Space>
              }
              className="flex-shrink-0"
              style={{ height: 'calc(100vh - 64px - 340px - 32px - 16px - 60px)' }}
              bodyStyle={{ padding: 0, height: 'calc(100% - 60px)' }}
            >
              <div 
                ref={agentLogsRef}
                className="h-full overflow-y-auto p-4 bg-gray-900 text-white text-sm font-mono"
              >
                {agentLogs.length === 0 ? (
                  <div className="text-gray-400 text-center py-8">
                    <RobotOutlined className="text-2xl mb-2 block" />
                    {t('workspace.waitingToStart')}
                  </div>
                ) : (
                  agentLogs.map(log => (
                    <div key={log.id} className="mb-2">
                      <span className="text-gray-400">
                        [{log.timestamp.toLocaleTimeString()}]
                      </span>
                      <span className={`ml-2 ${
                        log.type === 'success' ? 'text-green-400' : 
                        log.type === 'error' ? 'text-red-400' : 
                        'text-blue-400'
                      }`}>
                        {log.message}
                      </span>
                    </div>
                  ))
                )}
                {isGenerating && (
                  <div className="text-yellow-400 animate-pulse">
                    <ThunderboltOutlined className="mr-2" />
                    {t('workspace.agentThinking')}
                  </div>
                )}
              </div>
            </Card>

            {/* User Dialog */}
            <Card 
              title={
                <Space>
                  <UserOutlined className="text-blue-600" />
                  <span>{t('workspace.dialog')}</span>
                </Space>
              }
              className="flex-shrink-0"
              style={{ height: '340px' }}
              bodyStyle={{ height: 'calc(100% - 60px)' }}
            >
              <div className="h-full flex flex-col">
                <div className="flex-1 mb-4">
                  <Text className="text-gray-600 block mb-2">{t('workspace.userRequirements')}</Text>
                  <TextArea
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder={t('workspace.placeholder')}
                    autoSize={{ minRows: 4, maxRows: 8 }}
                    disabled={isGenerating}
                    className="mb-4"
                  />
                </div>
                
                <div className="flex justify-between items-center">
                  <Text className="text-xs text-gray-500">
                    {t('workspace.quickGenerate').replace('{key}', navigator.platform.includes('Mac') ? 'Cmd' : 'Ctrl')}
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
                        {t('workspace.startGeneration')}
                      </Button>
                    )}
                  </Space>
                </div>
              </div>
            </Card>
          </div>

          {/* Center Panel - Workflow Display */}
          <div className="col-span-6 h-full">
            <Card 
              title={
                <div className="flex justify-between items-center w-full">
                  <Space>
                    <CodeOutlined className="text-purple-600" />
                    <span>{t('workspace.userAgentDisplay')}</span>
                  </Space>
                  <Space size="small">
                    <Button 
                      size="small" 
                      icon={<ZoomOutOutlined />}
                      onClick={handleZoomOut}
                      disabled={workflowZoom <= 0.3}
                    />
                    <span className="text-xs text-gray-500 min-w-[50px] text-center">
                      {Math.round(workflowZoom * 100)}%
                    </span>
                    <Button 
                      size="small" 
                      icon={<ZoomInOutlined />}
                      onClick={handleZoomIn}
                      disabled={workflowZoom >= 3}
                    />
                    <Button 
                      size="small" 
                      icon={<FullscreenOutlined />}
                      onClick={handleResetView}
                      title="Reset View"
                    />
                  </Space>
                </div>
              }
              className="h-full"
              bodyStyle={{ height: '100%', padding: 0, overflow: 'hidden' }}
            >
              <div 
                className="h-full relative overflow-hidden"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
              >
                {workflowSteps.length === 0 ? (
                  <div className="text-center py-16 text-gray-400 absolute inset-0 flex items-center justify-center">
                    <div>
                      <CodeOutlined className="text-4xl mb-4 block" />
                      <Text className="text-gray-500">Start building to see the agent workflow</Text>
                    </div>
                  </div>
                ) : (
                  <div 
                    ref={workflowRef}
                    className="absolute inset-0 transition-transform duration-200"
                    style={{ 
                      transform: `translate(${workflowPosition.x}px, ${workflowPosition.y}px) scale(${workflowZoom})`,
                      transformOrigin: 'center center',
                      width: '100%',
                      height: '100%',
                      padding: '16px'
                    }}
                  >
                    {/* Excel Q&A Agent Workflow - Node-based visualization */}
                    <div className="space-y-3">
                      
                      {/* Workflow Title */}
                      <div className="text-center mb-4">
                        <Text className="font-semibold text-base">Excel Q&A Agent Workflow</Text>
                        <div className="text-xs text-gray-500">Node-based processing pipeline</div>
                      </div>

                      {/* Start Node */}
                      <div className="flex justify-center">
                        <div className="bg-green-50 border-2 border-green-400 rounded-lg p-2 min-w-[120px] text-center">
                          <div className="text-green-600 text-lg mb-1">🚀</div>
                          <Text className="font-semibold text-xs">START</Text>
                          <div className="text-xs text-gray-600">User Input</div>
                        </div>
                      </div>
                      
                      {/* Connection Line */}
                      <div className="flex justify-center">
                        <div className="w-0.5 h-4 bg-gray-300"></div>
                      </div>

                      {/* File Upload Node */}
                      <div className="flex justify-center">
                        <div className="bg-blue-50 border-2 border-blue-400 rounded-lg p-2 min-w-[120px] text-center relative">
                          <div className="text-blue-600 text-lg mb-1">📁</div>
                          <Text className="font-semibold text-xs">File Upload</Text>
                          <div className="text-xs text-gray-600">.xlsx, .csv</div>
                          {/* Node connector dots */}
                          <div className="absolute -top-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-blue-400 rounded-full"></div>
                          <div className="absolute -bottom-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-blue-400 rounded-full"></div>
                        </div>
                      </div>

                      {/* Connection Line */}
                      <div className="flex justify-center">
                        <div className="w-0.5 h-4 bg-gray-300"></div>
                      </div>

                      {/* Parallel Processing Nodes */}
                      <div className="grid grid-cols-2 gap-4">
                        <div className="text-center">
                          <div className="bg-purple-50 border-2 border-purple-400 rounded-lg p-2 relative">
                            <div className="text-purple-600 text-lg mb-1">🔍</div>
                            <Text className="font-semibold text-xs">Schema Validator</Text>
                            <div className="text-xs text-gray-600">Check format</div>
                            <div className="absolute -top-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-purple-400 rounded-full"></div>
                            <div className="absolute -bottom-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-purple-400 rounded-full"></div>
                          </div>
                        </div>
                        <div className="text-center">
                          <div className="bg-orange-50 border-2 border-orange-400 rounded-lg p-2 relative">
                            <div className="text-orange-600 text-lg mb-1">💬</div>
                            <Text className="font-semibold text-xs">Q&A Engine</Text>
                            <div className="text-xs text-gray-600">Answer questions</div>
                            <div className="absolute -top-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-orange-400 rounded-full"></div>
                            <div className="absolute -bottom-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-orange-400 rounded-full"></div>
                          </div>
                        </div>
                      </div>

                      {/* Connection Lines from parallel nodes */}
                      <div className="flex justify-center items-center space-x-6">
                        <div className="w-0.5 h-4 bg-gray-300"></div>
                        <div className="w-0.5 h-4 bg-gray-300"></div>
                      </div>

                      {/* Knowledge Base Node */}
                      <div className="flex justify-center">
                        <div className="bg-yellow-50 border-2 border-yellow-400 rounded-lg p-2 min-w-[140px] text-center relative">
                          <div className="text-yellow-600 text-lg mb-1">🧠</div>
                          <Text className="font-semibold text-xs">Knowledge Base</Text>
                          <div className="text-xs text-gray-600">Excel rules</div>
                          <div className="mt-1 flex justify-center space-x-1">
                            <Tag size="small" color="blue" className="text-xs px-1">Templates</Tag>
                            <Tag size="small" color="green" className="text-xs px-1">Rules</Tag>
                          </div>
                          <div className="absolute -top-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-yellow-400 rounded-full"></div>
                          <div className="absolute -bottom-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-yellow-400 rounded-full"></div>
                        </div>
                      </div>

                      {/* Connection Line */}
                      <div className="flex justify-center">
                        <div className="w-0.5 h-4 bg-gray-300"></div>
                      </div>

                      {/* Response Node */}
                      <div className="flex justify-center">
                        <div className="bg-red-50 border-2 border-red-400 rounded-lg p-2 min-w-[120px] text-center relative">
                          <div className="text-red-600 text-lg mb-1">📤</div>
                          <Text className="font-semibold text-xs">Response</Text>
                          <div className="text-xs text-gray-600">Validation + Answer</div>
                          <div className="absolute -top-0.5 left-1/2 transform -translate-x-1/2 w-1.5 h-1.5 bg-red-400 rounded-full"></div>
                        </div>
                      </div>

                      {/* Agent Status Panel */}
                      <div className="mt-4 p-3 bg-gray-50 border rounded-lg">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2">
                            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                            <div>
                              <Text className="font-semibold text-xs">Agent Status: ACTIVE</Text>
                              <div className="text-xs text-gray-600">All nodes connected</div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-xs text-gray-500">Memory</div>
                            <div className="text-xs font-semibold">2.3 MB</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Right Panel - Preview */}
          <div className="col-span-3 h-full">
            <Card 
              title={
                <Space>
                  {targetPlatform === 'frontend' ? 
                    <DesktopOutlined className="text-orange-600" /> : 
                    <MobileOutlined className="text-orange-600" />
                  }
                  <span>{t('workspace.preview')}</span>
                </Space>
              }
              className="h-full"
              bodyStyle={{ height: '100%', padding: 0 }}
            >
              <div className="h-full flex flex-col">
                {/* Platform Selector */}
                <div className="p-4 pb-2 flex justify-center border-b">
                  <Select
                    value={targetPlatform}
                    onChange={setTargetPlatform}
                    className="w-36"
                    size="small"
                  >
                    <Option value="frontend">
                      <DesktopOutlined className="mr-1" />
                      {t('workspace.frontend')}
                    </Option>
                    <Option value="android">
                      <MobileOutlined className="mr-1" />
                      {t('workspace.android')}
                    </Option>
                  </Select>
                </div>

                {/* Preview Container with Scroll */}
                <div className="flex-1 overflow-y-auto">
                  {workflowSteps.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-center text-gray-400 p-8">
                      <div>
                        {targetPlatform === 'frontend' ? (
                          <DesktopOutlined className="text-4xl mb-4 block" />
                        ) : (
                          <MobileOutlined className="text-4xl mb-4 block" />
                        )}
                        <Text className="text-gray-500">Agent preview will appear here</Text>
                      </div>
                    </div>
                  ) : (
                    <div className="p-4">
                      {/* Excel Q&A Chat Interface */}
                      <div className="bg-gray-50 rounded-lg border">
                        {/* Chat Header */}
                        <div className="bg-gradient-to-r from-blue-500 to-blue-600 text-white p-4 flex items-center space-x-3">
                          <div className="w-10 h-10 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                            <span className="text-xl">📊</span>
                          </div>
                          <div>
                            <Text className="font-semibold text-white text-base">Excel Q&A Assistant</Text>
                            <div className="text-sm text-blue-100">✅ Ready to help with Excel questions</div>
                          </div>
                        </div>

                        {/* Chat Messages with Scroll */}
                        <div className="p-4 space-y-4 bg-gray-50 max-h-[500px] overflow-y-auto">
                      {/* Welcome Message */}
                      <div className="flex items-start space-x-2">
                        <div className="w-7 h-7 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                          <span className="text-white text-xs">🤖</span>
                        </div>
                        <div className="bg-white rounded-lg p-3 max-w-[85%] shadow-sm border">
                          <Text className="text-sm">Hello! I'm your Excel validation assistant. Upload your Excel file or ask me questions about proper formatting. I can help with:</Text>
                          <div className="mt-2 text-xs space-y-1">
                            <div>• File structure validation</div>
                            <div>• Data type checking</div>
                            <div>• Formatting guidance</div>
                          </div>
                        </div>
                      </div>

                      {/* User Upload Request */}
                      <div className="flex items-start space-x-2 justify-end">
                        <div className="bg-blue-500 text-white rounded-lg p-3 max-w-[85%] shadow-sm">
                          <Text className="text-sm text-white">I need to validate my employee data Excel file. Can you check it?</Text>
                        </div>
                        <div className="w-7 h-7 bg-gray-400 rounded-full flex items-center justify-center flex-shrink-0">
                          <UserOutlined className="text-xs text-white" />
                        </div>
                      </div>

                      {/* Assistant Upload Interface */}
                      <div className="flex items-start space-x-2">
                        <div className="w-7 h-7 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                          <span className="text-white text-xs">🤖</span>
                        </div>
                        <div className="bg-white rounded-lg p-3 max-w-[85%] shadow-sm border">
                          <Text className="text-sm">Perfect! Please upload your Excel file:</Text>
                          <div className="mt-3 p-4 border-2 border-dashed border-blue-300 rounded-lg text-center bg-blue-50 hover:bg-blue-100 cursor-pointer transition-colors">
                            <div className="text-blue-500 text-2xl mb-2">📎</div>
                            <Text className="text-sm font-medium text-blue-600">Drop file here or click to browse</Text>
                            <div className="text-xs text-gray-500 mt-1">Supports .xlsx, .xls, .csv files</div>
                          </div>
                        </div>
                      </div>

                      {/* File Processing */}
                      <div className="flex items-start space-x-2">
                        <div className="w-7 h-7 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                          <span className="text-white text-xs">🤖</span>
                        </div>
                        <div className="bg-white rounded-lg p-3 max-w-[85%] shadow-sm border">
                          <Text className="text-sm">📄 Processing "employee_data.xlsx"...</Text>
                          <div className="mt-2 bg-gray-200 rounded-full h-2">
                            <div className="bg-blue-500 h-2 rounded-full w-full"></div>
                          </div>
                        </div>
                      </div>

                      {/* Validation Results */}
                      <div className="flex items-start space-x-2">
                        <div className="w-7 h-7 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                          <span className="text-white text-xs">🤖</span>
                        </div>
                        <div className="bg-white rounded-lg p-3 max-w-[85%] shadow-sm border">
                          <Text className="text-sm font-semibold text-green-600 mb-2">✅ Validation Results</Text>
                          <div className="space-y-2 text-sm">
                            <div className="flex items-center space-x-2">
                              <span className="text-green-500">✓</span>
                              <span>Headers are correctly formatted</span>
                            </div>
                            <div className="flex items-center space-x-2">
                              <span className="text-green-500">✓</span>
                              <span>All required columns present</span>
                            </div>
                            <div className="flex items-center space-x-2">
                              <span className="text-yellow-500">⚠️</span>
                              <span>3 rows have missing email addresses</span>
                            </div>
                            <div className="flex items-center space-x-2">
                              <span className="text-red-500">❌</span>
                              <span>Date format inconsistent in column D</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* User Follow-up */}
                      <div className="flex items-start space-x-2 justify-end">
                        <div className="bg-blue-500 text-white rounded-lg p-3 max-w-[85%] shadow-sm">
                          <Text className="text-sm text-white">How should I fix the date format issue?</Text>
                        </div>
                        <div className="w-7 h-7 bg-gray-400 rounded-full flex items-center justify-center flex-shrink-0">
                          <UserOutlined className="text-xs text-white" />
                        </div>
                      </div>

                            {/* Assistant Guidance */}
                            <div className="flex items-start space-x-3">
                              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                                <span className="text-white text-sm">🤖</span>
                              </div>
                              <div className="bg-white rounded-lg p-4 max-w-[80%] shadow-sm border">
                                <Text className="text-sm">For consistent date formatting:</Text>
                                <div className="mt-3 bg-gray-100 p-3 rounded-lg text-sm font-mono">
                                  Format: YYYY-MM-DD<br/>
                                  Example: 2024-03-15
                                </div>
                                <Text className="text-sm mt-3">This ensures proper sorting and validation. Would you like me to show you how to apply this format in Excel?</Text>
                              </div>
                            </div>

                            {/* User Follow-up Question */}
                            <div className="flex items-start space-x-3 justify-end">
                              <div className="bg-blue-500 text-white rounded-lg p-4 max-w-[80%] shadow-sm">
                                <Text className="text-sm text-white">Yes please! Can you also help with phone number formatting?</Text>
                              </div>
                              <div className="w-8 h-8 bg-gray-400 rounded-full flex items-center justify-center flex-shrink-0">
                                <UserOutlined className="text-sm text-white" />
                              </div>
                            </div>

                            {/* Assistant Phone Number Help */}
                            <div className="flex items-start space-x-3">
                              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                                <span className="text-white text-sm">🤖</span>
                              </div>
                              <div className="bg-white rounded-lg p-4 max-w-[80%] shadow-sm border">
                                <Text className="text-sm font-semibold mb-2">📞 Phone Number Formatting Guide</Text>
                                <div className="space-y-2 text-sm">
                                  <div className="bg-blue-50 p-3 rounded">
                                    <strong>Recommended format:</strong> +1 (555) 123-4567
                                  </div>
                                  <div className="bg-green-50 p-3 rounded">
                                    <strong>Alternative:</strong> 555-123-4567
                                  </div>
                                  <div className="bg-yellow-50 p-3 rounded">
                                    <strong>Avoid:</strong> Mixed formats in same column
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* More User Questions */}
                            <div className="flex items-start space-x-3 justify-end">
                              <div className="bg-blue-500 text-white rounded-lg p-4 max-w-[80%] shadow-sm">
                                <Text className="text-sm text-white">What about email validation? Any specific format I should follow?</Text>
                              </div>
                              <div className="w-8 h-8 bg-gray-400 rounded-full flex items-center justify-center flex-shrink-0">
                                <UserOutlined className="text-sm text-white" />
                              </div>
                            </div>

                            {/* Email Validation Response */}
                            <div className="flex items-start space-x-3">
                              <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                                <span className="text-white text-sm">🤖</span>
                              </div>
                              <div className="bg-white rounded-lg p-4 max-w-[80%] shadow-sm border">
                                <Text className="text-sm font-semibold mb-2">📧 Email Validation Tips</Text>
                                <div className="text-sm space-y-2">
                                  <div>✅ Ensure all emails contain @ symbol</div>
                                  <div>✅ Check for valid domain extensions (.com, .org, etc.)</div>
                                  <div>✅ No spaces in email addresses</div>
                                  <div>❌ Watch out for: multiple @, missing domains</div>
                                </div>
                                <div className="mt-3 p-3 bg-gray-50 rounded text-xs">
                                  <strong>Excel Tip:</strong> Use Data Validation with custom formula to check email format automatically!
                                </div>
                              </div>
                            </div>

                        </div>

                        {/* Chat Input - Fixed at bottom */}
                        <div className="border-t bg-white p-4">
                          <div className="flex items-center space-x-3">
                            <Input 
                              placeholder="Ask about Excel formatting, validation rules..."
                              className="flex-1"
                              size="large"
                            />
                            <Button type="primary" size="large" icon={<SendOutlined />}>
                              Send
                            </Button>
                          </div>
                          <div className="text-xs text-gray-500 mt-2">
                            💡 Try: "How to format currency?" or "Validate address format"
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </Card>
          </div>
        </div>
      </Content>
    </Layout>
  );
};

export default WorkspacePage;