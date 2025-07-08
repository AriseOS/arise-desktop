import React, { useState, useEffect } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { apiService } from './services/api';
import SessionList from './components/SessionList';
import MessageList from './components/MessageList';
import MessageInput from './components/MessageInput';
import './App.css';

const App = () => {
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [initialized, setInitialized] = useState(false);

  const userId = 'default-user'; // 可以根据需要实现用户系统

  // 初始化应用
  useEffect(() => {
    const initApp = async () => {
      try {
        setLoading(true);
        await loadSessions();
        setInitialized(true);
      } catch (err) {
        setError('初始化应用失败');
        console.error('初始化失败:', err);
      } finally {
        setLoading(false);
      }
    };

    initApp();
  }, []);

  // 加载会话列表
  const loadSessions = async () => {
    try {
      const response = await apiService.getSessions(userId);
      setSessions(response.sessions || []);
    } catch (err) {
      console.error('加载会话列表失败:', err);
      setSessions([]);
    }
  };

  // 加载会话历史
  const loadSessionHistory = async (sessionId) => {
    try {
      setLoading(true);
      const response = await apiService.getSessionHistory(sessionId);
      setMessages(response.messages || []);
    } catch (err) {
      console.error('加载会话历史失败:', err);
      setError('加载会话历史失败');
      setMessages([]);
    } finally {
      setLoading(false);
    }
  };

  // 创建新会话
  const handleNewSession = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await apiService.createSession(userId);
      const newSession = response;
      
      // 更新会话列表
      setSessions(prev => [newSession, ...prev]);
      
      // 切换到新会话
      setCurrentSessionId(newSession.session_id);
      setMessages([]);
      
    } catch (err) {
      console.error('创建会话失败:', err);
      setError('创建会话失败');
    } finally {
      setLoading(false);
    }
  };

  // 选择会话
  const handleSelectSession = async (sessionId) => {
    if (sessionId === currentSessionId) return;
    
    setCurrentSessionId(sessionId);
    setError(null);
    
    if (sessionId) {
      await loadSessionHistory(sessionId);
    } else {
      setMessages([]);
    }
  };

  // 发送消息
  const handleSendMessage = async (messageText) => {
    if (!messageText.trim()) return;

    try {
      setLoading(true);
      setError(null);

      // 如果没有当前会话，先创建一个
      let sessionId = currentSessionId;
      if (!sessionId) {
        const newSession = await apiService.createSession(userId, messageText.substring(0, 20));
        sessionId = newSession.session_id;
        setCurrentSessionId(sessionId);
        setSessions(prev => [newSession, ...prev]);
      }

      // 立即添加用户消息到界面
      const userMessage = {
        id: uuidv4(),
        role: 'user',
        content: messageText,
        timestamp: new Date().toISOString(),
      };
      
      setMessages(prev => [...prev, userMessage]);

      // 发送消息到后端
      const response = await apiService.sendMessage(messageText, sessionId, userId);
      
      if (response.success) {
        // 更新消息列表（替换临时用户消息，添加助手回复）
        setMessages(prev => {
          const newMessages = [...prev];
          // 移除临时用户消息
          newMessages.pop();
          // 添加服务器返回的用户消息和助手回复
          newMessages.push(response.user_message);
          newMessages.push(response.assistant_message);
          return newMessages;
        });

        // 更新会话列表中的会话信息
        setSessions(prev => prev.map(session => 
          session.session_id === sessionId 
            ? { ...session, message_count: session.message_count + 2, updated_at: new Date().toISOString() }
            : session
        ));
      } else {
        setError(response.error || '发送消息失败');
        // 移除临时用户消息
        setMessages(prev => prev.slice(0, -1));
      }
    } catch (err) {
      console.error('发送消息失败:', err);
      setError('发送消息失败');
      // 移除临时用户消息
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  // 获取当前会话信息
  const getCurrentSession = () => {
    return sessions.find(session => session.session_id === currentSessionId);
  };

  if (!initialized) {
    return (
      <div className="app">
        <div className="loading">正在初始化...</div>
      </div>
    );
  }

  return (
    <div className="app">
      <SessionList
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        loading={loading}
      />
      
      <div className="chat-area">
        <div className="chat-header">
          <h2>
            {getCurrentSession()?.title || '选择对话或创建新对话'}
          </h2>
        </div>
        
        {error && (
          <div className="error">
            {error}
          </div>
        )}
        
        <MessageList
          messages={messages}
          loading={loading}
        />
        
        <MessageInput
          onSendMessage={handleSendMessage}
          loading={loading}
        />
      </div>
    </div>
  );
};

export default App;