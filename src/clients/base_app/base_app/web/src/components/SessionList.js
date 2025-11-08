import React from 'react';

const SessionList = ({ sessions, currentSessionId, onSelectSession, onNewSession, loading }) => {
  const formatTime = (timestamp) => {
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const isToday = date.toDateString() === now.toDateString();
      
      if (isToday) {
        return date.toLocaleTimeString('zh-CN', { 
          hour: '2-digit', 
          minute: '2-digit' 
        });
      } else {
        return date.toLocaleDateString('zh-CN', {
          month: '2-digit',
          day: '2-digit'
        });
      }
    } catch (error) {
      return '';
    }
  };

  const truncateTitle = (title, maxLength = 20) => {
    if (title.length <= maxLength) return title;
    return title.substring(0, maxLength) + '...';
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1>BaseApp</h1>
        <button 
          className="new-chat-btn" 
          onClick={onNewSession}
          disabled={loading}
        >
          {loading ? '创建中...' : '新建对话'}
        </button>
      </div>
      
      <div className="sessions-list">
        {sessions.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#6c757d', padding: '20px' }}>
            暂无对话记录
          </div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.session_id}
              className={`session-item ${currentSessionId === session.session_id ? 'active' : ''}`}
              onClick={() => onSelectSession(session.session_id)}
            >
              <div className="session-title">
                {truncateTitle(session.title)}
              </div>
              <div className="session-time">
                {formatTime(session.updated_at)} • {session.message_count} 条消息
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default SessionList;