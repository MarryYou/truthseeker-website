import React from 'react';
import { ThunderboltOutlined, LoadingOutlined, BulbOutlined, UpOutlined, DownOutlined } from '@ant-design/icons';
import type { ResearchMessage, VerificationClaim } from '@/types';
import { renderMarkdown } from '@/lib/markdown';
import ThoughtChainPanel from './ThoughtChainPanel';
import VerificationCard from './VerificationCard';

interface MessageListProps {
  messages: ResearchMessage[];
  isStreaming: boolean;
  onOpenArchive: (msg: ResearchMessage) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isStreaming,
  onOpenArchive,
  messagesEndRef,
}) => {
  return (
    <main className="flex-1 overflow-y-auto overflow-x-hidden pt-8 pb-32">
      <div className="max-w-[1000px] mx-auto px-4 sm:px-10">
        {messages.map((msg) => (
          <div key={msg.id} className="mb-12 animate-fade-in group">
            {msg.role === 'user' ? (
              <div className="flex justify-end mb-4">
                <div className="max-w-[70%] bg-[#14161f] border border-white/10 rounded-2xl px-5 py-3 text-slate-200 shadow-xl shadow-black/20">
                  {msg.content}
                </div>
              </div>
            ) : (
              <AssistantMessage msg={msg} isStreaming={isStreaming} onOpenArchive={onOpenArchive} />
            )}
          </div>
        ))}
        <div ref={messagesEndRef} className="h-4" />
      </div>
    </main>
  );
};

