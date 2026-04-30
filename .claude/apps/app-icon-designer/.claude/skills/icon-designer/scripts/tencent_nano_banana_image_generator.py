#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
腾讯云 AIGC 生图/生视频 API - HTTP 请求方式
使用腾讯云点播（VOD）服务的 AIGC 接口

支持功能：
1. AIGC 生图（CreateAigcImageTask）- 支持 Gemini、即梦、千问模型
2. AIGC 生视频（CreateAigcVideoTask）- 支持 Google Veo、Kling、海螺、Seedance、Sora 模型
3. 任务查询（DescribeTaskDetail）
4. 等待任务完成（wait_for_task_completion）

使用方式：
- 设置环境变量或直接传入密钥参数
- 调用 create_aigc_image_task() 生成图片
- 调用 create_aigc_video_task() 生成视频
"""

import hashlib
import hmac
import json
import os
import time
from datetime import datetime
import requests
import tempfile
from urllib.parse import urlparse
from PIL import Image
import io


# 尝试导入 BatchUploadImageUtil，如果不存在则使用本地实现
try:
    from run.worker.util.batch_upload_image_util import BatchUploadImageUtil
except ImportError:
    # 本地实现的图片下载工具类
    class BatchUploadImageUtil:
        """本地实现的图片下载工具类（当外部模块不可用时）"""
        
        @staticmethod
        def downloadImage(url, max_retries=3, wait_time=2, timeout=60):
            """
            下载图片
            
            :param url: 图片 URL
            :param max_retries: 最大重试次数
            :param wait_time: 重试等待时间（秒）
            :param timeout: 请求超时时间（秒）
            :return: 图片数据 (bytes)
            """
            print(f"downloadImage {url} start.")
            retries = 0
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/56.0.2924.76 Safari/537.36',
                "Upgrade-Insecure-Requests": "1", "DNT": "1",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5", "Accept-Encoding": "gzip, deflate"
            }
            while retries < max_retries:
                try:
                    response = requests.get(url, headers=headers, stream=True, timeout=timeout)
                    print(f"downloadImage {url} finished.")
                    if response.status_code == 200:
                        return response.content
                    else:
                        raise Exception(f"Failed to download image. Status code: {response.status_code}")
                except Exception as e:
                    print(f"Error downloading image from {url}: {e}")
                    retries += 1
                    if retries < max_retries:
                        print(f"Retrying in {wait_time} seconds... ({retries}/{max_retries})")
                        time.sleep(wait_time)
            raise Exception(f"Failed to download image from {url} after {max_retries} attempts")


class TencentAigcImageGenerator:
    """腾讯云 AIGC 生图生成器封装类"""
    
    def __init__(self, secret_id=None, secret_key=None, sub_app_id=None):
        """
        初始化腾讯云 API 客户端
        
        :param secret_id: 腾讯云 SecretId，如果不传则从环境变量 TENCENT_SECRET_ID 获取
        :param secret_key: 腾讯云 SecretKey，如果不传则从环境变量 TENCENT_SECRET_KEY 获取
        :param sub_app_id: 点播应用 ID，如果不传则从环境变量 TENCENT_SUB_APP_ID 获取
        """
        self.app_id = os.environ["TENCENT_APP_ID"]
        self.secret_id = os.environ["TENCENT_SECRET_ID"]
        self.secret_key = os.environ["TENCENT_SECRET_KEY"]
        self.sub_app_id = os.environ["TENCENT_SUB_APP_ID"]
        self.region = "ap-guangzhou"
        
        if not self.secret_id or not self.secret_key:
            raise ValueError("请设置腾讯云 SecretId 和 SecretKey")
        
        if not self.sub_app_id:
            raise ValueError("请设置点播应用 SubAppId")
        
        self.host = "vod.tencentcloudapi.com"
        self.service = "vod"
        self.version = "2018-07-17"
        self.algorithm = "TC3-HMAC-SHA256"
        self.endpoint = f"https://{self.host}"
    
    def _sha256_hex(self, s):
        """计算 SHA256 哈希值并转换为十六进制字符串"""
        return hashlib.sha256(s.encode("utf-8")).hexdigest()
    
    def _hmac_sha256(self, key, msg):
        """计算 HMAC-SHA256"""
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
    
    def _get_signature(self, action, payload, timestamp):
        """
        生成签名（TC3-HMAC-SHA256）
        
        :param action: 接口名称
        :param payload: 请求体（JSON字符串）
        :param timestamp: 请求时间戳
        :return: Authorization 头部值
        """
        # 步骤 1：拼接规范请求串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_query_string = ""
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{self.host}\nx-tc-action:{action.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = self._sha256_hex(payload)
        canonical_request = (
            http_request_method + "\n" +
            canonical_uri + "\n" +
            canonical_query_string + "\n" +
            canonical_headers + "\n" +
            signed_headers + "\n" +
            hashed_request_payload
        )
        
        # 步骤 2：拼接待签名字符串
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        credential_scope = f"{date}/{self.service}/tc3_request"
        hashed_canonical_request = self._sha256_hex(canonical_request)
        string_to_sign = (
            self.algorithm + "\n" +
            str(timestamp) + "\n" +
            credential_scope + "\n" +
            hashed_canonical_request
        )
        
        # 步骤 3：计算签名
        secret_date = self._hmac_sha256(("TC3" + self.secret_key).encode("utf-8"), date)
        secret_service = self._hmac_sha256(secret_date, self.service)
        secret_signing = self._hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        
        # 步骤 4：拼接 Authorization
        authorization = (
            self.algorithm + " " +
            "Credential=" + self.secret_id + "/" + credential_scope + ", " +
            "SignedHeaders=" + signed_headers + ", " +
            "Signature=" + signature
        )
        
        return authorization
    
    # @staticmethod
    # def _resize_and_compress_image(image_data, max_size_bytes=5 * 1024 * 1024, max_dimension=3500):
    #     """
    #     缩放并压缩图片以满足大小限制
        
    #     :param image_data: 图片数据（bytes）
    #     :param max_size_bytes: 最大文件大小（字节），默认 5MB
    #     :param max_dimension: 最大边长（像素），默认 5000
    #     :return: 压缩后的图片数据（bytes）
    #     """
    #     # 打开图片
    #     img = Image.open(io.BytesIO(image_data))
        
    #     # 转换为 RGB 模式（处理 RGBA 和其他模式）
    #     if img.mode in ('RGBA', 'LA', 'P'):
    #         # 创建白色背景
    #         background = Image.new('RGB', img.size, (255, 255, 255))
    #         if img.mode == 'P':
    #             img = img.convert('RGBA')
    #         background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
    #         img = background
    #     elif img.mode != 'RGB':
    #         img = img.convert('RGB')
        
    #     original_width, original_height = img.size
    #     need_resize = False
        
    #     # 检查是否需要缩放
    #     if original_width > max_dimension or original_height > max_dimension:
    #         need_resize = True
    #         # 计算缩放比例
    #         if original_width > original_height:
    #             new_width = max_dimension
    #             new_height = int(original_height * max_dimension / original_width)
    #         else:
    #             new_height = max_dimension
    #             new_width = int(original_width * max_dimension / original_height)
            
    #         print(f"图片尺寸 {original_width}x{original_height} 超过限制，缩放至 {new_width}x{new_height}")
    #         img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
    #     # 保存为 JPG 格式并压缩
    #     output = io.BytesIO()
    #     quality = 100  # 起始质量
        
    #     output.seek(0)
    #     output.truncate()
    #     img.save(output, format='JPEG', quality=quality, optimize=True)
        
    #     result_data = output.getvalue()
    #     result_size = len(result_data)
        
    #     if need_resize or len(image_data) > max_size_bytes:
    #         print(f"图片处理完成: {len(image_data) / 1024:.2f}KB -> {result_size / 1024:.2f}KB (质量: {quality})")
    #     else:
    #         print(f"图片转换为 JPG 格式: {result_size / 1024:.2f}KB")
        
    #     return result_data
    
    @staticmethod
    def _resize_and_compress_image(image_bytes, max_size_mb=5, max_dimension=5000):
        """
        压缩图片并转换为 JPG 格式
        
        :param image_bytes: 图片的 bytes 数据
        :param max_size_mb: 最大文件大小（MB）
        :param max_dimension: 最大尺寸（像素）
        :return: 处理后的 JPG 图片 bytes 数据
        """
        original_size = len(image_bytes)
        print(f"原始文件大小: {original_size / 1024:.2f} KB")
        
        # 如果文件大于限制，进行压缩处理
        if original_size > max_size_mb * 1024 * 1024:
            print(f"⚠️  图片大于 {max_size_mb}MB，开始压缩处理...")
            
            # 使用 PIL 打开图片
            img = Image.open(io.BytesIO(image_bytes))
            print(f"原始尺寸: {img.size[0]} x {img.size[1]} 像素")
            
            # 检查是否需要缩放
            max_dim = max(img.size)
            if max_dim > max_dimension:
                # 计算缩放比例
                scale = max_dimension / max_dim
                new_width = int(img.size[0] * scale)
                new_height = int(img.size[1] * scale)
                
                # 缩放图片
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"✅ 图片已缩放到: {new_width} x {new_height} 像素")
            else:
                print(f"图片尺寸未超过 {max_dimension} 像素，仅转换格式")
            
            # 转换为 RGB 模式（JPEG 不支持透明通道，透明部分用白色填充）
            if img.mode in ('RGBA', 'LA'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                # 使用 alpha 通道作为遮罩，将图片粘贴到白色背景上
                background.paste(img, mask=img.split()[-1])
                img = background
                print(f"✅ 已将透明通道转换为白色背景")
            elif img.mode == 'P':
                # 调色板模式，检查是否有透明度
                if 'transparency' in img.info:
                    # 先转换为 RGBA 以保留透明信息
                    img = img.convert('RGBA')
                    # 创建白色背景
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    # 使用 alpha 通道作为遮罩
                    background.paste(img, mask=img.split()[-1])
                    img = background
                    print(f"✅ 已将透明通道转换为白色背景")
                else:
                    # 没有透明度，直接转换为 RGB
                    img = img.convert('RGB')
            elif img.mode != 'RGB':
                # 其他模式直接转换为 RGB
                img = img.convert('RGB')
            
            # 保存为 JPEG 格式
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=100, optimize=True)
            image_bytes = output.getvalue()
            
            compressed_size = len(image_bytes)
            print(f"✅ 压缩完成: {compressed_size / 1024:.2f} KB (压缩率: {(1 - compressed_size/original_size)*100:.1f}%)")
            
            # 如果压缩后仍然超出限制，继续迭代降低像素尺寸
            scale_factor = 0.9  # 每次缩小到原来的 90%
            iteration = 0
            max_iterations = 20  # 最多迭代 20 次，避免无限循环
            
            while compressed_size > max_size_mb * 1024 * 1024 and iteration < max_iterations:
                iteration += 1
                # 计算新的尺寸
                new_width = int(img.size[0] * scale_factor)
                new_height = int(img.size[1] * scale_factor)
                
                # 确保尺寸不会太小
                if new_width < 100 or new_height < 100:
                    print(f"⚠️  图片尺寸已降至最小限制 ({new_width}x{new_height})，停止压缩")
                    break
                
                # 缩小图片
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # 重新保存
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=100, optimize=True)
                image_bytes = output.getvalue()
                compressed_size = len(image_bytes)
                
                print(f"🔄 继续压缩 (第{iteration}次，尺寸={new_width}x{new_height}): {compressed_size / 1024:.2f} KB (压缩率: {(1 - compressed_size/original_size)*100:.1f}%)")
            
            # 最终检查是否满足大小要求
            if compressed_size > max_size_mb * 1024 * 1024:
                raise ValueError(f"即使降低到最小尺寸，图片仍大于 {max_size_mb}MB: {compressed_size / 1024 / 1024:.2f}MB")
        
        return image_bytes
    
    def _make_request(self, action, params):
        """
        发起 HTTP 请求
        
        :param action: 接口名称
        :param params: 请求参数字典
        :return: 响应结果
        """
        # 准备请求数据
        timestamp = int(time.time())
        payload = json.dumps(params)
        
        # 生成签名
        authorization = self._get_signature(action, payload, timestamp)
        
        # 构建请求头
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": self.host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.version,
        }
        
        # 发起请求
        try:
            response = requests.post(self.endpoint, headers=headers, data=payload, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"响应内容: {e.response.text}")
            raise
    
    def create_aigc_image_task(
        self,
        model_name,
        model_version,
        prompt=None,
        file_infos=None,
        negative_prompt=None,
        enhance_prompt=None,
        generation_mode=None,
        output_config=None,
        session_id=None,
        session_context=None,
        tasks_priority=None,
        ext_info=None
    ):
        """
        创建 AIGC 生图任务
        
        :param model_name: 模型名称。取值：GEM（Gemini）、Seedream（即梦）、Qwen（千问）
        :param model_version: 模型版本。GEM=2.5, Seedream=4.0, Qwen=2.0
        :param prompt: 生成图片的提示词（最大1000字符）
        :param file_infos: 输入图片文件信息列表（最多3个）
        :param negative_prompt: 负面提示词（最大500字符）
        :param enhance_prompt: 是否自动优化提示词。取值：Enabled、Disabled
        :param generation_mode: 生成模式。取值：Standard（标准）、Professional（高品质）
        :param output_config: 输出媒体文件配置
        :param session_id: 去重识别码（最长50字符）
        :param session_context: 来源上下文（最长1000字符）
        :param tasks_priority: 任务优先级（-10到10）
        :param ext_info: 保留字段
        :return: 返回 TaskId
        """
        # 构建请求参数
        params = {
            "SubAppId": int(self.sub_app_id),
            "ModelName": model_name,
            "ModelVersion": model_version,
        }
        
        # 添加可选参数
        if file_infos is not None:
            params["FileInfos"] = file_infos
        
        if prompt is not None:
            params["Prompt"] = prompt
        
        if negative_prompt is not None:
            params["NegativePrompt"] = negative_prompt
        
        if enhance_prompt is not None:
            params["EnhancePrompt"] = enhance_prompt
        
        if generation_mode is not None:
            params["GenerationMode"] = generation_mode
        
        if output_config is not None:
            params["OutputConfig"] = output_config
        
        if session_id is not None:
            params["SessionId"] = session_id
        
        if session_context is not None:
            params["SessionContext"] = session_context
        
        if tasks_priority is not None:
            params["TasksPriority"] = tasks_priority
        
        if ext_info is not None:
            params["ExtInfo"] = ext_info
        
        # 发起请求
        result = self._make_request("CreateAigcImageTask", params)
        
        # 返回结果
        if "Response" in result:
            response = result["Response"]
            if "Error" in response:
                error = response["Error"]
                raise Exception(f"API 错误: {error.get('Code')} - {error.get('Message')}")
            return response
        
        return result
    
    def describe_task_detail(self, task_id):
        """
        查询任务详情
        
        :param task_id: 任务 ID
        :return: 任务详情
        """
        params = {
            "TaskId": task_id,
            "SubAppId": int(self.sub_app_id),
        }
        
        result = self._make_request("DescribeTaskDetail", params)
        
        # 返回结果
        if "Response" in result:
            response = result["Response"]
            if "Error" in response:
                error = response["Error"]
                raise Exception(f"API 错误: {error.get('Code')} - {error.get('Message')}")
            return response
        
        return result
    
    def wait_for_task_completion(self, task_id, max_wait_time=600, check_interval=5):
        """
        等待任务完成
        
        :param task_id: 任务 ID
        :param max_wait_time: 最大等待时间（秒）
        :param check_interval: 检查间隔（秒）
        :return: 任务结果
        """
        start_time = time.time()
        
        while True:
            # 检查是否超时
            if time.time() - start_time > max_wait_time:
                raise TimeoutError(f"任务 {task_id} 等待超时")
            
            # 查询任务状态
            result = self.describe_task_detail(task_id)
            status = result.get("Status")
            
            print(f"任务状态: {status}")
            
            if status == "FINISH":
                print("任务完成！")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                # return result
                
                # 检查返回结果的完整性
                if "AigcImageTask" not in result:
                    raise Exception(f"任务完成但返回结果中缺少 AigcImageTask 字段: {result}")
                
                if "Output" not in result["AigcImageTask"]:
                    raise Exception(f"任务完成但返回结果中缺少 Output 字段: {result}")
                
                if "FileInfos" not in result["AigcImageTask"]["Output"]:
                    raise Exception(f"任务完成但返回结果中缺少 FileInfos 字段: {result}")
                
                file_infos = result["AigcImageTask"]["Output"]["FileInfos"]
                if not file_infos or len(file_infos) == 0:
                    raise Exception(f"任务完成但 FileInfos 为空: {result}")
                
                file_url = file_infos[0]["FileUrl"]
                print(f"✅ 获得 FileUrl: {file_url}")
                return file_url
            elif status == "ABORTED":
                raise Exception(f"任务已终止: {result}")
            elif status in ["WAITING", "PROCESSING"]:
                print(f"任务进行中，{check_interval}秒后再次查询...")
                time.sleep(check_interval)
            else:
                raise Exception(f"未知任务状态: {status}")
    
    def create_aigc_video_task(
        self,
        model_name,
        model_version,
        prompt=None,
        file_infos=None,
        last_frame_file_id=None,
        negative_prompt=None,
        enhance_prompt=None,
        generation_mode=None,
        output_config=None,
        session_id=None,
        session_context=None,
        tasks_priority=None,
        ext_info=None
    ):
        """
        创建 AIGC 生视频任务
        
        :param model_name: 模型名称。取值：Hailuo（海螺）、Kling（可灵）、Seedance、GV（Google Veo）、OS（OpenAI Sora）
        :param model_version: 模型版本
            - Hailuo: 02, 2.3
            - Kling: 2.0, 2.1
            - Seedance: 3.0pro
            - GV: 3.1, 3.1-fast
            - OS: 2.0
        :param prompt: 生成视频的提示词（最大1000字符）
        :param file_infos: 输入图片文件信息列表
            - GV模型最多3个，其他模型最多1个
            - 当GV模型长度>1时，不能指定last_frame_file_id
        :param last_frame_file_id: 用作尾帧的媒体文件ID（仅支持GV和Kling模型）
        :param negative_prompt: 负面提示词（最大500字符）
        :param enhance_prompt: 是否自动优化提示词。取值：Enabled、Disabled
        :param generation_mode: 生成模式。取值：Standard（标准）、Professional（高品质）
        :param output_config: 输出媒体文件配置
        :param session_id: 去重识别码（最长50字符）
        :param session_context: 来源上下文（最长1000字符）
        :param tasks_priority: 任务优先级（-10到10）
        :param ext_info: 保留字段
        :return: 返回 TaskId
        """
        # 构建请求参数
        params = {
            "SubAppId": int(self.sub_app_id),
            "ModelName": model_name,
            "ModelVersion": model_version,
        }
        
        # 添加可选参数
        if file_infos is not None:
            params["FileInfos"] = file_infos
        
        if last_frame_file_id is not None:
            params["LastFrameFileId"] = last_frame_file_id
        
        if prompt is not None:
            params["Prompt"] = prompt
        
        if negative_prompt is not None:
            params["NegativePrompt"] = negative_prompt
        
        if enhance_prompt is not None:
            params["EnhancePrompt"] = enhance_prompt
        
        if generation_mode is not None:
            params["GenerationMode"] = generation_mode
        
        if output_config is not None:
            params["OutputConfig"] = output_config
        
        if session_id is not None:
            params["SessionId"] = session_id
        
        if session_context is not None:
            params["SessionContext"] = session_context
        
        if tasks_priority is not None:
            params["TasksPriority"] = tasks_priority
        
        if ext_info is not None:
            params["ExtInfo"] = ext_info
        
        # 发起请求
        result = self._make_request("CreateAigcVideoTask", params)
        
        # 返回结果
        if "Response" in result:
            response = result["Response"]
            if "Error" in response:
                error = response["Error"]
                raise Exception(f"API 错误: {error.get('Code')} - {error.get('Message')}")
            return response
        
        return result
    
    def gen_file_id(self, image_path_or_url):
        upload_info = self.upload_local_image(image_path_or_url)
        return upload_info['FileId']
    
    # @staticmethod
    def upload_local_image(self, image_path):
        """
        上传本地图片或 URL 图片到腾讯云点播服务（静态方法）
        
        :param image_path: 本地图片路径或图片 URL
                          - 本地路径示例: "/path/to/photo.jpg"
                          - URL 示例: "https://example.com/image.jpg"
        :param secret_id: 腾讯云 SecretId
        :param secret_key: 腾讯云 SecretKey
        :param sub_app_id: 点播应用 ID（可选）
        :param region: 上传地域，默认 "ap-guangzhou"（广州）
        :return: 返回包含 FileId 和 MediaUrl 的字典
        
        示例：
            # 上传本地图片
            result = TencentAigcImageGenerator.upload_local_image(
                image_path="/path/to/image.jpg",
                secret_id="你的SecretId",
                secret_key="你的SecretKey",
                sub_app_id="你的SubAppId"
            )
            
            # 上传 URL 图片
            result = TencentAigcImageGenerator.upload_local_image(
                image_path="https://example.com/image.jpg",
                secret_id="你的SecretId",
                secret_key="你的SecretKey",
                sub_app_id="你的SubAppId"
            )
            
            file_id = result['FileId']
            media_url = result['MediaUrl']
        
        注意：
            1. 需要安装腾讯云 VOD SDK: pip install vod-python-sdk
            2. 需要安装 requests 库（URL 图片下载）: pip install requests
            3. 需要安装 Pillow 库（图片处理）: pip install pillow
            4. 支持的图片格式：jpeg, jpg, png, webp
            5. 图片大小限制：
               - 如果图片大于 5MB，会自动压缩和缩放
               - 缩放规则：最大边不超过 5000 像素
               - 如果各条边都小于 5000 像素，仅转换为 JPG 格式
               - 压缩后的图片质量为 60-95 之间（自动调整）
            6. 地域选项：ap-guangzhou(广州), ap-beijing(北京), ap-shanghai(上海) 等
        """
        try:
            from qcloud_vod.vod_upload_client import VodUploadClient
            from qcloud_vod.model import VodUploadRequest
        except ImportError:
            raise ImportError(
                "需要安装腾讯云 VOD SDK 才能使用上传功能。\n"
                "请运行：pip install vod-python-sdk"
            )
        
        # 判断是 URL 还是本地路径
        is_url = image_path.startswith(('http://', 'https://'))
        temp_file = None
        actual_image_path = image_path
        
        try:
            if is_url:                
                print(f"检测到 URL 图片，开始下载: {image_path}")
                
                # 下载图片
                response_content = BatchUploadImageUtil.downloadImage(image_path)
                
                # 检查文件大小
                file_size = len(response_content)
                print(f"原始文件大小: {file_size / 1024:.2f} KB")
                
                # 如果文件大于 5MB，进行压缩和缩放
                if file_size > 5 * 1024 * 1024:  # 5MB
                    print(f"图片文件过大 ({file_size / 1024 / 1024:.2f}MB)，开始压缩处理...")
                    response_content = self._resize_and_compress_image(response_content)
                    file_size = len(response_content)
                    
                    # 再次检查压缩后的大小
                    if file_size > 5 * 1024 * 1024:
                        raise ValueError(f"图片压缩后仍然过大: {file_size / 1024 / 1024:.2f}MB，必须小于 5MB")
                
                # 创建临时文件（统一使用 .jpg 后缀，因为压缩后都是 JPG 格式）
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                temp_file.write(response_content)
                temp_file.close()
                actual_image_path = temp_file.name
                
                print(f"✅ URL 图片下载成功")
                print(f"   最终文件大小: {file_size / 1024:.2f} KB")
                print(f"   临时文件: {actual_image_path}")
                
            else:
                # 处理本地文件
                # 检查文件是否存在
                if not os.path.exists(image_path):
                    raise FileNotFoundError(f"图片文件不存在: {image_path}")
                
                # 检查文件大小
                file_size = os.path.getsize(image_path)
                print(f"本地图片: {image_path}")
                print(f"原始文件大小: {file_size / 1024:.2f} KB")
                
                # 如果文件大于 5MB，进行压缩和缩放
                if file_size > 5 * 1024 * 1024:  # 5MB
                    print(f"图片文件过大 ({file_size / 1024 / 1024:.2f}MB)，开始压缩处理...")
                    
                    # 读取文件内容
                    with open(image_path, 'rb') as f:
                        image_data = f.read()
                    
                    # 压缩图片
                    compressed_data = self._resize_and_compress_image(image_data)
                    file_size = len(compressed_data)
                    
                    # 再次检查压缩后的大小
                    if file_size > 5 * 1024 * 1024:
                        raise ValueError(f"图片压缩后仍然过大: {file_size / 1024 / 1024:.2f}MB，必须小于 5MB")
                    
                    # 创建临时文件保存压缩后的图片
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                    temp_file.write(compressed_data)
                    temp_file.close()
                    actual_image_path = temp_file.name
                    print(f"   已创建压缩后的临时文件: {actual_image_path}")
                
                print(f"开始上传图片")
                print(f"最终文件大小: {file_size / 1024:.2f} KB")
            
            # 检查文件格式
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp']
            file_ext = os.path.splitext(actual_image_path)[1].lower()
            if file_ext not in allowed_extensions:
                raise ValueError(f"不支持的图片格式: {file_ext}，支持的格式: {', '.join(allowed_extensions)}")
            
            print(f"上传地域: {self.region}")
            
            # 创建上传客户端
            client = VodUploadClient(self.secret_id, self.secret_key)
            
            # 创建上传请求
            request = VodUploadRequest()
            request.MediaFilePath = actual_image_path
            
            # 设置子应用 ID（如果提供）
            if self.sub_app_id:
                request.SubAppId = int(self.sub_app_id)
            
            # 执行上传
            response = client.upload(self.region, request)
            
            result = {
                'FileId': response.FileId,
                'MediaUrl': response.MediaUrl,
                'RequestId': response.RequestId
            }

            print(f"✅ 图片上传成功！")
            print(f"   FileId: {response.FileId}")
            print(f"   MediaUrl: {response.MediaUrl}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"下载 URL 图片失败: {str(e)}")
        except Exception as e:
            raise Exception(f"上传图片失败: {str(e)}")
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                    print(f"✅ 临时文件已清理: {temp_file.name}")
                except Exception as e:
                    print(f"⚠️  清理临时文件失败: {str(e)}")


api = TencentAigcImageGenerator()


# ============================================================
# 拆分为三步的生图函数（适配 sandbox 60 秒网络超时限制）
# 每个函数都应在 60 秒内完成
# ============================================================

def step1_submit_task(img_urls=None, prompt="", ratio="1:1", resolution="2K"):
    """
    第一步：提交生图任务
    - 上传参考图片（如有）并创建 AIGC 生图任务
    - 返回 task_id 供后续轮询使用
    
    :param img_urls: 输入图片 URL 列表（用于图生图/多图融合，文本生图时传 None）
    :param prompt: 图片描述提示词
    :param ratio: 宽高比，默认 "1:1"
    :param resolution: 分辨率 (1K, 2K, 4K)，默认 "2K"
    :return: task_id (字符串) 或 None（失败时）
    """
    try:
        if not prompt:
            prompt = "保持第一张图片的构图不变，只将第一张图片里的鞋子替换为第二张图片里的鞋子。"
        
        file_infos = []
        if img_urls:
            for url in img_urls:
                file_id = api.gen_file_id(image_path_or_url=url)
                file_infos.append({"FileId": file_id})
        
        # 创建生图任务
        result = api.create_aigc_image_task(
            model_name="GEM",
            model_version="3.0",
            file_infos=file_infos,
            prompt=prompt,
            enhance_prompt="Enabled",
            output_config={
                "StorageMode": "Temporary",
                "AspectRatio": ratio,
                "Resolution": resolution
            }
        )
        
        task_id = result.get("TaskId")
        print(f"[TASK_ID] {task_id}")
        return task_id
    except Exception as e:
        print(f"[ERROR] 提交任务失败: {e}")
        return None


def step2_poll_task(task_id, max_poll_time=50):
    """
    第二步：轮询任务状态
    - 在 max_poll_time 秒内反复查询任务状态
    - 如果任务完成，返回生成的图片 URL
    - 如果超时仍未完成，返回 "PENDING" 表示需要再次调用本函数
    
    :param task_id: 第一步返回的任务 ID
    :param max_poll_time: 本次轮询的最大时间（秒），默认 50 秒（留 10 秒余量给 shell 启动）
    :return: 
        - 图片 URL 字符串（任务完成时）
        - "PENDING"（任务仍在进行中，需要再次调用）
        - None（任务失败时）
    """
    try:
        start_time = time.time()
        check_interval = 5
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > max_poll_time:
                print(f"[PENDING] 已轮询 {elapsed:.0f} 秒，任务仍在进行中，请再次调用 step2_poll_task")
                return "PENDING"
            
            result = api.describe_task_detail(task_id)
            status = result.get("Status")
            print(f"任务状态: {status} (已等待 {elapsed:.0f}s)")
            
            if status == "FINISH":
                print("任务完成！")
                # 提取图片 URL
                if "AigcImageTask" not in result:
                    print(f"[ERROR] 返回结果缺少 AigcImageTask 字段")
                    return None
                if "Output" not in result["AigcImageTask"]:
                    print(f"[ERROR] 返回结果缺少 Output 字段")
                    return None
                if "FileInfos" not in result["AigcImageTask"]["Output"]:
                    print(f"[ERROR] 返回结果缺少 FileInfos 字段")
                    return None
                
                file_infos = result["AigcImageTask"]["Output"]["FileInfos"]
                if not file_infos or len(file_infos) == 0:
                    print(f"[ERROR] FileInfos 为空")
                    return None
                
                file_url = file_infos[0]["FileUrl"]
                print(f"[FILE_URL] {file_url}")
                return file_url
                
            elif status == "ABORTED":
                print(f"[ERROR] 任务已终止")
                return None
            elif status in ["WAITING", "PROCESSING"]:
                time.sleep(check_interval)
            else:
                print(f"[ERROR] 未知任务状态: {status}")
                return None
    except Exception as e:
        print(f"[ERROR] 轮询任务失败: {e}")
        return None


def step3_download_and_upload(file_url):
    """
    第三步：下载生成的图片并上传到 R2 CDN
    - 从腾讯云临时 URL 下载图片
    - 上传到 R2 CDN 获取永久 URL
    
    :param file_url: 第二步返回的图片 URL（腾讯云临时 URL）
    :return: R2 CDN URL 字符串，或 None（失败时）
    """
    try:
        from uploader_factory import get_uploader

        # 下载图片
        image_bytes = BatchUploadImageUtil.downloadImage(file_url)

        # 上传到 CDN
        uploader = get_uploader()
        image_url = uploader.upload_bytes(image_bytes, extension='png')
        
        if image_url:
            print(f"[IMAGE_URL] {image_url}")
            return image_url
        else:
            print(f"[ERROR] R2 上传失败")
            return None
    except Exception as e:
        print(f"[ERROR] 下载或上传失败: {e}")
        return None


# ============================================================
# 保留原有的一体化函数（向后兼容）
# ============================================================

def gen_img_by_tencent_nana_banana(img_urls=None, prompt="", ratio="1:1", resolution="2K"):
    """
    一体化生图函数（向后兼容）
    注意：此函数可能运行超过 60 秒，在 sandbox 环境中建议使用分步函数
    """
    try:
        if not prompt:
            prompt = "保持第一张图片的构图不变，只将第一张图片里的鞋子替换为第二张图片里的鞋子。"
        
        file_infos = []
        if img_urls:
            for url in img_urls:
                file_id = api.gen_file_id(image_path_or_url=url)
                file_infos.append({"FileId": file_id})
        
        start_time = time.time()
        
        # 创建生图任务
        result = api.create_aigc_image_task(
            model_name="GEM",
            model_version="3.0",
            file_infos=file_infos,
            prompt=prompt,
            enhance_prompt="Enabled",
            output_config={
                "StorageMode": "Temporary",
                "AspectRatio": ratio,
                "Resolution": resolution
            }
        )
        
        task_id = result.get("TaskId")
        print(f"任务创建成功！TaskId: {task_id}")
        
        # 等待任务完成
        file_url = api.wait_for_task_completion(task_id)

        end_time = time.time()
        print(f"总执行时间: {end_time - start_time:.2f} 秒")

        image_bytes = BatchUploadImageUtil.downloadImage(file_url)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp_file.write(image_bytes)
        temp_file.close()
        
        return [temp_file.name]
    except Exception as e:
        print(f"错误: {e}")
        return None

def gen_vid():
    """示例：使用 AIGC 生图和生视频 API"""
    
    # 初始化 API 客户端
    # 方式1：从环境变量获取（推荐）
    # export TENCENT_SECRET_ID="你的SecretId"
    # export TENCENT_SECRET_KEY="你的SecretKey"
    # export TENCENT_SUB_APP_ID="你的SubAppId"
    api = TencentAigcImageGenerator()
    
    # 方式2：直接传入（不推荐，避免泄露）
    # api = TencentAigcImageGenerator(
    #     secret_id="你的SecretId",
    #     secret_key="你的SecretKey",
    #     sub_app_id="你的SubAppId"
    # )
    
    # 示例3：完整流程 - 从本地图片上传到生成视频（需要本地图片）
    try:
        print("\n" + "=" * 60)
        print("示例：从本地图片到生成视频")
        print("=" * 60)
        image_path_list = [
            "10-20251127_134345-gen.jpg",
            "10-20251127_150634-gen.jpg",
            "10-20251127_160850-gen.jpg",
        ]
        
        for image_path in image_path_list:
            # 步骤1：上传本地图片
            print("\n步骤1：上传本地图片...")
            upload_result = TencentAigcImageGenerator.upload_local_image(
                image_path=image_path,  # 修改为你的本地图片路径
                secret_id=api.secret_id,
                secret_key=api.secret_key,
                sub_app_id=api.sub_app_id
            )
            
            file_id = upload_result['FileId']
            print(f"✅ 获得 FileId: {file_id}")
            
            # 步骤2：使用 FileId 生成视频
            print("\n步骤2：使用图片生成视频...")
            result = api.create_aigc_video_task(
                model_name="Kling",
                model_version="2.1",
                file_infos=[
                    {"FileId": file_id}
                ],
                prompt="场景轻微旋转，添加自然流畅的运动效果，保持商品主体稳定不变形",
                enhance_prompt="Enabled",
                output_config={
                    "StorageMode": "Temporary",
                    # "AudioGeneration": "Disabled"
                }
            )
            
            task_id = result.get("TaskId")
            print(f"✅ 视频任务创建成功！TaskId: {task_id}")
            
            # 等待任务完成
            print("\n等待视频生成完成...")
            final_result = api.wait_for_task_completion(task_id, max_wait_time=600)
            print(json.dumps(final_result, indent=2, ensure_ascii=False))
            
            # 输出结果
            if "AigcVideoResultSet" in final_result:
                video_url = final_result["AigcVideoResultSet"][0].get("Url")
                print(f"\n🎬 视频生成成功！")
                print(f"视频地址: {video_url}")
            
    except Exception as e:
        print(f"错误: {e}")
    
    exit()    
    
    # 示例4-2：使用 OpenAI Sora 模型生成视频
    try:
        result = api.create_aigc_video_task(
            model_name="OS",  # 使用 OpenAI Sora 模型
            model_version="2.0",  # Sora 模型版本 2.0
            prompt="一只可爱的金色小狗在阳光明媚的公园里奔跑玩耍，镜头跟随小狗流畅移动，背景有绿树和蓝天",
            enhance_prompt="Enabled",  # 自动优化提示词
            output_config={
                "StorageMode": "Temporary",  # 临时存储
                "Resolution": "1280x720",  # Sora 支持分辨率：1280*720（横屏）或 720*1280（竖屏）
                "Duration": 4,  # 视频时长（秒），可选值：4、8、12，默认为 8
                "AudioGeneration": "Enabled",  # 生成音频
                "PersonGeneration": "AllowAdult",  # 允许生成成人
                "InputComplianceCheck": "Enabled",  # 输入合规检查
                "OutputComplianceCheck": "Enabled"  # 输出合规检查
            }
        )
        
        task_id = result.get("TaskId")
        print(f"\n✅ Sora 视频任务创建成功！TaskId: {task_id}")
        print(f"RequestId: {result.get('RequestId')}")
        
        # 等待任务完成（视频生成通常需要更长时间）
        print("\n开始等待 Sora 视频任务完成（可能需要较长时间）...")
        print("=" * 60)
        final_result = api.wait_for_task_completion(task_id, max_wait_time=600)  # 最长等待10分钟
        
        print("\n🎬 Sora 视频最终结果:")
        print(json.dumps(final_result, indent=2, ensure_ascii=False))
        
        # 输出结果
        if "AigcVideoResultSet" in final_result:
            video_url = final_result["AigcVideoResultSet"][0].get("Url")
            print(f"\n🎥 Sora 视频生成成功！")
            print(f"视频地址: {video_url}")
        
    except Exception as e:
        print(f"\n❌ Sora 视频生成错误: {e}")
        
    # exit()
    
    # 示例1：纯文本生图
    try:
        result = api.create_aigc_image_task(
            model_name="GEM",  # 使用 Gemini 模型
            model_version="2.5",
            prompt="generate a beautiful sunset over the ocean with palm trees",
            enhance_prompt="Enabled",  # 自动优化提示词
            output_config={
                "StorageMode": "Temporary",  # 临时存储
                "AspectRatio": "16:9",  # 宽高比
                "PersonGeneration": "AllowAdult",  # 允许生成成人
                "InputComplianceCheck": "Enabled",  # 输入合规检查
                "OutputComplianceCheck": "Enabled"  # 输出合规检查
            }
        )
        
        task_id = result.get("TaskId")
        print(f"\n任务创建成功！TaskId: {task_id}")
        print(f"RequestId: {result.get('RequestId')}")
        
        # 等待任务完成
        print("\n开始等待任务完成...")
        print("=" * 60)
        final_result = api.wait_for_task_completion(task_id)
        
        print("\n最终结果:")
        print(json.dumps(final_result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"\n错误: {e}")
    
    # 示例2：带图片输入的生图（如果你有 FileId）
    try:
        result = api.create_aigc_image_task(
            model_name="GEM",
            model_version="3.0",
            file_infos=[
                {"FileId": "你的文件ID"}
            ],
            prompt="modify the image to add more colors",
            output_config={
                "StorageMode": "Temporary",
                "AspectRatio": "1:1",
                "Resolution": "2K"
            }
        )
        
        task_id = result.get("TaskId")
        print(f"任务创建成功！TaskId: {task_id}")
        
        # 等待任务完成
        final_result = api.wait_for_task_completion(task_id)
        print("最终结果:", json.dumps(final_result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"错误: {e}")
    
    print("\n" + "=" * 60)
    print("开始创建 AIGC 生视频任务")
    print("=" * 60)
    
    # 示例4：纯文本生视频（Kling 模型）
    try:
        result = api.create_aigc_video_task(
            model_name="Kling",  # 使用 Kling 模型
            model_version="2.1",  # 注意：只支持 2.0 或 2.1
            prompt="A camera pans across a beautiful beach at sunset with waves crashing gently",
            enhance_prompt="Enabled",  # 自动优化提示词
            output_config={
                "StorageMode": "Temporary",  # 临时存储
                "AspectRatio": "16:9",  # 宽高比
                "AudioGeneration": "Disabled",  # 生成音频
                "PersonGeneration": "AllowAdult",  # 允许生成成人
                "InputComplianceCheck": "Enabled",  # 输入合规检查
                "OutputComplianceCheck": "Enabled"  # 输出合规检查
            }
        )
        
        task_id = result.get("TaskId")
        print(f"\n视频任务创建成功！TaskId: {task_id}")
        print(f"RequestId: {result.get('RequestId')}")
        
        # 等待任务完成（视频生成通常需要更长时间）
        print("\n开始等待视频任务完成（可能需要较长时间）...")
        print("=" * 60)
        final_result = api.wait_for_task_completion(task_id, max_wait_time=600)  # 最长等待10分钟
        
        print("\n视频最终结果:")
        print(json.dumps(final_result, indent=2, ensure_ascii=False))
        
    except Exception as e:
        print(f"\n视频生成错误: {e}")
    
    print("\n" + "=" * 60)
    print("开始创建 OpenAI Sora 生视频任务")
    print("=" * 60)


# if __name__ == "__main__":
#     # gen_vid()
    
#     url = "https://example-cdn.invalid/generate/p_s_i_w_n_m/cfc7e35e-4d53-4500-bad3-c97d75ee0fa6.png"
#     prompt = "移除人物头上的帽子"
#     file_id = api.gen_file_id(image_path_or_url=url)
#     file_infos = [{"FileId": file_id}]
#     gen_img_by_tencent_nana_banana(file_infos=file_infos, prompt=prompt)

