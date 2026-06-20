'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sender, Prompts } from '@ant-design/x';
import { Button, Space, Dropdown, Tooltip, Segmented, Typography, Tag } from 'antd';
import { 
  SettingOutlined, HistoryOutlined, UserOutlined, 
  LogoutOutlined, CompassOutlined, LoadingOutlined,
  ThunderboltOutlined, SendOutlined, SearchOutlined,
  FileTextOutlined, RobotOutlined, SafetyCertificateOutlined,
  DeploymentUnitOutlined, FileProtectOutlined, GlobalOutlined
} from '@ant-design/icons';
import { EXECUTION_MODES } from '@/lib/constants';

const { Title, Paragraph, Text } = Typography;

/** 模式特性定义 — 仅保留 UI 专属部分（icon + 高亮词），title/desc 从后端 schema 读取 */
const MODE_UI_FEATURES: Record<string, { icon: React.ReactNode; highlights: string[] }> = {
  [EXECUTION_MODES.AUTO]: {
    icon: <RobotOutlined className="text-blue-400" />,
    highlights: ['最优路径规划', '动态算力分配', '全场景覆盖'],
  },
  [EXECUTION_MODES.FAST]: {
    icon: <ThunderboltOutlined className="text-amber-400" />,
    highlights: ['毫秒级检索', '高并发采集', '极简摘要'],
  },
  [EXECUTION_MODES.EXPERT]: {
    icon: <SearchOutlined className="text-indigo-400" />,
    highlights: ['思维链推理', '自主深度阅读', '背景调研'],
  },
  [EXECUTION_MODES.PIPELINE]: {
    icon: <FileProtectOutlined className="text-emerald-400" />,
    highlights: ['多源证据对齐', '冲突自动识别', '结构化研报'],
  },
};

const VITALITY_METRICS = [
  { label: '核验信源', value: '1,240k+', icon: <SafetyCertificateOutlined /> },
  { label: '活跃 Agent', value: '42', icon: <DeploymentUnitOutlined /> },
  { label: '认知深度', value: '8.5层', icon: <CompassOutlined /> },
];

const AMBIENT_TAGS = [
  { label: '多源证据对齐', top: '15%', left: '15%', delay: '0s' },
  { label: '逻辑一致性核验', top: '25%', right: '10%', delay: '1s' },
  { label: '深度语义分析', bottom: '40%', left: '8%', delay: '2s' },
  { label: '隐私加密传输', top: '10%', right: '20%', delay: '0.5s' },
  { label: '实时互联搜索', bottom: '30%', right: '12%', delay: '1.5s' },
];

interface UserClaims {
  sub: string;
  name?: string;
  email?: string;
  picture?: string;
  [key: string]: unknown;
}

interface DashboardProps {
  userClaims: UserClaims;
}

import { useSettingsStore } from '@/store/useSettingsStore';
import { useResearchStore } from '@/store/useResearchStore';

