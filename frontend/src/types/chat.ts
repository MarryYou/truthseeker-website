// --- 思考链 ---

export type ThoughtStepStatus = 'pending' | 'running' | 'suspended' | 'success' | 'completed' | 'error';

export interface ThoughtStep {
  key: string;
  id?: string;
  label: string;
  status: ThoughtStepStatus;
  description?: string;
  sub_steps?: Array<{
    message: string;
    type: string;
    ts: number;
    data?: unknown;
  }>;
}

// --- 验证结论 ---

export interface VerificationClaim {
  claim: string;
  verdict: 'verified' | 'likely_true' | 'disputed' | 'refuted' | 'unverifiable';
  confidence: number;
  supporting_sources: string[];
  evidence: {
    supports: string[];
    refutes: string[];
  };
  warnings: string[];
}

// --- 任务状态 ---

export type TaskStatus = 'idle' | 'running' | 'completed' | 'failed' | 'suspended';

// --- 执行模式 ---

export type ExecutionMode = 'fast_react' | 'expert_search' | 'research_pipeline';

// --- HITL 断点 (v3.0) ---

export type BreakpointType = 'dimensions' | 'sources';

export interface Breakpoint {
  type: BreakpointType;
  payload: any;
  research_id: string;
  task_id: string;
}

// --- 研究消息 ---

export interface ResearchMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  taskId?: string;
  thoughtSteps: ThoughtStep[];
  status: TaskStatus;
  reportContent?: string;
  thinkingContent?: string;  // Agent 思考过程的流式文本（独立于报告内容）
  agentContent?: string;     // Agent 模式的最终回答内容（独立于 Pipeline 报告）
  runConfigSnapshot?: Record<string, any>;
  durationSeconds?: number;
  confidence?: number;
  claims?: VerificationClaim[];
  executionMode?: ExecutionMode; // 记录该消息产生时使用的执行模式
}

// --- SSE 事件类型 (对齐后端 create_sse_handler) ---

export type SSEEventName =
  | 'sync'
  | 'progress'
  | 'metadata'
  | 'token'
  | 'agent_token'
  | 'thinking'
  | 'breakpoint'
  | 'complete'
  | 'error';

export interface SSESyncPayload {
  thought_steps: ThoughtStep[];
  task_id: string;
}

export interface SSEProgressPayload {
  thought_steps?: ThoughtStep[];
  step?: string;
  key?: string;
  status?: string;
  message?: string;
}

export interface SSEMetadataPayload {
  strategy_overrides?: Record<string, unknown>;
  execution_mode?: string;
  [key: string]: unknown;
}

export interface SSETokenPayload {
  text: string;
}

export interface SSEBreakpointPayload {
  type: BreakpointType;
  payload: unknown;
  research_id: string;
  task_id: string;
}

export interface SSECompletePayload {
  research_id: string;
  task_id: string;
  claims: VerificationClaim[];
  warnings: string[];
  error_log: Array<{ node: string; message: string; detail?: string }>;
  confidence: number;
  conflict_dimensions: string[];
  duration_seconds: number;
  report: string;
  research_conclusion: string;
  message: string;
}

export interface SSEErrorPayload {
  message: string;
}

// --- 请求体 ---

export interface BusinessControl {
  execution_mode: 'auto' | 'preset';
  speed: ExecutionMode;
  enable_hitl: boolean;
}

export interface RuntimeOverrides {
  engines?: string[];
  temperature?: number;
}

export interface ChatRequest {
  message: string;
  research_id?: string;
  preset_name?: string;
  control?: BusinessControl;
  runtime_overrides?: RuntimeOverrides;
}
