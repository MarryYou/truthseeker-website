/**
 * 全局业务与技术常量 (单一事实来源)
 */

// ── API 路径 ──────────────────────────────────────────────────
export const API_BASE_PATH = '/api/v1';
export const LOGIN_PATH = '/login';
export const AUTH_LOGIN_PATH = `${API_BASE_PATH}/auth/login`;

// ── SSE & Streaming ──────────────────────────────────────────
export const SSE_MAX_RETRIES = 3;
export const DEFAULT_QUERY_STALE_TIME = 60 * 1000;

// ── UI 布局与深度 ──────────────────────────────────────────────
export const MAX_HISTORY_DISPLAY_TURNS = 10;
export const ARCHIVE_CONTENT_TRUNCATE_LENGTH = 160;

// ── 执行模式定义 (与后端对齐) ─────────────────────────────────────
export const EXECUTION_MODES = {
  AUTO: 'auto',
  FAST: 'fast_react',
  EXPERT: 'expert_search',
  PIPELINE: 'research_pipeline',
} as const;
