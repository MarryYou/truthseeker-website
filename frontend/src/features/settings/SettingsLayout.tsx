'use client';

import React, { useEffect } from 'react';
import { Layout, Menu, Typography, Spin, Segmented } from 'antd';
import { 
  UserOutlined, 
  ApiOutlined, 
  DatabaseOutlined, 
  DeploymentUnitOutlined,
  LoadingOutlined
} from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useSettingsStore } from '@/store/useSettingsStore';

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

// 子面板组件 (待实现)
import ProfilePanel from './ProfilePanel';
import ConnectionsPanel from './ConnectionsPanel';
import WorkflowPanel from './WorkflowPanel';

export default function SettingsLayout({ userClaims }: { userClaims: any }) {
  const router = useRouter();
  const { 
    activeTab, 
    setActiveTab, 
    fetchSettings, 
    loading
  } = useSettingsStore();

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const menuItems = [
    { key: 'profile', icon: <UserOutlined />, label: '个人档案', shortLabel: '档案' },
    { key: 'connections', icon: <ApiOutlined />, label: '模型与服务', shortLabel: '服务' },
    { key: 'workflow', icon: <DeploymentUnitOutlined />, label: '研究工作流', shortLabel: '工作流' },
  ];

  const renderContent = () => {
    switch (activeTab) {
      case 'profile': return <ProfilePanel userClaims={userClaims} />;
      case 'connections': return <ConnectionsPanel />;
      case 'workflow': return <WorkflowPanel />;
      default: return <ConnectionsPanel />;
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} spin />} description="加载引擎配置..." />
      </div>
    );
  }

  return (
    <div className="h-full py-6 px-4 sm:px-8 w-full font-sans relative overflow-x-hidden text-slate-200 flex flex-col">
      {/* Background decorations */}
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-blue-600/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[40%] h-[50%] bg-purple-600/5 rounded-full blur-[120px] pointer-events-none" />

      <div className="w-full relative z-10 flex flex-col h-full">
        {/* Navigation Header */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-6 sm:mb-8 gap-4">
          <div className="flex flex-col gap-2">
            <h2 className="text-2xl sm:text-3xl font-black text-transparent bg-clip-text bg-linear-to-r from-slate-100 to-slate-400 tracking-tight m-0 flex flex-wrap items-center gap-3">
              系统设置
              <Text className="text-slate-500 font-normal text-[10px] sm:text-xs uppercase tracking-widest mt-1 sm:mt-2 border border-slate-700/50 rounded-full px-2 py-0.5 whitespace-nowrap">v2.0 Architecture</Text>
            </h2>
            <p className="text-slate-500 text-xs sm:text-sm m-0">配置研究引擎、模型底座及自定义专家工作流。</p>
          </div>
        </div>

        <div className="flex flex-col flex-1 w-full gap-4 sm:gap-6 min-h-0">
          {/* 移动端导航栏 (分段选择) */}
          <div className="w-full shrink-0 block sm:hidden">
            <Segmented
              options={menuItems.map(item => ({
                label: (
                  <span className="flex items-center gap-1 py-1 justify-center font-bold text-xs">
                    {item.icon}
                    <span>{item.shortLabel}</span>
                  </span>
                ),
                value: item.key
              }))}
              value={activeTab}
              onChange={(val) => setActiveTab(val as any)}
              block
              className="bg-[#12141c]/40 backdrop-blur-md border border-white/5 p-1 rounded-xl custom-settings-segmented"
            />
          </div>

          {/* 桌面端导航栏 (水平模式) - 支持移动端滚动 */}
          <div className="w-full shrink-0 hidden sm:block bg-[#12141c]/40 backdrop-blur-md border border-white/5 rounded-2xl p-1 px-2 overflow-x-auto custom-scrollbar">
            <Menu
              theme="dark"
              mode="horizontal"
              selectedKeys={[activeTab]}
              onClick={({ key }) => setActiveTab(key as any)}
              className="bg-transparent border-none custom-settings-menu-horizontal min-w-max"
              items={menuItems.map(({ shortLabel, ...rest }) => rest)}
            />
          </div>

          {/* 下方内容区 */}
          <div className="flex-1 bg-[#12141c]/60 backdrop-blur-xl border border-white/5 rounded-3xl shadow-xl overflow-hidden relative p-4 sm:p-8 overflow-y-auto custom-scrollbar">
             {renderContent()}
          </div>
        </div>
      </div>

    </div>
  );
}
