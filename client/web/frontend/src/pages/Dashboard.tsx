import React from 'react';
import { Layout, Button, Typography, Avatar, Dropdown, Space } from 'antd';
import { UserOutlined, LogoutOutlined, MessageOutlined, RobotOutlined, ExperimentOutlined, SettingOutlined } from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { RootState } from '../store';
import { logout } from '../store/authSlice';
import ChatBox from '../components/ChatBox';

const { Header, Content } = Layout;
const { Title, Text } = Typography;

const Dashboard: React.FC = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { user } = useSelector((state: RootState) => state.auth);

  const handleLogout = () => {
    dispatch(logout());
  };

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人资料',
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

  return (
    <Layout className="min-h-screen">
      <Header className="bg-white shadow-sm flex items-center justify-between px-6">
        <div className="flex items-center">
          <Title level={3} className="m-0 text-blue-600">
            ami.dev
          </Title>
        </div>
        
        <div className="flex items-center space-x-4">
          <Space>
            <Button 
              type="default" 
              icon={<RobotOutlined />}
              onClick={() => navigate(`/users/${user?.id}/agents/baseapp`)}
            >
              BaseApp
            </Button>
            <Text>欢迎回来，{user?.username}！</Text>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Avatar 
                icon={<UserOutlined />} 
                className="cursor-pointer bg-blue-500"
              />
            </Dropdown>
          </Space>
        </div>
      </Header>

      <Content className="p-6">
        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 主要内容区域 */}
            <div className="lg:col-span-2">
              <div className="bg-white rounded-lg shadow-sm p-6">
                <Title level={4} className="mb-4">
                  <MessageOutlined className="mr-2" />
                  Agent 助手
                </Title>
                <div className="text-gray-600 mb-4">
                  与您的 AI 助手对话，创建和管理您的 Agent。
                </div>
                
                {/* 快捷操作 */}
                <div className="grid grid-cols-2 gap-4 mb-6">
                  <div 
                    className="p-4 border rounded-lg hover:bg-gray-50 cursor-pointer"
                    onClick={() => navigate('/workspace')}
                  >
                    <h4 className="font-medium flex items-center">
                      <MessageOutlined className="mr-2" />
                      工作台
                    </h4>
                    <p className="text-sm text-gray-600">开始构建您的专属 AI 助手</p>
                  </div>
                  <div 
                    className="p-4 border rounded-lg hover:bg-gray-50 cursor-pointer"
                    onClick={() => navigate(`/users/${user?.id}/agents/baseapp`)}
                  >
                    <h4 className="font-medium flex items-center">
                      <RobotOutlined className="mr-2" />
                      BaseApp
                    </h4>
                    <p className="text-sm text-gray-600">体验高级 AI 对话功能</p>
                  </div>
                  <div 
                    className="p-4 border rounded-lg hover:bg-gray-50 cursor-pointer"
                    onClick={() => navigate('/agent-manage')}
                  >
                    <h4 className="font-medium flex items-center">
                      <SettingOutlined className="mr-2" />
                      Agent管理
                    </h4>
                    <p className="text-sm text-gray-600">管理您的所有Agent</p>
                  </div>
                  <div 
                    className="p-4 border rounded-lg hover:bg-gray-50 cursor-pointer"
                    onClick={() => navigate('/agent-test')}
                  >
                    <h4 className="font-medium flex items-center">
                      <ExperimentOutlined className="mr-2" />
                      架构测试
                    </h4>
                    <p className="text-sm text-gray-600">测试新Agent架构组件</p>
                  </div>
                </div>
              </div>
            </div>

            {/* 聊天区域 */}
            <div className="lg:col-span-1">
              <ChatBox />
            </div>
          </div>
        </div>
      </Content>
    </Layout>
  );
};

export default Dashboard;