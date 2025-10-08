import { configureStore } from '@reduxjs/toolkit';
import authReducer from './store/authSlice';

export const simpleStore = configureStore({
  reducer: {
    auth: authReducer,
  },
});

export type SimpleRootState = ReturnType<typeof simpleStore.getState>;
export type SimpleAppDispatch = typeof simpleStore.dispatch;