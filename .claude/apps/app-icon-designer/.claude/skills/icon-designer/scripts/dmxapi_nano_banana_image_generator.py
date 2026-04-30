"""
DMXAPI Banana 图片生成工具类
支持文本生图、图生图、多图生图功能
基于 Gemini 3 Pro Image Preview 模型
"""

import time
import requests
import base64
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime



class DmxApiNanoBananaImageGenerator:
    """DMXAPI 图片生成工具类"""
    
    # 支持的宽高比
    ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
    
    # 支持的分辨率
    IMAGE_SIZES = ["1K", "2K", "4K"]
    
    # 响应模式
    RESPONSE_MODALITIES = {
        "IMAGE_ONLY": ["IMAGE"],
        "TEXT_AND_IMAGE": ["TEXT", "IMAGE"]
    }
    
    def __init__(self, api_key: str = None, base_url: str = "https://www.dmxapi.com/v1beta",
                 image_base_url: str = None):
        """
        初始化 DMXAPI 图片生成器
        
        Args:
            api_key: DMXAPI 密钥
            base_url: API 基础地址
            image_base_url: 图片访问的基础 URL（仅在 R2 上传不可用时作为备选）。
                           如果不设置且 R2 也不可用，则使用 file:// 协议 + 绝对路径。
        """
        self.api_key = api_key if api_key else os.environ["DMX_API_KEY"]
        self.base_url = base_url
        self.image_base_url = image_base_url
        self.model = "gemini-3-pro-image-preview"
        
        # 初始化上传器（根据 APP_LANG 自动选择 R2 或 OBS）
        self._uploader = None
        try:
            from uploader_factory import get_uploader
            uploader = get_uploader()
            if uploader.is_connected():
                self._uploader = uploader
                print("CDN 上传器已连接，生成的图片将自动上传到 CDN")
            else:
                print("CDN 上传器连接失败，将使用本地路径作为 image_url")
        except Exception as e:
            print(f"R2 上传器不可用 ({e})，将使用本地路径作为 image_url")
        
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        
    def _downloadImage(self, url, max_retries=3, wait_time=2, timeout=60):
        print("downloadImage " + url + " start.")
        retries = 0
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/56.0.2924.76 Safari/537.36',
            "Upgrade-Insecure-Requests": "1", "DNT": "1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5", "Accept-Encoding": "gzip, deflate"}
        while retries < max_retries:
            try:
                response = requests.get(url, headers=headers, stream=True, timeout=timeout)
                print("downloadImage " + url + " finished.")
                if response.status_code == 200:
                    return response.content
                else:
                    raise Exception(f"Failed to download video. Status code: {response.status_code}")
            except Exception as e:
                print(f"Error downloading image from {url}: {e}")
                retries += 1
                if retries < max_retries:
                    print(f"Retrying in {wait_time} seconds... ({retries}/{max_retries})")
                    time.sleep(wait_time)
        raise Exception(f"Failed to download image from {url} after {max_retries} attempts")
    
    def _encode_image_to_base64(self, image_path: str) -> Tuple[str, str]:
        """
        将图片编码为 base64
        
        Args:
            image_path: 图片文件路径或图片 URL
            
        Returns:
            (base64_string, mime_type) 元组
        """
        # 判断是 URL 还是本地文件路径
        is_url = image_path.startswith(('http://', 'https://'))
        
        if is_url:
            # 从 URL 下载图片，使用带重试机制的下载方法
            try:
                image_data = self._downloadImage(image_path)
                
                # 从 URL 路径提取扩展名来确定 mime_type
                ext = os.path.splitext(image_path.split('?')[0])[1].lower()
                mime_types = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                }
                mime_type = mime_types.get(ext, 'image/jpeg')
            except Exception as e:
                raise Exception(f"从 URL 下载图片失败: {str(e)}")
        else:
            # 本地文件路径
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"图片文件不存在: {image_path}")
            
            ext = os.path.splitext(image_path)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
            }
            mime_type = mime_types.get(ext, 'image/jpeg')
            
            with open(image_path, 'rb') as f:
                image_data = f.read()
        
        return base64.b64encode(image_data).decode('utf-8'), mime_type
    
    def _extract_image_from_response(self, response_data: Dict) -> Optional[bytes]:
        """
        从响应中提取图片数据
        支持两种返回格式：
        1. 标准格式: {"inlineData": {"mimeType": "...", "data": "..."}}
        2. 非标准格式: {"text": "data:image/png;base64,..."}
        
        Args:
            response_data: API 响应的 JSON 数据
            
        Returns:
            图片二进制数据，如果未找到则返回 None
        """
        candidates = response_data.get("candidates", [])
        
        for candidate in candidates:
            parts = candidate.get("content", {}).get("parts", [])
            
            for part in parts:
                # 方式1: 标准 inlineData 格式
                if "inlineData" in part:
                    image_data = part["inlineData"].get("data", "")
                    if image_data:
                        return base64.b64decode(image_data)
                
                # 方式2: 文本格式的 base64 数据
                elif "text" in part:
                    text = part["text"]
                    # 检查是否是 data:image/xxx;base64, 格式
                    if text.startswith("data:image/") and ";base64," in text:
                        # 提取 base64 部分
                        base64_data = text.split(";base64,", 1)[1]
                        return base64.b64decode(base64_data)
        
        return None
    
    def _extract_text_from_response(self, response_data: Dict) -> Optional[str]:
        """
        从响应中提取文本数据
        
        Args:
            response_data: API 响应的 JSON 数据
            
        Returns:
            文本内容，如果未找到则返回 None
        """
        candidates = response_data.get("candidates", [])
        
        for candidate in candidates:
            parts = candidate.get("content", {}).get("parts", [])
            
            for part in parts:
                if "text" in part:
                    text = part["text"]
                    # 排除 base64 数据格式的文本
                    if not (text.startswith("data:image/") and ";base64," in text):
                        return text
        
        return None
    
    def _save_image(self, image_bytes: bytes, output_dir: str = "output", 
                    filename_prefix: str = "generated_image") -> Tuple[str, str]:
        """
        保存图片到本地文件，并上传到 R2 获取 CDN URL
        
        Args:
            image_bytes: 图片二进制数据
            output_dir: 输出目录
            filename_prefix: 文件名前缀
            
        Returns:
            (image_path, image_url) 元组:
                - image_path: 本地绝对文件路径
                - image_url: R2 CDN URL（优先），或 image_base_url 拼接的 URL，或 file:// URL
        """
        # 1. 保存到本地
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        relative_path = f"{output_dir}/{filename_prefix}_{timestamp}.png"
        absolute_path = os.path.abspath(relative_path)
        
        with open(relative_path, 'wb') as f:
            f.write(image_bytes)
        
        # 2. 上传到 CDN 获取 URL（优先）
        image_url = None
        if self._uploader:
            r2_url = self._uploader.upload_bytes(image_bytes, extension='png')
            if r2_url:
                image_url = r2_url
        
        # 3. R2 不可用时使用备选方案
        if not image_url:
            if self.image_base_url:
                image_url = f"{self.image_base_url.rstrip('/')}/{relative_path}"
            else:
                image_url = f"file://{absolute_path}"
        
        return absolute_path, image_url
    
    def text_to_image(self, 
                     prompt: str,
                     aspect_ratio: str = "1:1",
                     image_size: Optional[str] = None,
                     response_mode: str = "IMAGE_ONLY",
                     use_google_search: bool = False,
                     save_to_file: bool = True,
                     output_dir: str = "output") -> Dict:
        """
        文本生成图片
        
        Args:
            prompt: 图片生成提示词
            aspect_ratio: 宽高比 (1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9)
            image_size: 分辨率 (1K, 2K, 4K)，None 为默认 1K
            response_mode: 响应模式 (IMAGE_ONLY 或 TEXT_AND_IMAGE)
            use_google_search: 是否使用 Google 搜索工具
            save_to_file: 是否保存到文件
            output_dir: 输出目录
            
        Returns:
            包含结果的字典: {"success": bool, "image_path": str, "image_url": str, "text": str, "error": str}
        """
        if aspect_ratio not in self.ASPECT_RATIOS:
            return {"success": False, "error": f"不支持的宽高比: {aspect_ratio}"}
        
        if image_size and image_size not in self.IMAGE_SIZES:
            return {"success": False, "error": f"不支持的分辨率: {image_size}"}
        
        # 构建请求体
        payload = {
            "model": self.model,
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseModalities": self.RESPONSE_MODALITIES[response_mode],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                }
            }
        }
        
        # 添加分辨率配置（仅当指定时）
        if image_size:
            payload["generationConfig"]["imageConfig"]["imageSize"] = image_size
        
        # 添加 Google 搜索工具（如果需要）
        if use_google_search:
            payload["tools"] = [{"google_search": {}}]
            # 使用搜索工具时必须返回文本
            payload["generationConfig"]["responseModalities"] = self.RESPONSE_MODALITIES["TEXT_AND_IMAGE"]
        
        # 发送请求
        api_url = f"{self.base_url}/models/{self.model}:generateContent"
        
        try:
            response = requests.post(
                api_url,
                headers=self._get_headers(),
                json=payload,
                timeout=(30, 300)
            )
            
            response.raise_for_status()
            result_data = response.json()
            
            # 提取图片
            image_bytes = self._extract_image_from_response(result_data)
            text_content = self._extract_text_from_response(result_data)
            
            result = {"success": True}
            
            if image_bytes:
                if save_to_file:
                    image_path, image_url = self._save_image(image_bytes, output_dir, "text_to_image")
                    result["image_path"] = image_path
                    result["image_url"] = image_url
                else:
                    result["image_bytes"] = image_bytes
            else:
                result["success"] = False
                result["error"] = "响应中未找到图片数据"
            
            if text_content:
                result["text"] = text_content
            
            return result
            
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"请求失败: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"处理失败: {str(e)}"}
    
    def image_to_image(self,
                      input_image_path: str,
                      prompt: str,
                      aspect_ratio: str = "1:1",
                      image_size: Optional[str] = None,
                      response_mode: str = "IMAGE_ONLY",
                      use_google_search: bool = False,
                      save_to_file: bool = True,
                      output_dir: str = "output") -> Dict:
        """
        图片生成图片（图片编辑）
        
        Args:
            input_image_path: 输入图片路径或图片 URL
            prompt: 图片编辑提示词
            aspect_ratio: 宽高比
            image_size: 分辨率
            response_mode: 响应模式
            use_google_search: 是否使用 Google 搜索工具
            save_to_file: 是否保存到文件
            output_dir: 输出目录
            
        Returns:
            包含结果的字典
        """
        try:
            # 编码输入图片
            img_base64, mime_type = self._encode_image_to_base64(input_image_path)
        except Exception as e:
            return {"success": False, "error": f"图片编码失败: {str(e)}"}
        
        # 构建请求体
        payload = {
            "model": self.model,
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": img_base64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "responseModalities": self.RESPONSE_MODALITIES[response_mode],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                }
            }
        }
        
        if image_size:
            payload["generationConfig"]["imageConfig"]["imageSize"] = image_size
        
        if use_google_search:
            payload["tools"] = [{"google_search": {}}]
            payload["generationConfig"]["responseModalities"] = self.RESPONSE_MODALITIES["TEXT_AND_IMAGE"]
        
        # 发送请求
        api_url = f"{self.base_url}/models/{self.model}:generateContent"
        
        try:
            response = requests.post(
                api_url,
                headers=self._get_headers(),
                json=payload,
                timeout=(30, 300)
            )
            
            response.raise_for_status()
            result_data = response.json()
            
            # 提取图片
            image_bytes = self._extract_image_from_response(result_data)
            text_content = self._extract_text_from_response(result_data)
            
            result = {"success": True}
            
            if image_bytes:
                if save_to_file:
                    image_path, image_url = self._save_image(image_bytes, output_dir, "image_to_image")
                    result["image_path"] = image_path
                    result["image_url"] = image_url
                else:
                    result["image_bytes"] = image_bytes
            else:
                result["success"] = False
                result["error"] = "响应中未找到图片数据"
            
            if text_content:
                result["text"] = text_content
            
            return result
            
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"请求失败: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"处理失败: {str(e)}"}
    
    def images_to_image(self,
                       input_image_paths: List[str],
                       prompt: str,
                       aspect_ratio: str = "1:1",
                       image_size: Optional[str] = None,
                       response_mode: str = "IMAGE_ONLY",
                       use_google_search: bool = False,
                       save_to_file: bool = True,
                       output_dir: str = "output") -> Dict:
        """
        多图生成图片（图片融合）
        注意: 最多支持 14 张参考图片
        - 最多 6 张高保真对象图片
        - 最多 5 张人像照片
        
        Args:
            input_image_paths: 输入图片路径或 URL 列表（支持混合使用）
            prompt: 图片融合提示词
            aspect_ratio: 宽高比
            image_size: 分辨率
            response_mode: 响应模式
            use_google_search: 是否使用 Google 搜索工具
            save_to_file: 是否保存到文件
            output_dir: 输出目录
            
        Returns:
            包含结果的字典
        """
        if len(input_image_paths) > 14:
            return {"success": False, "error": "最多支持 14 张参考图片"}
        
        if len(input_image_paths) == 0:
            return {"success": False, "error": "至少需要提供一张图片"}
        
        # 编码所有图片
        image_parts = []
        for path in input_image_paths:
            try:
                img_base64, mime_type = self._encode_image_to_base64(path)
                image_parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": img_base64
                    }
                })
            except Exception as e:
                return {"success": False, "error": f"图片处理失败 ({path}): {str(e)}"}
        
        # 构建请求体
        payload = {
            "model": self.model,
            "contents": [{
                "parts": [
                    {"text": prompt},
                    *image_parts  # 展开所有图片数据
                ]
            }],
            "generationConfig": {
                "responseModalities": self.RESPONSE_MODALITIES[response_mode],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                }
            }
        }
        
        if image_size:
            payload["generationConfig"]["imageConfig"]["imageSize"] = image_size
        
        if use_google_search:
            payload["tools"] = [{"google_search": {}}]
            payload["generationConfig"]["responseModalities"] = self.RESPONSE_MODALITIES["TEXT_AND_IMAGE"]
        
        # 发送请求
        api_url = f"{self.base_url}/models/{self.model}:generateContent"
        
        try:
            response = requests.post(
                api_url,
                headers=self._get_headers(),
                json=payload,
                timeout=(30, 300)
            )
            
            response.raise_for_status()
            result_data = response.json()
            
            # 提取图片
            image_bytes = self._extract_image_from_response(result_data)
            text_content = self._extract_text_from_response(result_data)
            
            result = {"success": True}
            
            if image_bytes:
                if save_to_file:
                    image_path, image_url = self._save_image(image_bytes, output_dir, "images_to_image")
                    result["image_path"] = image_path
                    result["image_url"] = image_url
                else:
                    result["image_bytes"] = image_bytes
            else:
                result["success"] = False
                result["error"] = "响应中未找到图片数据"
            
            if text_content:
                result["text"] = text_content
            
            return result
            
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"请求失败: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"处理失败: {str(e)}"}


# This module is imported by the provider adapter. Configure DMX_API_KEY in the
# environment and call the adapter through generate_icon_design.py.
