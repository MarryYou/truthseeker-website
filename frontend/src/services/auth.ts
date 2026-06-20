import api from './api';
import type { User } from '@/types';

/** 获取当前登录用户信息 */
export async function getCurrentUser(): Promise<User | null> {
  const { data } = await api.get('/auth/me');
  if (!data) return null;
  return {
    user_id: data.id,
    tenant_id: data.tenant_id,
    email: data.email,
    name: data.name,
    avatar: data.avatar,
  };
}

/** 更新用户资料 */
export async function updateProfile(payload: { name?: string; avatar?: string }): Promise<User> {
  const { data } = await api.put('/auth/me', payload);
  return {
    user_id: data.id,
    tenant_id: data.tenant_id,
    email: data.email,
    name: data.name,
    avatar: data.avatar,
  };
}
