'use client';

import React from 'react';
import { Typography, Select, InputNumber, Input, Switch, Tag, Empty } from 'antd';
import { NODE_LABELS, PARAMETER_DESCRIPTIONS, ENUM_LABELS, STAGES, isAdvancedParam } from './constants';
import type { WorkflowShared } from './constants';
import type { ParamSchema, ModelAsset } from '@/types';

const { Text } = Typography;

interface StageInspectorProps extends WorkflowShared {
  stageKey: string;
}

/**
 * 阶段检查器 — 渲染模型绑定 + 该阶段各节点的参数
 */
export default function StageInspector({ stageKey, activePreset, schema, assets, isSystemPreset, updateStageConfig, updateStageParams }: StageInspectorProps) {
  const stageDef = STAGES.find(s => s.key === stageKey);
  if (!stageDef) return <Empty description="未知阶段" />;

  const stageConfig = activePreset.nodes_config?.stages?.[stageKey] || { asset_id: null, temperature: 0.1, params: {} };
  const isEmbedding = stageKey === 'embedding';

  // ── 模型绑定 ──
  const boundAsset = assets.find(a => a.id === stageConfig.asset_id);
  const assetOptions = getAssetOptionsForStage(stageKey, assets);

  const handleAssetChange = (assetId: string | null) => {
    updateStageConfig(stageKey, { asset_id: assetId });
  };

  // ── 节点参数 ──
  const nodeParams = schema?.node_params || {};
  const enums = schema?.enums || {};

  const getEnumOptions = (enumKey: string): string[] => {
    const val = enums[enumKey];
    return Array.isArray(val) ? val : [];
  };

  const renderNodeParam = (nodeType: string, paramKey: string, pSchema: ParamSchema) => {
    // Read nested params: stages[stageKey].params[nodeType][paramKey]
    const allParams = (stageConfig.params || {}) as Record<string, Record<string, unknown>>;
    const nodeParamsMap = allParams[nodeType] || {};
    const currentVal = nodeParamsMap[paramKey];

    const desc = PARAMETER_DESCRIPTIONS[paramKey] || '';
    const { type } = pSchema;

    const handleParamChange = (val: unknown) => {
      updateStageParams(stageKey, nodeType, { [paramKey]: val });
    };

    // bool
    if (type === 'bool') {
      const checked = currentVal !== undefined ? !!currentVal : !!pSchema.default;
      return (
        <div key={paramKey} className="flex items-center justify-between gap-4 py-2">
          <div className="flex-1 min-w-0">
            <Text className="text-xs font-bold text-slate-300">{paramKey}</Text>
            <p className="text-caption text-slate-500 leading-relaxed m-0 mt-0.5">{desc}</p>
          </div>
          <Switch size="small" checked={checked} disabled={false} onChange={handleParamChange} />
        </div>
      );
    }

    // enum (单选)
    if (pSchema.enum) {
      const options = getEnumOptions(pSchema.enum);
      const displayVal = currentVal !== undefined ? (currentVal as string) : (pSchema.default as string);
      return (
        <div key={paramKey} className="py-2">
          <div className="flex items-center justify-between mb-1">
            <Text className="text-xs font-bold text-slate-300">{paramKey}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-1.5">{desc}</p>
          <Select<string>
            size="small"
            value={displayVal}
            disabled={false}
            onChange={handleParamChange}
            className="w-full"
            options={options.map(v => ({ label: ENUM_LABELS[v] || v, value: v }))}
          />
        </div>
      );
    }

    // item_enum (多选枚举)
    if (pSchema.item_enum) {
      const options = getEnumOptions(pSchema.item_enum);
      const displayVal: string[] = Array.isArray(currentVal) ? currentVal as string[] : [];
      return (
        <div key={paramKey} className="py-2">
          <div className="flex items-center justify-between mb-1">
            <Text className="text-xs font-bold text-slate-300">{paramKey}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-1.5">{desc}</p>
          <Select
            mode="multiple"
            size="small"
            value={displayVal}
            disabled={false}
            onChange={handleParamChange}
            className="w-full"
            options={options.map(v => ({ label: ENUM_LABELS[v] || v, value: v }))}
          />
        </div>
      );
    }

    // int / float
    if (type === 'int' || type === 'float') {
      const displayVal = currentVal !== undefined ? (currentVal as number) : ((pSchema.default as number) ?? pSchema.min ?? 0);
      return (
        <div key={paramKey} className="py-2">
          <div className="flex items-center justify-between mb-1">
            <Text className="text-xs font-bold text-slate-300">{paramKey}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-1.5">{desc}</p>
          <InputNumber
            size="small"
            value={displayVal}
            disabled={false}
            min={pSchema.min}
            max={pSchema.max}
            step={type === 'float' ? 0.1 : 1}
            onChange={handleParamChange}
            className="w-full"
          />
        </div>
      );
    }

    // string
    if (type === 'string' || type === 'str') {
      const displayVal = currentVal !== undefined ? String(currentVal) : '';
      return (
        <div key={paramKey} className="py-2">
          <div className="flex items-center justify-between mb-1">
            <Text className="text-xs font-bold text-slate-300">{paramKey}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-1.5">{desc}</p>
          <Input
            size="small"
            value={displayVal}
            disabled={false}
            onChange={(e) => handleParamChange(e.target.value)}
          />
        </div>
      );
    }

    return null;
  };

  const renderNodeSection = (nodeType: string) => {
    const nodeSchema = nodeParams[nodeType];
    if (!nodeSchema || Object.keys(nodeSchema).length === 0) return null;

    // System preset: filter out advanced params
    const entries = isSystemPreset
      ? Object.entries(nodeSchema).filter(([paramKey]) => !isAdvancedParam(paramKey))
      : Object.entries(nodeSchema);

    if (entries.length === 0) return null;

    return (
      <div key={nodeType} className="mb-4">
        <div className="mb-2 pb-1.5 border-b border-white/5">
          <Text className="text-note font-bold text-slate-400 uppercase tracking-wider">{NODE_LABELS[nodeType] || nodeType}</Text>
        </div>
        {entries.map(([paramKey, pSchema]) =>
          renderNodeParam(nodeType, paramKey, pSchema)
        )}
      </div>
    );
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
      {/* ── 左列: 模型绑定区 ── */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <Text className="text-note text-slate-400 font-bold uppercase tracking-wider">
            {isEmbedding ? '嵌入模型绑定' : '执行模型绑定'}
          </Text>
          {!stageConfig.asset_id && (
            <Tag className="text-xs! border-rose-500/30! text-rose-400! bg-rose-500/10!">未绑定</Tag>
          )}
          {stageConfig.asset_id && boundAsset && (
            <Tag className="text-xs! border-emerald-500/30! text-emerald-400! bg-emerald-500/10!">已绑定</Tag>
          )}
        </div>

        <Select
          placeholder={`选择${isEmbedding ? '嵌入模型' : '大语言模型'}资产…`}
          className="w-full"
          value={stageConfig.asset_id || undefined}
          disabled={false}
          onChange={handleAssetChange}
          allowClear
          options={assetOptions}
        />
        {boundAsset && (
          <div className="mt-2 px-3 py-1.5 rounded-lg bg-white/2 border border-white/5">
            <div className="flex items-center gap-2 text-caption text-slate-500">
              <span>提供商:</span>
              <Tag className="text-xs! border-white/10! text-slate-300!">{boundAsset.provider_name}</Tag>
              <span>模型:</span>
              <span className="text-slate-400 font-mono">{boundAsset.model_name}</span>
            </div>
          </div>
        )}
      </div>

      {/* ── 右列: 节点参数区 ── */}
      {stageDef.nodes.length > 0 && (
        <div className="lg:border-l lg:border-white/5 lg:pl-6">
          <div className="mb-3 pb-2 border-b border-white/10">
            <Text className="text-note text-slate-400 font-bold uppercase tracking-wider">节点运行参数</Text>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6">
            {stageDef.nodes.map(renderNodeSection)}
          </div>
        </div>
      )}
    </div>
  );
}

/** 过滤资产选项 — embedding 阶段只显示嵌入模型，其他阶段只显示 LLM */
function getAssetOptionsForStage(stageKey: string, assets: ModelAsset[]) {
  const isEmbedding = stageKey === 'embedding';
  const filtered = assets.filter(a => {
    const isEmbedAsset = a.capabilities?.includes('embedding');
    return isEmbedding ? !!isEmbedAsset : !isEmbedAsset;
  });

  return filtered.map(a => ({
    label: (
      <div className="flex items-center justify-between w-full py-0.5">
        <span className="font-medium text-slate-200 text-xs">{a.display_name || a.model_name}</span>
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded px-1.5 py-0.5 uppercase">
            {a.provider_name}
          </span>
          {a.capabilities?.includes('embedding') && (
            <span className="text-xs font-bold bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded px-1.5 py-0.5 uppercase">
              EMBED
            </span>
          )}
        </div>
      </div>
    ),
    value: a.id,
  }));
}
