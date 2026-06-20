/**
 * 净化错误消息，隐藏底层技术细节（如 Python Traceback、底层组件名、API 库异常），
 * 返回对最终用户友好的中文提示信息。
 */
export function sanitizeErrorMessage(message: string): string {
  if (!message) return '发生未知错误，请重试';

  const lower = message.toLowerCase();

  // 1. 判断是否是严重的 traceback 或底层模块代码报错
  if (
    lower.includes('traceback') ||
    lower.includes('line ') ||
    lower.includes('file "') ||
    lower.includes('exception:') ||
    lower.includes('valueerror') ||
    lower.includes('keyerror') ||
    lower.includes('typeerror') ||
    lower.includes('indexerror')
  ) {
    return '系统核心组件处理异常，请微调您的问题并重试。';
  }

  // 2. 判断是否是模型服务/API 服务相关错误
  if (
    lower.includes('dashscope') ||
    lower.includes('openai') ||
    lower.includes('deepseek') ||
    lower.includes('api_error') ||
    lower.includes('apierror') ||
    lower.includes('api error') ||
    lower.includes('llm') ||
    lower.includes('model_error')
  ) {
    return '智能模型服务响应异常，请稍后重新尝试。';
  }

  // 3. 判断是否是网络连接、超时、数据库相关错误
  if (
    lower.includes('timeout') ||
    lower.includes('time out') ||
    lower.includes('httpx') ||
    lower.includes('httpstatuserror') ||
    lower.includes('connection') ||
    lower.includes('failed to fetch') ||
    lower.includes('unreachable') ||
    lower.includes('network') ||
    lower.includes('database') ||
    lower.includes('sqlalchemy') ||
    lower.includes('redis')
  ) {
    return '网络通信超时或数据库响应缓慢，请稍后再试。';
  }

  // 4. 判断是否是 JSON 或序列化反序列化解析错误
  if (
    lower.includes('json') ||
    lower.includes('parse') ||
    lower.includes('decode') ||
    lower.includes('serialize')
  ) {
    return '数据流解析异常，请稍后重新发起请求。';
  }

  // 5. 如果是 SSE 相关的错误
  if (lower.includes('sse') || lower.includes('event source') || lower.includes('interrupted')) {
    return '数据传输通道临时中断，系统正在尝试自动重连。';
  }

  // 6. 前面有 "Error: " 标识的，去除 "Error: "，且若剩余消息过长且为纯英文，则安全兜底
  let cleanMsg = message.replace(/^Error:\s*/i, '').trim();
  if (cleanMsg.length > 50 && /^[a-zA-Z0-9_\s\(\)\:\.\,\-\'\"\!\?]+$/.test(cleanMsg)) {
    return '系统处理任务时遇到非预期异常，请稍后重新提交。';
  }

  return cleanMsg;
}
