import React from 'react';
import { Drawer, Tabs, Empty, Typography, Grid, Tag, Collapse } from 'antd';
import { FileTextOutlined, CheckSquareOutlined, ExclamationCircleOutlined, CloseCircleOutlined, InfoCircleOutlined, SettingOutlined, CodeOutlined, CaretRightOutlined } from '@ant-design/icons';
import { useResearchStore } from '@/store/useResearchStore';
import type { VerificationClaim } from '@/types';
import { renderMarkdown } from '@/lib/markdown';
import VerificationCard from './VerificationCard';

const { Text } = Typography;
const { useBreakpoint } = Grid;

/** 参数名中文映射字典 */
const PARAM_LABEL_MAP: Record<string, string> = {
  max_search_rounds: '搜索迭代轮次',
  max_dimensions: '研究维度上限',
  keywords_per_dimension: '单维度关键词数',
  bilingual: '中英双语检索',
  include_year: '包含当前年份',
  verification_level: '交叉验证等级',
  max_total_results: '分析信源总量',
  speed: '响应层级基准',
  engines: '搜索引擎组合',
  allow_ai_override: '允许 AI 调参',
};

/** 响应层级标签映射 */
const SPEED_LABEL_MAP: Record<string, string> = {
  fast_react: '极速快问',
  expert_search: '专家搜索',
  research_pipeline: '深度研报',
};

/** 验证等级中文映射 */
const VERIF_LABEL_MAP: Record<string, string> = {
  skip: '跳过验证 (极速)',
  standard: '标准验证 (均衡)',
  strict: '深度验证 (严谨)',
};

interface ReportDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: string;
  onTabChange: (key: string) => void;
  reportContent: string;
  isStreaming: boolean;
  claims: VerificationClaim[];
}

