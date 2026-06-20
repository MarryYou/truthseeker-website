import type { ExecutionMode, Breakpoint } from '@/types';

export interface ConfigSlice {
  executionMode: 'auto' | 'preset';
  speed: ExecutionMode;
  enableHitl: boolean;
  pendingBreakpoint: Breakpoint | null;

  setExecutionMode: (mode: 'auto' | 'preset') => void;
  setSpeed: (speed: ExecutionMode) => void;
  setEnableHitl: (enable: boolean) => void;
  setPendingBreakpoint: (breakpoint: Breakpoint | null) => void;
}

export const createConfigSlice = (set: any, _get: any, _api?: any): ConfigSlice => ({
  executionMode: 'auto',
  speed: 'research_pipeline',
  enableHitl: false,
  pendingBreakpoint: null,

  setExecutionMode: (executionMode) => set({ executionMode }),
  setSpeed: (speed) => set({ speed }),
  setEnableHitl: (enableHitl) => set({ enableHitl }),
  setPendingBreakpoint: (pendingBreakpoint) => set({ pendingBreakpoint }),
});
