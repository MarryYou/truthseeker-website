import React, { useState, useEffect } from 'react';
import { Button, Checkbox, Input, Tag, Typography, Card } from 'antd';
import { 
  CheckCircleOutlined, 
  PlusOutlined,
  GlobalOutlined,
  BlockOutlined,
  CloseCircleFilled
} from '@ant-design/icons';
import { useResearchStore } from '@/store/useResearchStore';
import { useResearchStream } from '@/hooks/useResearchStream';

const { Text } = Typography;

export const BreakpointHandler: React.FC = () => {
  const { pendingBreakpoint, activeResearchId } = useResearchStore();
  const { startResearch } = useResearchStream();

  const [approvedDimensions, setApprovedDimensions] = useState<string[]>([]);
  const [newDimension, setNewDimension] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const [approvedSources, setApprovedSources] = useState<string[]>([]);

  // 同步内部状态与 Store 中的断点载荷
  useEffect(() => {
    if (pendingBreakpoint?.type === 'dimensions') {
      setApprovedDimensions(pendingBreakpoint.payload || []);
    } else if (pendingBreakpoint?.type === 'sources') {
      const initialSources = (pendingBreakpoint.payload as any[] || []).map(s => s.url);
      setApprovedSources(initialSources);
    }
  }, [pendingBreakpoint]);

  if (!pendingBreakpoint) return null;

  const handleResume = () => {
    if (!activeResearchId) return;

    if (pendingBreakpoint.type === 'dimensions') {
      startResearch('', {
        researchId: activeResearchId,
        resumeData: { approved_dimensions: approvedDimensions }
      });
    } else if (pendingBreakpoint.type === 'sources') {
      startResearch('', {
        researchId: activeResearchId,
        resumeData: { approved_sources: approvedSources }
      });
    }
  };

  const handleAddDimension = () => {
    if (newDimension.trim()) {
      setApprovedDimensions([...approvedDimensions, newDimension.trim()]);
      setNewDimension('');
      setIsAdding(false);
    } else {
      setIsAdding(false);
    }
  };

  return (
    <div className="mb-8 animate-fade-in sm:pl-11">
      <Card 
        className="bg-[#14161f]/90 border-blue-500/30 shadow-2xl shadow-blue-900/10 rounded-2xl overflow-hidden"
        styles={{ body: { padding: '24px' } }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-400 text-lg">
            {pendingBreakpoint.type === 'dimensions' ? <BlockOutlined /> : <GlobalOutlined />}
          </div>
          <div className="flex flex-col">
            <Text className="text-slate-100 font-bold text-lg leading-tight">
              {pendingBreakpoint.type === 'dimensions' ? '确认研究维度' : '挑选参考信源'}
            </Text>
            <Text className="text-slate-500 text-sm mt-1">
              {pendingBreakpoint.type === 'dimensions' 
                ? 'AI 已规划以下维度，您可以增删改以引导后续研究' 
                : '请勾选您认为最相关的信源进行深度解析'}
            </Text>
          </div>
        </div>

        {pendingBreakpoint.type === 'dimensions' && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2.5">
              {approvedDimensions.map((dim, idx) => (
                <Tag 
                  key={idx} 
                  closable 
                  onClose={() => setApprovedDimensions(approvedDimensions.filter((_, i) => i !== idx))}
                  className="bg-white/5 border-white/10 text-slate-300 px-3.5 py-1.5 rounded-xl text-sm m-0 hover:border-blue-500/50 transition-colors"
                >
                  {dim}
                </Tag>
              ))}
              {isAdding ? (
                <Input
                  autoFocus
                  size="middle"
                  value={newDimension}
                  onChange={(e) => setNewDimension(e.target.value)}
                  onBlur={handleAddDimension}
                  onPressEnter={handleAddDimension}
                  className="w-40 bg-white/5 border-blue-500/50 text-white text-sm rounded-xl"
                />
              ) : (
                <Tag 
                  onClick={() => setIsAdding(true)} 
                  className="bg-blue-500/10 border-blue-500/30 text-blue-400 border-dashed px-3.5 py-1.5 rounded-xl text-sm m-0 cursor-pointer hover:bg-blue-500/20"
                >
                  <PlusOutlined /> 新增维度
                </Tag>
              )}
            </div>
          </div>
        )}

        {pendingBreakpoint.type === 'sources' && (
          <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
            <Checkbox.Group 
              className="w-full flex flex-col gap-2" 
              value={approvedSources} 
              onChange={(vals) => setApprovedSources(vals as string[])}
            >
              {(pendingBreakpoint.payload as any[] || []).map((source) => (
                <div 
                  key={source.url}
                  className={`p-3 rounded-xl border transition-all cursor-pointer ${
                    approvedSources.includes(source.url) 
                      ? 'bg-blue-500/10 border-blue-500/30' 
                      : 'bg-white/5 border-transparent hover:border-white/10'
                  }`}
                  onClick={() => {
                    if (approvedSources.includes(source.url)) {
                      setApprovedSources(approvedSources.filter(u => u !== source.url));
                    } else {
                      setApprovedSources([...approvedSources, source.url]);
                    }
                  }}
                >
                  <div className="flex items-start gap-3">
                    <Checkbox value={source.url} className="mt-0.5" onClick={(e) => e.stopPropagation()} />
                    <div className="flex flex-col min-w-0 flex-1">
                      <Text className="text-slate-200 text-sm font-bold truncate leading-tight">
                        {source.title || '未知标题'}
                      </Text>
                      <Text className="text-slate-500 text-xs truncate font-mono mt-1">
                        {source.url}
                      </Text>
                    </div>
                  </div>
                </div>
              ))}
            </Checkbox.Group>
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <Button 
            icon={<CloseCircleFilled className="text-slate-400" />}
            className="bg-white/5 border-white/10 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl"
            onClick={() => useResearchStore.getState().setPendingBreakpoint(null)}
          >
            跳过确认
          </Button>
          <Button 
            type="primary"
            icon={<CheckCircleOutlined />}
            className="bg-blue-600 hover:bg-blue-500 border-none rounded-xl px-6 font-bold shadow-lg shadow-blue-900/20"
            onClick={handleResume}
          >
            开始执行
          </Button>
        </div>
      </Card>
    </div>
  );
};
