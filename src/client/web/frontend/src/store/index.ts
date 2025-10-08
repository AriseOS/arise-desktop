import { configureStore } from '@reduxjs/toolkit';
import authReducer from './authSlice';
import chatReducer from './chatSlice';
import baseappReducer from './baseappSlice';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    chat: chatReducer,
    baseapp: baseappReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;