'use client';

import React, { useMemo } from 'react';
import { Typography, Tag, Button, Select, InputNumber, Slider, Card, Empty, Row, Col, Space, Switch } from 'antd';
import {
  BulbOutlined,
  SearchOutlined,
  CheckSquareOutlined,
  DeploymentUnitOutlined,
  SaveOutlined,
  SettingOutlined,
  DoubleRightOutlined,
  GlobalOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { useSettingsStore } from '@/store/useSettingsStore';
import { 
  STAGES, 
  PIPELINE_SUB_STAGES,
  WorkflowShared,
} from './workflow/constants';
import EffectPanel from './workflow/EffectPanel';
import type { PresetStageConfig } from '@/types';

const { Title, Text } = Typography;

const STAGE_ICONS: Record<string, React.ReactNode> = {
  fast_react: <BulbOutlined />,
  expert_search: <SearchOutlined />,
  research_pipeline: <CheckSquareOutlined />,
  embedding: <DeploymentUnitOutlined />,
};

const MODE_NAME_MAP: Record<string, string> = { 
  'fast_react': '极速快问', 
  'expert_search': '专家搜索', 
  'research_pipeline': '深度研报' 
};

/** 
 * 单行配置项组件 (仿 NextChat 风格) 
 */
const ConfigRow = ({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) => (
  <div className="group flex items-center justify-between py-3.5 px-5 transition-colors hover:bg-white/[0.02] border-b border-white/[0.02] last:border-none">
    <div className="flex-1 pr-8">
      <div className="text-sm font-bold text-slate-200 tracking-tight">{label}</div>
      {description && <div className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{description}</div>}
    </div>
    <div className="flex-shrink-0 flex justify-end">
      {children}
    </div>
  </div>
);

export default function WorkflowPanel() {
  const {
    assets,
    presets,
    activePresetId,
    setActivePresetId,
    schema,
    updateLocalPreset,
    secrets,
    saveLoading,
    applyChanges,
    disabledModelIds,
  } = useSettingsStore();

  const activePreset = useMemo(
    () => presets.find(p => p.id === activePresetId),
    [presets, activePresetId],
  );

  const isSystemPreset = !!activePreset?.is_system_default;

  const updateStageConfig = (stageKey: string, data: Record<string, unknown>) => {
    if (!activePreset) return;
    const newConfig = { ...activePreset.nodes_config };
    const existing: PresetStageConfig = newConfig.stages[stageKey] || { asset_id: null, params: {} };
    newConfig.stages = { ...newConfig.stages, [stageKey]: { ...existing, ...data } };
    updateLocalPreset(activePreset.id, { nodes_config: newConfig });
  };

  const updateStageParams = (stageKey: string, nodeType: string, params: Record<string, unknown>) => {
    if (!activePreset) return;
    const newConfig = { ...activePreset.nodes_config };
    const existing: PresetStageConfig = newConfig.stages[stageKey] || { asset_id: null, params: {} };
    const oldParams = (existing.params || {}) as Record<string, Record<string, unknown>>;
    const oldNodeParams = oldParams[nodeType] || {};
    newConfig.stages = {
      ...newConfig.stages,
      [stageKey]: { ...existing, params: { ...oldParams, [nodeType]: { ...oldNodeParams, ...params } } },
    };
    updateLocalPreset(activePreset.id, { nodes_config: newConfig });
  };

  const updateBusinessConfig = (key: string, val: unknown) => {
    if (!activePreset) return;
    const newConfig = { ...activePreset.nodes_config };
    newConfig.business = { ...newConfig.business, [key]: val };
    updateLocalPreset(activePreset.id, { nodes_config: newConfig });
  };

  if (!activePreset) {
    return (
      <div className="flex items-center justify-center h-96 bg-[#090a0f] rounded-3xl border border-white/5">
        <Empty description={<Text className="text-slate-500">正在同步数据...</Text>} />
      </div>
    );
  }

  const sharedProps: WorkflowShared = {
    activePreset,
    schema,
    assets,
    secrets,
    isSystemPreset,
    updateStageConfig,
    updateStageParams,
    updateBusinessConfig,
  };

  const getAssetOptions = (stageKey: string) => {
    const isEmbedding = stageKey === 'embedding';
    const filtered = assets.filter(a => {
      if (disabledModelIds.includes(a.id)) return false;
      const isEmbedAsset = a.capabilities?.includes('embedding');
      return isEmbedding ? !!isEmbedAsset : !isEmbedAsset;
    });
    return filtered.map(a => ({
      label: (
        <div className="flex items-center justify-between w-full">
          <span className="font-medium text-xs">{a.display_name || a.model_name}</span>
          <Tag className="m-0 text-[9px] bg-blue-500/10 text-blue-400 border-none px-1 uppercase leading-none h-4">
            {a.provider_name}
          </Tag>
        </div>
      ),
      value: a.id,
    }));
  };

  const isDeepMode = activePreset.name === 'research_pipeline';
  const activeStageDef = STAGES.find(s => s.key === activePreset.name);

  return (
    <div className="animate-fade-in w-full h-full flex flex-col px-4 sm:px-6">
      
      {/* 紧凑型头部 */}
      <header className="flex items-center justify-between mb-6 pb-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-600/10 flex items-center justify-center border border-blue-500/20">
            <SettingOutlined className="text-blue-500" />
          </div>
          <Title level={4} className="!m-0 text-white font-black tracking-tight">研究工作流编排</Title>
        </div>
        <Button 
          type="primary" 
          icon={<SaveOutlined />} 
          loading={saveLoading}
          size="middle"
          className="bg-blue-600 hover:bg-blue-500 border-none h-9 px-6 font-bold text-xs rounded-xl"
          onClick={applyChanges}
        >
          应用并保存
        </Button>
      </header>

      <Row gutter={40} className="flex-1 min-h-0">
        {/* 左侧：模式选择 */}
        <Col span={6} className="h-full">
          <div className="space-y-2 sticky top-4">
            <Text className="text-[10px] font-black text-slate-500 uppercase tracking-widest block mb-4 ml-1">
              Select Research Tier
            </Text>
            {presets
              .filter(p => ['fast_react', 'expert_search', 'research_pipeline'].includes(p.name))
              .sort((a, b) => {
                const order = { 'fast_react': 0, 'expert_search': 1, 'research_pipeline': 2 };
                return (order[a.name as keyof typeof order] ?? 99) - (order[b.name as keyof typeof order] ?? 99);
              })
              .map(p => {
                const isSelected = p.id === activePresetId;
                return (
                  <div
                    key={p.id}
                    onClick={() => setActivePresetId(p.id)}
                    className={`group flex items-center justify-between p-3.5 rounded-xl cursor-pointer transition-all border ${
                      isSelected 
                        ? 'bg-blue-600/10 border-blue-500/30 ring-1 ring-blue-500/5 shadow-lg shadow-blue-500/5' 
                        : 'bg-white/[0.01] border-transparent hover:bg-white/[0.03] opacity-70 hover:opacity-100'
                    }`}
                  >
                    <div className="flex items-center gap-3 overflow-hidden">
                      <div className={`text-base transition-colors ${isSelected ? 'text-blue-400' : 'text-slate-500 group-hover:text-slate-300'}`}>
                        {STAGE_ICONS[p.name]}
                      </div>
                      <div className="overflow-hidden">
                        <div className={`text-xs font-bold truncate ${isSelected ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'}`}>
                          {MODE_NAME_MAP[p.name]}
                        </div>
                      </div>
                    </div>
                    {isSelected && <DoubleRightOutlined className="text-blue-500 text-[10px]" />}
                  </div>
                );
              })}
          </div>
        </Col>

        {/* 右侧：全显式分步配置 */}
        <Col span={18} className="h-full overflow-auto pr-2 custom-scrollbar">
          <div className="space-y-8">
            
            {/* 1. 模型编排区 */}
            <div className="bg-white/[0.01] rounded-2xl border border-white/[0.03] overflow-hidden">
              <div className="flex items-center gap-2.5 px-5 py-3 bg-white/[0.02] border-b border-white/[0.03]">
                <span className="text-blue-400 text-sm flex items-center"><SettingOutlined /></span>
                <span className="text-xs font-black text-slate-300 uppercase tracking-widest">Step 01. 核心模型编排 (Model Orchestration)</span>
              </div>
              
              <div className="divide-y divide-white/[0.01]">
                {!isDeepMode ? (
                  // Agent 模式：单阶段配置
                  <div className="p-2">
                    <ConfigRow label={`${MODE_NAME_MAP[activePreset.name]} 主模型`} description={activeStageDef?.recommendation}>
                      <Select
                        placeholder="绑定模型资产…"
                        className="min-w-[200px] max-w-[300px] custom-select-transparent-small"
                        size="small"
                        value={activePreset.nodes_config.stages[activePreset.name]?.asset_id || undefined}
                        onChange={(assetId: string | null) => updateStageConfig(activePreset.name, { asset_id: assetId })}
                        allowClear
                        options={getAssetOptions(activePreset.name)}
                      />
                    </ConfigRow>
                    <ConfigRow label="推理温度 (Temperature)" description="控制回答的创造性。0 为严谨，2 为极度发散。">
                      <div className="flex items-center gap-4 w-48">
                        <Slider
                          value={activePreset.nodes_config.stages[activePreset.name]?.temperature ?? 0.1}
                          min={0} max={2} step={0.1}
                          onChange={(v) => updateStageConfig(activePreset.name, { temperature: v })}
                          className="flex-1"
                        />
                        <span className="text-[10px] font-mono text-slate-400 w-8 text-right">{activePreset.nodes_config.stages[activePreset.name]?.temperature ?? 0.1}</span>
                      </div>
                    </ConfigRow>
                    <ConfigRow label="最大 Token 限制" description="单词回答允许消耗的最大 Token 数量。">
                      <InputNumber
                        size="small"
                        min={1024} max={2048000} step={1024}
                        className="bg-black/20 border-white/5 w-24 text-xs"
                        value={activePreset.nodes_config.stages[activePreset.name]?.max_tokens ?? 128000}
                        onChange={(v) => updateStageConfig(activePreset.name, { max_tokens: v })}
                      />
                    </ConfigRow>
                  </div>
                ) : (
                  // Pipeline 模式：全量阶段配置 (显式)
                  <div className="p-2">
                    {PIPELINE_SUB_STAGES.map(sub => {
                      const subCfg = activePreset.nodes_config.stages[sub.key] || { asset_id: null, temperature: 0.1, max_tokens: 128000, timeout: 60 };
                      return (
                        <div key={sub.key} className="border-b border-white/[0.02] last:border-none">
                          <ConfigRow label={sub.label} description={sub.description}>
                            <div className="flex items-center gap-4">
                                <Select
                                  placeholder="绑定模型资产…"
                                  className="min-w-[180px] max-w-[240px] custom-select-transparent-small"
                                  size="small"
                                  value={subCfg.asset_id || undefined}
                                  onChange={(val) => updateStageConfig(sub.key, { ...subCfg, asset_id: val })}
                                  options={getAssetOptions(sub.key)}
                                />
                                
                                <div className="flex items-center gap-2">
                                  {/* Temp */}
                                  <div className="flex items-center gap-1.5 bg-black/20 px-2 py-1 rounded-lg border border-white/5">
                                    <span className="text-[8px] text-slate-500 font-black uppercase">Temp</span>
                                    <InputNumber
                                      min={0} max={2} step={0.1} size="small"
                                      className="w-10 bg-transparent border-none text-[10px] h-4"
                                      value={subCfg.temperature ?? 0.1}
                                      onChange={(v) => updateStageConfig(sub.key, { ...subCfg, temperature: v })}
                                    />
                                  </div>
                                  {/* Tokens */}
                                  <div className="flex items-center gap-1.5 bg-black/20 px-2 py-1 rounded-lg border border-white/5">
                                    <span className="text-[8px] text-slate-500 font-black uppercase">MaxT</span>
                                    <InputNumber
                                      min={1024} max={2048000} step={1024} size="small"
                                      className="w-14 bg-transparent border-none text-[10px] h-4"
                                      value={subCfg.max_tokens ?? 128000}
                                      onChange={(v) => updateStageConfig(sub.key, { ...subCfg, max_tokens: v })}
                                    />
                                  </div>
                                  {/* Wait */}
                                  <div className="flex items-center gap-1.5 bg-black/20 px-2 py-1 rounded-lg border border-white/5">
                                    <span className="text-[8px] text-slate-500 font-black uppercase">Wait</span>
                                    <InputNumber
                                      min={5} max={600} step={5} size="small"
                                      className="w-10 bg-transparent border-none text-[10px] h-4"
                                      value={subCfg.timeout ?? 60}
                                      onChange={(v) => updateStageConfig(sub.key, { ...subCfg, timeout: v })}
                                    />
                                  </div>
                                </div>
                            </div>
                          </ConfigRow>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* 2. 搜索引擎与基建 */}
            <div className="bg-white/[0.01] rounded-2xl border border-white/[0.03] overflow-hidden">
              <div className="flex items-center gap-2.5 px-5 py-3 bg-white/[0.02] border-b border-white/[0.03]">
                <span className="text-emerald-400 text-sm flex items-center"><GlobalOutlined /></span>
                <span className="text-xs font-black text-slate-300 uppercase tracking-widest">Step 02. 搜索与向量基建</span>
              </div>
              <div className="divide-y divide-white/[0.01]">
                <ConfigRow label="搜索引擎集群" description="支持多选。系统将并发调用这些引擎以获取最全结果。">
                  <Select
                    mode="multiple"
                    placeholder="选择检索源…"
                    className="min-w-[240px] max-w-[400px] custom-select-transparent-small"
                    size="small"
                    value={activePreset.nodes_config.business?.engines || []}
                    onChange={(val) => updateBusinessConfig('engines', val)}
                    options={(schema?.enums?.search_engines as string[] | undefined)?.map(v => ({ label: v.toUpperCase(), value: v }))}
                  />
                </ConfigRow>

                {isDeepMode && (
                  <ConfigRow label="向量引擎 (Embedding)" description="用于文档去重、交叉验证。请务必绑定一个 Embedding 模型。">
                    <Select
                      placeholder="选择模型…"
                      className="min-w-[200px] max-w-[300px] custom-select-transparent-small"
                      size="small"
                      value={activePreset.nodes_config.stages['embedding']?.asset_id || undefined}
                      onChange={(assetId: string | null) => updateStageConfig('embedding', { asset_id: assetId })}
                      options={getAssetOptions('embedding')}
                    />
                  </ConfigRow>
                )}
              </div>
            </div>

            {/* 3. 微观参数 (EffectPanel) */}
            <div className="space-y-4">
               <div className="flex items-center gap-2 px-2">
                  <ExperimentOutlined className="text-amber-500" />
                  <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Step 03. 运行参数调优</span>
               </div>
               <EffectPanel {...sharedProps} />
            </div>

          </div>
        </Col>
      </Row>
    </div>
  );
}
