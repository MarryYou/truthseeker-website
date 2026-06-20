'use client';

import React from 'react';
import { Typography, Select, InputNumber, Input } from 'antd';
import { PARAMETER_DESCRIPTIONS, ENUM_LABELS, isAdvancedParam } from './constants';
import type { WorkflowShared } from './constants';
import type { ParamSchema } from '@/types';

const { Text } = Typography;

interface GlobalParamsPanelProps extends WorkflowShared {}

/**
 * 全局业务参数面板 — 渲染 preset_params (business 层) 中定义的所有字段
 */
export default function GlobalParamsPanel({ activePreset, schema, isSystemPreset, updateBusinessConfig }: GlobalParamsPanelProps) {
  const bizConfig = activePreset.nodes_config.business || {};
  const bizSchema = schema?.preset_params || {};
  const enums = schema?.enums || {};

  /** 获取枚举选项列表 */
  const getEnumOptions = (enumKey: string): string[] => {
    const val = enums[enumKey];
    return Array.isArray(val) ? val : [];
  };

  /** 渲染单个业务参数 */
  const renderParam = (key: string) => {
    const pSchema = bizSchema[key];
    if (!pSchema) return null;

    const desc = PARAMETER_DESCRIPTIONS[key] || '';
    const val = bizConfig[key];
    const { type } = pSchema;

    // ── bool 类型 ──
    if (type === 'bool') {
      const checked =(val !== undefined ? !!val : !!pSchema.default);
      return (
        <div key={key} className="flex items-center justify-between gap-6 py-2">
          <div className="flex-1 min-w-0">
            <Text className="text-xs font-bold text-slate-300">{key}</Text>
            <p className="text-caption text-slate-500 leading-relaxed m-0 mt-0.5">{desc}</p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer shrink-0">
            <input
              type="checkbox"
              checked={checked}
              disabled={false}
              onChange={(e) => updateBusinessConfig(key, e.target.checked)}
              className="sr-only peer disabled:cursor-not-allowed"
            />
            <div className={`w-9 h-5 rounded-full peer-checked:bg-blue-500 transition-colors ${checked ? 'bg-blue-500' : 'bg-white/10'}`} />
            <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4" />
          </label>
        </div>
      );
    }

    // ── enum 类型 (单选) ──
    if ('enum' in pSchema && pSchema.enum) {
      const options = (enums[pSchema.enum] as string[]) || [];
      const displayVal = val !== undefined ? val : pSchema.default;
      return (
        <div key={key} className="py-2">
          <div className="flex items-center justify-between mb-1.5">
            <Text className="text-xs font-bold text-slate-300">{key}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-2">{desc}</p>
          <Select
            size="small"
            value={displayVal}
            disabled={false}
            onChange={(v) => updateBusinessConfig(key, v)}
            className="w-full"
            options={options.map(v => ({ label: ENUM_LABELS[v] || v, value: v }))}
          />
        </div>
      );
    }

    // ── list + item_enum 类型 (多选) ──
    if ('item_enum' in pSchema && pSchema.item_enum) {
      const options = (enums[pSchema.item_enum] as string[]) || [];
      const displayVal: string[] = Array.isArray(val) ? val : (Array.isArray(pSchema.default) ? pSchema.default : []);
      return (
        <div key={key} className="py-2">
          <div className="flex items-center justify-between mb-1.5">
            <Text className="text-xs font-bold text-slate-300">{key}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-2">{desc}</p>
          <Select
            mode="multiple"
            size="small"
            value={displayVal}
            disabled={false}
            onChange={(v) => updateBusinessConfig(key, v)}
            className="w-full"
            options={options.map(v => ({ label: ENUM_LABELS[v] || v, value: v }))}
          />
        </div>
      );
    }

    // ── list + item_type=str (文本数组, 如 report_sections) ──
    if ('item_type' in pSchema && pSchema.item_type === 'str') {
      const displayVal: string[] = Array.isArray(val) ? val : [];
      return (
        <div key={key} className="py-2">
          <div className="flex items-center justify-between mb-1.5">
            <Text className="text-xs font-bold text-slate-300">{key}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-2">{desc}</p>
          <Select
            mode="tags"
            size="small"
            value={displayVal}
            disabled={false}
            onChange={(v) => updateBusinessConfig(key, v)}
            className="w-full"
            placeholder="输入并按回车添加"
          />
        </div>
      );
    }

    // ── int / float 类型 ──
    if (type === 'int' || type === 'float') {
      const displayVal = val !== undefined ? (val as number) : ((pSchema.default as number) ?? pSchema.min ?? 0);
      return (
        <div key={key} className="py-2">
          <div className="flex items-center justify-between mb-1.5">
            <Text className="text-xs font-bold text-slate-300">{key}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-2">{desc}</p>
          <InputNumber
            size="small"
            value={displayVal}
            disabled={false}
            min={pSchema.min}
            max={pSchema.max}
            step={type === 'float' ? 0.1 : 1}
            onChange={(v) => updateBusinessConfig(key, v)}
            className="w-full"
          />
        </div>
      );
    }

    // ── string 类型 ──
    if (type === 'string' || type === 'str') {
      const displayVal = val !== undefined ? String(val) : '';
      return (
        <div key={key} className="py-2">
          <div className="flex items-center justify-between mb-1.5">
            <Text className="text-xs font-bold text-slate-300">{key}</Text>
          </div>
          <p className="text-caption text-slate-500 leading-relaxed m-0 mb-2">{desc}</p>
          <Input
            size="small"
            value={displayVal}
            disabled={false}
            onChange={(e) => updateBusinessConfig(key, e.target.value)}
          />
        </div>
      );
    }

    return null;
  };

  const allParamKeys = Object.keys(bizSchema);
  const paramKeys = isSystemPreset ? allParamKeys.filter(k => !isAdvancedParam(k)) : allParamKeys;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1">
      {paramKeys.map(renderParam)}
    </div>
  );
}
