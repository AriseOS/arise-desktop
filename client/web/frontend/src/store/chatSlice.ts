import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { chatAPI } from '../services/chatAPI';

export interface ChatMessage {
  id: string;
  message: string;
  response: string;
  timestamp: Date;
  session_id: string;
}

interface ChatState {
  messages: ChatMessage[];
  currentSessionId: string | null;
  loading: boolean;
  error: string | null;
}

const initialState: ChatState = {
  messages: [],
  currentSessionId: null,
  loading: false,
  error: null,
};

// 发送聊天消息
export const sendMessage = createAsyncThunk(
  'chat/sendMessage',
  async (message: string, { getState, rejectWithValue }) => {
    try {
      const state = getState() as any;
      const sessionId = state.chat.currentSessionId;
      
      const response = await chatAPI.sendMessage({
        message,
        session_id: sessionId
      });
      
      return {
        id: Date.now().toString(),
        message,
        response: response.response,
        timestamp: new Date(),
        session_id: response.session_id,
      };
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '发送消息失败');
    }
  }
);

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    clearMessages: (state) => {
      state.messages = [];
      state.currentSessionId = null;
    },
    setSessionId: (state, action: PayloadAction<string>) => {
      state.currentSessionId = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(sendMessage.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(sendMessage.fulfilled, (state, action) => {
        state.loading = false;
        state.messages.push(action.payload);
        state.currentSessionId = action.payload.session_id;
      })
      .addCase(sendMessage.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { clearMessages, setSessionId, clearError } = chatSlice.actions;
export default chatSlice.reducer;