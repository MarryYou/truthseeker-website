'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useResearchStore } from '@/store/useResearchStore';
import { Input, Select, Button, Popconfirm, App, Empty, Pagination, Tooltip } from 'antd';
import { 
  DeleteOutlined, 
  SearchOutlined, ReloadOutlined, 
  FileTextOutlined, CalendarOutlined,
  CheckCircleOutlined, SyncOutlined, CloseCircleOutlined
} from '@ant-design/icons';

import { listSessions, deleteSession } from '@/services/research';
import type { ResearchSession } from '@/types';

export default function HistoryPanel() {
  const router = useRouter();
  const { message } = App.useApp();
  
  const [data, setData] = useState<ResearchSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(12);
  const [searchWord, setSearchWord] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listSessions({
        page,
        page_size: pageSize,
        keyword: searchWord || undefined,
        status: statusFilter,
      });
      setData(result.items || []);
      setTotal(result.total || 0);
    } catch {
      message.error('加载出错，请重试');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchWord, statusFilter, message]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleSearchSubmit = () => {
    setPage(1);
    loadHistory();
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await deleteSession(id);
      message.success('已成功删除研究记录');
      loadHistory();
      useResearchStore.getState().triggerRecentRefresh();
    } catch {
      message.error('删除出错');
    }
  };

  const getStatusDisplay = (status: string) => {
    switch (status) {
      case 'running':
      case 'suspended':
        return <div className="flex items-center gap-1.5 text-blue-400 text-xs font-medium"><SyncOutlined spin /> 执行中</div>;
      case 'completed':
      case 'active':
        return <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-medium"><CheckCircleOutlined /> 已完成</div>;
      case 'failed':
        return <div className="flex items-center gap-1.5 text-rose-400 text-xs font-medium"><CloseCircleOutlined /> 失败中断</div>;
      default:
        return <div className="flex items-center gap-1.5 text-slate-400 text-xs font-medium"><FileTextOutlined /> {status || '未知状态'}</div>;
    }
  };

  return (
    <div className="h-full py-6 px-4 sm:px-8 w-full font-sans relative overflow-x-hidden text-slate-200 flex flex-col">
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-blue-600/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[40%] h-[50%] bg-purple-600/5 rounded-full blur-[120px] pointer-events-none" />
      
      <div className="w-full relative z-10 flex flex-col h-full">
        {/* Navigation Header */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between mb-8 gap-4">
          <div className="flex flex-col gap-2">
            <h2 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-slate-100 to-slate-400 tracking-tight m-0">
              研究档案
            </h2>
            <p className="text-slate-500 text-sm m-0">回顾并管理您过往的深度核查与决策报告。</p>
          </div>
          
          {/* Filter Bar - Responsive wrapping on mobile */}
          <div className="flex flex-wrap items-center gap-3 bg-[#12141c]/80 backdrop-blur-xl border border-white/10 rounded-2xl p-1.5 shadow-lg w-full lg:w-auto">
            <Input
              placeholder="搜索主题关键字..."
              value={searchWord}
              onChange={(e) => setSearchWord(e.target.value)}
              onPressEnter={handleSearchSubmit}
              prefix={<SearchOutlined className="text-slate-500 ml-1 mr-2" />}
              className="flex-1 min-w-[150px] sm:w-[240px] bg-transparent border-none shadow-none text-slate-200 text-sm focus:ring-0 placeholder:text-slate-600"
              variant="borderless"
            />
            
            <div className="hidden sm:block w-[1px] h-5 bg-white/10 mx-1" />

            <div className="flex items-center gap-2 w-full sm:w-auto">
              <Select
                placeholder="全部状态"
                value={statusFilter}
                onChange={(val: string | undefined) => {
                  setStatusFilter(val);
                  setPage(1);
                }}
                allowClear
                variant="borderless"
                className="flex-1 sm:w-[110px] custom-history-select"
                styles={{ popup: { root: { background: '#1e212b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px' } } }}
                options={[
                  { value: 'completed', label: <span className="text-emerald-400">已完成</span> },
                  { value: 'running', label: <span className="text-blue-400">进行中</span> },
                  { value: 'failed', label: <span className="text-rose-400">已失败</span> }
                ]}
              />
              
              <Tooltip title="刷新列表">
                <Button
                  type="text"
                  icon={<ReloadOutlined className={loading ? 'animate-spin' : ''} />}
                  className="w-8 h-8 flex items-center justify-center p-0 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl transition-all shrink-0"
                  onClick={handleSearchSubmit}
                />
              </Tooltip>
            </div>
          </div>
        </div>

        {/* Grid Card Wall */}
        <div className="flex-1 w-full relative">
          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 sm:gap-6 animate-pulse">
              {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
                <div key={i} className="bg-[#12141c]/60 border border-white/5 rounded-3xl p-4 sm:p-6 min-h-[200px] flex flex-col justify-between">
                  <div className="flex justify-between items-start">
                    <div className="h-6 w-20 bg-white/5 rounded-md" />
                    <div className="h-4 w-16 bg-white/5 rounded-md" />
                  </div>
                  <div className="space-y-3 mt-4 flex-1">
                    <div className="h-5 bg-white/5 rounded-md w-full" />
                    <div className="h-5 bg-white/5 rounded-md w-4/5" />
                  </div>
                  <div className="h-8 bg-white/5 rounded-xl w-full mt-4" />
                </div>
              ))}
            </div>
          ) : data.length > 0 ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4 sm:gap-6 mb-10">
                {data.map((item) => (
                  <div 
                    key={item.id}
                    onClick={() => router.push(`/research/${item.id}`)}
                    className="group relative bg-gradient-to-b from-[#161821]/80 to-[#0e1017]/80 backdrop-blur-xl border border-white/5 hover:border-blue-500/40 rounded-3xl p-5 sm:p-6 shadow-xl hover:shadow-blue-900/20 hover:-translate-y-1 transition-all duration-300 cursor-pointer flex flex-col justify-between min-h-[200px] h-auto overflow-hidden"
                  >
                    <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
                    
                    {/* Delete button */}
                    <div className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-20">
                      <Popconfirm
                        title="确定要删除该项研究记录吗？"
                        description="此操作不可撤销，关联的所有数据将被清空。"
                        onConfirm={(e) => {
                          if (e) handleDelete(e as unknown as React.MouseEvent, item.id);
                        }}
                        okText="删除"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                      >
                        <Button
                          type="text"
                          shape="circle"
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                          className="bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 hover:text-rose-300 border-none flex items-center justify-center w-8 h-8 transition-colors"
                        />
                      </Popconfirm>
                    </div>

                    {/* Card Header */}
                    <div className="flex justify-between items-center mb-4 relative z-10">
                      <div className="flex items-center gap-2 text-note text-slate-500">
                        <CalendarOutlined />
                        {new Date(item.created_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </div>
                      {item.total_duration_seconds ? (
                        <div className="bg-white/5 border border-white/10 rounded px-1.5 py-0.5 text-[10px] text-slate-500 font-mono">
                          {item.total_duration_seconds}s
                        </div>
                      ) : null}
                    </div>

                    {/* Card Body: Title */}
                    <div className="flex-1 relative z-10 mt-1">
                      <h3 className="text-slate-200 font-semibold text-[15px] leading-relaxed line-clamp-3 pr-2 group-hover:text-blue-100 transition-colors">
                        {item.title}
                      </h3>
                    </div>

                    {/* Card Footer: Status */}
                    <div className="relative z-10 pt-4 border-t border-white/5 mt-4">
                      {getStatusDisplay(item.status)}
                    </div>
                  </div>
                ))}
              </div>
              
              {/* Pagination */}
              <div className="flex justify-center pb-10 overflow-x-auto">
                <Pagination
                  current={page}
                  pageSize={pageSize}
                  total={total}
                  onChange={(p) => setPage(p)}
                  showSizeChanger={false}
                  className="custom-pagination-v2"
                  responsive
                />
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-[50vh] bg-gradient-to-b from-[#12141c]/50 to-transparent border border-white/5 rounded-3xl p-6 sm:p-16 shadow-inner text-center">
              <Empty 
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <div className="flex flex-col gap-2 mt-4">
                    <span className="text-slate-300 font-medium text-sm">暂无研究档案</span>
                    <span className="text-slate-500 text-xs">您还没有发起过任何研究任务，或者没有符合条件的记录。</span>
                  </div>
                }
              />
              <Button 
                type="primary" 
                className="mt-6 bg-blue-600 hover:bg-blue-500 border-none shadow-lg shadow-blue-900/20 rounded-xl h-10 px-6 font-medium"
                onClick={() => router.push('/')}
              >
                发起新研究
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
