"""Uploader factory for the open-source sample.

Default behavior is local-only: generated files are kept on disk and returned
as ``file://`` URLs. Set ``UPLOAD_PROVIDER=r2`` and the R2 environment
variables to publish files through Cloudflare R2.
"""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


class LocalUploader:
    """Local fallback that requires no cloud credentials."""

    def __init__(self) -> None:
        self.output_dir = Path(os.environ.get("ICON_DESIGNER_OUTPUT_DIR", ".generated/icon-designer"))
        self.public_base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

    def is_connected(self) -> bool:
        return True

    def upload_local_file(self, file_path: str, prefix: str = "uploads", date_str: str = None) -> Optional[str]:
        path = Path(file_path)
        if not path.exists():
            return None
        if not self.public_base_url:
            return path.resolve().as_uri()

        extension = path.suffix.lstrip(".") or "bin"
        target = self._target_path(prefix, extension, date_str)
        shutil.copy2(path, target)
        return self._public_url(target)

    def upload_bytes(self, data: bytes, extension: str = "png", prefix: str = "uploads", date_str: str = None) -> Optional[str]:
        target = self._target_path(prefix, extension, date_str)
        target.write_bytes(data)
        return self._public_url(target) if self.public_base_url else target.resolve().as_uri()

    def upload_and_get_new_url(self, original_url: str, date_str: str = None) -> str:
        return original_url

    def _target_path(self, prefix: str, extension: str, date_str: str = None) -> Path:
        upload_date = date_str or datetime.now().strftime("%Y%m%d")
        target = self.output_dir / prefix / upload_date / f"{uuid.uuid4()}.{extension}"
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _public_url(self, target: Path) -> str:
        rel = target.relative_to(self.output_dir).as_posix()
        return f"{self.public_base_url}/{rel}"


_uploader_instance = None


def get_uploader():
    """Get the configured uploader singleton."""
    global _uploader_instance
    if _uploader_instance is not None:
        return _uploader_instance

    provider = os.environ.get("UPLOAD_PROVIDER", "local").lower()
    if provider == "r2":
        from r2_uploader import get_r2_uploader

        _uploader_instance = get_r2_uploader()
    else:
        _uploader_instance = LocalUploader()

    return _uploader_instance
