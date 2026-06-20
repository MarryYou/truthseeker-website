'use client';

import React, { useState, useMemo } from 'react';
import { Typography, Input, Button, Tag, Empty, App, AutoComplete, Segmented, Popconfirm, Divider, Row, Col, Switch } from 'antd';
import { 
  ThunderboltOutlined, 
  GlobalOutlined, 
  CheckCircleFilled, 
  LinkOutlined,
  SaveOutlined,
  DatabaseOutlined,
  PlusOutlined,
  SettingOutlined,
  CloudDownloadOutlined,
  DeleteOutlined,
  DownOutlined,
  UpOutlined,
  ApiOutlined,
  ControlOutlined,
  CloseCircleFilled,
} from '@ant-design/icons';
import { useSettingsStore } from '@/store/useSettingsStore';
import { fetchRemoteModels } from '@/services/settings';
import type { UserSecret, ModelAsset } from '@/types';

const { Title, Text, Paragraph } = Typography;

const PROVIDER_DESCRIPTIONS: Record<string, string> = {
  "openai": "全球领先的 AI 研究机构，提供 GPT 系列模型。",
  "deepseek": "高性价比国产模型，推理能力极其出色。",
  "dashscope": "阿里通义千问，中文理解与长文本优势显著。",
  "anthropic": "Claude 模型，文笔优雅且指令遵循极强。",
  "bocha": "国产结构化搜索引擎，提供精准中文摘要。",
  "tavily": "AI 代理优化引擎，过滤干扰，数据质量高。",
  "zhihu": "高质量问答社区，获取深度专业见解。",
};

/** 
 * 单行配置项组件 (外层服务商 & 内层资产通用)
 */
const FlatRow = ({ icon, label, labelExtra, children, subLabel, className }: { icon?: React.ReactNode, label: string; labelExtra?: React.ReactNode; children: React.ReactNode; subLabel?: string, className?: string }) => (
  <div className={`flex items-center justify-between py-4 px-6 transition-all hover:bg-white/[0.01] border-b border-white/[0.02] last:border-none ${className}`}>
    <div className="flex-1 pr-8 min-w-0">
      <div className="flex items-center gap-2.5 mb-0.5">
        {icon && <span className="text-slate-500 flex items-center">{icon}</span>}
        <span className="text-sm font-black text-slate-100 uppercase tracking-tight truncate">{label}</span>
        {labelExtra}
      </div>
      {subLabel && <div className="text-[11px] text-slate-500 leading-relaxed truncate max-w-2xl">{subLabel}</div>}
    </div>
    <div className="flex-shrink-0 flex justify-end">
      {children}
    </div>
  </div>
);

