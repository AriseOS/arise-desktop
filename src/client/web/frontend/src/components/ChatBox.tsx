import React, { useState, useRef, useEffect } from 'react';
import { Card, Input, Button, List, Avatar, Typography, message, Spin } from 'antd';
import { SendOutlined, UserOutlined, RobotOutlined } from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../store';
import { sendMessage, clearMessages } from '../store/chatSlice';

const { Title, Text } = Typography;

const ChatBox: React.FC = () => {
  const dispatch = useDispatch();
  const { messages, loading, error } = useSelector((state: RootState) => state.chat);
  const { user } = useSelector((state: RootState) => state.auth);
  const [inputMessage, setInputMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (error) {
      message.error(error);
    }
  }, [error]);

  const handleSendMessage = () => {
    if (!inputMessage.trim()) return;
    
    dispatch(sendMessage(inputMessage) as any);
    setInputMessage('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleClearChat = () => {
    dispatch(clearMessages());
  };

  return (
    <Card 
      className="h-full"
      title={
        <div className="flex items-center justify-between">
          <Title level={5} className="m-0">
            <RobotOutlined className="mr-2" />
            AI 助手
          </Title>
          <Button 
            type="text" 
            size="small" 
            onClick={handleClearChat}
            disabled={messages.length === 0}
          >
            清空
          </Button>
        </div>
      }
    >
      <div className="flex flex-col h-96">
        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto mb-4">
          {messages.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <RobotOutlined className="text-4xl mb-2" />
              <p>开始与 AI 助手对话吧！</p>
            </div>
          ) : (
            <List
              dataSource={messages.flatMap(msg => [
                { type: 'user', content: msg.message, timestamp: msg.timestamp },
                { type: 'assistant', content: msg.response, timestamp: msg.timestamp }
              ])}
              renderItem={(item) => (
                <List.Item key={`${item.timestamp}-${item.type}`} className="border-none py-2">
                  <div className={`w-full flex ${item.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-xs lg:max-w-md flex ${item.type === 'user' ? 'flex-row-reverse' : 'flex-row'} items-start gap-2`}>
                      <Avatar 
                        size="small" 
                        icon={item.type === 'user' ? <UserOutlined /> : <RobotOutlined />}
                        className={item.type === 'user' ? 'bg-blue-500' : 'bg-green-500'}
                      />
                      <div className={`p-3 rounded-lg ${
                        item.type === 'user' 
                          ? 'bg-blue-500 text-white' 
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        <Text className={item.type === 'user' ? 'text-white' : 'text-gray-800'}>
                          {item.content}
                        </Text>
                      </div>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          )}
          
          {/* 加载指示器 */}
          {loading && (
            <div className="flex justify-start mb-2">
              <div className="max-w-xs lg:max-w-md flex items-start gap-2">
                <Avatar 
                  size="small" 
                  icon={<RobotOutlined />}
                  className="bg-green-500"
                />
                <div className="p-3 rounded-lg bg-gray-100">
                  <Spin size="small" />
                  <Text className="ml-2 text-gray-600">正在思考...</Text>
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
            placeholder="输入消息..."
            autoSize={{ minRows: 1, maxRows: 3 }}
            disabled={loading}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSendMessage}
            loading={loading}
            disabled={!inputMessage.trim()}
          >
            发送
          </Button>
        </div>
      </div>
    </Card>
  );
};

export default ChatBox;