import type { ResearchMessage, ThoughtStep } from '@/types';

/**
 * 合并思考步骤：对已有的 steps 数组进行 upsert 操作。
 * 如果传入的 step 在已存在的数组中找到了相同的 key/id，则合并更新；
 * 否则追加到数组末尾。
 */
export function mergeThoughtSteps(existing: ThoughtStep[], updates: ThoughtStep[]): ThoughtStep[] {
  const newSteps = [...existing];
  for (const incoming of updates) {
    const incomingKey = incoming.key || incoming.id;
    if (!incomingKey) continue;
    const idx = newSteps.findIndex(s => s.key === incomingKey || s.id === incomingKey);
    if (idx > -1) {
      newSteps[idx] = {
        ...newSteps[idx],
        ...incoming,
        status: incoming.status || newSteps[idx].status,
        label: incoming.label || newSteps[idx].label,
        description: incoming.description || newSteps[idx].description,
        sub_steps: incoming.sub_steps || newSteps[idx].sub_steps,
      };
    } else {
      newSteps.push({
        ...incoming,
        key: incomingKey,
      });
    }
  }
  return newSteps;
}

/** 查找最后一个 role=assistant 的消息索引 */
export function findLastAssistantIdx(messages: ResearchMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'assistant') return i;
  }
  return -1;
}
