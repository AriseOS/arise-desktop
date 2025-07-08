import React, { useEffect } from 'react';
import { Layout, Button, Typography, Avatar, Dropdown, Space, Card, Row, Col } from 'antd';
import { 
  UserOutlined, LogoutOutlined, MessageOutlined, 
  RobotOutlined, SettingOutlined, HistoryOutlined,
  ApiOutlined, HeartOutlined
} from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../store';
import { logout } from '../store/authSlice';
import { checkHealth, loadSessions } from '../store/baseappSlice';
import BaseAppChat from '../components/BaseAppChat';

const { Header, Content } = Layout;
const { Title, Text, Paragraph } = Typography;

const BaseAppPage: React.FC = () => {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const { connected, sessions } = useSelector((state: RootState) => state.baseapp);

  useEffect(() => {
    // 页面加载时检查连接状态
    dispatch(checkHealth() as any);
    if (user) {
      dispatch(loadSessions(user.id.toString()) as any);
    }
  }, [dispatch, user]);

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
      key: 'settings',
      icon: <SettingOutlined />,
      label: '设置',
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
          <Title level={3} className="m-0 text-green-600">
            <RobotOutlined className="mr-2" />
            BaseApp
          </Title>
          <div className="ml-4 flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
            <Text className={`text-sm ${connected ? 'text-green-600' : 'text-red-600'}`}>
              {connected ? '已连接' : '未连接'}
            </Text>
          </div>
        </div>
        
        <div className="flex items-center space-x-4">
          <Space>
            <Text>欢迎，{user?.username}！</Text>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Avatar 
                icon={<UserOutlined />} 
                className="cursor-pointer bg-green-500"
              />
            </Dropdown>
          </Space>
        </div>
      </Header>

      <Content className="p-6">
        <div className="max-w-7xl mx-auto">
          <Row gutter={[24, 24]}>
            {/* 左侧信息面板 */}
            <Col xs={24} lg={8}>
              <Space direction="vertical" className="w-full" size="large">
                {/* 欢迎卡片 */}
                <Card>
                  <Title level={4}>
                    <HeartOutlined className="mr-2 text-red-500" />
                    欢迎使用 BaseApp
                  </Title>
                  <Paragraph className="text-gray-600">
                    BaseApp 是一个强大的 AI 助手平台，可以帮助您处理各种任务和问题。
                    通过右侧的聊天界面开始与 AI 助手对话吧！
                  </Paragraph>
                </Card>

                {/* 统计信息 */}
                <Card title={
                  <span>
                    <HistoryOutlined className="mr-2" />
                    会话统计
                  </span>
                }>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <Text>总会话数：</Text>
                      <Text strong>{sessions.length}</Text>
                    </div>
                    <div className="flex justify-between items-center">
                      <Text>服务状态：</Text>
                      <Text className={connected ? 'text-green-600' : 'text-red-600'}>
                        {connected ? '正常' : '断线'}
                      </Text>
                    </div>
                    <div className="flex justify-between items-center">
                      <Text>总消息数：</Text>
                      <Text strong>
                        {sessions.reduce((total, session) => total + session.message_count, 0)}
                      </Text>
                    </div>
                  </div>
                </Card>

                {/* 功能介绍 */}
                <Card title={
                  <span>
                    <ApiOutlined className="mr-2" />
                    主要功能
                  </span>
                }>
                  <div className="space-y-2">
                    <div className="flex items-start space-x-2">
                      <MessageOutlined className="text-blue-500 mt-1" />
                      <div>
                        <Text strong>智能对话</Text>
                        <div className="text-sm text-gray-600">与 AI 助手进行自然语言对话</div>
                      </div>
                    </div>
                    <div className="flex items-start space-x-2">
                      <HistoryOutlined className="text-green-500 mt-1" />
                      <div>
                        <Text strong>会话管理</Text>
                        <div className="text-sm text-gray-600">创建、保存和管理多个对话会话</div>
                      </div>
                    </div>
                    <div className="flex items-start space-x-2">
                      <RobotOutlined className="text-purple-500 mt-1" />
                      <div>
                        <Text strong>持续学习</Text>
                        <div className="text-sm text-gray-600">AI 助手会记住对话上下文</div>
                      </div>
                    </div>
                  </div>
                </Card>
              </Space>
            </Col>

            {/* 右侧聊天区域 */}
            <Col xs={24} lg={16}>
              <BaseAppChat className="h-full" />
            </Col>
          </Row>
        </div>
      </Content>
    </Layout>
  );
};

export default BaseAppPage;