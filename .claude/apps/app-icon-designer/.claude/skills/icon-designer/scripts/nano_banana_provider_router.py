"""
Provider 路由模块

负责适配器的缓存、获取、路由以及 provider 检测。
"""

from typing import Dict, Tuple
import os
from base_three_step_nano_banana_adapter import BaseThreeStepNanoBananaAdapter
from tencent_banana_adapter import TencentAdapter
from dmxapi_banana_adapter import DmxApiAdapter
from mock_banana_adapter import MockAdapter


class ProviderRouter:
    """Provider 路由器，管理适配器缓存和路由逻辑"""
    
    # CDN URL 前缀列表
    CDN_PREFIXES = tuple(
        prefix.strip()
        for prefix in os.environ.get("PUBLIC_CDN_PREFIXES", "https://").split(",")
        if prefix.strip()
    )
    
    def __init__(self):
        """初始化路由器"""
        self._adapter_cache: Dict[str, BaseThreeStepNanoBananaAdapter] = {}
    
    def get_adapter(self, provider: str) -> BaseThreeStepNanoBananaAdapter:
        """
        获取 provider 适配器实例（带缓存）
        
        Args:
            provider: provider 名称，如 "tencent"、"dmxapi"
            
        Returns:
            适配器实例
            
        Raises:
            ValueError: 不支持的 provider
        """
        if provider not in self._adapter_cache:
            if provider == "mock":
                self._adapter_cache[provider] = MockAdapter()
            elif provider == "tencent":
                self._adapter_cache[provider] = TencentAdapter()
            elif provider == "dmxapi":
                self._adapter_cache[provider] = DmxApiAdapter()
            else:
                raise ValueError(f"不支持的 provider: {provider}，可选: mock, tencent, dmxapi")
        return self._adapter_cache[provider]
    
    def detect_provider_from_task_id(self, task_id: str) -> str:
        """
        根据 task_id 格式自动判断来自哪个 provider
        
        Args:
            task_id: 任务 ID
            
        Returns:
            provider 名称，如 "tencent" 或 "dmxapi"
        """
        if task_id and task_id.startswith(MockAdapter.DONE_PREFIX):
            return "mock"
        if task_id and task_id.startswith(DmxApiAdapter.DONE_PREFIX):
            return "dmxapi"
        return "tencent"
    
    def is_cdn_url(self, url: str) -> bool:
        """
        判断 URL 是否已经是 CDN URL
        
        Args:
            url: 图片 URL
            
        Returns:
            True 如果是 CDN URL，否则 False
        """
        return url and url.startswith(self.CDN_PREFIXES)
