import { useEffect, useCallback } from 'react';
import { useUserStore } from '@/store/useUserStore';
import { getCurrentUser } from '@/services/auth';

/**
 * 用户信息 Hook。
 * 从后端 /auth/me 获取真实用户信息。
 */
export const useUser = () => {
  const { setUser, clearUser, user, isAuthenticated } = useUserStore();

  const initUser = useCallback(async () => {
    try {
      const user = await getCurrentUser();
      if (user) {
        setUser(user);
        return true;
      } else {
        clearUser();
        return false;
      }
    } catch (error: unknown) {
      const err = error as { response?: { status?: number } };
      if (err.response?.status !== 401) {
        console.warn('Failed to fetch current user info:', error);
      }
      clearUser();
      return false;
    }
  }, [setUser, clearUser]);

  useEffect(() => {
    if (!user) {
      initUser();
    }
  }, [user, initUser]);

  return { user, isAuthenticated, refreshUser: initUser };
};
