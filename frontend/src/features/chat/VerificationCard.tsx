'use client';

import React, { useState } from 'react';
import { Tag, Space, Collapse, Tooltip, Button } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined, CloseCircleOutlined, DownOutlined, UpOutlined, LinkOutlined } from '@ant-design/icons';
import type { VerificationClaim } from '@/types';

interface VerificationCardProps {
  claim: VerificationClaim;
}

export default function VerificationCard({ claim }: VerificationCardProps) {
  const [expanded, setExpanded] = useState(false);

  const verdictStyles = {
    verified: {
      color: '#2dd4bf', // 莫兰迪青色
      bg: 'bg-teal-950/20',
      border: 'border-teal-900/60',
      icon: <CheckCircleOutlined className="text-teal-400" />,
      text: '已证实 (Verified)',
      tagColor: 'cyan' as const
    },
    likely_true: {
      color: '#60a5fa', // 莫兰迪蓝色
      bg: 'bg-blue-950/20',
      border: 'border-blue-900/60',
      icon: <InfoCircleOutlined className="text-blue-400" />,
      text: '基本属实 (Likely True)',
      tagColor: 'blue' as const
    },
    disputed: {
      color: '#fbbf24', // 莫兰迪橙色
      bg: 'bg-amber-950/20',
      border: 'border-amber-900/60',
      icon: <ExclamationCircleOutlined className="text-amber-400" />,
      text: '存在争议 (Disputed)',
      tagColor: 'warning' as const
    },
    refuted: {
      color: '#f87171', // 莫兰迪红色
      bg: 'bg-rose-950/20',
      border: 'border-rose-900/60',
      icon: <CloseCircleOutlined className="text-rose-400" />,
      text: '已驳回 (Refuted)',
      tagColor: 'error' as const
    },
    unverifiable: {
      color: '#94a3b8', // 莫兰迪灰色
      bg: 'bg-slate-900/40',
      border: 'border-slate-800/80',
      icon: <InfoCircleOutlined className="text-slate-400" />,
      text: '无法核实 (Unverifiable)',
      tagColor: 'default' as const
    }
  };

  const style = verdictStyles[claim.verdict] || verdictStyles.unverifiable;

  // Extract base domain for clean rendering of URLs
  const getDomain = (url: string) => {
    try {
      const parsed = new URL(url);
      return parsed.hostname.replace('www.', '');
    } catch {
      return url;
    }
  };

  return (
    <div className={`p-4 sm:p-5 rounded-2xl border ${style.border} ${style.bg} mb-4 shadow-md shadow-black/40 transition-all duration-200 bg-[#14161f]/60 backdrop-blur-sm`}>
      <div className="flex flex-wrap sm:flex-nowrap justify-between items-start gap-2 sm:gap-4 mb-3">
        <h4 className="text-sm font-semibold text-slate-200 leading-relaxed m-0 flex-1 w-full sm:w-auto">
          {claim.claim}
        </h4>
        <Tag
          icon={style.icon}
          color={style.tagColor}
          className="rounded-full px-2 sm:px-3 py-0.5 text-micro sm:text-xs m-0 border-0 flex items-center gap-1 shadow-sm shrink-0"
        >
          {style.text}
        </Tag>
      </div>

      <div className="flex flex-wrap items-center justify-between text-xs text-slate-400 gap-y-2 mt-2 sm:mt-0">
        <Space size="middle" className="flex-wrap">
          <span>置信度: <strong style={{ color: style.color }} className="font-semibold">{(claim.confidence * 100).toFixed(0)}%</strong></span>
          <span className="hidden sm:inline">•</span>
          <span>信源数: <strong className="text-slate-350 font-semibold">{claim.supporting_sources?.length || 0}</strong></span>
        </Space>
        
        <Button
          type="link"
          size="small"
          onClick={() => setExpanded(!expanded)}
          className="p-0 h-auto text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium transition-all ml-auto sm:ml-0"
        >
          {expanded ? (
            <>收起细节 <UpOutlined className="text-micro sm:text-caption" /></>
          ) : (
            <>查看依据与信源 <DownOutlined className="text-micro sm:text-caption" /></>
          )}
        </Button>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-white/5">
          {/* Warnings if present */}
          {claim.warnings && claim.warnings.length > 0 && (
            <div className="bg-amber-950/20 border border-amber-900/40 rounded-xl p-3 mb-4 text-xs text-amber-300">
              {claim.warnings.map((w, idx) => (
                <div key={idx} className="flex gap-2 items-start">
                  <ExclamationCircleOutlined className="mt-0.5" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          {/* Evidence support/refute text */}
          <Collapse
            ghost
            size="small"
            className="mb-4 text-xs custom-collapse"
            items={[
              {
                key: 'support',
                label: <span className="text-slate-300 font-medium text-xs">支持论据 ({claim.evidence?.supports?.length || 0})</span>,
                children: (
                  <ul className="list-disc pl-4 text-slate-400 text-xs space-y-1.5">
                    {claim.evidence?.supports?.map((s, idx) => <li key={idx}>{s}</li>)}
                    {(!claim.evidence?.supports || claim.evidence.supports.length === 0) && <li className="list-none -ml-4 text-slate-500">无显式支持性陈述</li>}
                  </ul>
                )
              },
              {
                key: 'refute',
                label: <span className="text-slate-300 font-medium text-xs">反驳/矛盾论据 ({claim.evidence?.refutes?.length || 0})</span>,
                children: (
                  <ul className="list-disc pl-4 text-slate-400 text-xs space-y-1.5">
                    {claim.evidence?.refutes?.map((r, idx) => <li key={idx}>{r}</li>)}
                    {(!claim.evidence?.refutes || claim.evidence.refutes.length === 0) && <li className="list-none -ml-4 text-slate-500">无显式反驳性陈述</li>}
                  </ul>
                )
              }
            ]}
          />

          {/* Supporting URLs */}
          <div>
            <div className="text-micro sm:text-note text-slate-400 font-semibold mb-2 uppercase tracking-wider">原始信源</div>
            <div className="flex gap-2 flex-wrap">
              {claim.supporting_sources?.map((url, idx) => (
                <Tooltip title={url} key={idx}>
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 bg-white/2 border border-white/5 rounded-lg px-2 sm:px-2.5 py-1 text-micro sm:text-xs text-blue-400 hover:text-blue-300 hover:border-blue-500/30 hover:bg-blue-500/10 transition-all shadow-sm max-w-full"
                  >
                    <LinkOutlined className="text-micro sm:text-caption shrink-0" />
                    <span className="truncate">{getDomain(url)}</span>
                  </a>
                </Tooltip>
              ))}
              {(!claim.supporting_sources || claim.supporting_sources.length === 0) && (
                <span className="text-xs text-slate-500">无关联外部信源</span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