/** 助手消息头：包含图标、名称、模式标签和状态指标 */
function MessageHeader({ msg, isStreaming }: { msg: ResearchMessage; isStreaming: boolean }) {
  const execLabel = msg.executionMode === 'fast_react' ? '极速快问' :
    msg.executionMode === 'expert_search' ? '专家搜索' : '深度研报';

  return (
    <div className="flex items-center gap-3 mb-1">
      <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shadow-md">
        <ThunderboltOutlined className="text-white text-sm" />
      </div>
      <span className="font-black text-white tracking-tight">TruthSeeker Intelligence</span>
      <span className="text-[10px] text-slate-500 font-mono ml-1 px-2 py-0.5 rounded-md bg-white/5 border border-white/5">
        {execLabel}
      </span>
      {msg.streaming && <LoadingOutlined className="text-blue-500 text-xs animate-spin" />}
      {msg.durationSeconds && !msg.streaming && (
        <span className="text-[10px] text-slate-500 font-mono tabular-nums">
          耗时 {msg.durationSeconds}s
        </span>
      )}
      {msg.confidence !== undefined && (
        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-md border ${
          msg.confidence >= 0.8 ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' :
          msg.confidence >= 0.5 ? 'text-blue-400 bg-blue-500/10 border-blue-500/20' :
          'text-amber-400 bg-amber-500/10 border-amber-500/20'
        }`}>
          置信度 {(msg.confidence * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
}

/** 助手消息正文：渲染 Markdown 内容，带最小高度优化 */
function MessageContent({ msg, hasContent }: { msg: ResearchMessage; hasContent: boolean }) {
  if (msg.status === 'failed') {
    return (
      <div className="p-4 bg-rose-950/10 border border-rose-900/30 rounded-2xl flex flex-col gap-2.5 max-w-[90%] shadow-lg shadow-black/10">
        <div className="text-xs text-slate-400 font-mono bg-black/40 p-3 rounded-xl border border-white/5 whitespace-pre-wrap select-text leading-relaxed">
          {msg.content || '发生未知管道错误，未获取到具体的异常日志。'}
        </div>
      </div>
    );
  }

  if (hasContent) {
    return (
      <div className="space-y-4 min-h-[40px]">
        {/* Agent 流式内容（agent_token） */}
        {msg.agentContent && (
          <div className="markdown-content text-sm text-slate-300/90"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.agentContent) }} />
        )}
        {/* Pipeline 报告内容（token / summary） */}
        {msg.content && msg.content !== msg.agentContent && (
          <div className="markdown-content text-sm text-slate-300/90"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
        )}
      </div>
    );
  }

  if (msg.streaming) {
    return (
      <span className="text-slate-500 italic flex items-center gap-2 text-sm">
        <span className="animate-pulse">⏳</span> 正在组织研究结论…
      </span>
    );
  }

  return null;
}

/** 事实核查区域：渲染 VerificationCard 列表 */
function ClaimsSection({ claims, confidence }: { claims: VerificationClaim[]; confidence?: number }) {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <div className="mt-4 animate-fade-in border border-white/5 bg-[#14161f]/40 backdrop-blur-sm rounded-2xl overflow-hidden shadow-xl shadow-black/20">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-1.5 h-1.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)] animate-pulse" />
          <span className="text-xs font-black text-slate-350 uppercase tracking-widest">
            Research Verification Claims
          </span>
          <span className="text-[10px] text-slate-500 font-mono">({claims.length} items)</span>
        </div>

        <div className="flex items-center gap-3">
          {confidence !== undefined && (
            <span className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-md border ${
              confidence >= 0.8 ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' :
              confidence >= 0.5 ? 'text-blue-400 bg-blue-500/10 border-blue-500/20' :
              'text-amber-400 bg-amber-500/10 border-amber-500/20'
            }`}>
              综合置信度: {(confidence * 100).toFixed(0)}%
            </span>
          )}
          <span className="text-slate-500 hover:text-slate-300 transition-colors">
            {isOpen ? <UpOutlined className="text-[10px]" /> : <DownOutlined className="text-[10px]" />}
          </span>
        </div>
      </button>

      {isOpen && (
        <div className="p-5 bg-black/10 border-t border-white/5 space-y-4">
          <div className="grid grid-cols-1 gap-1">
            {claims.map((claim, idx) => (
              <VerificationCard key={idx} claim={claim} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 统一助手消息渲染 */
function AssistantMessage({ msg, isStreaming, onOpenArchive }: {
  msg: ResearchMessage;
  isStreaming: boolean;
  onOpenArchive: (msg: ResearchMessage) => void;
}) {
  const hasContent = !!(msg.agentContent || msg.content);

  return (
    <div className="flex flex-col gap-4">
      <MessageHeader msg={msg} isStreaming={isStreaming} />

      {/* 思考链：历史消息默认折叠（通过 key 强制重置状态，或传入 isOpen 初始值） */}
      {(msg.streaming || (msg.thoughtSteps && msg.thoughtSteps.length > 0)) && (
        <div className="mb-4">
          <ThoughtChainPanel
            key={`${msg.id}-${msg.streaming}`}
            steps={msg.thoughtSteps || []}
            loading={!!msg.streaming}
          />
        </div>
      )}

      {/* 推理过程 */}
      {msg.thinkingContent && <ThinkingPanel content={msg.thinkingContent} isStreaming={!!msg.streaming} />}

      <div className="text-slate-200 leading-relaxed mb-6">
        <MessageContent msg={msg} hasContent={hasContent} />
      </div>

      {msg.claims && msg.claims.length > 0 && (
        <ClaimsSection claims={msg.claims} confidence={msg.confidence} />
      )}
    </div>
  );
}

/** 可折叠的 AI 推理过程面板（用于 reasoning_content 展示） */
function ThinkingPanel({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  const [isOpen, setIsOpen] = React.useState(true);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (scrollRef.current && isStreaming) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [content, isStreaming]);

  if (!content) return null;

  return (
    <div className="mb-4">
      <div className="border border-amber-500/15 rounded-xl overflow-hidden bg-amber-950/5">
        <button
          className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-amber-500/5 transition-colors"
          onClick={() => setIsOpen(!isOpen)}
        >
          <div className="flex items-center gap-2">
            <BulbOutlined className="text-amber-400 text-xs" />
            <span className="text-xs font-bold text-amber-300/80 uppercase tracking-wider">AI Thinking</span>
            {isStreaming && <span className="text-[10px] text-amber-400/60 animate-pulse ml-1">streaming...</span>}
          </div>
          <div className="text-slate-500 hover:text-slate-300 transition-colors">
            {isOpen ? <UpOutlined className="text-[10px]" /> : <DownOutlined className="text-[10px]" />}
          </div>
        </button>
        {isOpen && (
          <div
            ref={scrollRef}
            className="px-4 pb-3 text-xs text-slate-400/90 leading-relaxed border-t border-amber-500/10 bg-black/20 max-h-80 overflow-y-auto markdown-content"
          >
            <div dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
          </div>
        )}
      </div>
    </div>
  );
}
