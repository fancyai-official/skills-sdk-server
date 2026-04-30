"""
腾讯云 AIGC 适配器（异步任务模式，真正三步走）
"""

from base_three_step_nano_banana_adapter import BaseThreeStepNanoBananaAdapter


class TencentAdapter(BaseThreeStepNanoBananaAdapter):
    """腾讯云 AIGC 适配器（异步任务模式，真正三步走）"""

    @property
    def NAME(self) -> str:
        """Provider 标识符"""
        return "tencent"

    def __init__(self):
        from tencent_nano_banana_image_generator import (
            step1_submit_task,
            step2_poll_task,
            step3_download_and_upload,
        )
        self._step1 = step1_submit_task
        self._step2 = step2_poll_task
        self._step3 = step3_download_and_upload

    def step1_submit_task(self, img_urls, prompt, ratio, resolution):
        """提交任务 -> 返回 task_id 或 None"""
        return self._step1(img_urls=img_urls, prompt=prompt,
                           ratio=ratio, resolution=resolution)

    def step2_poll_task(self, task_id, max_poll_time):
        """轮询状态 -> 返回 file_url / "PENDING" / None"""
        return self._step2(task_id, max_poll_time=max_poll_time)

    def step3_download_and_upload(self, file_url):
        """下载+上传 R2 -> 返回 image_url 或 None"""
        return self._step3(file_url)
