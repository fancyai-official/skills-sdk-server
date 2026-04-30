"""
图片生成适配器抽象基类

定义了所有图片生成 provider 适配器必须实现的接口规范。
遵循三步调用原则（适配 Claude sandbox 60 秒网络超时限制）。
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseThreeStepNanoBananaAdapter(ABC):
    """
    图片生成适配器抽象基类
    
    所有 provider 适配器（如 TencentAdapter、DmxApiAdapter）必须继承此类
    并实现三步接口：step1（提交任务）、step2（轮询状态）、step3（下载上传）。
    
    三步调用原则：
        Step 1: step1() - 提交生图任务，返回 task_id（< 30s）
        Step 2: step2() - 轮询任务状态，返回 file_url（< 50s）
        Step 3: step3() - 下载图片+上传 R2，返回 CDN URL（< 30s）
    """
    
    @property
    @abstractmethod
    def NAME(self) -> str:
        """
        Provider 标识符
        
        Returns:
            str: provider 名称，如 "tencent"、"dmxapi"
        """
        pass
    
    @abstractmethod
    def step1_submit_task(self, img_urls: Optional[list], prompt: str, 
                          ratio: str, resolution: str) -> Optional[str]:
        """
        第一步：提交生图任务
        
        每次 Bash 调用必须在 60 秒内完成。本函数通常 5-30 秒内完成。
        
        Args:
            img_urls: 参考图片 URL 列表（文本生图传 None 或空列表）
            prompt: 图片描述提示词
            ratio: 宽高比，如 "1:1"、"16:9"、"3:4"
            resolution: 分辨率，如 "1K"、"2K"、"4K"
            
        Returns:
            str: 任务 ID（成功）
            None: 提交失败
            
        输出标记（供外层解析）:
            [TASK_ID] xxx  - 成功，提取 task_id 供 step2 使用
            [ERROR] xxx    - 失败
        """
        pass
    
    @abstractmethod
    def step2_poll_task(self, task_id: str, max_poll_time: int) -> Optional[str]:
        """
        第二步：轮询任务状态
        
        每次 Bash 调用必须在 60 秒内完成。本函数最多轮询 max_poll_time 秒。
        
        Args:
            task_id: 第一步返回的任务 ID
            max_poll_time: 单次轮询最大时间（秒），默认 50
            
        Returns:
            str: 图片 URL（任务完成）
            "PENDING": 任务仍在处理中，需再次调用本函数
            None: 任务失败
            
        输出标记（供外层解析）:
            [FILE_URL] xxx - 任务完成，提取 file_url 供 step3 使用
            [PENDING]      - 任务进行中，需要再次运行 step2
            [ERROR] xxx    - 任务失败
        """
        pass
    
    @abstractmethod
    def step3_download_and_upload(self, file_url: str) -> Optional[str]:
        """
        第三步：下载生成的图片并上传到 R2 CDN
        
        每次 Bash 调用必须在 60 秒内完成。本函数通常 5-30 秒内完成。
        
        Args:
            file_url: 第二步返回的图片 URL
            
        Returns:
            str: R2 CDN URL（成功）
            None: 下载或上传失败
            
        输出标记（供外层解析）:
            [IMAGE_URL] xxx - 成功，这是最终返回给用户的 URL
            [ERROR] xxx     - 失败
        """
        pass
