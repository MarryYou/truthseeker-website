"""SSE 令牌流处理器 — 负责状态化地解析 LLM 输出并过滤特定标签"""
from __future__ import annotations

class ThinkingTagProcessor:
    """
    状态化地过滤 <thinking> 标签及其内容。
    设计目标：处理被网络包随机截断的令牌流。
    """
    THINKING_START = "<thinking>"
    THINKING_END = "</thinking>"

    def __init__(self):
        self.thinking_open = False
        self.carry = ""

    def process(self, text: str) -> str:
        """
        处理新到达的文本块。
        返回剔除掉思考过程后的可见文本。
        """
        buffer = self.carry + text
        self.carry = ""
        visible_parts: list[str] = []
        cursor = 0
        buffer_len = len(buffer)

        while cursor < buffer_len:
            if self.thinking_open:
                # 寻找结束标签
                end_index = buffer.find(self.THINKING_END, cursor)
                if end_index == -1:
                    # 没找到结束标签，可能被截断了，也可能还在思考中
                    self.carry = self._longest_suffix_prefix(buffer[cursor:], (self.THINKING_END,))
                    return "".join(visible_parts)

                # 找到结束标签
                cursor = end_index + len(self.THINKING_END)
                self.thinking_open = False
                continue

            # 处于可见模式，寻找开始标签
            start_index = buffer.find(self.THINKING_START, cursor)
            
            # 这里还需要考虑结束标签意外出现的情况（虽然理论上不会，但为了健壮性）
            end_index = buffer.find(self.THINKING_END, cursor)
            
            tag_index = -1
            tag_length = 0
            tag_is_start = False

            if start_index != -1 and (end_index == -1 or start_index < end_index):
                tag_index = start_index
                tag_length = len(self.THINKING_START)
                tag_is_start = True
            elif end_index != -1:
                tag_index = end_index
                tag_length = len(self.THINKING_END)

            if tag_index == -1:
                # 没有任何完整标签，检查末尾是否有半个标签
                suffix = self._longest_suffix_prefix(buffer[cursor:], (self.THINKING_START, self.THINKING_END))
                safe_end = buffer_len - len(suffix)
                if safe_end > cursor:
                    visible_parts.append(buffer[cursor:safe_end])
                self.carry = buffer[safe_end:]
                return "".join(visible_parts)

            # 提取标签前的可见文本
            if tag_index > cursor:
                visible_parts.append(buffer[cursor:tag_index])

            cursor = tag_index + tag_length
            if tag_is_start:
                self.thinking_open = True

        return "".join(visible_parts)

    def _longest_suffix_prefix(self, text: str, candidates: tuple[str, ...]) -> str:
        """寻找文本末尾可能属于候选标签前缀的最长部分"""
        max_len = min(max((len(candidate) for candidate in candidates), default=0), len(text))
        for size in range(max_len, 0, -1):
            suffix = text[-size:]
            if any(candidate.startswith(suffix) for candidate in candidates):
                return suffix
        return ""
