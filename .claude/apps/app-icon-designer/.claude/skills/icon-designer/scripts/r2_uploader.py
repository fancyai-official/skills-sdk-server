"""
Cloudflare R2 上传器

用于下载原始文件并上传到 R2 存储，替换为新的 URL。
"""

import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import boto3
from botocore.config import Config
import requests



class R2Uploader:
    """Cloudflare R2 上传器，用于上传图片和视频"""
    
    def __init__(self):
        self.client = None
        self.bucket_name = None
        self.public_domain = None
        self._upload_cache = {}  # 缓存已上传的 URL 映射
        self._current_task_date = None  # 当前处理任务的日期
        self._connect()
    
    def _connect(self):
        """连接 R2"""
        account_id = os.environ["R2_ACCOUNT_ID"]
        access_key_id = os.environ["R2_ACCESS_KEY_ID"]
        secret_access_key = os.environ["R2_SECRET_ACCESS_KEY"]
        self.bucket_name = os.environ["R2_BUCKET_NAME"]
        self.public_domain = os.environ["R2_PUBLIC_DOMAIN"]
        
        if not all([account_id, access_key_id, secret_access_key, self.bucket_name]):
            raise ValueError("R2 连接失败，请检查环境变量")
        
        try:
            self.client = boto3.client(
                's3',
                endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                config=Config(signature_version='s3v4'),
                region_name='auto'
            )
        except Exception:
            self.client = None
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.client is not None
    
    def _download_file(self, url: str) -> Optional[bytes]:
        """下载文件内容"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception:
            return None
    
    def _get_file_extension(self, url: str) -> str:
        """从 URL 获取文件扩展名"""
        parsed = urlparse(url)
        path = parsed.path
        if '.' in path:
            return path.rsplit('.', 1)[-1].lower()
        return 'bin'
    
    def _get_content_type(self, extension: str) -> str:
        """根据扩展名获取 Content-Type"""
        content_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'mp4': 'video/mp4',
            'webm': 'video/webm',
            'mov': 'video/quicktime',
            'md': 'text/markdown; charset=utf-8',
            'txt': 'text/plain; charset=utf-8',
            'html': 'text/html; charset=utf-8',
            'json': 'application/json; charset=utf-8',
        }
        return content_types.get(extension, 'application/octet-stream')
    
    def upload_bytes(self, data: bytes, extension: str = 'png', date_str: str = None,
                     prefix: str = 'generate') -> Optional[str]:
        """
        直接上传二进制数据到 R2，返回 CDN URL
        
        参数:
            data: 文件二进制数据
            extension: 文件扩展名（如 'png', 'jpg'）
            date_str: 日期字符串 (YYYYMMDD)，用于目录路径，默认使用当前日期
            prefix: 路径前缀，默认 'generate'
            
        返回:
            上传成功返回 R2 CDN URL，失败返回 None
        """
        if not self.is_connected():
            print("R2 未连接，无法上传")
            return None
        
        upload_date = date_str or datetime.now().strftime('%Y%m%d')
        new_filename = f"{prefix}/{upload_date}/{uuid.uuid4()}.{extension}"
        
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=new_filename,
                Body=data,
                ContentType=self._get_content_type(extension)
            )
            new_url = f"https://{self.public_domain}/{new_filename}"
            print(f"R2 上传成功: {new_url}")
            return new_url
        except Exception as e:
            print(f"R2 上传失败: {e}")
            return None
    
    def upload_local_file(self, file_path: str, prefix: str = 'uploads', date_str: str = None) -> Optional[str]:
        """
        上传本地文件到 R2，返回 CDN URL
        
        参数:
            file_path: 本地文件路径
            prefix: 路径前缀，默认 'uploads'
            date_str: 日期字符串 (YYYYMMDD)，用于目录路径，默认使用当前日期
            
        返回:
            上传成功返回 R2 CDN URL，失败返回 None
        """
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return None
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            extension = os.path.splitext(file_path)[1].lstrip('.').lower() or 'bin'
            return self.upload_bytes(data, extension=extension, date_str=date_str, prefix=prefix)
        except Exception as e:
            print(f"上传本地文件失败: {e}")
            return None
    
    def upload_and_get_new_url(self, original_url: str, date_str: str = None) -> str:
        """
        下载文件并上传到 R2，返回新的 URL
        如果上传失败，返回原始 URL
        
        参数:
            original_url: 原始 URL
            date_str: 日期字符串 (YYYYMMDD)，用于目录路径，默认使用当前日期
        """
        if not self.is_connected():
            return original_url
        
        # 使用传入的日期或当前处理的任务日期或当前日期
        upload_date = date_str or self._current_task_date or datetime.now().strftime('%Y%m%d')
        
        # 检查缓存（包含日期的缓存key）
        cache_key = f"{upload_date}:{original_url}"
        if cache_key in self._upload_cache:
            return self._upload_cache[cache_key]
        
        # 下载文件
        content = self._download_file(original_url)
        if content is None:
            return original_url
        
        # 生成新的文件名（使用任务日期）
        extension = self._get_file_extension(original_url)
        new_filename = f"uploads/{upload_date}/{uuid.uuid4()}.{extension}"
        
        try:
            # 上传到 R2
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=new_filename,
                Body=content,
                ContentType=self._get_content_type(extension)
            )
            
            # 生成新的 URL
            new_url = f"https://{self.public_domain}/{new_filename}"
            self._upload_cache[cache_key] = new_url
            return new_url
        except Exception:
            return original_url
    
    def process_task_data(self, task_params: Dict, result_list: List, task_date: str = None) -> Tuple[Dict, List, Dict]:
        """
        处理任务数据中的所有 URL，上传到 R2 并替换
        
        参数:
            task_params: 任务参数
            result_list: 结果列表
            task_date: 任务日期 (YYYYMMDD)，用于上传目录路径
        
        返回: (new_task_params, new_result_list, stats)
        stats: {'downloads': int, 'uploads': int, 'url_mappings': [(original, new), ...]}
        """
        stats = {'downloads': 0, 'uploads': 0, 'url_mappings': []}
        
        if not self.is_connected():
            return task_params, result_list, stats
        
        # 设置当前任务日期
        self._current_task_date = task_date
        
        # 记录处理前的缓存
        cache_before = set(self._upload_cache.keys())
        
        new_task_params = self._process_dict_urls(task_params)
        new_result_list = self._process_list_urls(result_list)
        
        # 清除当前任务日期
        self._current_task_date = None
        
        # 找出新上传的 URL 映射
        for cache_key, new_url in self._upload_cache.items():
            if cache_key not in cache_before:
                # cache_key 格式: "date:original_url"
                original_url = cache_key.split(':', 1)[1] if ':' in cache_key else cache_key
                stats['url_mappings'].append((original_url, new_url))
        
        stats['downloads'] = len(stats['url_mappings'])
        stats['uploads'] = len(stats['url_mappings'])
        
        return new_task_params, new_result_list, stats
    
    def _process_dict_urls(self, data: Dict) -> Dict:
        """递归处理字典中的 URL"""
        result = {}
        for key, value in data.items():
            if isinstance(value, str) and self._is_url(value):
                result[key] = self.upload_and_get_new_url(value)
            elif isinstance(value, dict):
                result[key] = self._process_dict_urls(value)
            elif isinstance(value, list):
                result[key] = self._process_list_urls(value)
            else:
                result[key] = value
        return result
    
    def _process_list_urls(self, data: List) -> List:
        """递归处理列表中的 URL"""
        result = []
        for item in data:
            if isinstance(item, str) and self._is_url(item):
                result.append(self.upload_and_get_new_url(item))
            elif isinstance(item, dict):
                result.append(self._process_dict_urls(item))
            elif isinstance(item, list):
                result.append(self._process_list_urls(item))
            else:
                result.append(item)
        return result
    
    def _is_url(self, text: str) -> bool:
        """检查字符串是否是 URL"""
        return text.startswith('http://') or text.startswith('https://')
    
    def get_stats(self) -> Dict:
        """获取上传统计"""
        return {
            'uploaded_count': len(self._upload_cache),
        }


# 全局单例
_r2_uploader: Optional[R2Uploader] = None


def get_r2_uploader() -> R2Uploader:
    """获取 R2 上传器单例"""
    global _r2_uploader
    if _r2_uploader is None:
        _r2_uploader = R2Uploader()
    return _r2_uploader
