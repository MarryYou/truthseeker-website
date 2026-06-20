import { MessageInstance } from 'antd/es/message/interface';
import { NotificationInstance } from 'antd/es/notification/interface';
import { ModalStaticFunctions } from 'antd/es/modal/confirm';

let messageInstance: MessageInstance;
let notificationInstance: NotificationInstance;
let modalInstance: Omit<ModalStaticFunctions, 'warn'>;

/**
 * 导出静态代理对象，供非 React 组件代码（如 Zustand Store 或 Axios 拦截器）使用。
 * 必须在 App 组件内通过 setAntdInstances 初始化。
 */
export const setAntdInstances = (
  msg: MessageInstance,
  notif: NotificationInstance,
  mdl: Omit<ModalStaticFunctions, 'warn'>
) => {
  messageInstance = msg;
  notificationInstance = notif;
  modalInstance = mdl;
};

/**
 * 消息代理对象，确保即使在未初始化时调用也不会崩溃（但建议在 App 挂载后使用）
 */
export const message: MessageInstance = {
  info: (...args: any[]) => messageInstance?.info(...(args as [any])),
  success: (...args: any[]) => messageInstance?.success(...(args as [any])),
  error: (...args: any[]) => messageInstance?.error(...(args as [any])),
  warning: (...args: any[]) => messageInstance?.warning(...(args as [any])),
  loading: (...args: any[]) => messageInstance?.loading(...(args as [any])),
  open: (...args: any[]) => messageInstance?.open(...(args as [any])),
  destroy: (key?: React.Key) => messageInstance?.destroy(key),
} as any;

export const notification: NotificationInstance = {
  success: (...args: any[]) => notificationInstance?.success(...(args as [any])),
  error: (...args: any[]) => notificationInstance?.error(...(args as [any])),
  info: (...args: any[]) => notificationInstance?.info(...(args as [any])),
  warning: (...args: any[]) => notificationInstance?.warning(...(args as [any])),
  open: (...args: any[]) => notificationInstance?.open(...(args as [any])),
  destroy: (key?: React.Key) => notificationInstance?.destroy(key),
} as any;

export const modal = {
  confirm: (...args: any[]) => modalInstance?.confirm(...(args as [any])),
  info: (...args: any[]) => modalInstance?.info(...(args as [any])),
  success: (...args: any[]) => modalInstance?.success(...(args as [any])),
  error: (...args: any[]) => modalInstance?.error(...(args as [any])),
  warning: (...args: any[]) => modalInstance?.warning(...(args as [any])),
} as any;
