#!/usr/bin/env python3
"""
VLM客户端模块
提供视频分析功能，支持同步和异步调用
"""

import os
import base64
import asyncio
import logging
from typing import Optional, Dict, List, Any
from openai import AsyncOpenAI

# 导入配置管理模块
from ..core.config import load_config

logger = logging.getLogger(__name__)

class DashScopeVLMClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, 
                 base_url: Optional[str] = None):
        """
        初始化DashScope VLM客户端（使用OpenAI SDK）
        
        Args:
            api_key: API密钥，如果为None则从配置文件读取
            model: 使用的模型名称，如果为None则从配置文件读取
            base_url: API基础URL，如果为None则从配置文件读取
        """
        # 加载配置
        config = load_config()
        vlm_config = config.get('vlm', {})
        
        # 获取API密钥
        self.api_key = api_key or vlm_config.get('api_key')
        if not self.api_key:
            # 尝试从环境变量获取
            self.api_key = os.environ.get('DASHSCOPE_API_KEY')
        
        if not self.api_key:
            raise ValueError("API密钥未设置，请在配置文件中设置、设置DASHSCOPE_API_KEY环境变量或传入api_key参数")
        
        # 获取其他配置
        self.model = model or vlm_config.get('model', 'qwen-vl-max-latest')
        self.base_url = base_url or vlm_config.get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        self.max_video_size_mb = vlm_config.get('max_video_size_mb', 100)
        self.max_base64_size_mb = vlm_config.get('max_base64_size_mb', 10)
        
        # 获取默认提示词
        self.default_prompt = vlm_config.get('default_prompt', {})
        self.system_prompt = self.default_prompt.get('system', 
            "You are a helpful assistant that analyzes videos and returns structured JSON responses.")
        self.user_prompt_template = self.default_prompt.get('user_template', 
            "请分析这段视频内容")
        
        # 创建异步OpenAI客户端
        self.async_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        
        logger.info(f"✅ VLM客户端初始化完成:")
        logger.info(f"  - 模型: {self.model}")
        logger.info(f"  - 基础URL: {self.base_url}")
        logger.info(f"  - 最大视频大小: {self.max_video_size_mb}MB")
        logger.info(f"  - 最大Base64大小: {self.max_base64_size_mb}MB")
        
    def encode_video(self, video_path: str) -> str:
        """将视频文件编码为base64格式"""
        try:
            # 检查原始文件大小
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            logger.info(f"原始视频文件大小: {file_size_mb:.2f}MB")
            
            if file_size_mb > self.max_video_size_mb:
                raise ValueError(f"视频文件过大: {file_size_mb:.2f}MB > {self.max_video_size_mb}MB限制")
            
            with open(video_path, "rb") as video_file:
                video_data = video_file.read()
                base64_data = base64.b64encode(video_data).decode("utf-8")
                
                # 检查Base64编码后的大小
                base64_size_mb = len(base64_data.encode('utf-8')) / (1024 * 1024)
                logger.info(f"Base64编码后大小: {base64_size_mb:.2f}MB")
                
                # 校验Base64大小限制
                if base64_size_mb > self.max_base64_size_mb:
                    raise ValueError(f"Base64编码后的视频过大: {base64_size_mb:.2f}MB > {self.max_base64_size_mb}MB限制")
                
                return base64_data
        except Exception as e:
            logger.error(f"视频编码失败: {str(e)}")
            raise
        
    def analyze_video(self, video_path: str, prompt: Optional[str] = None, fps: int = 2) -> Optional[str]:
        """
        同步分析视频内容（兼容性方法）
        
        Args:
            video_path: 视频文件路径
            prompt: 分析提示词，如果为None则使用配置文件中的默认提示词
            fps: 视频帧率（用于控制分析的帧数）
            
        Returns:
            分析结果文本，如果失败返回None
        """
        try:
            # 使用asyncio运行异步方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self.analyze_video_async(video_path, prompt, fps))
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"同步视频分析失败: {str(e)}")
            return None
    
    async def analyze_video_async(self, video_path: str, prompt: Optional[str] = None, fps: int = 2) -> Optional[str]:
        """
        异步分析视频内容
        
        Args:
            video_path: 视频文件路径
            prompt: 分析提示词，如果为None则使用配置文件中的默认提示词
            fps: 视频帧率（用于控制分析的帧数）
            
        Returns:
            分析结果文本，如果失败返回None
        """
        try:
            # 检查文件大小
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            if file_size_mb > self.max_video_size_mb:
                logger.error(f"视频文件过大: {file_size_mb:.2f}MB，超过{self.max_video_size_mb}MB限制")
                return None
                
            logger.info(f"开始异步分析视频: {video_path} ({file_size_mb:.2f}MB)")
            
            # 编码视频为base64
            base64_video = self.encode_video(video_path)
            
            # 使用配置文件中的默认提示词
            if prompt is None:
                prompt = self.user_prompt_template
            
            # 构建消息 - 使用正确的类型
            messages: List[Dict[str, Any]] = [
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": f"data:video/mp4;base64,{base64_video}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            
            # 异步调用API
            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages  # type: ignore
            )
            
            # 处理响应
            if completion.choices and len(completion.choices) > 0:
                result = completion.choices[0].message.content
                if result is not None:
                    logger.info(f"异步视频分析完成，结果长度: {len(result)} 字符")
                    return result
                else:
                    logger.error("API返回结果为空")
                    return None
            else:
                logger.error(f"API响应格式异常: {completion}")
                return None
                
        except Exception as e:
            logger.error(f"异步视频分析失败: {str(e)}")
            return None 