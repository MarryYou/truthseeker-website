'use client';

import React from 'react';
import { Spin } from 'antd';
import ChatLayout from '@/features/chat/ChatLayout';
import { useUser } from '@/hooks/useUser';

/**
 * Dashboard 路由组共享布局。
 * 统一处理身份校验 + ChatLayout 侧边栏，
 * 子页面无须重复包装。
 */
export default function DashboardGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated } = useUser();

  if (!isAuthenticated) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-[#090a0f]">
        <Spin size="large" description="正在校验身份..." />
      </div>
    );
  }

  return <ChatLayout>{children}</ChatLayout>;
}
