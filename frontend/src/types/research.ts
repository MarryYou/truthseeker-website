import type { ThoughtStep } from './chat';

/** 后端 SessionItemResponse — 研究会话列表项 */
export interface ResearchSession {
  id: string;
  title: string;
  status: string;
  total_duration_seconds?: number;
  created_at: string;
}

/** 后端 TaskItemResponse — 单个研究任务 */
export interface ResearchTask {
  id: string;
  ordinal: number;
  query: string;
  status: string;
  pending_approval: boolean;
  breakpoint_type: string | null;
  summary: string | null;
  research_conclusion: string | null;
  dimensions?: any[] | null;
  sources?: any[] | null;
  claims?: any[] | null;
  thought_steps: ThoughtStep[];
  warnings?: string[];
  error_log?: Array<{ node: string; message: string; detail?: string }>;
  run_config_snapshot?: Record<string, any>;
  duration_seconds?: number;
  created_at: string;
  completed_at: string | null;
}

/** 后端 SessionListResponse */
export interface SessionListResponse {
  total: number;
  page: number;
  page_size: number;
  items: ResearchSession[];
}

/** 后端 SessionDetailResponse */
export interface SessionDetailResponse extends ResearchSession {
  preset_id: string | null;
  updated_at: string;
  tasks: ResearchTask[];
}
