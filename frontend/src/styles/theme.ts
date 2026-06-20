import type { ThemeConfig } from 'antd';

/**
 * 全局 Ant Design 主题配置 (Dark Mode Only)
 */
export const themeConfig: ThemeConfig = {
  token: {
    colorPrimary: '#1677ff',
    colorInfo: '#1677ff',
    colorSuccess: '#52c41a',
    colorWarning: '#faad14',
    colorError: '#ff4d4f',
    borderRadius: 8,
    wireframe: false,
    colorBgBase: '#090a0f',
    colorTextBase: '#f1f5f9',
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  components: {
    Button: {
      borderRadius: 10,
      fontWeight: 600,
    },
    Input: {
      borderRadius: 10,
      colorBgContainer: 'rgba(255, 255, 255, 0.05)',
    },
    Segmented: {
      itemSelectedBg: '#3b82f6',
      itemSelectedColor: '#fff',
      trackBg: 'rgba(255, 255, 255, 0.03)',
      itemColor: '#94a3b8',
      itemHoverColor: '#cbd5e1',
    },
  },
};

/**
 * 品牌颜色与状态色 (供非 Antd 组件使用)
 */
export const COLORS = {
  BRAND: '#1677ff',
  BG_DARK: '#090a0f',
  BG_CARD: '#14161f',
  TEXT_MAIN: '#f1f5f9',
  TEXT_MUTED: '#94a3b8',
  BORDER_THIN: 'rgba(255, 255, 255, 0.1)',
};
