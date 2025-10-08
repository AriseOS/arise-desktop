import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { 
  baseappService, 
  BaseAppChatResponse, 
  BaseAppSessionInfo, 
  BaseAppMessage as APIBaseAppMessage,
  BaseAppSessionListResponse 
} from '../services/baseappAPI';

export interface BaseAppMessage {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: string;
}

export interface BaseAppSession {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  messages?: BaseAppMessage[];
}

interface BaseAppState {
  currentSession: BaseAppSession | null;
  sessions: BaseAppSession[];
  messages: BaseAppMessage[];
  loading: boolean;
  sendingMessage: boolean;
  error: string | null;
  connected: boolean;
}

const initialState: BaseAppState = {
  currentSession: null,
  sessions: [],
  messages: [],
  loading: false,
  sendingMessage: false,
  error: null,
  connected: false,
};

// 异步thunks
export const sendMessage = createAsyncThunk(
  'baseapp/sendMessage',
  async ({ message, userId, sessionId }: { message: string; userId: string; sessionId?: string }, { rejectWithValue }) => {
    try {
      const response = await baseappService.sendMessage({
        message,
        user_id: userId,
        session_id: sessionId,
      });
      return response;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '发送消息失败');
    }
  }
);

export const createSession = createAsyncThunk(
  'baseapp/createSession',
  async ({ userId, title }: { userId: string; title?: string }, { rejectWithValue }) => {
    try {
      const response = await baseappService.createSession({
        user_id: userId,
        title: title || `新对话 ${new Date().toLocaleString()}`,
      });
      return response;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '创建会话失败');
    }
  }
);

export const loadSessions = createAsyncThunk(
  'baseapp/loadSessions',
  async (userId: string, { rejectWithValue }) => {
    try {
      const response = await baseappService.getSessions(userId);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '加载会话列表失败');
    }
  }
);

export const loadSessionHistory = createAsyncThunk(
  'baseapp/loadSessionHistory',
  async ({ sessionId, limit }: { sessionId: string; limit?: number }, { rejectWithValue }) => {
    try {
      const response = await baseappService.getSessionHistory(sessionId, limit);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '加载会话历史失败');
    }
  }
);

export const deleteSession = createAsyncThunk(
  'baseapp/deleteSession',
  async ({ sessionId, userId }: { sessionId: string; userId: string }, { rejectWithValue }) => {
    try {
      await baseappService.deleteSession(sessionId, userId);
      return sessionId;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '删除会话失败');
    }
  }
);

export const checkHealth = createAsyncThunk(
  'baseapp/checkHealth',
  async (_, { rejectWithValue }) => {
    try {
      const response = await baseappService.healthCheck();
      return response;
    } catch (error: any) {
      return rejectWithValue('BaseApp 服务连接失败');
    }
  }
);

const baseappSlice = createSlice({
  name: 'baseapp',
  initialState,
  reducers: {
    setCurrentSession: (state, action: PayloadAction<BaseAppSession | null>) => {
      state.currentSession = action.payload;
      if (action.payload) {
        state.messages = action.payload.messages || [];
      } else {
        state.messages = [];
      }
    },
    clearMessages: (state) => {
      state.messages = [];
    },
    clearError: (state) => {
      state.error = null;
    },
    addMessage: (state, action: PayloadAction<BaseAppMessage>) => {
      state.messages.push(action.payload);
    },
    updateSessionInList: (state, action: PayloadAction<BaseAppSession>) => {
      const index = state.sessions.findIndex(s => s.session_id === action.payload.session_id);
      if (index !== -1) {
        state.sessions[index] = action.payload;
      }
    },
  },
  extraReducers: (builder) => {
    builder
      // 发送消息
      .addCase(sendMessage.pending, (state) => {
        state.sendingMessage = true;
        state.error = null;
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        state.sendingMessage = false;
        
        // 添加用户消息
        const userMessage: BaseAppMessage = {
          id: `user_${Date.now()}`,
          content: action.meta.arg.message,
          role: 'user',
          timestamp: action.payload.timestamp,
        };
        state.messages.push(userMessage);
        
        // 添加助手回复
        const assistantMessage: BaseAppMessage = {
          id: action.payload.message_id || `assistant_${Date.now()}`,
          content: action.payload.response,
          role: 'assistant',
          timestamp: action.payload.timestamp,
        };
        state.messages.push(assistantMessage);
        
        // 更新当前会话
        if (state.currentSession) {
          state.currentSession.session_id = action.payload.session_id;
          state.currentSession.message_count = state.messages.length;
          state.currentSession.updated_at = action.payload.timestamp;
        } else {
          // 创建新会话
          state.currentSession = {
            session_id: action.payload.session_id,
            title: `对话 ${new Date().toLocaleString()}`,
            created_at: action.payload.timestamp,
            updated_at: action.payload.timestamp,
            message_count: state.messages.length,
            messages: state.messages,
          };
        }
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.sendingMessage = false;
        state.error = action.payload as string;
      })
      
      // 创建会话
      .addCase(createSession.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createSession.fulfilled, (state, action) => {
        state.loading = false;
        const newSession: BaseAppSession = action.payload;
        state.sessions.unshift(newSession);
        state.currentSession = newSession;
        state.messages = [];
      })
      .addCase(createSession.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // 加载会话列表
      .addCase(loadSessions.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadSessions.fulfilled, (state, action) => {
        state.loading = false;
        state.sessions = action.payload.sessions;
      })
      .addCase(loadSessions.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // 加载会话历史
      .addCase(loadSessionHistory.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadSessionHistory.fulfilled, (state, action) => {
        state.loading = false;
        // 转换 API 消息格式到内部格式
        state.messages = action.payload.messages.map((msg: APIBaseAppMessage) => ({
          id: msg.id,
          content: msg.content,
          role: msg.role,
          timestamp: msg.timestamp,
        }));
        
        // 更新当前会话的消息
        if (state.currentSession && state.currentSession.session_id === action.payload.session_id) {
          state.currentSession.messages = state.messages;
          state.currentSession.message_count = state.messages.length;
        }
      })
      .addCase(loadSessionHistory.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // 删除会话
      .addCase(deleteSession.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteSession.fulfilled, (state, action) => {
        state.loading = false;
        const sessionId = action.payload;
        state.sessions = state.sessions.filter(s => s.session_id !== sessionId);
        
        // 如果删除的是当前会话，清空当前会话
        if (state.currentSession && state.currentSession.session_id === sessionId) {
          state.currentSession = null;
          state.messages = [];
        }
      })
      .addCase(deleteSession.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      
      // 健康检查
      .addCase(checkHealth.fulfilled, (state) => {
        state.connected = true;
      })
      .addCase(checkHealth.rejected, (state) => {
        state.connected = false;
      });
  },
});

export const { 
  setCurrentSession, 
  clearMessages, 
  clearError, 
  addMessage, 
  updateSessionInList 
} = baseappSlice.actions;

export default baseappSlice.reducer;