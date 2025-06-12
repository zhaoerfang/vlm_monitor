#!/usr/bin/env python3
"""
VLM客户端模块
提供视频和图像分析功能，支持同步和异步调用
"""

import os
import base64
import asyncio
import logging
import math
import time
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from openai import AsyncOpenAI
from pathlib import Path
from PIL import Image
import requests
import json as json_module

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
        
        # 支持的文件格式
        self.video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        
        logger.info(f"✅ VLM客户端初始化完成:")
        logger.info(f"  - 模型: {self.model}")
        logger.info(f"  - 基础URL: {self.base_url}")
        logger.info(f"  - 最大视频大小: {self.max_video_size_mb}MB")
        logger.info(f"  - 最大Base64大小: {self.max_base64_size_mb}MB")
        
    def _is_video_file(self, file_path: str) -> bool:
        """判断文件是否为视频文件"""
        return Path(file_path).suffix.lower() in self.video_extensions
    
    def _is_image_file(self, file_path: str) -> bool:
        """判断文件是否为图像文件"""
        return Path(file_path).suffix.lower() in self.image_extensions
        
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
    
    def encode_image(self, image_path: str) -> str:
        """将图像文件编码为base64格式"""
        try:
            # 检查原始文件大小
            file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
            logger.info(f"原始图像文件大小: {file_size_mb:.2f}MB")
            
            if file_size_mb > self.max_base64_size_mb:
                raise ValueError(f"图像文件过大: {file_size_mb:.2f}MB > {self.max_base64_size_mb}MB限制")
            
            with open(image_path, "rb") as image_file:
                image_data = image_file.read()
                base64_data = base64.b64encode(image_data).decode("utf-8")
                
                # 检查Base64编码后的大小
                base64_size_mb = len(base64_data.encode('utf-8')) / (1024 * 1024)
                logger.info(f"Base64编码后大小: {base64_size_mb:.2f}MB")
                
                return base64_data
        except Exception as e:
            logger.error(f"图像编码失败: {str(e)}")
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
    
    def analyze_image(self, image_path: str, prompt: Optional[str] = None, 
                     user_question: Optional[str] = None, 
                     enable_camera_control: bool = True) -> Optional[str]:
        """
        同步分析图像内容
        
        Args:
            image_path: 图像文件路径
            prompt: 分析提示词，如果为None则使用配置文件中的默认提示词
            user_question: 用户问题，如果有则会添加到提示词中
            enable_camera_control: 是否启用摄像头控制功能（哨兵模式）
            
        Returns:
            分析结果文本，如果失败返回None
        """
        try:
            # 使用asyncio运行异步方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.analyze_image_async(image_path, prompt, user_question, enable_camera_control)
                )
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"同步图像分析失败: {str(e)}")
            return None
    
    def analyze_media(self, media_path: str, prompt: Optional[str] = None, fps: int = 2, 
                     user_question: Optional[str] = None, 
                     enable_camera_control: bool = True) -> Optional[str]:
        """
        自动识别并分析媒体文件（视频或图像）
        
        Args:
            media_path: 媒体文件路径
            prompt: 分析提示词，如果为None则使用配置文件中的默认提示词
            fps: 视频帧率（仅对视频有效）
            user_question: 用户问题，如果有则会添加到提示词中
            enable_camera_control: 是否启用摄像头控制功能（哨兵模式）
            
        Returns:
            分析结果文本，如果失败返回None
        """
        if self._is_video_file(media_path):
            logger.info(f"检测到视频文件: {media_path}")
            return self.analyze_video(media_path, prompt, fps)
        elif self._is_image_file(media_path):
            logger.info(f"检测到图像文件: {media_path}")
            return self.analyze_image(media_path, prompt, user_question, enable_camera_control)
        else:
            logger.error(f"不支持的文件格式: {media_path}")
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
            
            # 构建消息 - 视频格式
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
    
    async def analyze_image_async(self, image_path: str, prompt: Optional[str] = None, 
                                 user_question: Optional[str] = None, 
                                 enable_camera_control: bool = True) -> Optional[str]:
        """
        异步分析图像内容
        
        Args:
            image_path: 图像文件路径
            prompt: 分析提示词，如果为None则使用配置文件中的默认提示词
            user_question: 用户问题，如果有则会添加到提示词中
            enable_camera_control: 是否启用摄像头控制功能
            
        Returns:
            分析结果文本，如果失败返回None
        """
        try:
            # 检查文件大小
            file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
            if file_size_mb > self.max_base64_size_mb:
                logger.error(f"图像文件过大: {file_size_mb:.2f}MB，超过{self.max_base64_size_mb}MB限制")
                return None
                
            logger.info(f"开始异步分析图像: {image_path} ({file_size_mb:.2f}MB)")

            if user_question:
                logger.info(f"用户问题: {user_question}")
            if enable_camera_control:
                logger.info("启用摄像头控制功能")
            
            # 创建并行任务列表
            tasks = []
            
            # 任务1: VLM图像分析（总是执行）
            vlm_task = asyncio.create_task(self._perform_vlm_analysis(image_path, prompt, user_question))
            tasks.append(vlm_task)
            
            # 任务2: MCP摄像头控制（如果启用且没有用户问题）
            mcp_task = None
            if enable_camera_control and not user_question:
                mcp_task = asyncio.create_task(self._perform_mcp_control(image_path, user_question))
                tasks.append(mcp_task)
            
            # 并行执行所有任务
            logger.info(f"🚀 开始并行执行 {len(tasks)} 个任务...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理VLM分析结果
            vlm_result = results[0]
            if isinstance(vlm_result, Exception):
                logger.error(f"VLM分析失败: {vlm_result}")
                vlm_result = None
            
            # 处理MCP控制结果
            mcp_result = None
            if mcp_task is not None and len(results) > 1:
                mcp_result = results[1]
                if isinstance(mcp_result, Exception):
                    logger.error(f"MCP控制失败: {mcp_result}")
                    mcp_result = None
            
            # 保存MCP结果到对应的frame详情目录
            if mcp_result:
                self._save_mcp_result_to_details(image_path, mcp_result)
            
            logger.info(f"✅ 并行任务执行完成，VLM结果长度: {len(vlm_result) if vlm_result else 0} 字符")
            return vlm_result
                
        except Exception as e:
            logger.error(f"异步图像分析失败: {str(e)}")
            return None

    async def _perform_vlm_analysis(self, image_path: str, prompt: Optional[str] = None, 
                                   user_question: Optional[str] = None) -> Optional[str]:
        """
        执行VLM图像分析
        
        Args:
            image_path: 图像文件路径
            prompt: 分析提示词
            user_question: 用户问题
            
        Returns:
            分析结果文本
        """
        try:
            logger.info("🔍 开始VLM图像分析...")
            vlm_start_time = time.time()
            
            # 编码图像为base64
            base64_image = self.encode_image(image_path)
            
            # 获取图像文件扩展名，用于确定MIME类型
            ext = Path(image_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.bmp': 'image/bmp',
                '.gif': 'image/gif', '.tiff': 'image/tiff',
                '.webp': 'image/webp'
            }.get(ext, 'image/jpeg')
            
            # 使用配置文件中的默认提示词
            if prompt is None:
                prompt = self.user_prompt_template
            
            # 如果有用户问题，添加到提示词中
            if user_question:
                prompt = f"{prompt}\n\n用户问题: {user_question}"
            
            # 构建消息 - 图像格式
            messages: List[Dict[str, Any]] = [
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
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
                    vlm_duration = time.time() - vlm_start_time
                    logger.info(f"✅ VLM图像分析完成，耗时: {vlm_duration:.2f}s，结果长度: {len(result)} 字符")
                    return result
                else:
                    logger.error("VLM API返回结果为空")
                    return None
            else:
                logger.error(f"VLM API响应格式异常: {completion}")
                return None
                
        except Exception as e:
            logger.error(f"VLM图像分析失败: {str(e)}")
            return None

    async def _perform_mcp_control(self, image_path: str, user_question: Optional[str] = None) -> Optional[Dict]:
        """
        执行MCP摄像头控制
        
        Args:
            image_path: 图像文件路径
            user_question: 用户问题
            
        Returns:
            MCP调用结果数据
        """
        try:
            logger.info("🎯 开始MCP摄像头控制...")
            
            # 通过 HTTP 请求 MCP 推理服务
            import requests
            
            # 从配置文件读取推理服务地址
            config = load_config()
            inference_config = config.get('camera_inference_service', {})
            host = inference_config.get('host', 'localhost')
            port = inference_config.get('port', 8082)
            inference_url = f"http://localhost:{port}/analyze"
            
            logger.info(f"🌐 发送请求到 MCP 推理服务: {inference_url}")
            
            # 记录MCP调用开始时间
            mcp_start_time = time.time()
            mcp_start_timestamp = datetime.now().isoformat()
            
            # 构建请求数据
            request_data = {
                "image_path": image_path,
            }
            
            # 使用asyncio在线程池中执行同步的HTTP请求
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(
                    inference_url,
                    json=request_data,
                    timeout=30
                )
            )
            
            # 记录MCP调用结束时间
            mcp_end_time = time.time()
            mcp_end_timestamp = datetime.now().isoformat()
            mcp_duration = mcp_end_time - mcp_start_time
            
            if response.status_code == 200:
                camera_result = response.json()
                logger.info(f"✅ MCP摄像头控制完成，耗时: {mcp_duration:.2f}s")
                
                # 构建MCP结果数据
                mcp_result = {
                    'image_path': image_path,
                    'mcp_start_time': mcp_start_time,
                    'mcp_end_time': mcp_end_time,
                    'mcp_start_timestamp': mcp_start_timestamp,
                    'mcp_end_timestamp': mcp_end_timestamp,
                    'mcp_duration': mcp_duration,
                    'mcp_request_data': request_data,
                    'mcp_response_status': response.status_code,
                    'mcp_response_data': camera_result,
                    'mcp_success': camera_result.get('success', False)
                }
                
                # 记录详细的控制结果
                if camera_result.get('success') and camera_result.get('data'):
                    data = camera_result['data']
                    control_result = data.get('control_result')
                    
                    if control_result:
                        if isinstance(control_result, dict):
                            if control_result.get('success'):
                                logger.info(f"🎮 摄像头控制执行成功 - 工具: {control_result.get('tool_name')}, 参数: {control_result.get('arguments')}")
                                logger.info(f"📋 控制原因: {control_result.get('reason')}")
                                logger.info(f"📝 执行结果: {control_result.get('result')}")
                            else:
                                logger.warning(f"⚠️ 摄像头控制执行失败: {control_result.get('result')}")
                        else:
                            logger.info("📝 摄像头推理服务未返回控制结果")
                    else:
                        logger.info("📝 摄像头推理服务未返回控制结果")
                else:
                    logger.warning("⚠️ 摄像头推理服务返回失败或无数据")
                
                return mcp_result
            else:
                logger.error(f"❌ MCP摄像头控制失败: {response.status_code} - {response.text}")
                
                # 即使失败也记录MCP结果
                mcp_result = {
                    'image_path': image_path,
                    'mcp_start_time': mcp_start_time,
                    'mcp_end_time': mcp_end_time,
                    'mcp_start_timestamp': mcp_start_timestamp,
                    'mcp_end_timestamp': mcp_end_timestamp,
                    'mcp_duration': mcp_duration,
                    'mcp_request_data': request_data,
                    'mcp_response_status': response.status_code,
                    'mcp_response_text': response.text,
                    'mcp_success': False,
                    'mcp_error': f"HTTP {response.status_code}: {response.text}"
                }
                return mcp_result
                
        except Exception as camera_error:
            logger.error(f"❌ MCP摄像头控制异常: {camera_error}")
            
            # 记录异常情况的MCP结果
            mcp_result = {
                'image_path': image_path,
                'mcp_start_time': mcp_start_time if 'mcp_start_time' in locals() else time.time(),
                'mcp_end_time': time.time(),
                'mcp_start_timestamp': mcp_start_timestamp if 'mcp_start_timestamp' in locals() else datetime.now().isoformat(),
                'mcp_end_timestamp': datetime.now().isoformat(),
                'mcp_duration': time.time() - (mcp_start_time if 'mcp_start_time' in locals() else time.time()),
                'mcp_request_data': request_data if 'request_data' in locals() else None,
                'mcp_success': False,
                'mcp_error': str(camera_error),
                'mcp_exception': True
            }
            return mcp_result
    
    def _save_mcp_result_to_details(self, image_path: str, mcp_result: Dict):
        """
        保存MCP结果到对应的frame详情目录
        
        Args:
            image_path: 图像文件路径
            mcp_result: MCP调用结果数据
        """
        try:
            # 从图像路径推断frame详情目录
            # 图像路径格式通常为: .../session_*/frame_*_details/frame_*.jpg
            image_path_obj = Path(image_path)
            
            # 检查是否在details目录中
            if image_path_obj.parent.name.endswith('_details'):
                details_dir = image_path_obj.parent
            else:
                # 如果不在details目录中，尝试查找对应的details目录
                # 这种情况可能发生在临时文件或其他情况下
                logger.warning(f"图像路径不在details目录中: {image_path}")
                return
            
            # 创建MCP结果文件路径
            mcp_result_file = details_dir / 'mcp_result.json'
            
            # 增强MCP结果数据，添加更多有用信息
            enhanced_mcp_result = mcp_result.copy()
            enhanced_mcp_result.update({
                'saved_at': time.time(),
                'saved_timestamp': datetime.now().isoformat(),
                'frame_details_dir': str(details_dir),
                'image_filename': image_path_obj.name
            })
            
            # 保存MCP结果到文件
            with open(mcp_result_file, 'w', encoding='utf-8') as f:
                json_module.dump(enhanced_mcp_result, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"📁 MCP结果已保存到: {mcp_result_file}")
            
            # 如果MCP结果包含对话历史信息，记录到日志
            if 'mcp_response_data' in enhanced_mcp_result:
                response_data = enhanced_mcp_result['mcp_response_data']
                if isinstance(response_data, dict) and 'conversation_summary' in response_data:
                    conv_summary = response_data['conversation_summary']
                    logger.info(f"📋 对话历史状态: {conv_summary.get('conversation_rounds', 0)} 轮对话，{conv_summary.get('total_messages', 0)} 条消息")
            
        except Exception as e:
            logger.error(f"保存MCP结果失败: {str(e)}")
    
    async def analyze_media_async(self, media_path: str, prompt: Optional[str] = None, fps: int = 2) -> Optional[str]:
        """
        自动识别并异步分析媒体文件（视频或图像）
        
        Args:
            media_path: 媒体文件路径
            prompt: 分析提示词，如果为None则使用配置文件中的默认提示词
            fps: 视频帧率（仅对视频有效）
            
        Returns:
            分析结果文本，如果失败返回None
        """
        if self._is_video_file(media_path):
            logger.info(f"检测到视频文件: {media_path}")
            return await self.analyze_video_async(media_path, prompt, fps)
        elif self._is_image_file(media_path):
            logger.info(f"检测到图像文件: {media_path}")
            return await self.analyze_image_async(media_path, prompt)
        else:
            logger.error(f"不支持的文件格式: {media_path}")
            return None 

def smart_resize(
    height: int, width: int, factor: int = 28, min_pixels: int = 56 * 56, max_pixels: int = 14 * 14 * 4 * 1280
) -> Tuple[int, int]:
    """
    模型服务的图像resize逻辑
    
    Rescales the image so that the following conditions are met:
    1. Both dimensions (height and width) are divisible by 'factor'.
    2. The total number of pixels is within the range ['min_pixels', 'max_pixels'].
    3. The aspect ratio of the image is maintained as closely as possible.
    
    Returns:
        Tuple[int, int]: (resized_height, resized_width)
    """
    if height < factor or width < factor:
        raise ValueError(f"height:{height} or width:{width} must be larger than factor:{factor}")
    elif max(height, width) / min(height, width) > 200:
        raise ValueError(
            f"absolute aspect ratio must be smaller than 200, got {max(height, width) / min(height, width)}"
        )
    h_bar = round(height / factor) * factor
    w_bar = round(width / factor) * factor
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = math.floor(height / beta / factor) * factor
        w_bar = math.floor(width / beta / factor) * factor
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar

def get_image_dimensions(image_path: str) -> Tuple[int, int]:
    """
    获取图像的原始尺寸
    
    Returns:
        Tuple[int, int]: (width, height)
    """
    try:
        with Image.open(image_path) as img:
            return img.size  # PIL返回(width, height)
    except Exception as e:
        logger.error(f"获取图像尺寸失败: {e}")
        return (0, 0) 