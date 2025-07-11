import React from 'react';
import { Modal, Card, Avatar, Typography, Descriptions, Tag, Button, Space } from 'antd';
import { UserOutlined, CalendarOutlined, MailOutlined, IdcardOutlined, CloseOutlined } from '@ant-design/icons';
import { useSelector } from 'react-redux';
import { RootState } from '../store';

const { Title, Text } = Typography;

interface UserProfileProps {
  visible: boolean;
  onClose: () => void;
}

const UserProfile: React.FC<UserProfileProps> = ({ visible, onClose }) => {
  const { user } = useSelector((state: RootState) => state.auth);

  if (!user) return null;

  return (
    <Modal
      title={null}
      open={visible}
      onCancel={onClose}
      footer={null}
      width={500}
      closeIcon={<CloseOutlined />}
      centered
    >
      <Card className="border-0 shadow-none">
        <div className="text-center mb-6">
          <Avatar 
            size={80} 
            icon={<UserOutlined />}
            className="bg-gradient-to-r from-blue-500 to-purple-500 mb-4"
          />
          <Title level={3} className="mb-2">{user.username}</Title>
          <Tag color="blue" className="mb-4">活跃用户</Tag>
        </div>

        <Descriptions column={1} size="middle" className="mb-6">
          <Descriptions.Item 
            label={
              <Space>
                <IdcardOutlined className="text-gray-500" />
                <span>用户ID</span>
              </Space>
            }
          >
            {user.id || 'N/A'}
          </Descriptions.Item>
          
          <Descriptions.Item 
            label={
              <Space>
                <UserOutlined className="text-gray-500" />
                <span>用户名</span>
              </Space>
            }
          >
            {user.username}
          </Descriptions.Item>

          <Descriptions.Item 
            label={
              <Space>
                <MailOutlined className="text-gray-500" />
                <span>邮箱</span>
              </Space>
            }
          >
            {user.email || '未设置'}
          </Descriptions.Item>

          <Descriptions.Item 
            label={
              <Space>
                <CalendarOutlined className="text-gray-500" />
                <span>注册时间</span>
              </Space>
            }
          >
            {user.created_at ? new Date(user.created_at).toLocaleDateString('zh-CN') : '未知'}
          </Descriptions.Item>
        </Descriptions>

        <div className="bg-gray-50 rounded-lg p-4 mb-6">
          <Title level={5} className="mb-3">账户统计</Title>
          <div className="grid grid-cols-2 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-blue-600">0</div>
              <Text className="text-gray-600">创建的代理</Text>
            </div>
            <div>
              <div className="text-2xl font-bold text-green-600">0</div>
              <Text className="text-gray-600">对话次数</Text>
            </div>
          </div>
        </div>

        <div className="text-center">
          <Space>
            <Button type="primary" onClick={onClose}>
              关闭
            </Button>
            <Button type="default" disabled>
              编辑资料
            </Button>
          </Space>
        </div>
      </Card>
    </Modal>
  );
};

export default UserProfile;