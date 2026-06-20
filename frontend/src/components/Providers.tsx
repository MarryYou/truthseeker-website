'use client';

import { ReactNode } from 'react';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { ThemeProvider } from './ThemeProvider';
import { QueryProvider } from './QueryProvider';
import { AuthInitializer } from './AuthInitializer';

export default function Providers({ children }: { children: ReactNode }) {
  return (
    <AntdRegistry>
      <ThemeProvider>
        <QueryProvider>
          <AuthInitializer>
            {children}
          </AuthInitializer>
        </QueryProvider>
      </ThemeProvider>
    </AntdRegistry>
  );
}
