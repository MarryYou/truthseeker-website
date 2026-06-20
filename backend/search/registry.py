"""插件注册表单例"""
from __future__ import annotations
from backend.search.base import SearchPlugin
from backend.core.logging import logger


class SearchPluginRegistry:
    _instance = None
    _plugins: dict[str, SearchPlugin] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SearchPluginRegistry, cls).__new__(cls)
        return cls._instance

    def register(self, plugin: SearchPlugin) -> None:
        """注册插件"""
        self._plugins[plugin.name] = plugin
        logger.info("搜索插件注册成功: {}", plugin.name)

    def get_plugin(self, name: str) -> SearchPlugin | None:
        """根据名称获取插件"""
        return self._plugins.get(name)

    def list_plugins(self) -> list[SearchPlugin]:
        """获取所有已注册插件"""
        return list(self._plugins.values())


# 暴露全局单例
plugin_registry = SearchPluginRegistry()
