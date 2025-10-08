import React, { useState, useRef, useEffect } from 'react';
import { 
  Card, Input, Button, List, Avatar, Typography, message, Spin, Divider,
  Select, Space, Tooltip, Modal, Popconfirm
} from 'antd';
import { 
  SendOutlined, UserOutlined, RobotOutlined, PlusOutlined, 
  DeleteOutlined, MessageOutlined, HistoryOutlined, ExclamationCircleOutlined
} from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../store';
import { 
  sendMessage, 
  createSession, 
  loadSessions, 
  loadSessionHistory, 
  deleteSession, 
  setCurrentSession, 
  clearMessages, 
  clearError,
  checkHealth 
} from '../store/baseappSlice';

const { Title, Text } = Typography;
const { Option } = Select;

interface BaseAppChatProps {
  className?: string;
}

const BaseAppChat: React.FC<BaseAppChatProps> = ({ className }) => {
  const dispatch = useDispatch();
  const { user } = useSelector((state: RootState) => state.auth);
  const { 
    currentSession, 
    sessions, 
    messages, 
    loading, 
    sendingMessage, 
    error, 
    connected 
  } = useSelector((state: RootState) => state.baseapp);
  
  const [inputMessage, setInputMessage] = useState('');
  const [selectedSessionId, setSelectedSessionId] = useState<string | undefined>();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 显示错误消息
  useEffect(() => {
    if (error) {
      message.error(error);
      dispatch(clearError());
    }
  }, [error, dispatch]);

  // 组件加载时检查健康状态和加载会话
  useEffect(() => {
    if (user) {
      dispatch(checkHealth() as any);
      dispatch(loadSessions(user.id.toString()) as any);
    }
  }, [user, dispatch]);

  // 发送消息
  const handleSendMessage = () => {
    if (!inputMessage.trim() || !user) return;
    
    dispatch(sendMessage({
      message: inputMessage,
      userId: user.id.toString(),
      sessionId: currentSession?.session_id,
    }) as any);
    setInputMessage('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // 创建新会话
  const handleCreateSession = () => {
    if (!user) return;
    
    const title = `新对话 ${new Date().toLocaleString()}`;
    dispatch(createSession({ userId: user.id.toString(), title }) as any);
  };

  // 选择会话
  const handleSelectSession = (sessionId: string) => {
    const session = sessions.find(s => s.session_id === sessionId);
    if (session) {
      dispatch(setCurrentSession(session));
      dispatch(loadSessionHistory({ sessionId }) as any);
      setSelectedSessionId(sessionId);
    }
  };

  // 删除会话
  const handleDeleteSession = (sessionId: string) => {
    if (!user) return;
    
    dispatch(deleteSession({ sessionId, userId: user.id.toString() }) as any);
    
    // 如果删除的是当前选中的会话，清空选择
    if (sessionId === selectedSessionId) {
      setSelectedSessionId(undefined);
    }
  };

  // 清空当前对话
  const handleClearChat = () => {
    dispatch(clearMessages());
    dispatch(setCurrentSession(null));
    setSelectedSessionId(undefined);
  };

  // 连接状态指示器
  const ConnectionStatus = () => (
    <div className="flex items-center space-x-2 mb-4">
      <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
      <Text className={`text-sm ${connected ? 'text-green-600' : 'text-red-600'}`}>
        {connected ? 'BaseApp 已连接' : 'BaseApp 连接断开'}
      </Text>
      {!connected && (
        <Button 
          size="small" 
          type="link" 
          onClick={() => dispatch(checkHealth() as any)}
        >
          重试连接
        </Button>
      )}
    </div>
  );

  // 会话选择器
  const SessionSelector = () => (
    <div className="mb-4">
      <Space direction="vertical" className="w-full">
        <div className="flex items-center space-x-2">
          <Select
            value={selectedSessionId}
            placeholder="选择或创建会话"
            className="flex-1"
            onChange={handleSelectSession}
            loading={loading}
            allowClear
            onClear={() => handleClearChat()}
          >
            {sessions.map(session => (
              <Option key={session.session_id} value={session.session_id}>
                <div className="flex items-center justify-between">
                  <span className="truncate">{session.title}</span>
                  <div className="flex items-center space-x-1 text-xs text-gray-500">
                    <MessageOutlined />
                    <span>{session.message_count}</span>
                  </div>
                </div>
              </Option>
            ))}
          </Select>
          
          <Tooltip title="创建新会话">
            <Button 
              type="primary" 
              icon={<PlusOutlined />} 
              onClick={handleCreateSession}
              loading={loading}
            />
          </Tooltip>
          
          {selectedSessionId && (
            <Popconfirm
              title="确定要删除这个会话吗？"
              onConfirm={() => handleDeleteSession(selectedSessionId)}
              okText="删除"
              cancelText="取消"
              icon={<ExclamationCircleOutlined style={{ color: 'red' }} />}
            >
              <Tooltip title="删除当前会话">
                <Button 
                  danger 
                  icon={<DeleteOutlined />} 
                  loading={loading}
                />
              </Tooltip>
            </Popconfirm>
          )}
        </div>
        
        {currentSession && (
          <div className="text-xs text-gray-500">
            <HistoryOutlined className="mr-1" />
            创建于：{new Date(currentSession.created_at).toLocaleString()}
            {currentSession.updated_at !== currentSession.created_at && (
              <span className="ml-2">
                最后更新：{new Date(currentSession.updated_at).toLocaleString()}
              </span>
            )}
          </div>
        )}
      </Space>
    </div>
  );

  return (
    <Card 
      className={`h-full ${className || ''}`}
      title={
        <div className="flex items-center justify-between">
          <Title level={5} className="m-0">
            <RobotOutlined className="mr-2" />
            BaseApp AI 助手
          </Title>
          <Button 
            type="text" 
            size="small" 
            onClick={handleClearChat}
            disabled={messages.length === 0}
          >
            清空对话
          </Button>
        </div>
      }
    >
      <div className="flex flex-col h-96">
        {/* 连接状态 */}
        <ConnectionStatus />
        
        {/* 会话选择器 */}
        <SessionSelector />
        
        <Divider className="my-2" />

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto mb-4">
          {messages.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <RobotOutlined className="text-4xl mb-2" />
              <p>开始与 BaseApp AI 助手对话吧！</p>
              <p className="text-sm">选择已有会话或创建新会话开始聊天</p>
            </div>
          ) : (
            <List
              dataSource={messages}
              renderItem={(msg) => (
                <List.Item key={msg.id} className="border-none py-2">
                  <div className={`w-full flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-xs lg:max-w-md flex ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'} items-start gap-2`}>
                      <Avatar 
                        size="small" 
                        icon={msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                        className={msg.role === 'user' ? 'bg-blue-500' : 'bg-green-500'}
                      />
                      <div className={`p-3 rounded-lg ${
                        msg.role === 'user' 
                          ? 'bg-blue-500 text-white' 
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        <Text className={msg.role === 'user' ? 'text-white' : 'text-gray-800'}>
                          {msg.content}
                        </Text>
                        <div className={`text-xs mt-1 ${msg.role === 'user' ? 'text-blue-100' : 'text-gray-500'}`}>
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          )}
          
          {/* 发送消息时的加载指示器 */}
          {sendingMessage && (
            <div className="flex justify-start mb-2">
              <div className="max-w-xs lg:max-w-md flex items-start gap-2">
                <Avatar 
                  size="small" 
                  icon={<RobotOutlined />}
                  className="bg-green-500"
                />
                <div className="p-3 rounded-lg bg-gray-100">
                  <Spin size="small" />
                  <Text className="ml-2 text-gray-600">AI 正在思考...</Text>
                </div>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="flex gap-2">
          <Input.TextArea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={connected ? "输入消息..." : "BaseApp 未连接"}
            autoSize={{ minRows: 1, maxRows: 3 }}
            disabled={sendingMessage || !connected}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSendMessage}
            loading={sendingMessage}
            disabled={!inputMessage.trim() || !connected}
          >
            发送
          </Button>
        </div>
        
        {!connected && (
          <div className="mt-2 text-center">
            <Text className="text-red-500 text-sm">
              请检查 BaseApp 服务是否正常运行
            </Text>
          </div>
        )}
      </div>
    </Card>
  );
};

export default BaseAppChat;