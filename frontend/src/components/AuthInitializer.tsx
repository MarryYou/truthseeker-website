'use client';

import { ReactNode, useEffect } from 'react';
import { App } from 'antd';
import { useUser } from '@/hooks/useUser';
import { setAntdInstances } from '@/lib/antd';

/** 
 * 负责应用启动时的权限校验与 Antd 全局实例注入
 */
export function AuthInitializer({ children }: { children: ReactNode }) {
  const { refreshUser } = useUser();
  const { message, notification, modal } = App.useApp();
  
  useEffect(() => {
    // 将上下文感知的实例保存到全局静态变量中
    setAntdInstances(message, notification, modal);
    
    const checkAuth = async () => {
      const isAuth = await refreshUser();
      // 如果未登录且不在登录/回调页，强制跳转
      if (!isAuth && !window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/callback')) {
        window.location.href = '/login';
      }
    };
    
    checkAuth();
  }, [refreshUser, message, notification, modal]);

  return <>{children}</>;
}