export default function Dashboard({ userClaims }: DashboardProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [speed, setSpeed] = useState<string>(EXECUTION_MODES.AUTO);
  const [submitting, setSubmitting] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [isFocused, setIsFocused] = useState(false);

  const { schema, fetchSchema } = useSettingsStore();

  React.useEffect(() => {
    setMounted(true);
    fetchSchema();
  }, [fetchSchema]);

  const DOMAIN_LABELS: Record<string, string> = {
    [EXECUTION_MODES.AUTO]: 'AI 自动决策',
    [EXECUTION_MODES.FAST]: '极速响应 (Fast React)',
    [EXECUTION_MODES.EXPERT]: '专家搜索 (Expert Search)',
    [EXECUTION_MODES.PIPELINE]: '深度研究 (Research Pipeline)',
  };

  const uiFeature = MODE_UI_FEATURES[speed] || MODE_UI_FEATURES[EXECUTION_MODES.AUTO];
  const backendMeta = schema?.speed_profiles?.[speed] || schema?.speed_profiles?.[EXECUTION_MODES.PIPELINE];
  const activeFeature = {
    title: DOMAIN_LABELS[speed] || backendMeta?.label || speed,
    desc: backendMeta?.description || (speed === EXECUTION_MODES.AUTO ? 'AI 根据问题复杂度，自动规划最适合的响应层级与策略参数' : ''),
    icon: uiFeature.icon,
    highlights: uiFeature.highlights,
  };

  const handleSearch = (value: string, searchSpeed?: string) => {
    const finalValue = value || query;
    if (!finalValue.trim() || submitting) return;
    setSubmitting(true);
    
    const activeSpeed = searchSpeed || speed;
    useResearchStore.getState().setSpeed(activeSpeed as any);
    if (activeSpeed !== EXECUTION_MODES.AUTO) {
      useResearchStore.getState().setExecutionMode('preset');
    }
    const tempId = crypto.randomUUID();
    router.push(`/research/${tempId}?q=${encodeURIComponent(finalValue)}`);
  };

  // 动态构建模式选项，基于后端 Schema 并融合前端图标
  const MODE_OPTIONS = React.useMemo(() => {
    const defaults = [
      { 
        label: <div className="flex items-center gap-1.5"><RobotOutlined /> 智能</div>, 
        value: EXECUTION_MODES.AUTO, 
        desc: 'AI 自动规划响应层级，平衡速度、广度与深度' 
      }
    ];

    const ICON_MAP: Record<string, React.ReactNode> = {
      fast_react: <ThunderboltOutlined />,
      expert_search: <SearchOutlined />,
      research_pipeline: <FileTextOutlined />,
    };

    const DOMAIN_LABELS: Record<string, string> = {
      fast_react: '极速',
      expert_search: '专家',
      research_pipeline: '研究',
    };

    if (!schema?.speed_profiles) return [
      ...defaults,
      { label: <div className="flex items-center gap-1.5"><ThunderboltOutlined /> 极速</div>, value: EXECUTION_MODES.FAST, desc: '秒级极速响应，适合日常速查与简单确认' },
      { label: <div className="flex items-center gap-1.5"><SearchOutlined /> 专家</div>, value: EXECUTION_MODES.EXPERT, desc: '专家级自主深度检索，适合方案解释与背景调研' },
      { label: <div className="flex items-center gap-1.5"><FileTextOutlined /> 研究</div>, value: EXECUTION_MODES.PIPELINE, desc: '多源深度核查，适合高信度、结构化的深度研究报告' },
    ];

    const backendOptions = Object.entries(schema.speed_profiles).map(([val, meta]) => {
      return {
        label: <div className="flex items-center gap-1.5">{ICON_MAP[val] || <SearchOutlined />} {DOMAIN_LABELS[val] || meta.label}</div>,
        value: val,
        desc: meta.description
      };
    });

    return [...defaults, ...backendOptions];
  }, [schema]);

  const demoPrompts = [
    {
      key: '1',
      label: 'iPhone 16 Pro 和 华为 Mate 60 RS 核心差异在哪？目前这两种机型的真实用户槽点分别是什么？',
      description: '建议使用 ⚡ 极速快问',
      extra: 'fast_react'
    },
    {
      key: '2',
      label: '网传“马斯克的 Neuralink 脑机接口导致受试者大脑感染”，这个传闻是真的吗？有权威医学报道吗？',
      description: '建议使用 📄 深度研究',
      extra: 'research_pipeline'
    },
    {
      key: '3',
      label: '2025 年全球固态电池商业化进展如何？目前阻碍其大规模量产的核心技术瓶颈和主要玩家有哪些？',
      description: '建议使用 🔍 专家搜索',
      extra: 'expert_search'
    }
  ];

  return (
    <div className="min-h-screen flex flex-col text-slate-200 relative overflow-hidden selection:bg-blue-500/30 pb-20 bg-[#090a0f]">
      {/* 霓虹弥散背景 - 优化渲染防止边缘白边 */}
      <div className="absolute top-[-20%] left-[-20%] w-[60%] h-[60%] bg-blue-600/[0.08] rounded-full blur-[160px] pointer-events-none animate-pulse-slow will-change-transform" />
      <div className="absolute bottom-[-20%] right-[-20%] w-[60%] h-[60%] bg-indigo-600/[0.08] rounded-full blur-[160px] pointer-events-none animate-pulse-slow-reverse will-change-transform" />

      {/* 🆕 环境点缀标签 (Ambient Ornaments) - 调暗背景色 */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden hidden lg:block">
        {AMBIENT_TAGS.map((tag, i) => (
          <div 
            key={i}
            className="absolute px-3 py-1.5 rounded-full border border-white/5 bg-blue-500/[0.05] backdrop-blur-md text-[10px] font-bold text-slate-600 uppercase tracking-widest animate-float"
            style={{ 
              top: tag.top, 
              left: tag.left, 
              right: tag.right, 
              bottom: tag.bottom,
              animationDelay: tag.delay
            }}
          >
            {tag.label}
          </div>
        ))}
      </div>

      {/* 主体内容 */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 max-w-[950px] w-full mx-auto relative z-10 py-10 sm:py-20">
        
        {/* 精致的标题区域 */}
        <div className="text-center mb-12 sm:mb-20 relative">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/5 border border-blue-500/10 mb-8 animate-fade-in">
            <div className="w-1 h-1 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,1)]" />
            <span className="text-[10px] font-black uppercase tracking-[0.3em] text-blue-500/60">
              TruthSeeker v3.0 Intelligence
            </span>
          </div>

          <h1 className="text-4xl sm:text-6xl md:text-8xl font-black tracking-tighter mb-8 relative leading-none">
            <span className="bg-gradient-to-b from-white via-white to-slate-600 bg-clip-text text-transparent">
              探索真理
            </span>
          </h1>

          <div className="space-y-4 max-w-[650px] mx-auto">
            <p className="text-slate-500 text-lg sm:text-xl leading-relaxed font-medium">
              多代理驱动的研究引擎，为您提供 <span className="text-slate-300 font-bold">多源核查</span> 与 <span className="text-slate-300 font-bold"> 深度调研</span>。
            </p>
            
            {/* 技术栈点缀条 */}
            <div className="flex items-center justify-center gap-6 opacity-30 pt-2 grayscale hover:opacity-60 transition-opacity duration-700">
               <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest">
                  <DeploymentUnitOutlined /> LangGraph
               </div>
               <div className="w-1 h-1 rounded-full bg-slate-700" />
               <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest">
                  <ThunderboltOutlined /> ReAct-Engine
               </div>
               <div className="w-1 h-1 rounded-full bg-slate-700" />
               <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest">
                  <GlobalOutlined /> Web-Realtime
               </div>
            </div>
          </div>
        </div>

        {/* 核心输入区域 */}
        <div className="w-full relative group mb-16">
          <div className="absolute -inset-1 bg-gradient-to-r from-blue-600/20 via-indigo-600/20 to-blue-600/20 rounded-[32px] blur-xl opacity-0 group-focus-within:opacity-100 transition duration-1000" />
          
          <div className="relative bg-[#0d0f16]/80 backdrop-blur-2xl border border-white/10 group-hover:border-white/20 group-focus-within:border-blue-500/40 rounded-[28px] p-2 shadow-2xl transition-all duration-500">
            <div className="flex flex-col">
              {isFocused && query.trim() === '' && (
                <div className="animate-in fade-in slide-in-from-top-4 duration-500">
                  <Prompts
                    items={demoPrompts}
                    onItemClick={(info) => {
                      const data = info.data as any;
                      setSpeed(data.extra);
                      setQuery(data.label);
                    }}
                    className="custom-prompts-inside px-3 pt-4"
                  />
                </div>
              )}
              
              <Sender
                value={query}
                onChange={setQuery}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setTimeout(() => setIsFocused(false), 250)}
                onSubmit={(val) => handleSearch(val)}
                placeholder="在此输入您的求证问题或研究主题..."
                className="bg-transparent border-none text-white text-lg py-3"
                submitType="enter"
                prefix={submitting ? <LoadingOutlined className="text-blue-500 animate-spin mr-3" /> : null}
                suffix={
                  <Button 
                    type="primary"
                    shape="circle"
                    icon={<SendOutlined style={{ fontSize: 16 }} />}
                    onClick={() => handleSearch(query)}
                    disabled={!query.trim() || submitting}
                    className={`w-12 h-12 flex items-center justify-center border-none transition-all duration-500 ${
                      query.trim() && !submitting
                        ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_20px_rgba(37,99,235,0.4)] scale-105' 
                        : 'bg-white/5 text-slate-700 scale-95'
                    }`}
                  />
                }
              />
              
              <div className="flex items-center justify-between gap-4 px-5 py-4 border-t border-white/5">
                <div className="flex-1">
                  <div className="flex items-center gap-1 bg-black/30 rounded-2xl border border-white/5 p-0.5 w-fit">
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider pl-3 pr-1 select-none">
                      研究深度
                    </span>
                    {MODE_OPTIONS.map((opt) => {
                      const active = speed === opt.value;
                      return (
                        <button
                          key={opt.value}
                          disabled={submitting}
                          onClick={() => setSpeed(opt.value as string)}
                          className={`px-4 py-2 rounded-xl text-sm font-semibold tracking-wide transition-all duration-300 flex items-center gap-1.5 ${
                            active
                              ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/20 scale-[1.02]'
                              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                          } ${submitting ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
                
                <div className="hidden sm:flex text-micro font-bold text-slate-600 uppercase tracking-[0.2em] items-center gap-2 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.6)] animate-pulse" />
                  Engine Standby
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 动态 Bento Grid 布局 */}
        <div className="w-full grid grid-cols-1 md:grid-cols-12 gap-6 items-stretch">
            
            {/* 左侧大卡片：当前模式特性 (动态) */}
            <div className="md:col-span-8 p-8 rounded-[32px] bg-linear-to-br from-white/[0.03] to-transparent border border-white/5 relative overflow-hidden group transition-all duration-700 hover:border-blue-500/20">
                <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:opacity-20 transition-opacity">
                    <div className="text-8xl">{activeFeature.icon}</div>
                </div>
                
                <div className="relative z-10">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 bg-blue-500/10 rounded-xl text-blue-400 text-xl">
                            {activeFeature.icon}
                        </div>
                        <h3 className="text-xl font-bold text-slate-100 m-0">{activeFeature.title}</h3>
                    </div>
                    <p className="text-slate-500 text-sm leading-relaxed max-w-md mb-6">
                        {activeFeature.desc}
                    </p>
                    <div className="flex flex-wrap gap-2">
                        {activeFeature.highlights.map((h: string) => (
                            <span key={h} className="px-3 py-1 rounded-full bg-white/5 border border-white/5 text-xs text-slate-400 font-bold uppercase tracking-wider">
                                {h}
                            </span>
                        ))}
                    </div>
                </div>
            </div>

            {/* 右侧垂直列表：系统活力指标 */}
            <div className="md:col-span-4 grid grid-cols-1 gap-6">
                {VITALITY_METRICS.map(m => (
                    <div key={m.label} className="p-5 rounded-[24px] bg-white/[0.02] border border-white/5 flex items-center justify-between hover:bg-white/[0.04] transition-all">
                        <div className="flex items-center gap-3">
                            <div className="text-slate-600 text-lg">{m.icon}</div>
                            <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">{m.label}</span>
                        </div>
                        <div className="text-lg font-black text-slate-200 tracking-tight">{m.value}</div>
                    </div>
                ))}
            </div>

        </div>

      </main>

      <footer className="absolute bottom-4 sm:bottom-10 left-0 right-0 text-center opacity-30">
        <p className="text-xs font-bold text-slate-700 tracking-[0.4em] uppercase px-4">
          Precision • Objectivity • Transparency
        </p>
      </footer>
    </div>
  );
}
