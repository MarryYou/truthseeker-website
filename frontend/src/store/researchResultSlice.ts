import type { VerificationClaim } from '@/types';

export interface ResultSlice {
  reportContent: string;
  claims: VerificationClaim[];
  warnings: string[];
  runConfigSnapshot: Record<string, any> | null;
  durationSeconds: number | null;
  confidence: number | null;
  errorLog: Array<{ node: string; message: string; detail?: string }>;

  setReportContent: (content: string) => void;
  setClaims: (claims: VerificationClaim[]) => void;
  setWarnings: (warnings: string[]) => void;
  setRunConfigSnapshot: (snapshot: Record<string, any> | null) => void;
  setDurationSeconds: (seconds: number | null) => void;
  setConfidence: (confidence: number | null) => void;
  setErrorLog: (errorLog: Array<{ node: string; message: string; detail?: string }>) => void;
  resetResult: () => void;
}

export const createResultSlice = (set: any, _get: any, _api?: any): ResultSlice => ({
  reportContent: '',
  claims: [],
  warnings: [],
  runConfigSnapshot: null,
  durationSeconds: null,
  confidence: null,
  errorLog: [],

  setReportContent: (content) => set({ reportContent: content }),
  setClaims: (claims) => set({ claims }),
  setWarnings: (warnings) => set({ warnings }),
  setRunConfigSnapshot: (runConfigSnapshot) => set({ runConfigSnapshot }),
  setDurationSeconds: (durationSeconds) => set({ durationSeconds }),
  setConfidence: (confidence) => set({ confidence }),
  setErrorLog: (errorLog) => set({ errorLog }),

  resetResult: () => set({
    reportContent: '',
    claims: [],
    warnings: [],
    runConfigSnapshot: null,
    durationSeconds: null,
    confidence: null,
    errorLog: [],
  }),
});
