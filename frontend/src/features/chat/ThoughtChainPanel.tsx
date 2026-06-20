'use client';

import React, { useState } from 'react';
import { ThoughtChain } from '@ant-design/x';
import { LoadingOutlined, CheckCircleFilled, CloseCircleFilled, ThunderboltOutlined, UpOutlined, DownOutlined } from '@ant-design/icons';
import { Badge } from 'antd';
import { PauseCircleFilled } from '@ant-design/icons';
import { sanitizeErrorMessage } from '@/lib/utils';

import type { ThoughtStep } from '@/types';

interface ThoughtChainPanelProps {
  steps: ThoughtStep[];
  loading: boolean;
}

export default function ThoughtChainPanel({ steps, loading }: ThoughtChainPanelProps) {
  // 控制折叠状态的 state，默认根据 loading 状态决定：如果还在加载，默认展开；否则默认收缩。
  const [isOpen, setIsOpen] = useState<boolean>(loading);

  if (steps.length === 0) {
    return (
      <div className="p-8 text-center text-slate-500 text-sm border border-dashed border-white/5 rounded-2xl bg-white/2">
        {loading ? (
          <span className="flex items-center justify-center gap-3">
            <LoadingOutlined className="text-blue-500 animate-spin" />
            <span className="font-medium tracking-tight">AI 正在初始化深度研究...</span>
          </span>
        ) : (
          '等待发起探究...'
        )}
      </div>
    );
  }

  const items = steps.map((step, stepIdx) => {
    let icon = <CheckCircleFilled className="text-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]" />;
    let itemStatus: 'loading' | 'error' | 'success' = 'success';

    if (step.status === 'pending' || step.status === 'running') {
      icon = <LoadingOutlined className="text-blue-500 animate-spin" />;
      itemStatus = 'loading';
    } else if (step.status === 'suspended') {
      icon = <PauseCircleFilled className="text-blue-400 animate-pulse" />;
      itemStatus = 'loading'; // 进度条保持在当前位置
    } else if (step.status === 'error') {
      icon = <CloseCircleFilled className="text-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.3)]" />;
      itemStatus = 'error';
    }

    let descNode: React.ReactNode = null;
    if (step.sub_steps && step.sub_steps.length > 0) {
      descNode = (
        <div className="flex flex-col gap-1.5 mt-2 text-xs">
          {step.sub_steps.map((sub, idx) => {
            let textColor = 'text-slate-300';
            let dotColor = 'text-slate-500';
            let iconPrefix = '•';

            if (sub.type === 'error') {
              textColor = 'text-rose-400 font-semibold';
              dotColor = 'text-rose-500';
              iconPrefix = '🔴';
            } else if (sub.type === 'warning') {
              textColor = 'text-amber-400 font-medium';
              dotColor = 'text-amber-500';
              iconPrefix = '⚠️';
            } else if (sub.type === 'success') {
              textColor = 'text-emerald-400 font-medium';
              dotColor = 'text-emerald-500';
              iconPrefix = '✓';
            } else if (sub.type === 'tool_call') {
              textColor = 'text-blue-300';
              dotColor = 'text-blue-500';
              iconPrefix = '⚙️';
            }

            const timeStr = sub.ts ? new Date(sub.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
            const prevSub = idx > 0 ? step.sub_steps?.[idx - 1] : null;
            const elapsed = (sub.ts && prevSub?.ts) ? (sub.ts - prevSub.ts).toFixed(1) : null;

            return (
              <div key={idx} className="flex items-start gap-2 leading-relaxed transition-all duration-300 group/sub">
                <span className={`${dotColor} select-none shrink-0 text-[10px] font-bold mt-0.5`}>{iconPrefix}</span>
                <span className={`flex-1 ${textColor}`}>{sanitizeErrorMessage(sub.message)}</span>
                <span className="flex items-center gap-1.5 shrink-0">
                  {elapsed && (
                    <span className="text-[9px] text-slate-600/50 font-mono tabular-nums">
                      +{elapsed}s
                    </span>
                  )}
                  {timeStr && (
                    <span className="text-[9px] text-slate-600 font-mono tabular-nums">
                      {timeStr}
                    </span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      );
    } else {
      descNode = step.description;
    }

    const firstTs = step.sub_steps?.[0]?.ts;
    const stepTimeStr = firstTs ? new Date(firstTs * 1000).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' }) : '';

    return {
      key: step.key || step.id || `step-${stepIdx}`,
      title: (
        <div className="flex items-center justify-between w-full pr-4">
          <span>{step.label}</span>
          {stepTimeStr && <span className="text-[10px] text-slate-500 font-mono font-normal">{stepTimeStr}</span>}
        </div>
      ),
      status: itemStatus,
      description: descNode,
      icon,
    };
  });

  return (
    <div className="bg-[#14161f]/40 backdrop-blur-md border border-white/5 rounded-2xl p-4 sm:p-6 shadow-2xl shadow-black/40 transition-all">
      <div 
        className={`flex items-center justify-between cursor-pointer group select-none ${isOpen ? 'mb-6' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-blue-500/10 flex items-center justify-center border border-blue-500/20 group-hover:bg-blue-500/20 transition-colors">
            <ThunderboltOutlined className="text-blue-500 text-xs" />
          </div>
          <span className="text-xs font-black text-slate-400 uppercase tracking-widest group-hover:text-slate-300 transition-colors">
            Thought Chain
          </span>
          {!isOpen && (
             <span className="text-xs text-slate-500 ml-2 font-mono">({steps.length} steps)</span>
          )}
        </div>
        
        <div className="flex items-center gap-3">
          {loading && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-500/10 border border-blue-500/20">
              <Badge status="processing" />
              <span className="text-micro font-bold text-blue-400 uppercase tracking-wider leading-none mt-px">Active</span>
            </div>
          )}
          <div className="text-slate-500 group-hover:text-slate-300 transition-colors flex items-center">
             {isOpen ? <UpOutlined className="text-[10px]" /> : <DownOutlined className="text-[10px]" />}
          </div>
        </div>
      </div>
      
      {isOpen && (
        <div className="custom-thought-chain overflow-hidden animate-fade-in">
          <ThoughtChain
            items={items}
            className="text-slate-300"
          />
        </div>
      )}
    </div>
  );
}
