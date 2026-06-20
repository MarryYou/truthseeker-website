import api from './api';
import type {
  SessionListResponse,
  SessionDetailResponse,
} from '@/types';

/** 获取研究会话列表 */
export async function listSessions(params?: {
  page?: number;
  page_size?: number;
  keyword?: string;
  status?: string;
}): Promise<SessionListResponse> {
  const { data } = await api.get<SessionListResponse>('/researches', { params });
  return data;
}

/** 获取研究会话详情（含任务列表） */
export async function getSession(id: string): Promise<SessionDetailResponse> {
  const { data } = await api.get<SessionDetailResponse>(`/researches/${id}`);
  return data;
}

/** 删除研究会话 */
export async function deleteSession(id: string): Promise<void> {
  await api.delete(`/researches/${id}`);
}
