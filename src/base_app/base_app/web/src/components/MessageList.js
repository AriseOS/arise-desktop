import React, { useEffect, useRef } from 'react';

const MessageList = ({ messages, loading }) => {
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const formatTime = (timestamp) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('zh-CN', { 
        hour: '2-digit', 
        minute: '2-digit' 
      });
    } catch (error) {
      return '';
    }
  };

  const formatMessage = (content) => {
    // 简单的换行处理
    return content.split('\n').map((line, index) => (
      <React.Fragment key={index}>
        {line}
        {index < content.split('\n').length - 1 && <br />}
      </React.Fragment>
    ));
  };

  if (messages.length === 0 && !loading) {
    return (
      <div className="empty-state">
        <h3>开始对话</h3>
        <p>发送消息开始与AI助手对话</p>
      </div>
    );
  }

  return (
    <div className="messages-container">
      {messages.map((message) => (
        <div 
          key={message.id} 
          className={`message ${message.role}`}
        >
          <div className="message-content">
            {formatMessage(message.content)}
            <div className="message-time">
              {formatTime(message.timestamp)}
            </div>
          </div>
        </div>
      ))}
      
      {loading && (
        <div className="message assistant">
          <div className="message-content">
            <div className="loading">正在思考...</div>
          </div>
        </div>
      )}
      
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageList;