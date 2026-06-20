/**
 * 环境变量层 (含类型校验与默认值)
 */

const getEnv = (key: string, defaultValue: string = ''): string => {
  if (typeof process === 'undefined' || !process.env) return defaultValue;
  return process.env[key] || defaultValue;
};

export const NEXT_PUBLIC_API_URL = getEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8000');

export const IS_DEV = process.env.NODE_ENV === 'development';
export const IS_PROD = process.env.NODE_ENV === 'production';
export const IS_BROWSER = typeof window !== 'undefined';
