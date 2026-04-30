"""Local mock provider for open-source demos.

It preserves the same three-step contract as real image providers, but creates
a deterministic placeholder PNG locally so the example can run without cloud
credentials or paid image-generation APIs.
"""

from __future__ import annotations

import hashlib
import os
import textwrap
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from base_three_step_nano_banana_adapter import BaseThreeStepNanoBananaAdapter


class MockAdapter(BaseThreeStepNanoBananaAdapter):
    DONE_PREFIX = "mock_done:"

    @property
    def NAME(self) -> str:
        return "mock"

    def step1_submit_task(self, img_urls, prompt, ratio, resolution) -> Optional[str]:
        output_dir = Path(os.environ.get("ICON_DESIGNER_OUTPUT_DIR", ".generated/icon-designer/mock"))
        output_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        output_path = output_dir / f"mock-{digest}-{uuid.uuid4().hex[:8]}.png"
        self._render_placeholder(output_path, prompt, ratio)
        task_id = f"{self.DONE_PREFIX}{output_path.resolve().as_uri()}"
        print(f"[TASK_ID] {task_id}")
        return task_id

    def step2_poll_task(self, task_id, max_poll_time):
        if task_id and task_id.startswith(self.DONE_PREFIX):
            file_url = task_id[len(self.DONE_PREFIX):]
            print(f"[FILE_URL] {file_url}")
            return file_url
        print("[ERROR] Mock provider received an invalid task_id")
        return None

    def step3_download_and_upload(self, file_url):
        if file_url:
            print(f"[IMAGE_URL] {file_url}")
            return file_url
        print("[ERROR] Mock provider received an empty file_url")
        return None

    @staticmethod
    def _size_for_ratio(ratio: str) -> tuple[int, int]:
        sizes = {
            "1:1": (1024, 1024),
            "3:4": (900, 1200),
            "4:3": (1200, 900),
            "9:16": (900, 1600),
            "16:9": (1600, 900),
        }
        return sizes.get(ratio, (900, 1200))

    def _render_placeholder(self, output_path: Path, prompt: str, ratio: str) -> None:
        width, height = self._size_for_ratio(ratio)
        image = Image.new("RGB", (width, height), "#f4f1ea")
        draw = ImageDraw.Draw(image)
        draw.rectangle((40, 40, width - 40, height - 40), outline="#1f2937", width=4)
        draw.rectangle((80, 90, width - 80, height - 90), outline="#9ca3af", width=2)

        title = "Icon Designer Mock Output"
        subtitle = "Configure tencent or dmxapi for real image generation."
        prompt_excerpt = " ".join(prompt.split())[:520]
        lines = [title, "", subtitle, "", *textwrap.wrap(prompt_excerpt, width=54)]

        try:
            font_title = ImageFont.truetype("DejaVuSans.ttf", 34)
            font_body = ImageFont.truetype("DejaVuSans.ttf", 22)
        except Exception:
            font_title = ImageFont.load_default()
            font_body = ImageFont.load_default()

        y = 140
        for index, line in enumerate(lines):
            font = font_title if index == 0 else font_body
            draw.text((120, y), line, fill="#111827", font=font)
            y += 44 if index == 0 else 32

        image.save(output_path)
