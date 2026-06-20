import { useCallback, useRef } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useResearchStore } from '@/store/useResearchStore';
import { API_BASE_PATH, SSE_MAX_RETRIES } from '@/lib/constants';
import { NEXT_PUBLIC_API_URL, IS_BROWSER } from '@/lib/env';
import { sanitizeErrorMessage } from '@/lib/utils';

/**
 * Custom hook to manage real-time research streaming via Server-Sent Events (SSE).
 */
type NotifyFn = (title: string, description: string) => void;

const defaultNotify: NotifyFn = (title, description) => {
  console.error(`[SSE] ${title}: ${description}`);
};

export const useResearchStream = (onNotify?: NotifyFn) => {
  const notify = onNotify || defaultNotify;
  const {
    setActiveResearchId,
    addMessage,
    updateLastAssistantMessage,
    updateActiveTaskThoughtStep,
    updateActiveTaskThoughtSteps,
    setStreaming,
    setActiveTaskId,
    resetResearch,
    setIsNewResearch,
    setPendingBreakpoint,
    setConfidence,
    resetResult,
    finalizeActiveTask,
  } = useResearchStore();

  const abortControllerRef = useRef<AbortController | null>(null);

  const startResearch = useCallback(async (
    query: string,
    options: {
      researchId?: string;
      presetName?: string;
      customConfig?: Record<string, any>;
      resumeData?: {
        approved_dimensions?: string[];
        approved_sources?: string[];
      };
    } = {}
  ) => {
    let isFinished = false;
    let retryCount = 0;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setStreaming(true);

    // 如果是新研究，重置状态
    if (!options.researchId && !options.resumeData) {
      resetResearch();
      setIsNewResearch(true);
    } else if (!options.resumeData) {
      // 追问场景：清空上一轮的结果缓冲区
      resetResult();
    }

    // 如果提供了 resumeData，说明是在断点恢复
    const isResuming = !!options.resumeData;
    if (isResuming) {
      setPendingBreakpoint(null); // 清除当前的断点状态
    }

    if (!isResuming) {
      // 断线重连：无 query，但需要占位消息来接收 SSE 事件
      const currentSpeed = useResearchStore.getState().speed;
      if (!query && options.researchId) {
        const taskId = (Date.now() + 1).toString();
        addMessage({
          id: taskId, role: 'assistant', content: '', streaming: true,
          taskId, thoughtSteps: [], status: 'running', executionMode: currentSpeed,
        });
        setActiveTaskId(taskId);
      } else if (query) {
        addMessage({ id: Date.now().toString(), role: 'user', content: query, thoughtSteps: [], status: 'idle' });
        const taskId = (Date.now() + 1).toString();
        addMessage({
          id: taskId, role: 'assistant', content: '', streaming: true,
          taskId, thoughtSteps: [], status: 'running', executionMode: currentSpeed,
        });
        setActiveTaskId(taskId);
      }
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    };

    let basePath = `${API_BASE_PATH}/chat`;
    let bodyObj: any = {
      message: query,
      research_id: options.researchId,
      preset_name: options.presetName,
    };

    if (isResuming) {
      basePath = `${API_BASE_PATH}/chat/${options.researchId}/resume`;
      bodyObj = {
        approved_dimensions: options.resumeData?.approved_dimensions,
        approved_sources: options.resumeData?.approved_sources,
      };
    } else {
      const { executionMode, speed, enableHitl } = useResearchStore.getState();
      
      bodyObj.control = {
        execution_mode: executionMode,
        speed: speed,
        enable_hitl: enableHitl,
      };
      
      if (options.customConfig && Object.keys(options.customConfig).length > 0) {
        bodyObj.runtime_overrides = {
          engines: options.customConfig.engines,
          temperature: options.customConfig.temperature,
        };
      }
    }

    // 本地开发（next dev 端口 3000）：直接连接后端物理地址，绕过 Proxy
    // Docker / 生产环境（nginx 端口 80）：走相对路径经 nginx 反向代理
    const isLocalDev = IS_BROWSER && window.location.port === '3000';
    const sseUrl = isLocalDev ? `${NEXT_PUBLIC_API_URL}${basePath}` : basePath;

    let isBreakpoint = false;

    try {
      await fetchEventSource(sseUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(bodyObj),
        signal: controller.signal,
        openWhenHidden: true,
        credentials: 'include',
        async onopen(response) {
          if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
            retryCount = 0;
            return;
          }
          let errDetail = 'Connection failed.';
          try {
            const errData = await response.json();
            errDetail = errData.detail || errDetail;
          } catch (e) {
            console.warn('[SSE] Failed to parse error response:', e);
          }
          throw new Error(errDetail);
        },
        onmessage(ev) {
          retryCount = 0;
          const { event: eventName, data } = ev;
          if (!data) return;

          try {
            const parsed = JSON.parse(data);
            const store = useResearchStore.getState();

            switch (eventName) {
              case 'sync': {
                if (parsed.thought_steps) {
                  store.updateActiveTaskThoughtSteps(parsed.thought_steps);
                }
                if (parsed.task_id) {
                  store.setActiveTaskId(parsed.task_id);
                }
                break;
              }
              case 'progress': {
                const { step, status, message: stepMsg, key, thought_steps } = parsed;
                if (thought_steps) {
                  store.updateActiveTaskThoughtSteps(thought_steps);
                } else {
                  const targetKey = key || step;
                  updateActiveTaskThoughtStep(targetKey, status, stepMsg);
                }
                break;
              }
              case 'metadata': {
                store.updateActiveTaskMetadata(parsed);
                break;
              }
              case 'token': {
                updateLastAssistantMessage(parsed.text);
                break;
              }
              case 'agent_think': {
                // 模型原生推理过程（deepseek-reasoner 等支持），可折叠展示
                break; // 暂不展示，未来可加 ThinkingPanel
              }
              case 'breakpoint': {
                // v3.0 HITL 断点处理
                isFinished = true;
                isBreakpoint = true;
                store.setPendingBreakpoint(parsed);
                store.finalizeActiveTask({ status: 'suspended' });
                break;
              }
              case 'complete': {
                isFinished = true;
                setActiveResearchId(parsed.research_id);
                if (parsed.claims) store.setClaims(parsed.claims);
                if (parsed.warnings) store.setWarnings(parsed.warnings);
                if (parsed.error_log && Array.isArray(parsed.error_log)) {
                  const cleanedLogs = parsed.error_log.map((err: any) => ({
                    ...err,
                    message: sanitizeErrorMessage(err.message)
                  }));
                  store.setErrorLog(cleanedLogs);
                }
                if (parsed.duration_seconds) store.setDurationSeconds(parsed.duration_seconds);
                if (typeof parsed.confidence === 'number') store.setConfidence(parsed.confidence);

                finalizeActiveTask({
                  finalReport: parsed.report,
                  claims: parsed.claims,
                  confidence: parsed.confidence
                });
                break;
              }
              case 'error': {
                isFinished = true;
                const userFriendlyMsg = sanitizeErrorMessage(parsed.message || 'Unknown pipeline error.');
                notify('Execution Error', userFriendlyMsg);
                finalizeActiveTask({ errorMessage: `Error: ${userFriendlyMsg}` });
                break;
              }
            }
          } catch (e) {
            console.error('[SSE] Parse error:', e, data);
          }
        },
        onerror(err) {
          if (controller.signal.aborted) throw err;
          if (retryCount >= SSE_MAX_RETRIES) {
            finalizeActiveTask({ errorMessage: `Connection interrupted: ${err.message}` });
            throw err;
          }
          retryCount++;
        },
        onclose() {
          // 🚀 关键修复：如果是断点中断，则不触发默认的 finalizeActiveTask (防止覆盖 suspended 状态)
          if (!isBreakpoint && (isFinished || controller.signal.aborted || retryCount >= SSE_MAX_RETRIES)) {
            finalizeActiveTask({});
          }
        }
      });
    } catch (err: any) {
      if (err.name !== 'AbortError' && !controller.signal.aborted) {
        const msg = err.message || 'Unknown error';
        const userFriendlyMsg = sanitizeErrorMessage(msg);
        // 区分真正的连接错误和业务拒绝（如 400 验证失败）
        const isConnectionError = msg.includes('Backend unreachable') || msg.includes('Failed to fetch');
        notify(isConnectionError ? 'Connection Failed' : 'Request Failed', userFriendlyMsg);
        finalizeActiveTask({ errorMessage: userFriendlyMsg });
      }
    }
  }, [
    setActiveResearchId, addMessage, updateLastAssistantMessage,
    updateActiveTaskThoughtStep, updateActiveTaskThoughtSteps, setActiveTaskId,
    setStreaming, resetResearch, setIsNewResearch, setPendingBreakpoint,
    setConfidence, resetResult, finalizeActiveTask, notify
  ]);

  const stopResearch = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      finalizeActiveTask({});
    }
  }, [finalizeActiveTask]);

  return { startResearch, stopResearch };
};
