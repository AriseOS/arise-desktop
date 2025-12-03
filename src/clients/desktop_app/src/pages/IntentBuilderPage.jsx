import React, { useState, useEffect, useRef } from 'react';
import Icon from '../components/Icons';
import '../styles/IntentBuilderPage.css';

const API_BASE = "http://127.0.0.1:8765";

/**
 * Intent Builder Page - Lovable-style real-time AI assistant UI
 *
 * This page provides a conversational interface to modify MetaFlow/Workflow
 * with real-time streaming updates showing:
 * - AI thinking process
 * - Tool calls (Read, Write, Edit)
 * - Generated content
 */
function IntentBuilderPage({ session, onNavigate, showStatus, params = {} }) {
  const userId = session?.username;
  // Session state
  const [sessionId, setSessionId] = useState(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);

  // Chat state
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');

  // Current streaming state
  const [currentText, setCurrentText] = useState('');
  const [currentToolUse, setCurrentToolUse] = useState(null);
  const [agentState, setAgentState] = useState(null);

  // Refs
  const messagesEndRef = useRef(null);
  const eventSourceRef = useRef(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentText, currentToolUse]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (sessionId) {
        // Close session
        fetch(`${API_BASE}/api/intent-builder/${sessionId}`, {
          method: 'DELETE'
        }).catch(console.error);
      }
    };
  }, [sessionId]);

  // Start a new session
  const startSession = async (userQuery) => {
    try {
      setIsConnecting(true);
      showStatus('Starting Intent Builder session...', 'info');

      // Create session
      const response = await fetch(`${API_BASE}/api/intent-builder/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          user_query: userQuery,
          task_description: params.taskDescription || null
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to start session: ${response.statusText}`);
      }

      const result = await response.json();
      setSessionId(result.session_id);

      // Add user message
      setMessages(prev => [...prev, {
        role: 'user',
        content: userQuery
      }]);

      // Start streaming
      streamResponse(result.session_id, true);

    } catch (error) {
      console.error('Start session error:', error);
      showStatus(`Failed to start session: ${error.message}`, 'error');
    } finally {
      setIsConnecting(false);
    }
  };

  // Stream response from server
  const streamResponse = async (sid, isInitial = false) => {
    setIsStreaming(true);
    setCurrentText('');
    setCurrentToolUse(null);

    try {
      const url = isInitial
        ? `${API_BASE}/api/intent-builder/${sid}/stream`
        : `${API_BASE}/api/intent-builder/${sid}/chat`;

      // For chat, we need to POST with the message
      if (!isInitial) {
        // Use fetch with POST for chat
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: inputValue })
        });

        if (!response.ok) {
          throw new Error(`Stream request failed: ${response.statusText}`);
        }

        // Read the stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let accumulatedText = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete SSE events
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const jsonStr = line.slice(6);
              try {
                const event = JSON.parse(jsonStr);
                accumulatedText = handleStreamEvent(event, accumulatedText);
              } catch (e) {
                console.error('Failed to parse event:', e);
              }
            }
          }
        }

        // Finalize message
        if (accumulatedText) {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: accumulatedText
          }]);
        }

      } else {
        // For initial stream, use EventSource pattern with GET
        const eventSource = new EventSource(url);
        eventSourceRef.current = eventSource;

        let accumulatedText = '';

        eventSource.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            accumulatedText = handleStreamEvent(data, accumulatedText);
          } catch (e) {
            console.error('Failed to parse event:', e);
          }
        };

        eventSource.onerror = (error) => {
          console.error('EventSource error:', error);
          eventSource.close();
          setIsStreaming(false);

          // Finalize message
          if (accumulatedText) {
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: accumulatedText
            }]);
          }
        };
      }

    } catch (error) {
      console.error('Stream error:', error);
      showStatus(`Stream error: ${error.message}`, 'error');
    } finally {
      setIsStreaming(false);
      setCurrentText('');
      setCurrentToolUse(null);
    }
  };

  // Handle a single stream event
  const handleStreamEvent = (event, accumulatedText) => {
    switch (event.type) {
      case 'text':
        accumulatedText += event.content;
        setCurrentText(accumulatedText);
        break;

      case 'tool_use':
        setCurrentToolUse({
          name: event.tool_name,
          input: event.tool_input
        });
        break;

      case 'tool_result':
        // Clear tool use indicator
        setCurrentToolUse(null);
        break;

      case 'complete':
        setAgentState(event.result);
        setCurrentText('');
        setCurrentToolUse(null);

        // Add final message
        if (accumulatedText) {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: accumulatedText
          }]);
          accumulatedText = '';
        }

        // Note: Changes are automatically saved by the Agent on complete event

        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
        setIsStreaming(false);
        showStatus('Response complete (auto-saved to cloud)', 'success');
        break;

      case 'error':
        showStatus(`Error: ${event.content}`, 'error');
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
        }
        setIsStreaming(false);
        break;

      default:
        console.log('Unknown event type:', event.type);
    }

    return accumulatedText;
  };

  // Send a message
  const handleSend = async () => {
    if (!inputValue.trim() || isStreaming) return;

    const message = inputValue.trim();
    setInputValue('');

    if (!sessionId) {
      // Start new session
      await startSession(message);
    } else {
      // Add user message
      setMessages(prev => [...prev, {
        role: 'user',
        content: message
      }]);

      // Continue conversation
      streamResponse(sessionId, false);
    }
  };

  // Handle Enter key
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Render tool use indicator
  const renderToolUse = () => {
    if (!currentToolUse) return null;

    const { name, input } = currentToolUse;
    let description = '';

    switch (name) {
      case 'Read':
        description = `Reading ${input?.file_path || 'file'}...`;
        break;
      case 'Write':
        description = `Writing to ${input?.file_path || 'file'}...`;
        break;
      case 'Edit':
        description = `Editing ${input?.file_path || 'file'}...`;
        break;
      case 'Glob':
        description = `Searching for ${input?.pattern || 'files'}...`;
        break;
      case 'Grep':
        description = `Searching for "${input?.pattern || 'pattern'}"...`;
        break;
      case 'Bash':
        description = `Running command...`;
        break;
      default:
        description = `Using ${name}...`;
    }

    return (
      <div className="tool-use-indicator">
        <div className="tool-spinner"></div>
        <span className="tool-name">{name}</span>
        <span className="tool-desc">{description}</span>
      </div>
    );
  };

  return (
    <div className="page intent-builder-page">
      <div className="page-header">
        <button className="back-button" onClick={() => onNavigate('main')}>
          <Icon icon="arrowLeft" />
        </button>
        <div className="page-title"><Icon icon="cpu" size={28} /> Intent Builder</div>
        {agentState && (
          <div className="agent-state-badge">
            Phase: {agentState.phase}
          </div>
        )}
      </div>

      <div className="chat-container">
        {/* Messages */}
        <div className="messages-list">
          {messages.length === 0 && !isStreaming && (
            <div className="empty-state">
              <h3><Icon icon="cpu" size={32} /> Intent Builder Assistant</h3>
              <p>Describe what modifications you want to make to your MetaFlow or Workflow.</p>
              <div className="example-prompts">
                <p><strong>Example prompts:</strong></p>
                <ul>
                  <li>"Add a scroll step before data extraction"</li>
                  <li>"Change the output format to include timestamps"</li>
                  <li>"Add error handling for network failures"</li>
                </ul>
              </div>
            </div>
          )}

          {messages.map((msg, index) => (
            <div key={index} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? <Icon icon="user" size={20} /> : <Icon icon="cpu" size={20} />}
              </div>
              <div className="message-content">
                <pre>{msg.content}</pre>
              </div>
            </div>
          ))}

          {/* Current streaming content */}
          {isStreaming && currentText && (
            <div className="message assistant streaming">
              <div className="message-avatar"><Icon icon="cpu" size={20} /></div>
              <div className="message-content">
                <pre>{currentText}</pre>
                <span className="cursor-blink">▊</span>
              </div>
            </div>
          )}

          {/* Tool use indicator */}
          {renderToolUse()}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="input-area">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={sessionId ? "Type your message..." : "Describe what you want to build or modify..."}
            disabled={isStreaming || isConnecting}
            rows={3}
          />
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isStreaming || isConnecting}
            className="send-button"
          >
            {isStreaming ? (
              <div className="button-spinner"></div>
            ) : (
              <Icon icon="send" size={20} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default IntentBuilderPage;
