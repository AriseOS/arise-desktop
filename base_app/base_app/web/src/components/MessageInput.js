import React, { useState, useRef, useEffect } from 'react';

const MessageInput = ({ onSendMessage, loading }) => {
  const [message, setMessage] = useState('');
  const textareaRef = useRef(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (message.trim() && !loading) {
      onSendMessage(message.trim());
      setMessage('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleInputChange = (e) => {
    setMessage(e.target.value);
  };

  // 自动调整文本框高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [message]);

  return (
    <div className="input-container">
      <form className="input-form" onSubmit={handleSubmit}>
        <textarea
          ref={textareaRef}
          className="input-textarea"
          placeholder="输入消息... (按 Enter 发送，Shift+Enter 换行)"
          value={message}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          disabled={loading}
          rows={1}
        />
        <button
          type="submit"
          className="send-btn"
          disabled={!message.trim() || loading}
        >
          {loading ? '发送中...' : '发送'}
        </button>
      </form>
    </div>
  );
};

export default MessageInput;