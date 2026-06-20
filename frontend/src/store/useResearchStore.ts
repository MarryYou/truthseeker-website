import { create } from 'zustand';
import type { ResearchMessage, ThoughtStep, VerificationClaim, ExecutionMode, Breakpoint } from '@/types';
import { mergeThoughtSteps, findLastAssistantIdx } from '@/utils/thoughtSteps';
import { createSessionSlice, type SessionSlice } from './researchSessionSlice';
import { createResultSlice, type ResultSlice } from './researchResultSlice';
import { createConfigSlice, type ConfigSlice } from './researchConfigSlice';

// ── 组合 Store 类型 ──────────────────────────────────────────

interface ResearchActions {
  /** 追加 token 流式内容到最后一条 assistant 消息 */
  updateLastAssistantMessage: (delta: string) => void;
  /** 追加思考过程 */
  appendThinkingContent: (delta: string) => void;
  /** 追加 Agent 内容 */
  appendAgentContent: (delta: string) => void;
  /** 更新最后一条 assistant 的 thought steps */
  updateActiveTaskThoughtSteps: (steps: ThoughtStep[]) => void;
  /** 更新单个 step 状态 */
  updateActiveTaskThoughtStep: (key: string, status: ThoughtStep['status'], description?: string) => void;
  /** 更新任务元数据 */
  updateActiveTaskMetadata: (metadata: Record<string, any>) => void;
  /** 结束任务 */
  finalizeActiveTask: (params: {
    errorMessage?: string;
    status?: ResearchMessage['status'];
    finalReport?: string;
    claims?: VerificationClaim[];
    confidence?: number;
  }) => void;
  /** 快速获取已完成的结论摘要（research_conclusion 格式化） */
  extractCoreAnswer: (researchConclusion: string) => string;
}

export type ResearchStore = SessionSlice & ResultSlice & ConfigSlice & ResearchActions;

// ── 组合 Store 实现 ──────────────────────────────────────────

export const useResearchStore = create<ResearchStore>()((set, get) => ({
  // Slices
  ...createSessionSlice(set, get),
  ...createResultSlice(set, get),
  ...createConfigSlice(set, get),

  // Actions
  updateLastAssistantMessage: (delta: string) => set((state) => {
    const msgs = [...state.messages];
    const idx = findLastAssistantIdx(msgs);
    if (idx === -1) return state;
    const m = msgs[idx];
    msgs[idx] = { ...m, content: m.content + delta, reportContent: (m.reportContent || '') + delta };
    return { messages: msgs, reportContent: state.reportContent + delta };
  }),

  appendThinkingContent: (delta: string) => set((state) => {
    const msgs = [...state.messages];
    const idx = findLastAssistantIdx(msgs);
    if (idx === -1) return state;
    const m = msgs[idx];
    msgs[idx] = { ...m, thinkingContent: (m.thinkingContent || '') + delta };
    return { messages: msgs };
  }),

  appendAgentContent: (delta: string) => set((state) => {
    const msgs = [...state.messages];
    const idx = findLastAssistantIdx(msgs);
    if (idx === -1) return state;
    const m = msgs[idx];
    msgs[idx] = { ...m, agentContent: (m.agentContent || '') + delta };
    return { messages: msgs };
  }),

  updateActiveTaskThoughtSteps: (steps: ThoughtStep[]) => set((state) => {
    const msgs = [...state.messages];
    const idx = findLastAssistantIdx(msgs);
    if (idx === -1) return state;
    const m = msgs[idx];
    msgs[idx] = { ...m, thoughtSteps: mergeThoughtSteps(m.thoughtSteps, steps) };
    return { messages: msgs };
  }),

  updateActiveTaskThoughtStep: (key: string, status: ThoughtStep['status'], description?: string) => set((state) => {
    const msgs = [...state.messages];
    const idx = findLastAssistantIdx(msgs);
    if (idx === -1) return state;
    const m = msgs[idx];
    msgs[idx] = {
      ...m,
      thoughtSteps: m.thoughtSteps.map(s =>
        s.key === key ? { ...s, status, description: description || s.description } : s
      ),
    };
    return { messages: msgs };
  }),

  updateActiveTaskMetadata: (metadata: Record<string, any>) => set((state) => {
    const msgs = [...state.messages];
    const idx = findLastAssistantIdx(msgs);
    const newSnapshot = { ...(state.runConfigSnapshot || {}), ...metadata };
    if (idx > -1) {
      msgs[idx] = { ...msgs[idx], executionMode: metadata.execution_mode || msgs[idx].executionMode };
    }
    return { messages: msgs, runConfigSnapshot: newSnapshot };
  }),

  finalizeActiveTask: ({ errorMessage, status, finalReport, claims, confidence }) => set((state) => {
    const msgs = [...state.messages];
    const idx = findLastAssistantIdx(msgs);
    if (idx === -1) return { isStreaming: false };
    const m = msgs[idx];

    let content: string;
    if (errorMessage) {
      content = m.content || errorMessage;
    } else if (finalReport) {
      // 完整 report 优先（来自 complete 事件的 parsed.report）
      content = finalReport;
    } else {
      content = state.reportContent || m.content || '';
    }

    msgs[idx] = {
      ...m, streaming: false, content,
      status: status || (errorMessage ? 'failed' as const : 'completed' as const),
      reportContent: finalReport || m.reportContent,
      durationSeconds: state.durationSeconds || undefined,
      claims: claims || state.claims || undefined,
      confidence: confidence ?? (state.confidence || undefined),
    };
    return { messages: msgs, isStreaming: false, isNewResearch: false, activeTaskId: null };
  }),

  extractCoreAnswer: (researchConclusion: string) => {
    try {
      const obj = JSON.parse(researchConclusion);
      return obj.core_answer || '';
    } catch { return ''; }
  },
}));
