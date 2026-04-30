"""
图片生成器工厂 - 向后兼容入口

本文件提供向后兼容的导入接口，内部委托给重构后的模块。
所有函数签名保持不变，确保现有代码无需修改。
"""

# 导入单任务三步接口
from nano_banana_image_generator import (
    step1_submit_task,
    step2_poll_task,
    step3_download_and_upload,
)

# 导入批量处理接口（包装函数）
from nano_banana_batch_util import (
    batch_step1_submit_tasks as _batch_step1,
    batch_step2_poll_tasks as _batch_step2,
    batch_step3_download_and_upload as _batch_step3,
)
from typing import List, Dict


# ============================================================
# 批量接口包装函数（保持原有签名）
# ============================================================

def batch_step1_submit_tasks(tasks: List[Dict], max_workers: int = 3) -> List[Dict]:
    """
    批量并行提交多个生图任务。
    
    详细文档参见 nano_banana_batch_util.batch_step1_submit_tasks
    """
    return _batch_step1(step1_submit_task, tasks, max_workers)


def batch_step2_poll_tasks(
    task_infos: List[Dict],
    max_poll_time: int = 50,
    max_workers: int = 9
) -> List[Dict]:
    """
    批量并行轮询多个任务状态。
    
    详细文档参见 nano_banana_batch_util.batch_step2_poll_tasks
    """
    return _batch_step2(step2_poll_task, task_infos, max_poll_time, max_workers)


def batch_step3_download_and_upload(
    file_infos: List[Dict],
    max_workers: int = 3
) -> List[Dict]:
    """
    批量并行下载图片并上传到 R2 CDN。
    
    详细文档参见 nano_banana_batch_util.batch_step3_download_and_upload
    """
    return _batch_step3(step3_download_and_upload, file_infos, max_workers)


# ============================================================
# 导出列表（明确公开 API）
# ============================================================


__all__ = [
    # 单任务三步接口
    "step1_submit_task",
    "step2_poll_task",
    "step3_download_and_upload",
    # 批量处理接口
    "batch_step1_submit_tasks",
    "batch_step2_poll_tasks",
    "batch_step3_download_and_upload",
]
