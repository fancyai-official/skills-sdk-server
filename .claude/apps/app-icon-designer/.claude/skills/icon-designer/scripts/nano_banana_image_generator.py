"""
Nano Banana 图片生成器 - 核心单任务接口

!!!!! 遵循三步调用原则（适配 Claude sandbox 60 秒网络超时限制）!!!!!

每一步都是独立的函数调用，每次 Bash 执行必须在 60 秒内完成：
  Step 1: step1_submit_task()          — 提交生图任务，返回 task_id     (< 30s)
  Step 2: step2_poll_task()            — 轮询任务状态，返回 file_url    (< 50s)
  Step 3: step3_download_and_upload()  — 下载图片并通过配置的 uploader 返回 URL (< 30s)

支持 provider：
  - "mock"    : 本地占位图 provider，适合开源演示和测试
  - "tencent" : Tencent Cloud AIGC，需自行配置凭据
  - "dmxapi"  : DMXAPI provider，需自行配置凭据
  - "auto"    : Tencent 优先，失败自动切换 DMXAPI

用法（在 sandbox 中每步一次独立 Bash 调用）:

    import sys
    sys.path.insert(0, 'scripts')
    from nano_banana_image_generator import step1_submit_task

    task_id = step1_submit_task(
        prompt="A beautiful sunset",
        ratio="16:9",
        resolution="2K",
        provider="mock"      # or "tencent", "dmxapi", "auto"
    )

函数签名与返回值与原 tencent_nano_banana_image_generator 完全一致，仅多一个 provider 参数。
"""

from typing import Optional, List
from nano_banana_provider_router import ProviderRouter
from nano_banana_fallback_strategy import FallbackStrategy


# ============================================================
# 初始化路由器和降级策略
# ============================================================

_router = ProviderRouter()
_fallback = FallbackStrategy(_router)


# ============================================================
# 公开接口：三步分步函数（主接口，适配 sandbox 60 秒超时）
# ============================================================

def step1_submit_task(
    img_urls: Optional[List[str]] = None,
    prompt: str = "",
    ratio: str = "1:1",
    resolution: str = "2K",
    provider: str = "mock"
) -> Optional[str]:
    """
    第一步：提交生图任务

    每次 Bash 调用必须在 60 秒内完成。本函数通常 5-30 秒内完成。

    Args:
        img_urls:    参考图片 URL 列表（文本生图传 None）
        prompt:      图片描述提示词
        ratio:       宽高比，默认 "1:1"
        resolution:  分辨率 (1K, 2K, 4K)，默认 "2K"
        provider:    "mock" | "tencent" | "dmxapi" | "auto"

    Returns:
        task_id 字符串（成功）或 None（失败）

    输出标记:
        [TASK_ID] xxx  — 成功，提取 task_id 供 step2 使用
        [ERROR] xxx    — 失败
    """
    if provider == "auto":
        return _fallback.execute_step1_with_fallback(img_urls, prompt, ratio, resolution)

    try:
        adapter = _router.get_adapter(provider)
        return adapter.step1_submit_task(img_urls, prompt, ratio, resolution)
    except Exception as e:
        print(f"[ERROR] 提交任务失败: {e}")
        return None


def step2_poll_task(
    task_id: str,
    max_poll_time: int = 50,
    provider: str = "auto"
) -> Optional[str]:
    """
    第二步：轮询任务状态

    每次 Bash 调用必须在 60 秒内完成。本函数最多轮询 50 秒（留 10 秒余量）。

    Args:
        task_id:        第一步返回的任务 ID
        max_poll_time:  单次轮询最大时间（秒），默认 50
        provider:       "tencent" | "dmxapi" | "auto"
                        推荐使用 "auto"，会根据 task_id 格式自动路由

    Returns:
        - 图片 URL 字符串（任务完成）
        - "PENDING"（任务仍在处理中，需再次调用本函数）
        - None（任务失败）

    输出标记:
        [FILE_URL] xxx — 任务完成，提取 file_url 供 step3 使用
        [PENDING]      — 任务进行中，需要再次运行 step2
        [ERROR] xxx    — 任务失败
    """
    # auto 模式：根据 task_id 自动判断 provider
    if provider == "auto":
        provider = _router.detect_provider_from_task_id(task_id)

    try:
        adapter = _router.get_adapter(provider)
        return adapter.step2_poll_task(task_id, max_poll_time)
    except Exception as e:
        print(f"[ERROR] 轮询任务失败: {e}")
        return None


def step3_download_and_upload(
    file_url: str,
    provider: str = "auto"
) -> Optional[str]:
    """
    第三步：下载生成的图片并上传到 R2 CDN

    每次 Bash 调用必须在 60 秒内完成。本函数通常 5-30 秒内完成。

    Args:
        file_url:   第二步返回的图片 URL
        provider:   "tencent" | "dmxapi" | "auto"
                    推荐使用 "auto"，会自动判断是否需要上传

    Returns:
        R2 CDN URL 字符串（成功）或 None（失败）

    输出标记:
        [IMAGE_URL] xxx — 成功，这是最终返回给用户的 URL
        [ERROR] xxx     — 失败
    """
    # auto 模式：如果已经是 CDN URL，直接返回（DMXAPI 的结果已经是 CDN URL）
    if provider == "auto":
        if _router.is_cdn_url(file_url):
            print(f"[IMAGE_URL] {file_url}")
            return file_url
        # 否则走 Tencent 的下载+上传流程
        provider = "tencent"

    try:
        adapter = _router.get_adapter(provider)
        return adapter.step3_download_and_upload(file_url)
    except Exception as e:
        print(f"[ERROR] 下载或上传失败: {e}")
        return None
