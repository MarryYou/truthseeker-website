'use client';

import { ReactNode } from 'react';
import { ConfigProvider, theme, App } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { themeConfig } from '@/styles/theme';

/**
 * 集中管理 Ant Design 的全局主题与样式注入
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        ...themeConfig,
        algorithm: theme.darkAlgorithm,
      }}
    >
      <App className="h-full">
        {children}
      </App>
    </ConfigProvider>
  );
}
