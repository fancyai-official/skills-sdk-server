"""
DMXAPI 适配器（同步模式，step1 直接出结果）
"""

from base_three_step_nano_banana_adapter import BaseThreeStepNanoBananaAdapter



class DmxApiAdapter(BaseThreeStepNanoBananaAdapter):
    """DMXAPI 适配器（同步模式，step1 直接出结果）"""

    @property
    def NAME(self) -> str:
        """Provider 标识符"""
        return "dmxapi"

    # task_id 前缀，用于标识 DMXAPI 的同步结果
    DONE_PREFIX = "dmxapi_done:"

    def __init__(self):
        from dmxapi_nano_banana_image_generator import DmxApiNanoBananaImageGenerator
        self._gen = DmxApiNanoBananaImageGenerator()

    @staticmethod
    def _map_resolution(resolution):
        valid = {"1K", "2K", "4K"}
        return resolution if resolution in valid else "1K"

    def step1_submit_task(self, img_urls, prompt, ratio, resolution):
        """
        DMXAPI 是同步 API，step1 直接完成生图+上传 R2。
        返回一个特殊 task_id (dmxapi_done:<image_url>)，
        使 step2/step3 可以直接提取结果。
        """
        try:
            image_size = self._map_resolution(resolution)

            if not img_urls:
                result = self._gen.text_to_image(
                    prompt=prompt, aspect_ratio=ratio,
                    image_size=image_size, output_dir="output"
                )
            elif len(img_urls) == 1:
                result = self._gen.image_to_image(
                    input_image_path=img_urls[0], prompt=prompt,
                    aspect_ratio=ratio, image_size=image_size,
                    output_dir="output"
                )
            else:
                result = self._gen.images_to_image(
                    input_image_paths=img_urls, prompt=prompt,
                    aspect_ratio=ratio, image_size=image_size,
                    output_dir="output"
                )

            if result.get("success") and result.get("image_url"):
                # 将最终 URL 编码进 task_id
                task_id = f"{self.DONE_PREFIX}{result['image_url']}"
                print(f"[TASK_ID] {task_id}")
                return task_id

            print(f"[ERROR] DMXAPI 生图失败: {result.get('error', '未知错误')}")
            return None
        except Exception as e:
            print(f"[ERROR] DMXAPI 生图异常: {e}")
            return None

    def step2_poll_task(self, task_id, max_poll_time):
        """DMXAPI 同步完成，直接从 task_id 中提取 URL"""
        if task_id and task_id.startswith(self.DONE_PREFIX):
            file_url = task_id[len(self.DONE_PREFIX):]
            print(f"[FILE_URL] {file_url}")
            return file_url
        print("[ERROR] DMXAPI: 无效的 task_id")
        return None

    def step3_download_and_upload(self, file_url):
        """DMXAPI 已在 step1 自动上传到 R2，直接返回 URL"""
        if file_url:
            print(f"[IMAGE_URL] {file_url}")
            return file_url
        print("[ERROR] DMXAPI: file_url 为空")
        return None
