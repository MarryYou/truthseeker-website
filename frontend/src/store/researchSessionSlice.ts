import type { ResearchMessage } from '@/types';

export interface SessionSlice {
  activeResearchId: string | null;
  messages: ResearchMessage[];
  isStreaming: boolean;
  activeTaskId: string | null;
  recentRefreshTrigger: number;
  isNewResearch: boolean;
  isDrawerOpen: boolean;

  setActiveResearchId: (id: string | null) => void;
  setMessages: (messages: ResearchMessage[]) => void;
  addMessage: (message: ResearchMessage) => void;
  setDrawerOpen: (open: boolean) => void;
  setStreaming: (streaming: boolean) => void;
  setActiveTaskId: (taskId: string | null) => void;
  resetResearch: () => void;
  triggerRecentRefresh: () => void;
  setIsNewResearch: (isNew: boolean) => void;
}

export const createSessionSlice = (set: any, _get: any, _api?: any): SessionSlice => ({
  activeResearchId: null,
  messages: [],
  isStreaming: false,
  activeTaskId: null,
  recentRefreshTrigger: 0,
  isNewResearch: false,
  isDrawerOpen: false,

  setActiveResearchId: (id) => set({ activeResearchId: id }),
  setMessages: (messages) => set({ messages }),
  addMessage: (message) => set((state: any) => ({ messages: [...(state.messages || []), message] })),
  setDrawerOpen: (open) => set({ isDrawerOpen: open }),
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  triggerRecentRefresh: () => set((state: any) => ({ recentRefreshTrigger: (state.recentRefreshTrigger || 0) + 1 })),
  setIsNewResearch: (isNewResearch) => set({ isNewResearch }),

  setActiveTaskId: (taskId) => set((state: any) => {
    const newMessages = [...state.messages];
    for (let i = newMessages.length - 1; i >= 0; i--) {
      if (newMessages[i].role === 'assistant') {
        newMessages[i] = { ...newMessages[i], id: taskId || newMessages[i].id, taskId: taskId || newMessages[i].taskId };
        break;
      }
    }
    return { activeTaskId: taskId, messages: newMessages };
  }),

  resetResearch: () => set({
    activeResearchId: null, messages: [], activeTaskId: null,
    isStreaming: false, isDrawerOpen: false, isNewResearch: false,
  }),
});
