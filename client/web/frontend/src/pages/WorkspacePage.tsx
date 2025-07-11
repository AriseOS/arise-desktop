import React, { useState, useRef, useEffect } from 'react';
import { Layout, Card, Typography, Button, Input, Space, Avatar, Dropdown, Tag, Select } from 'antd';
import { 
  UserOutlined, 
  LogoutOutlined, 
  RobotOutlined, 
  PlayCircleOutlined, 
  StopOutlined,
  MobileOutlined,
  DesktopOutlined,
  CodeOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate, useLocation } from 'react-router-dom';
import { RootState } from '../store';
import { logout } from '../store/authSlice';

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

const WorkspacePage: React.FC = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useSelector((state: RootState) => state.auth);
  
  // Get initial prompt from navigation state
  const initialPrompt = (location.state as any)?.initialPrompt || '';
  
  // State management
  const [userInput, setUserInput] = useState(initialPrompt);
  const [isGenerating, setIsGenerating] = useState(false);
  const [targetPlatform, setTargetPlatform] = useState<'frontend' | 'android'>('frontend');
  const [agentLogs, setAgentLogs] = useState<Array<{id: string, timestamp: Date, message: string, type: 'info' | 'success' | 'error'}>>([]);
  const [workflowSteps, setWorkflowSteps] = useState<Array<{id: string, title: string, status: 'pending' | 'running' | 'completed' | 'error', description: string}>>([]);
  
  const agentLogsRef = useRef<HTMLDivElement>(null);

  const handleLogout = () => {
    dispatch(logout());
  };

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '用户信息',
    },
    {
      key: 'home',
      icon: <DesktopOutlined />,
      label: '返回首页',
      onClick: () => navigate('/'),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  const handleStartGeneration = async () => {
    if (!userInput.trim()) return;
    
    setIsGenerating(true);
    
    // Mock agent generation process
    const newLog = {
      id: Date.now().toString(),
      timestamp: new Date(),
      message: `开始分析用户需求: ${userInput}`,
      type: 'info' as const
    };
    setAgentLogs(prev => [...prev, newLog]);
    
    // Mock workflow steps
    const mockSteps = [
      { id: '1', title: '需求分析', status: 'running' as const, description: '正在分析用户输入的需求...' },
      { id: '2', title: '架构设计', status: 'pending' as const, description: '设计应用架构和组件结构' },
      { id: '3', title: '代码生成', status: 'pending' as const, description: '生成相应的代码文件' },
      { id: '4', title: '测试部署', status: 'pending' as const, description: '测试生成的代码并部署' }
    ];
    setWorkflowSteps(mockSteps);
    
    // TODO: Integrate with backend API
    setTimeout(() => {
      setIsGenerating(false);
      setAgentLogs(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        timestamp: new Date(),
        message: 'Agent生成功能开发中，敬请期待！',
        type: 'success'
      }]);
    }, 3000);
  };

  const handleStopGeneration = () => {
    setIsGenerating(false);
    setAgentLogs(prev => [...prev, {
      id: Date.now().toString(),
      timestamp: new Date(),
      message: '用户停止了生成过程',
      type: 'info'
    }]);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleStartGeneration();
    }
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
          <Tag color="blue" className="ml-4">工作台</Tag>
        </div>
        
        <div className="flex items-center space-x-4">
          <Select
            value={targetPlatform}
            onChange={setTargetPlatform}
            className="w-32"
            size="small"
          >
            <Option value="frontend">
              <DesktopOutlined className="mr-1" />
              前端
            </Option>
            <Option value="android">
              <MobileOutlined className="mr-1" />
              Android
            </Option>
          </Select>
          
          <Space>
            <Text className="text-gray-600">欢迎，{user?.username}！</Text>
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
      <Content className="p-4">
        <div className="h-full grid grid-cols-12 gap-4">
          
          {/* Left Panel - Agent Output & User Dialog */}
          <div className="col-span-3 flex flex-col space-y-4">
            
            {/* Agent Output */}
            <Card 
              title={
                <Space>
                  <RobotOutlined className="text-green-600" />
                  <span>Agent 输出框</span>
                  {isGenerating && <Tag color="processing">运行中</Tag>}
                </Space>
              }
              className="flex-1"
              bodyStyle={{ padding: 0 }}
            >
              <div 
                ref={agentLogsRef}
                className="h-80 overflow-y-auto p-4 bg-gray-900 text-white text-sm font-mono"
              >
                {agentLogs.length === 0 ? (
                  <div className="text-gray-400 text-center py-8">
                    <RobotOutlined className="text-2xl mb-2 block" />
                    等待开始生成...
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
                    Agent 正在思考中...
                  </div>
                )}
              </div>
            </Card>

            {/* User Dialog */}
            <Card 
              title={
                <Space>
                  <UserOutlined className="text-blue-600" />
                  <span>对话框</span>
                </Space>
              }
              className="h-80"
            >
              <div className="h-full flex flex-col">
                <div className="flex-1 mb-4">
                  <Text className="text-gray-600 block mb-2">用户描述新的修改需求：</Text>
                  <TextArea
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="描述您想要创建或修改的功能，例如：创建一个待办事项应用，包含添加、删除、标记完成等功能..."
                    autoSize={{ minRows: 4, maxRows: 8 }}
                    disabled={isGenerating}
                    className="mb-4"
                  />
                </div>
                
                <div className="flex justify-between items-center">
                  <Text className="text-xs text-gray-500">
                    按 {navigator.platform.includes('Mac') ? 'Cmd' : 'Ctrl'} + Enter 开始生成
                  </Text>
                  <Space>
                    {isGenerating ? (
                      <Button 
                        danger 
                        icon={<StopOutlined />}
                        onClick={handleStopGeneration}
                      >
                        停止
                      </Button>
                    ) : (
                      <Button
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        onClick={handleStartGeneration}
                        disabled={!userInput.trim()}
                      >
                        开始生成
                      </Button>
                    )}
                  </Space>
                </div>
              </div>
            </Card>
          </div>

          {/* Center Panel - Workflow Display */}
          <div className="col-span-6">
            <Card 
              title={
                <Space>
                  <CodeOutlined className="text-purple-600" />
                  <span>User Agent 逻辑展示 (workflow)</span>
                </Space>
              }
              className="h-full"
            >
              <div className="h-full overflow-y-auto">
                {workflowSteps.length === 0 ? (
                  <div className="text-center py-16 text-gray-400">
                    <CodeOutlined className="text-4xl mb-4 block" />
                    <Title level={4} className="text-gray-400">等待开始构建</Title>
                    <Paragraph className="text-gray-500">
                      Agent 将在这里展示构建过程和逻辑流程
                    </Paragraph>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {workflowSteps.map((step, index) => (
                      <div key={step.id} className="relative">
                        {index < workflowSteps.length - 1 && (
                          <div className="absolute left-6 top-12 w-0.5 h-16 bg-gray-300"></div>
                        )}
                        <div className="flex items-start space-x-4">
                          <div className={`w-12 h-12 rounded-full flex items-center justify-center text-white font-bold ${
                            step.status === 'completed' ? 'bg-green-500' :
                            step.status === 'running' ? 'bg-blue-500 animate-pulse' :
                            step.status === 'error' ? 'bg-red-500' :
                            'bg-gray-400'
                          }`}>
                            {index + 1}
                          </div>
                          <div className="flex-1">
                            <Title level={5} className="mb-1">{step.title}</Title>
                            <Text className="text-gray-600">{step.description}</Text>
                            <div className="mt-2">
                              <Tag color={
                                step.status === 'completed' ? 'success' :
                                step.status === 'running' ? 'processing' :
                                step.status === 'error' ? 'error' :
                                'default'
                              }>
                                {step.status === 'completed' ? '已完成' :
                                 step.status === 'running' ? '进行中' :
                                 step.status === 'error' ? '出错' :
                                 '等待中'}
                              </Tag>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Right Panel - Preview */}
          <div className="col-span-3">
            <Card 
              title={
                <Space>
                  {targetPlatform === 'frontend' ? 
                    <DesktopOutlined className="text-orange-600" /> : 
                    <MobileOutlined className="text-orange-600" />
                  }
                  <span>
                    User Agent {targetPlatform === 'frontend' ? '前端' : 'Android'} 展示
                  </span>
                </Space>
              }
              className="h-full"
            >
              <div className="h-full flex items-center justify-center">
                <div className="text-center text-gray-400">
                  {targetPlatform === 'frontend' ? (
                    <DesktopOutlined className="text-6xl mb-4 block" />
                  ) : (
                    <MobileOutlined className="text-6xl mb-4 block" />
                  )}
                  <Title level={4} className="text-gray-400">预览区域</Title>
                  <Paragraph className="text-gray-500">
                    生成的{targetPlatform === 'frontend' ? '前端界面' : 'Android应用'}将在这里展示
                  </Paragraph>
                  <Button type="dashed" disabled>
                    {targetPlatform === 'frontend' ? '前端预览' : 'Android模拟器'}
                  </Button>
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