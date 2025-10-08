import { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '../store';
import { getCurrentUser } from '../store/authSlice';

export const useAuth = () => {
  const dispatch = useDispatch();
  const { user, token, loading, error } = useSelector((state: RootState) => state.auth);

  useEffect(() => {
    if (token && !user) {
      dispatch(getCurrentUser() as any);
    }
  }, [token, user, dispatch]);

  return {
    user,
    token,
    loading,
    error,
    isAuthenticated: !!user,
  };
};