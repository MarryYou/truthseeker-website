'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Layout, Button, Tooltip, Avatar, Dropdown, Tag, Drawer } from 'antd';
import { 
  History, 
  Settings2, 
  User, 
  Plus,
  LogOut,
  Menu,
  MoreHorizontal,
  ChevronRight
} from 'lucide-react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { CompassOutlined } from '@ant-design/icons';
import { useUser } from '@/hooks/useUser';
import { useResearchStore } from '@/store/useResearchStore';

import { listSessions } from '@/services/research';
import type { ResearchSession } from '@/types';

const { Content, Sider } = Layout;

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isAuthenticated } = useUser();

  const [recentResearches, setRecentResearches] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // 路由变化时自动关闭移动端侧边栏
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  // 解析当前路由中活跃的 researchId
  const researchIdMatch = pathname.match(/^\/research\/([^/]+)/);
  const activeResearchId = researchIdMatch ? researchIdMatch[1] : null;

  // 获取最近研究记录
  const fetchRecentResearches = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    try {
      const result = await listSessions({ page: 1, page_size: 8 });
      if (result) {
        const filtered = (result.items || []).filter((item) => {
          if (item.id === activeResearchId && isStreaming && isNewResearch) {
            return false;
          }
          return true;
        });
        setRecentResearches(filtered);
      }
    } catch (err) {
      console.error('Failed to fetch recent researches:', err);
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, activeResearchId]);

  const isStreaming = useResearchStore(state => state.isStreaming);
  const isNewResearch = useResearchStore(state => state.isNewResearch);
  const recentRefreshTrigger = useResearchStore(state => state.recentRefreshTrigger);

  useEffect(() => {
    fetchRecentResearches();
  }, [pathname, isAuthenticated, isStreaming, recentRefreshTrigger, isNewResearch, fetchRecentResearches]);

  const profileContent = (
    <div className="w-[240px] p-2 bg-[#0f111a]/95 backdrop-blur-xl border border-white/[0.08] shadow-[0_20px_50px_rgba(0,0,0,0.5)] rounded-2xl flex flex-col gap-1">
      {/* 顶部用户信息 */}
      <div className="px-3 py-2.5 border-b border-white/5 flex items-center gap-3">
        <Avatar 
          size={36} 
          src={user?.avatar || undefined} 
          className="rounded-lg border border-white/10 shrink-0"
          icon={<User size={18} />}
        />
        <div className="flex flex-col min-w-0 flex-1">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-body-sm font-bold text-slate-200 truncate leading-tight">
              {user?.name || 'TruthSeeker User'}
            </span>
            <Tag className="m-0 bg-blue-500/10 text-blue-400 border-0 text-micro font-black px-1 rounded-sm scale-90 shrink-0">PRO</Tag>
          </div>
          <span className="text-caption text-slate-500 truncate font-mono mt-0.5 leading-none">
            {user?.email}
          </span>
        </div>
      </div>

      <div className="p-1 flex flex-col gap-1">
        {/* 历史档案菜单 */}
        <Link href="/history" className="w-full">
          <div className="w-full p-2.5 rounded-xl flex items-center justify-between hover:bg-white/[0.04] transition-all group cursor-pointer border border-transparent hover:border-white/5">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-400 shrink-0 group-hover:scale-105 transition-transform">
                <History size={16} />
              </div>
              <div className="flex flex-col text-left min-w-0">
                <span className="text-body-sm font-bold text-slate-200 group-hover:text-white transition-colors">
                  历史档案
                </span>
                <span className="text-caption text-slate-500 truncate mt-0.5">
                  查看过去的探索与研究
                </span>
              </div>
            </div>
            <ChevronRight size={14} className="text-slate-600 group-hover:text-slate-400 group-hover:translate-x-0.5 transition-all shrink-0" />
          </div>
        </Link>

        {/* 配置设置菜单 */}
        <Link href="/settings" className="w-full">
          <div className="w-full p-2.5 rounded-xl flex items-center justify-between hover:bg-white/[0.04] transition-all group cursor-pointer border border-transparent hover:border-white/5">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400 shrink-0 group-hover:scale-105 transition-transform">
                <Settings2 size={16} />
              </div>
              <div className="flex flex-col text-left min-w-0">
                <span className="text-body-sm font-bold text-slate-200 group-hover:text-white transition-colors">
                  配置设置
                </span>
                <span className="text-caption text-slate-500 truncate mt-0.5">
                  模型、API Key 与系统配置
                </span>
              </div>
            </div>
            <ChevronRight size={14} className="text-slate-600 group-hover:text-slate-400 group-hover:translate-x-0.5 transition-all shrink-0" />
          </div>
        </Link>
      </div>

      <div className="h-[1px] bg-white/5 my-0.5" />

      {/* 退出登录 */}
      <a href="/api/v1/auth/logout" className="w-full p-1 no-underline">
        <div className="w-full h-10 rounded-xl flex items-center justify-start hover:bg-rose-500/10 group px-2.5 text-slate-400 hover:text-rose-400 transition-all border border-transparent cursor-pointer">
          <LogOut size={15} className="text-slate-500 group-hover:text-rose-400 transition-colors shrink-0" />
          <span className="text-body-sm font-bold ml-2.5">退出登录</span>
        </div>
      </a>
    </div>
  );

  // 侧边栏内容（共享桌面端和移动端）
  const sidebarContent = (
    <div className="flex flex-col justify-between h-full w-full px-3 py-2 bg-[#0b0c11]">
      {/* 顶部 Logo 与新研究按钮 */}
      <div className="flex flex-col gap-5">
        <div className="flex items-center justify-between">
          <div 
            className="flex items-center gap-3 px-2 py-1.5 cursor-pointer active:scale-98 transition-all" 
            onClick={() => router.push('/')}
          >
            <div className="w-9 h-9 bg-gradient-to-tr from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-950/40">
              <CompassOutlined className="text-white text-base" />
            </div>
            <span className="font-black text-slate-100 text-base tracking-wide bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
              TruthSeeker
            </span>
          </div>
        </div>
        
        <Button 
          type="text" 
          icon={<Plus size={16} />} 
          className="w-full h-10 rounded-xl bg-white/5 hover:bg-white/10 text-slate-200 hover:text-white flex items-center justify-center gap-2 border border-white/5 transition-all text-body-sm font-bold"
          onClick={() => {
            router.push('/');
            setSidebarOpen(false);
          }}
        >
          发起新研究
        </Button>
      </div>

      {/* 中间：最近研究列表 */}
      <div className="flex-1 overflow-y-auto my-6 px-1 custom-scrollbar">
        <div className="text-caption font-black text-slate-500 uppercase tracking-widest px-2 mb-3">
          最近研究
        </div>
        
        {loading && recentResearches.length === 0 ? (
          <div className="space-y-2 px-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-8 bg-white/5 rounded-lg animate-pulse w-full" />
            ))}
          </div>
        ) : recentResearches.length > 0 ? (
          <div className="flex flex-col gap-1">
            {recentResearches.map((item) => {
              const isActive = activeResearchId === item.id;
              
              const getIcon = (type: string) => {
                if (type === 'compare') return '🛒';
                if (type === 'verify') return '🛡️';
                return '📚';
              };

              return (
                <Tooltip key={item.id} title={item.title} placement="right" mouseEnterDelay={0.3}>
                  <div
                    onClick={() => {
                      router.push(`/research/${item.id}`);
                      setSidebarOpen(false);
                    }}
                    className={`group relative flex items-center gap-2.5 px-3 py-2 rounded-xl cursor-pointer transition-all border text-left ${
                      isActive
                        ? 'bg-blue-500/10 text-blue-400 border-blue-500/20 font-semibold'
                        : 'text-slate-400 border-transparent hover:bg-white/5 hover:text-slate-200'
                    }`}
                  >
                    <span className="text-sm shrink-0">{getIcon(item.intent_type)}</span>
                    <span className="text-body-sm truncate flex-1 pr-1">{item.title}</span>
                  </div>
                </Tooltip>
              );
            })}
          </div>
        ) : (
          <div className="text-slate-600 text-body-sm text-center py-8 font-medium italic">
            暂无研究记录
          </div>
        )}
      </div>

      {/* 底部：账户信息 */}
      <div className="border-t border-white/5 pt-3">
        {isAuthenticated ? (
          <Dropdown 
            popupRender={() => profileContent}
            placement="top"
            trigger={['click']}
            classNames={{ root: 'profile-popover' }}
          >
            <div className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-xl cursor-pointer hover:bg-white/5 border border-transparent hover:border-white/5 transition-all group w-full">
              <div className="flex items-center gap-2.5 min-w-0 flex-1">
                <div className="relative shrink-0">
                  <Avatar 
                    size={32} 
                    src={user?.avatar || undefined} 
                    className="relative rounded-lg border border-white/10 group-hover:border-blue-500/30 transition-all shadow"
                    icon={<User size={16} />}
                  />
                </div>
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="text-note font-bold text-slate-200 truncate group-hover:text-white leading-tight">
                    {user?.name || 'TruthSeeker User'}
                  </span>
                  <span className="text-micro text-slate-500 truncate font-mono leading-none mt-0.5">
                    {user?.email}
                  </span>
                </div>
              </div>
              <MoreHorizontal size={14} className="text-slate-500 group-hover:text-slate-300 transition-colors shrink-0" />
            </div>
          </Dropdown>
        ) : (
          <a href="/api/v1/auth/login" className="w-full no-underline">
            <div className="flex items-center justify-between gap-2 px-2.5 py-2 rounded-xl cursor-pointer hover:bg-white/5 border border-transparent hover:border-white/5 transition-all text-slate-400 hover:text-slate-200 w-full group">
              <div className="flex items-center gap-2.5">
                <User size={16} />
                <span className="text-note font-bold">登录账号</span>
              </div>
              <MoreHorizontal size={14} className="text-slate-600 group-hover:text-slate-400 transition-colors shrink-0" />
            </div>
          </a>
        )}
      </div>
    </div>
  );

  return (
    <Layout className="h-screen bg-[#090a0f]">
      {/* ===== 移动端：顶部导航栏 ===== */}
      <div className="md:hidden fixed top-0 left-0 right-0 h-14 bg-[#0b0c11]/90 backdrop-blur-md border-b border-white/5 z-50 flex items-center px-4">
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-2 rounded-lg text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
        >
          <Menu size={20} />
        </button>
        <div 
          className="flex items-center gap-2 ml-3 cursor-pointer" 
          onClick={() => router.push('/')}
        >
          <div className="w-7 h-7 bg-gradient-to-tr from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
            <CompassOutlined className="text-white text-xs" />
          </div>
          <span className="font-black text-transparent bg-clip-text bg-gradient-to-r from-white to-slate-400 text-body-sm">
            TruthSeeker
          </span>
        </div>
      </div>

      {/* ===== 移动端：侧边栏 Drawer ===== */}
      <Drawer
        title={null}
        placement="left"
        closable={false}
        onClose={() => setSidebarOpen(false)}
        open={sidebarOpen}
        size={280}
        styles={{ body: { padding: 0 } }}
        className="md:hidden"
      >
        {sidebarContent}
      </Drawer>

      {/* ===== 桌面端：固定侧边栏 ===== */}
      <Sider
        width={240}
        theme="dark"
        className="hidden md:flex flex-col py-4 border-r border-white/5"
        style={{ 
          background: '#0b0c11',
          zIndex: 100,
          position: 'fixed',
          height: '100vh',
          left: 0,
          top: 0
        }}
      >
        {sidebarContent}
      </Sider>

      {/* 主内容区 */}
      <Layout className="min-h-screen bg-[#090a0f] md:ml-[240px] pt-14 md:pt-0">
        <Content className="h-full overflow-auto relative">
          {children}
        </Content>
      </Layout>

    </Layout>
  );
}
