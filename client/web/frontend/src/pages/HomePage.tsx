import React, { useState } from 'react';
import { Layout, Button, Typography, Avatar, Dropdown, Space, Card, Input, message } from 'antd';
import { UserOutlined, LogoutOutlined, SendOutlined, RobotOutlined } from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { RootState } from '../store';
import { logout } from '../store/authSlice';
import UserProfile from '../components/UserProfile';

const { Header, Content } = Layout;
const { Title, Text } = Typography;
const { TextArea } = Input;

const HomePage: React.FC = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);
  const [prompt, setPrompt] = useState('');
  const [showUserProfile, setShowUserProfile] = useState(false);

  const handleLogout = () => {
    dispatch(logout());
  };

  const handleLogin = () => {
    navigate('/login');
  };

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '用户信息',
      onClick: () => setShowUserProfile(true),
    },
    {
      key: 'dashboard',
      icon: <RobotOutlined />,
      label: '控制台',
      onClick: () => navigate('/dashboard'),
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

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning('请输入您的需求');
      return;
    }

    if (!user) {
      message.info('请先登录以使用对话功能');
      navigate('/login');
      return;
    }

    // Navigate to workspace with the prompt
    navigate('/workspace', { state: { initialPrompt: prompt } });
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleGenerate();
    }
  };

  const examplePrompts = [
    "创建一个任务管理应用",
    "设计一个电商网站首页",
    "构建一个聊天机器人",
    "开发一个数据分析dashboard"
  ];

  return (
    <Layout className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      <Header className="bg-white/80 backdrop-blur-md shadow-sm flex items-center justify-between px-6 border-0">
        <div className="flex items-center">
          <Title level={3} className="m-0 bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
            ami.dev
          </Title>
        </div>
        
        <div className="flex items-center space-x-4">
          {user ? (
            <Space>
              <Text className="text-gray-600">欢迎，{user.username}！</Text>
              <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
                <Avatar 
                  icon={<UserOutlined />} 
                  className="cursor-pointer bg-gradient-to-r from-blue-500 to-purple-500"
                />
              </Dropdown>
            </Space>
          ) : (
            <Space>
              <Button type="text" onClick={handleLogin}>
                登录
              </Button>
              <Button type="primary" onClick={() => navigate('/register')}>
                注册
              </Button>
            </Space>
          )}
        </div>
      </Header>

      <Content className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-4xl mx-auto">
          {/* Hero Section */}
          <div className="text-center mb-12">
            <Title level={1} className="mb-4 bg-gradient-to-r from-blue-600 via-purple-600 to-blue-800 bg-clip-text text-transparent">
              ami.dev
            </Title>
            <Text className="text-xl text-gray-600 block mb-12">
              使用 AI 驱动的工具，快速创建、部署和管理您的智能代理应用
            </Text>
          </div>

          {/* Main Dialog */}
          <Card className="max-w-3xl mx-auto shadow-lg border-0 bg-white/90 backdrop-blur-sm">
            <div className="mb-6">
              <Title level={3} className="text-center mb-2">
                <RobotOutlined className="mr-2 text-blue-600" />
                对话框
              </Title>
              <Text className="text-gray-600 block text-center">
                描述您想要创建的应用或功能，AI 将帮助您实现
              </Text>
            </div>

            <div className="space-y-4">
              <TextArea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="例如：创建一个待办事项管理应用，包含任务分类、优先级设置和进度跟踪功能..."
                autoSize={{ minRows: 4, maxRows: 8 }}
                className="resize-none text-lg"
              />

              <div className="flex justify-between items-center">
                <Text className="text-sm text-gray-500">
                  按 {navigator.platform.includes('Mac') ? 'Cmd' : 'Ctrl'} + Enter 快速生成
                </Text>
                <Button
                  type="primary"
                  size="large"
                  icon={<SendOutlined />}
                  onClick={handleGenerate}
                  disabled={!prompt.trim()}
                  className="bg-gradient-to-r from-blue-600 to-purple-600 border-0 h-12 px-8"
                >
                  开始构建
                </Button>
              </div>
            </div>

            {/* Example Prompts */}
            <div className="mt-8 pt-6 border-t border-gray-100">
              <Text className="text-sm text-gray-600 mb-3 block">尝试这些示例：</Text>
              <div className="flex flex-wrap gap-2">
                {examplePrompts.map((example, index) => (
                  <Button
                    key={index}
                    size="small"
                    type="text"
                    className="text-blue-600 border border-blue-200 hover:bg-blue-50"
                    onClick={() => setPrompt(example)}
                  >
                    {example}
                  </Button>
                ))}
              </div>
            </div>
          </Card>

          {/* Footer */}
          <div className="text-center mt-12 text-gray-500">
            <Text>
              基于先进的 AI 技术构建
            </Text>
          </div>
        </div>
      </Content>

      {/* User Profile Modal */}
      <UserProfile 
        visible={showUserProfile} 
        onClose={() => setShowUserProfile(false)} 
      />
    </Layout>
  );
};

export default HomePage;