export default function ConnectionsPanel() {
  const { message } = App.useApp();
  const { 
    secrets, 
    updateLocalSecret, 
    testConnection, 
    saveLoading, 
    applyChanges,
    assets,
    disabledModelIds,
    toggleModelActive
  } = useSettingsStore();

  const [testingMap, setTestingMap] = useState<Record<string, boolean>>({});
  const [testingAll, setTestingAll] = useState(false);
  const [latencyMap, setLatencyMap] = useState<Record<string, number>>({});
  const [errorMap, setPingErrorMap] = useState<Record<string, string>>({});
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({});

  const [newModelName, setNewModelName] = useState('');
  const [newModelType, setNewModelType] = useState<'llm' | 'embedding'>('llm');
  const [activeProviderName, setActiveProviderName] = useState<string | null>(null);
  const [fetchingMap, setFetchingMap] = useState<Record<string, boolean>>({});
  const [remoteModelsMap, setRemoteModelsMap] = useState<Record<string, string[]>>({});

  const llmProviders = useMemo(() => secrets.filter(s => s.category === 'llm'), [secrets]);
  const searchProviders = useMemo(() => secrets.filter(s => s.category === 'search'), [secrets]);

  const toggleExpand = (name: string) => {
    setExpandedProviders(prev => ({ ...prev, [name]: !prev[name] }));
  };

  const handleTestAll = async () => {
    const configuredSecrets = secrets.filter(s => s.is_configured || (s as any).plain_key);
    if (configuredSecrets.length === 0) {
      message.info("暂无可测试的已配置服务商");
      return;
    }
    
    setTestingAll(true);
    message.open({ type: 'loading', content: '正在并发检测所有连接通道...', key: 'test-all', duration: 0 });
    
    let successCount = 0;
    let failCount = 0;
    
    await Promise.all(configuredSecrets.map(async (p) => {
      const name = p.provider_name;
      setTestingMap(prev => ({ ...prev, [name]: true }));
      setPingErrorMap(prev => ({ ...prev, [name]: '' }));
      
      const result = await testConnection(name);
      
      setTestingMap(prev => ({ ...prev, [name]: false }));
      if (result.success) {
        successCount++;
        setLatencyMap(prev => ({ ...prev, [name]: result.latency || 0 }));
      } else {
        failCount++;
        setPingErrorMap(prev => ({ ...prev, [name]: result.error || '测试失败' }));
      }
    }));
    
    setTestingAll(false);
    message.open({
      type: failCount === 0 ? 'success' : 'warning',
      content: `检测完成：${successCount} 个成功${failCount > 0 ? `，${failCount} 个失败` : ''}`,
      key: 'test-all',
      duration: 3
    });
  };

  const handleTest = async (name: string) => {
    setTestingMap(prev => ({ ...prev, [name]: true }));
    const result = await testConnection(name);
    setTestingMap(prev => ({ ...prev, [name]: false }));
    if (result.success) {
      setLatencyMap(prev => ({ ...prev, [name]: result.latency || 0 }));
      message.success(`${name.toUpperCase()} 连接成功`);
    } else {
      setPingErrorMap(prev => ({ ...prev, [name]: result.error || '测试失败' }));
      message.error(`${name.toUpperCase()} 连接失败`);
    }
  };

  const handleFetchModels = async (providerName: string) => {
    setFetchingMap(prev => ({ ...prev, [providerName]: true }));
    try {
      const secret = secrets.find(s => s.provider_name === providerName);
      const models = await fetchRemoteModels(providerName, {
        plain_key: (secret as any)?.plain_key,
        base_url: secret?.base_url
      });
      setRemoteModelsMap(prev => ({ ...prev, [providerName]: models }));
      message.success(`已拉取云端模型列表`);
    } catch (err: any) {
      message.error("无法获取模型列表");
    } finally {
      setFetchingMap(prev => ({ ...prev, [providerName]: false }));
    }
  };

  const handleAddAsset = (providerName: string) => {
    const trimmed = newModelName.trim();
    if (!trimmed) return;
    if (assets.find(a => a.provider_name === providerName && a.model_name === trimmed)) return;
    useSettingsStore.setState({ 
      assets: [...assets, {
        id: crypto.randomUUID(),
        provider_name: providerName,
        model_name: trimmed,
        display_name: trimmed,
        capabilities: [newModelType],
        is_system_default: false
      }] 
    });
    setNewModelName('');
  };

  const handleRemoveAsset = (assetId: string) => {
    useSettingsStore.setState({ assets: assets.filter(a => a.id !== assetId) });
  };

  const renderProviderPanel = (p: UserSecret) => {
    const isTesting = testingMap[p.provider_name];
    const latency = latencyMap[p.provider_name];
    const pingError = errorMap[p.provider_name];
    const isExpanded = expandedProviders[p.provider_name];
    const hasValue = p.is_configured || (p as any).plain_key;
    const providerAssets = assets.filter(a => a.provider_name === p.provider_name);

    return (
      <div key={p.provider_name} className="bg-white/[0.01] border border-white/[0.03] rounded-3xl overflow-hidden transition-all duration-300">
        {/* 外层：服务商核心配置 */}
        <div className="flex items-center gap-6 px-8 py-5">
           <div className="flex items-center gap-4 min-w-[140px]">
              <div className={`w-9 h-9 rounded-2xl flex items-center justify-center border shrink-0 ${hasValue ? 'bg-blue-600/10 border-blue-500/20 text-blue-400' : 'bg-white/5 border-white/5 text-slate-700'}`}>
                {p.category === 'llm' ? <ThunderboltOutlined /> : <GlobalOutlined />}
              </div>
              <span className="text-sm font-black text-slate-100 uppercase tracking-tighter">{p.provider_name}</span>
           </div>

           <div className="flex-1 flex items-center gap-4">
              <Input.Password
                size="small"
                value={(p as any).plain_key}
                placeholder={p.is_configured ? '••••••••••••••••' : 'API Key'}
                className="bg-black/40 border-white/5 hover:border-blue-500/50 focus:border-blue-500/50 rounded-xl h-9 text-xs px-4"
                onChange={(e) => updateLocalSecret(p.provider_name, { plain_key: e.target.value })}
              />
              <Input
                size="small"
                value={p.base_url}
                placeholder="Base URL (Optional)"
                className="bg-black/40 border-white/5 hover:border-blue-500/50 focus:border-blue-500/50 rounded-xl h-9 text-xs px-4 font-mono w-1/3"
                onChange={(e) => updateLocalSecret(p.provider_name, { base_url: e.target.value })}
              />
           </div>

           <div className="flex items-center gap-3 pl-4 border-l border-white/[0.03]">
              {latency !== undefined && <span className="text-xs font-mono text-emerald-500 font-bold">{latency}ms</span>}
              <Button 
                size="small"
                loading={isTesting}
                className={`h-9 rounded-xl font-black text-[10px] border-none px-5 transition-all ${latency !== undefined ? 'bg-emerald-500/10 text-emerald-400' : 'bg-white/5 text-slate-500 hover:text-white'}`}
                onClick={() => handleTest(p.provider_name)}
              >
                PING
              </Button>
              
              {p.category === 'llm' && hasValue && (
                <Button 
                  size="small"
                  icon={isExpanded ? <UpOutlined /> : <SettingOutlined />}
                  className={`h-9 rounded-xl font-black text-[10px] border-none px-4 flex items-center gap-2 ${isExpanded ? 'bg-blue-600 text-white' : 'bg-white/5 text-slate-400 hover:text-blue-400 hover:bg-blue-500/10'}`}
                  onClick={() => toggleExpand(p.provider_name)}
                >
                  {isExpanded ? '关闭配置' : '模型配置'}
                </Button>
              )}
           </div>
        </div>

        {/* 内层：资产深度管理 */}
        {isExpanded && (
          <div className="bg-white/[0.005] border-t border-white/[0.02] animate-in fade-in slide-in-from-top-2 duration-300">
             
             {/* 1. 资产注册中心 (Asset Registrar) */}
             <div className="px-8 py-8 border-b border-white/[0.02] bg-blue-600/[0.01]">
                <div className="max-w-4xl mx-auto space-y-5">
                   <div className="flex items-center justify-between px-1">
                      <div className="flex items-center gap-2.5">
                         <div className="w-1 h-3.5 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.6)]" />
                         <span className="text-xs font-black text-slate-200 uppercase tracking-widest">注册新资产 (Add New Asset)</span>
                      </div>
                      <Button 
                        size="small" type="text" 
                        loading={fetchingMap[p.provider_name]}
                        icon={<CloudDownloadOutlined />}
                        className="text-blue-500/50 hover:text-blue-400 font-bold text-[10px] uppercase"
                        onClick={() => handleFetchModels(p.provider_name)}
                      >
                        Sync Cloud List
                      </Button>
                   </div>

                   <div className="flex items-center gap-4 bg-black/40 p-2 pr-3 rounded-2xl border border-white/5 focus-within:border-blue-500/50 transition-all shadow-xl">
                      <AutoComplete
                        className="flex-1"
                        options={(remoteModelsMap[p.provider_name] || []).map(m => ({ value: m, label: <span className="text-slate-300 text-xs font-mono">{m}</span> }))}
                        value={activeProviderName === p.provider_name ? newModelName : ''}
                        onChange={val => { setActiveProviderName(p.provider_name); setNewModelName(val); }}
                        onSelect={val => { setActiveProviderName(p.provider_name); setNewModelName(val); }}
                      >
                        <Input 
                          placeholder="输入模型 ID (如: gpt-4o, deepseek-v3)..." 
                          className="bg-transparent border-none text-xs text-slate-100 h-9 px-4 focus:ring-0" 
                          onPressEnter={() => handleAddAsset(p.provider_name)} 
                        />
                      </AutoComplete>
                      <div className="h-8 w-[1px] bg-white/5" />
                      <Segmented
                        size="small"
                        value={activeProviderName === p.provider_name ? newModelType : 'llm'}
                        onChange={val => { setActiveProviderName(p.provider_name); setNewModelType(val as any); }}
                        options={[{ label: 'LLM', value: 'llm' }, { label: 'Embed', value: 'embedding' }]}
                        className="bg-transparent custom-segmented-micro"
                      />
                      <Button 
                        size="middle" 
                        type="primary" 
                        icon={<PlusOutlined />} 
                        className="rounded-xl bg-blue-600 hover:bg-blue-500 border-none h-9 px-8 font-black text-[11px] shadow-lg shadow-blue-900/10" 
                        onClick={() => handleAddAsset(p.provider_name)}
                      >
                        ADD ASSET
                      </Button>
                   </div>
                </div>
             </div>

             {/* 2. 已注册资产列表 (Existing Assets) */}
             <div className="px-8 py-3 bg-white/[0.01] border-b border-white/[0.02] flex items-center justify-between">
                <div className="flex items-center gap-3">
                   <span className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">Registered Models</span>
                   <Tag className="m-0 border-none bg-blue-500/10 text-blue-400 text-[9px] font-bold uppercase">{providerAssets.length} Total</Tag>
                </div>
             </div>

             <div className="divide-y divide-white/[0.01]">
                {providerAssets.map(asset => {
                  const isDisabled = disabledModelIds.includes(asset.id);
                  const isEmbed = asset.capabilities?.includes('embedding');
                  return (
                    <FlatRow
                      key={asset.id}
                      label={asset.model_name}
                      labelExtra={
                        <Tag className={`m-0 border-none px-1.5 py-0 text-[8px] font-black uppercase rounded-sm ${isEmbed ? 'bg-purple-500/10 text-purple-400' : 'bg-blue-500/10 text-blue-400'}`}>
                          {isEmbed ? 'Embedding' : 'Inference'}
                        </Tag>
                      }
                      icon={<div className={`w-1.5 h-1.5 rounded-full ${isDisabled ? 'bg-slate-700' : isEmbed ? 'bg-purple-400 shadow-[0_0_8px_rgba(168,85,247,0.8)]' : 'bg-blue-400 shadow-[0_0_8px_rgba(59,130,246,0.8)]'}`} />}
                      subLabel={isEmbed ? "用于文本向量化、去重和相似度计算。" : "用于逻辑推理、对话生成和研报撰写。"}
                      className={isDisabled ? 'opacity-30 grayscale' : ''}
                    >
                      <div className="flex items-center gap-4">
                        <Switch 
                          size="small" 
                          checked={!isDisabled} 
                          onChange={() => toggleModelActive(asset.id)}
                          className="scale-90"
                        />
                        <Popconfirm title="确定注销此资产？" onConfirm={() => handleRemoveAsset(asset.id)} okText="确定" cancelText="取消">
                          <Button size="small" type="text" icon={<DeleteOutlined className="text-xs" />} className="text-slate-600 hover:text-rose-500" />
                        </Popconfirm>
                      </div>
                    </FlatRow>
                  );
                })}
                {providerAssets.length === 0 && (
                   <div className="py-12 flex flex-col items-center justify-center opacity-30">
                      <DatabaseOutlined className="text-3xl mb-3" />
                      <span className="text-xs uppercase font-bold tracking-widest">No assets found</span>
                   </div>
                )}
             </div>
          </div>
        )}
        
        {pingError && (
          <div className="px-8 py-3 bg-rose-500/5 border-t border-rose-500/10 text-xs text-rose-400 flex items-center gap-2">
            <CloseCircleFilled /> {pingError}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="animate-fade-in w-full h-full flex flex-col px-4 sm:px-6">
      <header className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-600/10 flex items-center justify-center border border-blue-500/20 text-lg">
            <ApiOutlined className="text-blue-500" />
          </div>
          <div>
            <Title level={4} className="!m-0 text-white font-black tracking-tight uppercase">模型与服务连接</Title>
            <Paragraph className="text-slate-500 text-xs m-0 mt-0.5">
              统一管理服务商凭证与模型资产。
            </Paragraph>
          </div>
        </div>
        <div className="flex gap-4">
          <Button loading={testingAll} icon={<ThunderboltOutlined />} className="h-10 rounded-xl bg-white/5 text-slate-400 font-bold text-xs border-none hover:bg-white/10" onClick={handleTestAll}>全量检测</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saveLoading} className="h-10 rounded-xl bg-blue-600 hover:bg-blue-500 border-none font-bold text-xs px-8 shadow-xl shadow-blue-900/20" onClick={applyChanges}>保存更改</Button>
        </div>
      </header>

      <div className="space-y-6 pb-40">
        <div className="space-y-4">
           <Text className="text-xs font-black text-slate-500 uppercase tracking-[0.25em] ml-2">Language Model Gateways</Text>
           {llmProviders.map(renderProviderPanel)}
        </div>
        <div className="space-y-4 pt-10">
           <Text className="text-xs font-black text-slate-500 uppercase tracking-[0.25em] ml-2">Search Engine Plugins</Text>
           {searchProviders.map(renderProviderPanel)}
        </div>
      </div>
    </div>
  );
}
