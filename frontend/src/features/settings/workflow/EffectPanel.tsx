'use client';

import React from 'react';
import { Typography, Select, Input, Slider, Switch, Tag, InputNumber } from 'antd';
import {
  CompassOutlined,
  SearchOutlined,
  SafetyCertificateOutlined,
  FileTextOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { PARAMETER_DESCRIPTIONS, ENUM_LABELS, GOAL_GROUPS, STAGES, PIPELINE_SUB_STAGES, isAdvancedParam, isParamVisible } from './constants';
import type { GoalGroupDef, ParamRef, WorkflowShared } from './constants';
import type { ParamSchema } from '@/types';

const { Text } = Typography;

const ICON_MAP: Record<string, React.ReactNode> = {
  CompassOutlined: <CompassOutlined />,
  SearchOutlined: <SearchOutlined />,
  SafetyCertificateOutlined: <SafetyCertificateOutlined />,
  FileTextOutlined: <FileTextOutlined />,
  ToolOutlined: <ToolOutlined />,
};

const COLOR_MAP: Record<string, { text: string; bg: string }> = {
  blue:    { text: 'text-blue-400', bg: 'bg-blue-400/10' },
  amber:   { text: 'text-amber-400', bg: 'bg-amber-400/10' },
  emerald: { text: 'text-emerald-400', bg: 'bg-emerald-400/10' },
  indigo:  { text: 'text-indigo-400', bg: 'bg-indigo-400/10' },
  slate:   { text: 'text-slate-400', bg: 'bg-slate-400/10' },
};

/** 
 * 单行配置项组件 (NextChat 风格) 
 */
const ConfigRow = ({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) => (
  <div className="group flex items-center justify-between py-3.5 px-5 transition-colors hover:bg-white/[0.015] border-b border-white/[0.02] last:border-none">
    <div className="flex-1 pr-12">
      <div className="text-sm font-bold text-slate-200 tracking-tight">{label}</div>
      {description && <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">{description}</div>}
    </div>
    <div className="flex-shrink-0 flex justify-end">
      {children}
    </div>
  </div>
);

interface EffectPanelProps extends WorkflowShared {}

export default function EffectPanel({ activePreset, schema, isSystemPreset, updateBusinessConfig, updateStageParams }: EffectPanelProps) {
  const bizConfig = activePreset.nodes_config?.business || {};
  const stagesConfig = activePreset.nodes_config?.stages || {};
  const bizSchema = schema?.preset_params || {};
  const nodeParamsSchema = schema?.node_params || {};
  const enums = schema?.enums || {};

  const getParamValue = (ref: ParamRef): unknown => {
    if (ref.source === 'business') return bizConfig[ref.key];
    for (const stageConfig of Object.values(stagesConfig)) {
      const sc = stageConfig as any;
      const nodeMap = sc?.params?.[ref.nodeType!];
      if (nodeMap && ref.key in nodeMap) return nodeMap[ref.key];
    }
    return undefined;
  };

  const getParamSchema = (ref: ParamRef): ParamSchema | undefined => {
    if (ref.source === 'business') return bizSchema[ref.key] as ParamSchema | undefined;
    return nodeParamsSchema[ref.nodeType!]?.[ref.key] as ParamSchema | undefined;
  };

  const handleParamChange = (ref: ParamRef, val: unknown) => {
    if (ref.source === 'business') {
      updateBusinessConfig(ref.key, val);
      return;
    }
    
    // 💡 核心修复：优先寻找精细化的 Pipeline 子阶段，确保参数落到正确的 Stage 内部
    let stage = PIPELINE_SUB_STAGES.find(s => s.nodes.includes(ref.nodeType!));
    
    // 如果子阶段没找到（说明是 Agent 专属节点），再回退到顶级模式阶段寻找
    if (!stage) {
      stage = STAGES.find(s => s.nodes.includes(ref.nodeType!));
    }

    if (stage) {
      updateStageParams(stage.key, ref.nodeType!, { [ref.key]: val });
    }
  };

  const getEnumOptions = (enumKey: string): string[] => {
    const val = enums[enumKey];
    return Array.isArray(val) ? val : [];
  };

  const renderParam = (ref: ParamRef) => {
    const pSchema = getParamSchema(ref);
    if (!pSchema) return null;
    if (isSystemPreset && isAdvancedParam(ref.key)) return null;

    const desc = PARAMETER_DESCRIPTIONS[ref.key] || '';
    const val = getParamValue(ref);
    const displayKey = ref.key;
    const { type } = pSchema;
    const onChange = (v: unknown) => handleParamChange(ref, v);

    // ── bool ──
    if (type === 'bool') {
      return (
        <ConfigRow key={ref.key} label={ref.key} description={desc}>
          <Switch 
            size="small" 
            checked={val !== undefined ? !!val : !!pSchema.default} 
            onChange={onChange}
            className="opacity-80 hover:opacity-100"
          />
        </ConfigRow>
      );
    }

    // ── enum / item_enum ──
    if (('enum' in pSchema && pSchema.enum) || ('item_enum' in pSchema && pSchema.item_enum)) {
      const isMulti = 'item_enum' in pSchema;
      const options = getEnumOptions((isMulti ? pSchema.item_enum : pSchema.enum) as string);
      return (
        <ConfigRow key={ref.key} label={ref.key} description={desc}>
          <Select
            size="small"
            mode={isMulti ? 'multiple' : undefined}
            value={val !== undefined ? val : pSchema.default}
            onChange={onChange}
            className="min-w-[160px] max-w-[280px] custom-select-transparent-small"
            options={options.map(v => ({ label: ENUM_LABELS[v] || v, value: v }))}
          />
        </ConfigRow>
      );
    }

    // ── int / float ──
    if (type === 'int' || type === 'float') {
      const displayVal = val !== undefined ? (val as number) : ((pSchema.default as number) ?? 0);
      return (
        <ConfigRow key={ref.key} label={ref.key} description={desc}>
          <div className="flex items-center gap-5 w-56">
            <Slider
              value={displayVal}
              min={pSchema.min}
              max={pSchema.max}
              step={type === 'float' ? 0.1 : 1}
              onChange={onChange}
              className="flex-1"
            />
            <span className="text-[11px] font-mono text-slate-400 w-8 text-right font-bold">{displayVal}</span>
          </div>
        </ConfigRow>
      );
    }

    // ── dict (Range) ──
    if (type === 'dict' || (val && typeof val === 'object' && 'min' in (val as any))) {
      const range = (val as { min: number; max: number }) || { min: pSchema.min || 1, max: pSchema.max || 10 };
      return (
        <ConfigRow key={ref.key} label={ref.key} description={desc}>
          <div className="flex items-center gap-5 w-72">
            <Slider
              range
              value={[range.min, range.max]}
              min={pSchema.min || 1}
              max={pSchema.max || 20}
              step={1}
              onChange={(vals) => onChange({ min: vals[0], max: vals[1] })}
              className="flex-1"
            />
            <span className="text-[11px] font-mono text-blue-400 font-bold w-14 text-right">
              {range.min}-{range.max}
            </span>
          </div>
        </ConfigRow>
      );
    }

    // ── string ──
    if (type === 'string' || type === 'str') {
      return (
        <ConfigRow key={ref.key} label={ref.key} description={desc}>
          <Input
            size="small"
            value={val !== undefined ? String(val) : ''}
            className="bg-black/20 border-white/5 hover:border-blue-500/50 focus:border-blue-500/50 text-xs text-slate-300 w-56 h-8"
            onChange={(e) => onChange(e.target.value)}
          />
        </ConfigRow>
      );
    }

    return null;
  };

  const currentMode = activePreset.name;

  return (
    <div className="space-y-12">
      {GOAL_GROUPS.map((group) => {
        const colors = COLOR_MAP[group.color] || COLOR_MAP.slate;
        const visibleParams = group.params.filter(p => {
          // 暂时移除高级参数过滤，让所有对当前模式有意义的参数都可见
          return isParamVisible(p.key, currentMode);
        });

        if (visibleParams.length === 0) return null;

        return (
          <div key={group.key} className="bg-white/[0.01] rounded-2xl border border-white/[0.03] overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-3.5 bg-white/[0.02] border-b border-white/[0.03]">
              <span className={`${colors.text} text-base flex items-center`}>{ICON_MAP[group.icon]}</span>
              <span className="text-[13px] font-black text-slate-200 uppercase tracking-widest">{group.label}</span>
              <span className="text-[11px] text-slate-600 font-medium ml-auto uppercase tracking-tighter">{group.description}</span>
            </div>
            <div className="divide-y divide-white/[0.01]">
              {visibleParams.map(renderParam)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
