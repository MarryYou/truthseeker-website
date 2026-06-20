"""搜索插件基类"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class SearchPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """插件唯一标识，如 'tavily', 'bocha'"""
        pass

    @property
    @abstractmethod
    def is_reader(self) -> bool:
        """是否为内容提取器 (内容提取器)"""
        pass

    @abstractmethod
    async def search(
        self, 
        query: str, 
        api_key: str, 
        context: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> list[dict]:
        """执行搜索或内容抓取提取
        - api_key 必须由外部解密后显式传入，防止插件内部暗自 fallback
        - context 可选，包含 db, user_id, tenant_id 等执行上下文
        """
        pass

    async def test_connection(self, api_key: str) -> bool:
        """测试连接可用性（由各插件覆盖实现）。
        默认使用 search 方法发送 'ping'。
        """
        await self.search("ping", api_key, max_results=1)
        return True