export const ReportDrawer: React.FC<ReportDrawerProps> = ({
  isOpen,
  onClose,
  activeTab,
  onTabChange,
  reportContent,
  isStreaming,
  claims,
}) => {
  const { warnings, errorLog, runConfigSnapshot, durationSeconds } = useResearchStore();
  
  // Use Ant Design's official breakpoint hook to avoid FOUC and manual resize listeners
  const screens = useBreakpoint();
  const isMobile = screens.md === false; // matches md: hidden threshold (768px)

  const renderValue = (key: string, val: any) => {
    if (key === 'speed' && typeof val === 'string') {
      return SPEED_LABEL_MAP[val] || val;
    }
    if (key === 'verification_level' && typeof val === 'string') {
      return VERIF_LABEL_MAP[val] || val;
    }
    if (typeof val === 'boolean') {
      return val ? '开启' : '关闭';
    }
    if (Array.isArray(val)) {
      return val.join(', ');
    }
    return String(val);
  };

  const executionMode = runConfigSnapshot?.execution_mode || 'research_pipeline';

  const tabItems = [
    {
      key: 'report',
      label: <span className="px-2 sm:px-4 py-2 flex items-center gap-2 text-sm"><FileTextOutlined /> <span className="hidden sm:inline">终稿报告</span></span>,
      children: (
        <div className="p-4 sm:p-8 h-full overflow-y-auto">
          {reportContent ? (
            <div className="prose prose-invert max-w-none text-sm sm:text-base">
              <div className="markdown-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(reportContent) }} />
            </div>
          ) : isStreaming ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-4 mt-20">
              <span className="animate-spin text-3xl">⏳</span>
              <p className="text-sm">正在努力编撰研究报告，请稍候...</p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-4 mt-20">
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="报告未生成" />
            </div>
          )}
        </div>
      )
    },
    // 🔒 仅在深度研报模式下显示断言核实面板
    ...(executionMode === 'research_pipeline' ? [{
      key: 'claims',
      label: <span className="px-2 sm:px-4 py-2 flex items-center gap-2 text-sm"><CheckSquareOutlined /> <span className="hidden sm:inline">断言核实</span></span>,
      children: (
        <div className="p-4 sm:p-6 h-full overflow-y-auto">
          {claims.length > 0 ? (
            <div className="flex flex-col gap-4">
              <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-4 mb-2 sm:mb-4">
                <div className="flex items-center gap-2 text-blue-400 font-bold text-xs mb-2">
                  <InfoCircleOutlined /> 智能核查摘要
                </div>
                <p className="text-xs text-slate-400 leading-relaxed m-0">
                  系统已自动识别并拆解出 {claims.length} 条核心断言，并基于全网高置信度信源进行了交叉比对。
                </p>
              </div>
              {claims.map((claim, idx) => (
                <VerificationCard key={idx} claim={claim} />
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无核实数据" className="mt-20 sm:mt-40" />
          )}
        </div>
      )
    }] : []),
    {
      key: 'logs',
      label: <span className="px-2 sm:px-4 py-2 flex items-center gap-2 text-sm"><ExclamationCircleOutlined /> <span className="hidden sm:inline">执行日志</span></span>,
      children: (
        <div className="p-4 sm:p-6 h-full overflow-y-auto">
          <div className="flex flex-col gap-6">
            <section>
              <h4 className="text-slate-300 font-bold mb-3 flex items-center gap-2 text-sm">
                <ExclamationCircleOutlined className="text-amber-500" /> 研究警告
              </h4>
              {warnings.length > 0 ? (
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4">
                  {warnings.map((w, i) => <div key={i} className="text-amber-400/90 text-xs sm:text-sm mb-1 break-words">• {w}</div>)}
                </div>
              ) : <Text className="text-slate-500 text-sm italic">无警告信息。</Text>}
            </section>
            
            <section>
              <h4 className="text-slate-300 font-bold mb-3 flex items-center gap-2 text-sm">
                <CloseCircleOutlined className="text-rose-500" /> 异常日志
              </h4>
              {errorLog.length > 0 ? (
                <div className="bg-rose-500/5 border border-rose-500/20 rounded-xl p-4 gap-4 flex flex-col">
                  {errorLog.map((err, i) => (
                    <div key={i} className="border-b border-rose-500/10 pb-3 last:border-0 last:pb-0">
                      <div className="text-rose-400 font-medium text-xs sm:text-sm break-all">节点: {err.node}</div>
                      <div className="text-rose-300/90 text-xs sm:text-sm break-words mt-1">{err.message}</div>
                    </div>
                  ))}
                </div>
              ) : <Text className="text-slate-500 text-sm italic">无阻断性异常。</Text>}
            </section>
          </div>
        </div>
      )
    },
    {
      key: 'strategy',
      label: <span className="px-2 sm:px-4 py-2 flex items-center gap-2 text-sm"><SettingOutlined /> <span className="hidden sm:inline">策略快照</span></span>,
      children: (
        <div className="p-4 sm:p-6 h-full overflow-y-auto text-slate-200">
          <div className="flex flex-col gap-6">
            {/* 顶部引导说明 */}
            <div className="bg-blue-500/5 border border-blue-500/20 rounded-2xl p-6 flex gap-4 items-start">
              <SettingOutlined className="text-blue-400 text-2xl mt-1 shrink-0" />
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="text-blue-400 font-bold text-base">运行时参数审计</div>
                  {durationSeconds !== null && (
                    <div className="bg-blue-500/10 border border-blue-500/20 rounded-full px-3 py-1 flex items-center gap-2">
                      <span className="text-[10px] text-blue-400/60 uppercase font-black tracking-tighter">Execution Time</span>
                      <span className="text-blue-300 font-mono font-bold text-sm">{durationSeconds}s</span>
                    </div>
                  )}
                </div>
                <p className="text-sm text-slate-400 leading-relaxed m-0">
                  本报告基于以下参数生成。系统已根据您的原始预设（Baseline），结合 AI 对问题的复杂度研判进行了实时战术调整。
                </p>
              </div>
            </div>

            {runConfigSnapshot ? (
              <div className="flex flex-col gap-10">
                {/* 1. AI 动态覆盖 */}
                {runConfigSnapshot.strategy_overrides && Object.keys(runConfigSnapshot.strategy_overrides).length > 0 ? (
                  <section>
                    <div className="flex items-center justify-between mb-5">
                      <h5 className="text-blue-400 text-sm font-black uppercase tracking-[0.2em] flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                        AI 智能优化策略
                      </h5>
                      <Tag color="blue" className="bg-blue-500/10 border-blue-500/20 text-xs px-2 py-0.5 m-0">已生效</Tag>
                    </div>
                    
                    <div className="grid grid-cols-1 gap-4">
                      {Object.entries(runConfigSnapshot.strategy_overrides).map(([key, val]) => (
                        <div key={key} className="relative group overflow-hidden bg-gradient-to-r from-blue-600/10 to-transparent border border-blue-500/20 rounded-2xl p-5 transition-all hover:border-blue-500/40">
                          <div className="flex items-center justify-between relative z-10">
                            <div className="flex flex-col gap-1.5">
                              <span className="text-xs text-blue-300/50 font-bold uppercase tracking-wider">{key}</span>
                              <span className="text-slate-200 text-base font-bold">{PARAM_LABEL_MAP[key] || key}</span>
                            </div>
                            <div className="flex flex-col items-end gap-1.5">
                              <span className="text-xs text-slate-500 italic">当前取值</span>
                              <span className="text-blue-400 font-mono font-black text-lg">{renderValue(key, val)}</span>
                            </div>
                          </div>
                          <div className="absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-32 h-32 bg-blue-500/5 rounded-full blur-3xl group-hover:bg-blue-500/10 transition-colors" />
                        </div>
                      ))}
                    </div>
                  </section>
                ) : (
                  <section className="bg-slate-500/5 border border-slate-500/10 rounded-2xl p-6 text-center italic text-slate-500 text-sm">
                    AI 评估后认为基准配置已足够，未触发动态调参。
                  </section>
                )}

                {/* 2. 基准业务预设 */}
                <section>
                  <h5 className="text-slate-400 text-sm font-black mb-5 uppercase tracking-[0.2em] flex items-center gap-2">
                    <div className="w-1.5 h-1.5 bg-slate-500 rounded-full" />
                    原始业务基准
                  </h5>
                  <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-6">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-8 gap-x-6">
                      {Object.entries(runConfigSnapshot.business || {}).map(([key, val]) => (
                        <div key={key} className="flex flex-col gap-2">
                          <span className="text-xs text-slate-500 font-bold uppercase tracking-widest">
                            {PARAM_LABEL_MAP[key] || key}
                          </span>
                          <span className="text-slate-300 text-sm font-mono break-all leading-relaxed">
                            {renderValue(key, val)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
                
                {/* 3. 源码存证 */}
                <section className="mt-8 border-t border-white/5 pt-8">
                  <Collapse
                    ghost
                    expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} className="text-slate-500 text-base" />}
                    items={[
                      {
                        key: 'raw',
                        label: (
                          <div className="flex items-center gap-3">
                            <CodeOutlined className="text-slate-500 text-base" />
                            <span className="text-slate-400 text-xs font-bold uppercase tracking-[0.15em]">
                              物理配置源码 (底层调试数据)
                            </span>
                          </div>
                        ),
                        children: (
                          <div className="relative group mt-2">
                            <div className="absolute top-4 right-6 text-xs text-slate-700 font-mono z-10 opacity-0 group-hover:opacity-100 transition-opacity uppercase tracking-widest">Immutable Snapshot</div>
                            <pre className="bg-[#050505] p-6 rounded-2xl text-sm text-slate-400 overflow-x-auto border border-white/[0.05] font-mono leading-relaxed shadow-inner scrollbar-thin scrollbar-thumb-white/10">
                              {JSON.stringify(runConfigSnapshot, null, 2)}
                            </pre>
                            <p className="mt-4 text-xs text-slate-600 italic px-2">
                              * 此数据为本次任务发起时后端执行引擎的原始入参，用于技术审计与历史溯源。
                            </p>
                          </div>
                        ),
                      },
                    ]}
                  />
                </section>
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span className="text-sm">未捕获到运行时配置快照</span>} className="mt-20" />
            )}
          </div>
        </div>
      )
    }
  ];

  return (
    <Drawer
      title={
        <div className="flex items-center gap-3">
          <FileTextOutlined className="text-blue-500" />
          <span className="text-slate-200 font-black tracking-tight text-sm sm:text-base">深度研究档案</span>
        </div>
      }
      placement={isMobile ? 'bottom' : 'right'}
      onClose={onClose}
      open={isOpen}
      size={isMobile ? '90vh' : 720}
      mask={isMobile}
      className="research-drawer"
      styles={{
        header: { borderBottom: '1px solid rgba(255,255,255,0.05)', background: '#0b0c11', padding: isMobile ? '12px 16px' : '16px 24px' },
        body: { padding: 0, background: '#090a0f' }
      }}
    >
      <Tabs
        activeKey={activeTab}
        onChange={onTabChange}
        centered
        className="custom-tabs h-full flex flex-col"
        items={tabItems}
        tabBarGutter={isMobile ? 12 : 32}
      />
    </Drawer>
  );
};
