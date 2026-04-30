"""
自动降级策略模块

实现 provider 的自动降级逻辑（Tencent → DMXAPI）。
"""

from typing import Optional, List
from nano_banana_provider_router import ProviderRouter


class FallbackStrategy:
    """自动降级策略类"""
    
    def __init__(self, router: ProviderRouter):
        """
        初始化降级策略
        
        Args:
            router: Provider 路由器实例
        """
        self.router = router
    
    def execute_step1_with_fallback(
        self,
        img_urls: Optional[List[str]],
        prompt: str,
        ratio: str,
        resolution: str
    ) -> Optional[str]:
        """
        执行 step1 并在失败时自动降级
        
        策略：先尝试 Tencent，失败后自动切换到 DMXAPI
        
        Args:
            img_urls: 参考图片 URL 列表
            prompt: 图片描述提示词
            ratio: 宽高比
            resolution: 分辨率
            
        Returns:
            task_id 字符串（成功）或 None（失败）
        """
        # 尝试 Tencent
        try:
            tencent = self.router.get_adapter("tencent")
            task_id = tencent.step1_submit_task(img_urls, prompt, ratio, resolution)
            if task_id:
                return task_id
            print("[Fallback] Tencent 提交失败，切换到 DMXAPI...")
        except Exception as e:
            print(f"[Fallback] Tencent 异常: {e}，切换到 DMXAPI...")

        # 回退到 DMXAPI
        try:
            dmxapi = self.router.get_adapter("dmxapi")
            return dmxapi.step1_submit_task(img_urls, prompt, ratio, resolution)
        except Exception as e:
            print(f"[ERROR] Tencent 和 DMXAPI 均失败。DMXAPI 错误: {e}")
            return None
