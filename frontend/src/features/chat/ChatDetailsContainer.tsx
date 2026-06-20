'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Sender } from '@ant-design/x';
import { LoadingOutlined, SendOutlined } from '@ant-design/icons';
import { useResearchStore } from '@/store/useResearchStore';
import type { ResearchMessage, TaskStatus } from '@/types';
import { useResearchStream } from '@/hooks/useResearchStream';
import { getSession } from '@/services/research';
import { Button, Segmented, ConfigProvider, App } from 'antd';
import {
  SearchOutlined,
  FileTextOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';

import { SessionHeader } from './SessionHeader';
import { MessageList } from './MessageList';
import { ReportDrawer } from './ReportDrawer';
import { useSettingsStore } from '@/store/useSettingsStore';

interface ChatDetailsContainerProps {
  researchId: string;
}

export default function ChatDetailsContainer({ researchId }: ChatDetailsContainerProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get('q');
  const initialSpeed = searchParams.get('speed');

  const { schema, fetchSchema } = useSettingsStore();

  React.useEffect(() => {
    fetchSchema();
  }, [fetchSchema]);

  const MODE_OPTIONS = [
    { label: '智能', value: 'auto' },
    { label: '手动', value: 'preset' }
  ];

  const SPEED_OPTIONS = React.useMemo(() => {
    if (!schema?.speed_profiles) return [
      { label: '极速', value: 'fast_react' },
      { label: '专家', value: 'expert_search' },
      { label: '研究', value: 'research_pipeline' },
    ];

    const LABEL_MAP: Record<string, string> = {
      fast_react: '极速',
      expert_search: '专家',
      research_pipeline: '研究',
    };

    return Object.entries(schema.speed_profiles).map(([val, meta]) => ({
      label: LABEL_MAP[val] || meta.label || val,
      value: val,
    }));
  }, [schema]);

  const {
    messages,
    reportContent,
    claims,
    isStreaming,
    isDrawerOpen,
    executionMode,
    speed,
    enableHitl,
    setMessages,
    setReportContent,
    setClaims,
    setDrawerOpen,
    setActiveResearchId,
    setWarnings,
    setErrorLog,
    setActiveTaskId,
    setExecutionMode,
    setSpeed,
    setEnableHitl,
    setPendingBreakpoint,
  } = useResearchStore();

  const { notification } = App.useApp();
  const { startResearch } = useResearchStream(
    (title, description) => notification.error({ title, description } as any)
  );

  const isInitialized = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState('report');
  const [inputVal, setInputVal] = useState('');

  useEffect(() => {
    const initializeSession = async () => {
      if (isInitialized.current) return;
      isInitialized.current = true;

      useResearchStore.getState().resetResearch();
      setActiveResearchId(researchId);

      if (initialQuery && researchId) {
        // 先查一下这个 session 是否已有完成的任务，避免重复发起研究
        let existingTasks = 0;
        try {
          const existing = await getSession(researchId);
          existingTasks = existing.tasks?.filter(t => t.status === 'completed').length || 0;
        } catch {
          // session 不存在，走新建流程
        }

        if (existingTasks > 0) {
          // 已有完成的任务 → 加载历史，跳过重复研究
          await loadSessionHistory(researchId);
          return;
        }

        // 没有历史任务 → 发起新的研究
        const storeSpeed = useResearchStore.getState().speed;
        if (storeSpeed) {
          setExecutionMode('preset');
          setSpeed(storeSpeed);
        } else {
          setExecutionMode('auto');
          setSpeed('research_pipeline');
        }

        startResearch(initialQuery, {
          researchId
        });
        router.replace(`/research/${researchId}`, { scroll: false });
      } else if (researchId) {
        await loadSessionHistory(researchId);
      }
    };

    const loadSessionHistory = async (id: string) => {
      try {
        const session = await getSession(id);
        const historyMessages: ResearchMessage[] = [];

        if (session.tasks && session.tasks.length > 0) {
          session.tasks.forEach((task: any) => {
            const taskSpeed = task.run_config_snapshot?.execution_mode || task.run_config_snapshot?.business?.speed || '';
            const isAgentMode = taskSpeed === 'fast_react' || taskSpeed === 'expert_search';

            historyMessages.push({
              id: `u-${task.id}`,
              role: 'user',
              content: task.query,
              thoughtSteps: [],
              status: 'idle' as const,
            });

            // 跳过 running 的任务（由 startResearch 重连处理）
            if (task.status === 'running') return;

            let chatContent = task.summary || '';

            historyMessages.push({
              id: `a-${task.id}`,
              role: 'assistant',
              content: chatContent,
              agentContent: isAgentMode ? chatContent : undefined,
              reportContent: task.summary || '',
              streaming: task.status === 'running',
              taskId: task.id,
              thoughtSteps: (task.thought_steps || []).map((s: any) => ({
                ...s,
                key: s.key || s.id || crypto.randomUUID()
              })),
              status: (task.status || 'completed') as TaskStatus,
              runConfigSnapshot: task.run_config_snapshot || undefined,
              durationSeconds: task.duration_seconds || undefined,
              confidence: task.overall_confidence ?? undefined,
              claims: task.claims || undefined,
              executionMode: task.run_config_snapshot?.execution_mode || task.run_config_snapshot?.business?.speed || 'research_pipeline',
            });
          });
        }

        setMessages(historyMessages);

        if (session.tasks && session.tasks.length > 0) {
          const lastTask = session.tasks[session.tasks.length - 1];
          setReportContent(lastTask.summary || '');
          setClaims(lastTask.claims || []);
          setWarnings(lastTask.warnings || []);
          setErrorLog(lastTask.error_log || []);
          setActiveTaskId(lastTask.id || null);

          const resolvedMode = lastTask.run_config_snapshot?.business?.speed ||
            lastTask.run_config_snapshot?.execution_mode ||
            'research_pipeline';
          setSpeed(resolvedMode as any);
          setExecutionMode(
            resolvedMode === 'fast_react' || resolvedMode === 'expert_search'
              ? 'preset'
              : lastTask.run_config_snapshot?.control?.execution_mode || 'auto'
          );

          if (lastTask.status === 'suspended' && lastTask.pending_approval) {
            setPendingBreakpoint({
              type: lastTask.breakpoint_type as any,
              payload: lastTask.breakpoint_type === 'dimensions' ? lastTask.dimensions : lastTask.sources,
              research_id: researchId,
              task_id: lastTask.id
            });
          }

          if (lastTask.status === 'running') {
            await startResearch('', { researchId });
          }
        }
      } catch (error: any) {
        console.error('Failed to load session history:', error);
        // 404 → session 不存在，回退到首页
        if (error?.response?.status === 404) {
          router.push('/');
        }
      }
    };

    initializeSession();
  }, [researchId, startResearch, setMessages, setReportContent, setClaims, setActiveResearchId, initialQuery, initialSpeed, router, setWarnings, setErrorLog, setActiveTaskId, setExecutionMode, setSpeed]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (val: string) => {
    if (!val.trim() || isStreaming) return;
    startResearch(val, { researchId });
    setInputVal('');
  };

  const sessionTitle = messages.find(m => m.role === 'user')?.content || '';

  return (
    <div className="flex h-full w-full overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0 transition-all duration-300 ease-in-out">
        <SessionHeader
          researchId={researchId}
          title={sessionTitle}
        />

        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onOpenArchive={() => { }}
          messagesEndRef={messagesEndRef}
        />

        {/* Input Area (Sticky Footer) */}
        <div className="shrink-0 p-4 sm:p-6 z-10 w-full">
          <div className="max-w-[1000px] mx-auto space-y-4">
            {/* Mode Selector and HITL Toggle */}
            <div className="flex justify-center items-center gap-6 bg-[#14161f]/80 backdrop-blur-xl border border-white/10 rounded-full px-6 py-2.5 shadow-2xl mx-auto w-fit">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 select-none font-medium">模式</span>
                <Segmented
                  options={MODE_OPTIONS}
                  value={executionMode}
                  onChange={(val) => setExecutionMode(val as any)}
                  disabled={isStreaming}
                  className="p-0.5 rounded-lg border border-white/5 bg-black/20"
                  size="small"
                />
              </div>

              <div className="w-[1px] h-4 bg-white/10" />

              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 select-none font-medium">层级</span>
                <Segmented
                  options={SPEED_OPTIONS}
                  value={speed}
                  onChange={(val) => setSpeed(val as any)}
                  disabled={isStreaming}
                  className="p-0.5 rounded-lg border border-white/5 bg-black/20"
                  size="small"
                />
              </div>
            </div>

            <div className="relative group">
              <div className="absolute -inset-1 bg-gradient-to-r from-blue-500/10 to-indigo-500/10 rounded-2xl blur opacity-0 group-focus-within:opacity-100 transition duration-500" />
              <div className="relative bg-[#14161f]/90 backdrop-blur-xl border border-white/10 rounded-2xl p-2 shadow-2xl shadow-black/60">
                <Sender
                  value={inputVal}
                  onChange={setInputVal}
                  onSubmit={handleSend}
                  placeholder={isStreaming ? "Research in progress..." : "Ask a follow-up question..."}
                  className="bg-transparent border-none text-white text-base"
                  submitType="enter"
                  prefix={isStreaming ? <LoadingOutlined className="text-blue-500 mr-2" /> : null}
                  disabled={isStreaming}
                  suffix={
                    <Button
                      type="primary"
                      shape="circle"
                      icon={<SendOutlined style={{ fontSize: 13 }} />}
                      onClick={() => handleSend(inputVal)}
                      disabled={!inputVal.trim() || isStreaming}
                      className={`w-8 h-8 flex items-center justify-center border-none transition-all duration-300 ${inputVal.trim() && !isStreaming
                          ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-900/30 scale-105'
                          : 'bg-white/5 text-slate-600 scale-95'
                        }`}
                    />
                  }
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <ReportDrawer
        isOpen={isDrawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        reportContent={reportContent}
        isStreaming={isStreaming}
        claims={claims}
      />
    </div>
  );
}
