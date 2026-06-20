import axios from 'axios';
import { API_BASE_PATH, LOGIN_PATH } from '@/lib/constants';

/**
 * 核心 API 调用实例。
 * 统一走 Next.js Rewrites Proxy (/api/v1)，由后端 Server 端处理 HttpOnly Cookie 与 Session 校验。
 */
const api = axios.create({
  baseURL: API_BASE_PATH,
  withCredentials: true,
});

// 防止 401 重定向爆炸
let isRedirecting = false;

// 响应拦截器：处理全局错误与自动登录跳转
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // 401 Unauthorized 表示 Session 失效
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith(LOGIN_PATH)) {
        if (!isRedirecting) {
          isRedirecting = true;
          // 重定向到登录页
          window.location.href = LOGIN_PATH;
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
