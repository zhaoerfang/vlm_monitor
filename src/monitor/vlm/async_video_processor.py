#!/usr/bin/env python3
"""
异步视频处理器模块
提供帧收集、视频生成和异步VLM推理功能
"""

import os
import cv2
import time
import threading
import queue
import tempfile
import asyncio
import json
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime
import logging

from .vlm_client import DashScopeVLMClient, get_image_dimensions, smart_resize
from .user_question_manager import UserQuestionManager, init_question_manager
from ..core.config import load_config
from ..utils.image_utils import smart_resize_frame, validate_frame, get_frame_info

logger = logging.getLogger(__name__)

class AsyncVideoProcessor:
    def __init__(self, vlm_client: Optional[DashScopeVLMClient] = None, temp_dir: Optional[str] = None,
                 target_video_duration: Optional[float] = None, frames_per_second: Optional[int] = None,
                 original_fps: Optional[float] = None, max_concurrent_inferences: Optional[int] = None):
        """
        异步视频处理器
        
        Args:
            vlm_client: VLM客户端，如果为None则自动创建
            temp_dir: 临时目录
            target_video_duration: 目标视频时长（秒），如果为None则从配置读取
            frames_per_second: 每秒抽取的帧数，如果为None则从配置读取
            original_fps: 原始视频帧率，如果为None则从配置读取
            max_concurrent_inferences: 最大并发推理数量，如果为None则从配置读取
        """
        # 加载配置
        config = load_config()
        video_config = config.get('video_processing', {})
        vlm_config = config.get('vlm', {})
        asr_config = config.get('asr', {})
        
        # 初始化VLM客户端
        self.vlm_client = vlm_client or DashScopeVLMClient()
        
        # 初始化用户问题管理器（如果ASR服务启用）
        self.question_manager = None
        if asr_config.get('enabled', False):
            asr_host = asr_config.get('host', 'localhost')
            asr_port = asr_config.get('port', 8081)
            asr_url = f"http://{asr_host}:{asr_port}"
            self.question_manager = init_question_manager(asr_server_url=asr_url)
            logger.info(f"用户问题管理器已初始化: {asr_url}")
        else:
            logger.info("ASR服务未启用，跳过用户问题管理器初始化")
        
        # 设置临时目录
        self.temp_dir = temp_dir or tempfile.gettempdir()
        
        # 抽帧参数（优先使用传入参数，否则从配置读取）
        self.target_video_duration = target_video_duration or video_config.get('target_video_duration', 3.0)
        self.frames_per_second = frames_per_second or video_config.get('frames_per_second', 5)
        self.original_fps = original_fps or video_config.get('default_fps', 25.0)
        self.target_frames_per_video = int(self.target_video_duration * self.frames_per_second)
        self.frames_per_interval = int(self.original_fps / self.frames_per_second)
        
        # 检测图像模式：当target_video_duration、frames_per_second、target_frames_per_video都为1时
        self.image_mode = (self.target_video_duration == 1.0 and 
                          self.frames_per_second == 1 and 
                          self.target_frames_per_video == 1)
        
        # 计算需要收集的总帧数（3秒的原始帧数）
        self.frames_to_collect_per_video = int(self.target_video_duration * self.original_fps)
        
        # 并发控制
        self.max_concurrent_inferences = max_concurrent_inferences or vlm_config.get('max_concurrent_inferences', 3)
        
        # 图像缩放配置（完全从配置文件读取）
        self.enable_frame_resize = video_config.get('enable_frame_resize', True)
        self.target_width = video_config.get('target_width', 640)
        self.target_height = video_config.get('target_height', 360)
        self.max_frame_size_mb = video_config.get('max_frame_size_mb', 5.0)
        self.maintain_aspect_ratio = video_config.get('maintain_aspect_ratio', True)
        
        # 缓冲区和队列
        self.frame_buffer = []
        self.frame_queue = queue.Queue(maxsize=100)
        self.result_queue = queue.Queue(maxsize=20)
        
        # 线程控制
        self.stop_event = threading.Event()
        self.video_writer_thread = None
        
        # 异步推理控制
        self.active_inference_tasks = []  # 存储活跃的异步任务
        self.inference_loop = None
        self.inference_event_loop = None
        
        # 🆕 同步推理模式控制
        self.sync_inference_mode = vlm_config.get('sync_inference_mode', True)  # 从配置读取，默认启用同步推理模式
        self.current_inference_lock = threading.Lock()  # 推理状态锁
        self.current_inference_active = False  # 当前是否有推理在进行
        self.current_inference_details = None  # 当前推理的详细信息
        self.pending_frame_data = None  # 待处理的最新帧数据
        self.pending_frame_lock = threading.Lock()  # 待处理帧锁
        self.last_inference_completion_time = 0  # 上次推理完成时间
        
        # 统计信息
        self.total_frames_received = 0
        self.total_videos_created = 0
        self.total_images_created = 0  # 新增：图像计数
        self.total_inferences_started = 0
        self.total_inferences_completed = 0
        self.start_time = None
        self.frames_resized = 0
        self.frames_invalid = 0
        
        # 🆕 同步模式统计
        self.frames_skipped_sync_mode = 0  # 同步模式下跳过的帧数
        self.user_questions_processed = 0  # 处理的用户问题数
        
        # 实验日志
        self.experiment_log = []
        
        # 哨兵模式状态管理
        self.sentry_mode_enabled = True  # 默认启用哨兵模式
        self._sentry_mode_lock = threading.Lock()  # 线程安全锁
        
        # 后端API配置（用于获取哨兵模式状态）
        self.backend_api_url = "http://localhost:8080"  # 默认后端API地址
        self._last_sentry_mode_check = 0  # 上次检查哨兵模式的时间
        self._sentry_mode_check_interval = 5.0  # 检查间隔（秒）
        
        # 🆕 用户问题主动监听机制
        self.user_question_monitor_thread = None
        self.user_question_monitor_enabled = True  # 是否启用用户问题主动监听
        self.last_question_check_time = 0  # 上次检查用户问题的时间
        self.question_check_interval = 0.5  # 用户问题检查间隔（秒）
        
        logger.info(f"异步视频处理器初始化:")
        if self.image_mode:
            logger.info(f"  - 🖼️ 图像模式已启用（每帧单独推理）")
            logger.info(f"  - 每帧推理间隔: 每{self.frames_per_interval:.1f}帧抽1帧")
        else:
            logger.info(f"  - 🎬 视频模式（批量帧推理）")
            logger.info(f"  - 目标视频时长: {self.target_video_duration}s")
            logger.info(f"  - 每个视频总帧数: {self.target_frames_per_video}帧")
            logger.info(f"  - 每个视频收集原始帧数: {self.frames_to_collect_per_video}帧")
        
        logger.info(f"  - 每秒抽帧数: {self.frames_per_second}帧")
        logger.info(f"  - 原始帧率: {self.original_fps}fps")
        logger.info(f"  - 抽帧间隔: 每{self.frames_per_interval:.1f}帧抽1帧")
        logger.info(f"  - 最大并发推理数: {self.max_concurrent_inferences}")
        logger.info(f"  - 🛡️ 哨兵模式: {'启用' if self.sentry_mode_enabled else '禁用'}")
        logger.info(f"  - 🔄 同步推理模式: {'启用' if self.sync_inference_mode else '禁用'}")
        if self.enable_frame_resize:
            logger.info(f"  - 帧缩放已启用: 目标尺寸 {self.target_width}x{self.target_height}")
            logger.info(f"    * 最大帧大小: {self.max_frame_size_mb}MB")
            logger.info(f"    * 保持宽高比: {self.maintain_aspect_ratio}")
        else:
            logger.info(f"  - 帧缩放已禁用")

    def start(self):
        """启动异步处理"""
        self.stop_event.clear()
        self.start_time = time.time()
        
        # 启动用户问题管理器（如果存在）
        if self.question_manager:
            self.question_manager.start()
        
        # 启动视频写入线程
        self.video_writer_thread = threading.Thread(
            target=self._video_writer_worker,
            name="VideoWriter"
        )
        self.video_writer_thread.start()
        
        # 启动异步推理事件循环线程
        self.inference_loop = threading.Thread(
            target=self._start_inference_loop,
            name="InferenceLoop"
        )
        self.inference_loop.start()
        
        # 🆕 启动用户问题监听线程
        if self.question_manager and self.user_question_monitor_enabled:
            self.user_question_monitor_thread = threading.Thread(
                target=self._user_question_monitor_worker,
                name="UserQuestionMonitor"
            )
            self.user_question_monitor_thread.start()
            logger.info("用户问题主动监听线程已启动")
        
        # 等待事件循环启动完成
        max_wait = 5.0  # 最多等待5秒
        wait_start = time.time()
        while self.inference_event_loop is None and time.time() - wait_start < max_wait:
            time.sleep(0.1)
        
        if self.inference_event_loop is None:
            logger.error("事件循环启动超时")
        else:
            logger.info("异步视频处理器已启动，事件循环就绪")

    def stop(self):
        """停止异步处理"""
        self.stop_event.set()
        
        # 停止用户问题管理器（如果存在）
        if self.question_manager:
            self.question_manager.stop()
        
        # 🆕 停止用户问题监听线程
        if self.user_question_monitor_thread:
            self.user_question_monitor_thread.join(timeout=5)
            logger.info("用户问题监听线程已停止")
        
        if self.video_writer_thread:
            self.video_writer_thread.join()
            
        # 停止异步推理循环
        if self.inference_event_loop and not self.inference_event_loop.is_closed():
            try:
                # 等待所有活跃任务完成
                if self.active_inference_tasks:
                    logger.info(f"等待 {len(self.active_inference_tasks)} 个推理任务完成...")
                    # 使用线程安全的方式停止事件循环
                    future = asyncio.run_coroutine_threadsafe(self._stop_inference_loop(), self.inference_event_loop)
                    future.result(timeout=30)  # 最多等待30秒
            except Exception as e:
                logger.warning(f"停止推理循环时出错: {str(e)}")
            
        if self.inference_loop:
            self.inference_loop.join(timeout=10)
            
        if self.sync_inference_mode:
            logger.info(f"异步视频处理器已停止（同步推理模式），总共处理{self.total_frames_received}帧，"
                       f"生成{self.total_videos_created}个视频片段，生成{self.total_images_created}个图像，"
                       f"完成{self.total_inferences_completed}/{self.total_inferences_started}个推理，"
                       f"跳过{self.frames_skipped_sync_mode}帧，处理{self.user_questions_processed}个用户问题")
        else:
            logger.info(f"异步视频处理器已停止（异步推理模式），总共处理{self.total_frames_received}帧，"
                       f"生成{self.total_videos_created}个视频片段，生成{self.total_images_created}个图像，"
                       f"完成{self.total_inferences_completed}/{self.total_inferences_started}个推理")
        
        # 保存并自动排序实验日志
        self._save_and_sort_experiment_log()

    def add_frame(self, frame, timestamp: Optional[float] = None):
        """添加帧到处理队列"""
        try:
            # 验证帧有效性
            if not validate_frame(frame):
                logger.warning("接收到无效帧，跳过")
                self.frames_invalid += 1
                return
            
            # 获取帧信息
            frame_info = get_frame_info(frame)
            logger.debug(f"接收帧: {frame_info['resolution']}, {frame_info['size_mb']:.2f}MB")
            
            # 应用图像缩放（如果启用）
            processed_frame = frame
            if self.enable_frame_resize:
                resized_frame = smart_resize_frame(
                    frame, 
                    target_width=self.target_width,
                    target_height=self.target_height,
                    max_size_mb=self.max_frame_size_mb,
                    maintain_aspect_ratio=self.maintain_aspect_ratio
                )
                if resized_frame is not None:
                    processed_frame = resized_frame
                    self.frames_resized += 1
                    
                    # 记录缩放信息
                    new_info = get_frame_info(processed_frame)
                    logger.debug(f"帧已缩放: {frame_info['resolution']} -> {new_info['resolution']}, "
                               f"{frame_info['size_mb']:.2f}MB -> {new_info['size_mb']:.2f}MB")
            
            frame_data = {
                'frame': processed_frame,
                'timestamp': timestamp or time.time(),
                'frame_number': self.total_frames_received + 1,
                'relative_timestamp': (timestamp or time.time()) - (self.start_time or time.time()),
                'original_info': frame_info,
                'processed_info': get_frame_info(processed_frame) if processed_frame is not frame else frame_info,
                'was_resized': processed_frame is not frame
            }
            
            # 🆕 同步推理模式控制逻辑
            if self.sync_inference_mode:
                # 检查是否有用户问题（优先级最高）
                has_user_question = False
                if self.question_manager:
                    has_user_question = self.question_manager.has_available_question()
                
                # 检查当前推理状态
                with self.current_inference_lock:
                    inference_active = self.current_inference_active
                
                if has_user_question:
                    # 🚨 用户问题优先，立即处理帧
                    logger.info(f"🚨 检测到用户问题，优先处理帧 {frame_data['frame_number']}")
                    
                    # 🔧 用户问题强制中断：如果有推理在进行，强制重置推理状态
                    with self.current_inference_lock:
                        if self.current_inference_active:
                            logger.warning(f"🚨 用户问题强制中断当前推理，重置推理状态")
                            self.current_inference_active = False
                            self.current_inference_details = None
                    
                    # 🔧 优化：如果有缓存帧，优先使用缓存帧处理用户问题（缓存帧可能更接近问题提出的时间）
                    with self.pending_frame_lock:
                        if self.pending_frame_data is not None:
                            # 使用缓存帧处理用户问题，当前帧成为新的缓存帧
                            pending_frame = self.pending_frame_data
                            self.pending_frame_data = frame_data  # 当前帧成为新的缓存帧
                            logger.info(f"🚨 使用缓存帧 {pending_frame['frame_number']} 处理用户问题，当前帧 {frame_data['frame_number']} 成为新缓存")
                            self._add_frame_to_queue(pending_frame)
                            self.user_questions_processed += 1
                            return  # 当前帧已缓存，不增加total_frames_received
                        else:
                            # 没有缓存帧，直接使用当前帧处理用户问题
                            self._add_frame_to_queue(frame_data)
                            self.user_questions_processed += 1
                elif not inference_active:
                    # 没有推理在进行，可以处理新帧
                    logger.debug(f"✅ 推理空闲，处理帧 {frame_data['frame_number']}")
                    
                    # 🔧 修复：检查是否有缓存帧需要先处理
                    with self.pending_frame_lock:
                        if self.pending_frame_data is not None:
                            # 有缓存帧，处理缓存帧，当前帧成为新的缓存帧
                            pending_frame = self.pending_frame_data
                            self.pending_frame_data = frame_data  # 当前帧成为新的缓存帧
                            logger.info(f"🔄 处理缓存帧 {pending_frame['frame_number']}，当前帧 {frame_data['frame_number']} 成为新缓存")
                            self._add_frame_to_queue(pending_frame)
                            return  # 当前帧已缓存，不增加total_frames_received
                        else:
                            # 没有缓存帧，直接处理当前帧
                            self._add_frame_to_queue(frame_data)
                else:
                    # 🔧 修复：有推理在进行，始终维护最新的待处理帧（保留最新帧）
                    with self.pending_frame_lock:
                        if self.pending_frame_data is None:
                            logger.debug(f"⏳ 推理进行中，缓存帧 {frame_data['frame_number']}")
                        else:
                            logger.debug(f"⏳ 推理进行中，更新缓存帧 {self.pending_frame_data['frame_number']} -> {frame_data['frame_number']}")
                            self.frames_skipped_sync_mode += 1
                        self.pending_frame_data = frame_data
                    return  # 不增加total_frames_received，因为帧被缓存而不是处理
            else:
                # 异步模式，直接添加到队列
                self._add_frame_to_queue(frame_data)
            
            self.total_frames_received += 1
            
            if self.total_frames_received % 50 == 0:
                if self.sync_inference_mode:
                    logger.info(f"已接收 {self.total_frames_received} 帧 "
                              f"(缩放: {self.frames_resized}, 无效: {self.frames_invalid}, "
                              f"同步跳过: {self.frames_skipped_sync_mode}, 用户问题: {self.user_questions_processed})")
                else:
                    logger.info(f"已接收 {self.total_frames_received} 帧 "
                              f"(缩放: {self.frames_resized}, 无效: {self.frames_invalid})")
                
        except Exception as e:
            logger.error(f"添加帧失败: {str(e)}")
    
    def _add_frame_to_queue(self, frame_data: Dict):
        """将帧数据添加到处理队列"""
        try:
            self.frame_queue.put(frame_data, timeout=1)
        except queue.Full:
            logger.warning("帧队列已满，丢弃帧")

    def get_result(self, timeout: float = 1.0) -> Optional[Dict]:
        """获取推理结果"""
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _start_inference_loop(self):
        """在单独线程中启动异步事件循环"""
        self.inference_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.inference_event_loop)
        
        logger.info("推理事件循环已创建")
        
        try:
            self.inference_event_loop.run_until_complete(self._inference_manager())
        except Exception as e:
            logger.error(f"推理事件循环错误: {str(e)}")
        finally:
            try:
                # 清理事件循环
                pending = asyncio.all_tasks(self.inference_event_loop)
                if pending:
                    logger.info(f"取消 {len(pending)} 个待处理任务")
                    for task in pending:
                        task.cancel()
                    # 等待任务取消完成
                    self.inference_event_loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception as e:
                logger.warning(f"清理事件循环时出错: {str(e)}")
            finally:
                self.inference_event_loop.close()

    async def _stop_inference_loop(self):
        """停止异步推理循环"""
        # 等待所有活跃任务完成
        if self.active_inference_tasks:
            completed_tasks = []
            for task in self.active_inference_tasks:
                if not task.done():
                    try:
                        result = await asyncio.wait_for(task, timeout=10.0)
                        completed_tasks.append(result)
                    except asyncio.TimeoutError:
                        logger.warning("推理任务超时，强制取消")
                        task.cancel()
                    except Exception as e:
                        logger.warning(f"推理任务异常: {str(e)}")
            logger.info(f"完成了 {len(completed_tasks)} 个推理任务")

    async def _inference_manager(self):
        """异步推理管理器"""
        logger.info("推理管理器启动")
        while not self.stop_event.is_set():
            try:
                # 清理已完成的任务
                before_count = len(self.active_inference_tasks)
                self.active_inference_tasks = [
                    task for task in self.active_inference_tasks 
                    if not task.done()
                ]
                after_count = len(self.active_inference_tasks)
                
                if before_count != after_count:
                    logger.debug(f"清理了 {before_count - after_count} 个已完成任务，剩余 {after_count} 个")
                
                # 短暂休眠避免忙等待
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"推理管理器错误: {str(e)}")
                await asyncio.sleep(1)  # 出错时等待更长时间
        
        logger.info("推理管理器停止")

    def _submit_inference_task(self, media_info: Dict):
        """提交异步推理任务"""
        if self.inference_event_loop and not self.inference_event_loop.is_closed() and len(self.active_inference_tasks) < self.max_concurrent_inferences:
            try:
                # 🆕 同步推理模式：设置推理状态
                if self.sync_inference_mode:
                    with self.current_inference_lock:
                        if self.current_inference_active:
                            logger.warning("同步推理模式下尝试提交新任务，但当前已有推理在进行")
                            return
                        self.current_inference_active = True
                        self.current_inference_details = {
                            'media_path': media_info.get('media_path', media_info.get('video_path', media_info.get('image_path', 'unknown'))),
                            'media_type': media_info.get('media_type', 'video'),
                            'start_time': time.time(),
                            'frame_number': media_info.get('frame_number', 'N/A')
                        }
                        logger.info(f"🔄 同步推理开始: {os.path.basename(self.current_inference_details['media_path'])} "
                                  f"(帧号: {self.current_inference_details['frame_number']})")
                
                task = asyncio.run_coroutine_threadsafe(
                    self._inference_worker_async(media_info),
                    self.inference_event_loop
                )
                self.active_inference_tasks.append(task)
                self.total_inferences_started += 1
                
                # 获取媒体路径，兼容图像和视频模式
                media_path = media_info.get('media_path', media_info.get('video_path', media_info.get('image_path', 'unknown')))
                media_type = media_info.get('media_type', 'video')
                
                if not self.sync_inference_mode:  # 异步模式才打印详细信息
                    logger.info(f"提交异步推理任务: {os.path.basename(media_path)} ({media_type})")
                    logger.info(f"  - 当前并发数: {len(self.active_inference_tasks)}/{self.max_concurrent_inferences}")
                    logger.info(f"  - 总启动数: {self.total_inferences_started}")
            except Exception as e:
                logger.error(f"提交推理任务失败: {str(e)}")
                # 🆕 同步推理模式：出错时重置状态
                if self.sync_inference_mode:
                    with self.current_inference_lock:
                        self.current_inference_active = False
                        self.current_inference_details = None
        else:
            if self.inference_event_loop is None:
                logger.warning("事件循环未就绪，跳过推理")
            elif self.inference_event_loop.is_closed():
                logger.warning("事件循环已关闭，跳过推理")
            elif len(self.active_inference_tasks) >= self.max_concurrent_inferences:
                if not self.sync_inference_mode:  # 异步模式才警告
                    logger.warning(f"推理任务队列已满 ({len(self.active_inference_tasks)}/{self.max_concurrent_inferences})，跳过推理")
            else:
                logger.warning("推理任务提交失败，原因未知")

    async def _inference_worker_async(self, media_info: Dict):
        """真正的异步推理工作函数"""
        try:
            # 记录推理开始时间
            inference_start_time = time.time()
            inference_start_timestamp = datetime.now().isoformat()
            
            media_type = media_info.get('media_type', 'video')
            media_path = media_info.get('media_path', media_info.get('video_path', media_info.get('image_path')))
            
            # 获取当前用户问题（原子性分配）
            user_question = None
            task_id = None
            if self.question_manager:
                user_question, task_id = self.question_manager.acquire_question()
            
            logger.info(f"开始异步VLM推理: {os.path.basename(media_path)} ({media_type})")
            logger.info(f"  - 推理开始时间: {inference_start_timestamp}")
            if user_question and task_id:
                logger.info(f"  - 用户问题: {user_question}")
                logger.info(f"  - 任务ID: {task_id}")
            
            if media_type == 'image':
                logger.info(f"  - 图像帧号: {media_info.get('frame_number', 'N/A')}")
                logger.info(f"  - 图像时间戳: {media_info.get('relative_timestamp', 'N/A'):.2f}s")
                
                # 从后端同步哨兵模式状态
                self._update_sentry_mode_from_backend()
                
                # 获取当前哨兵模式状态
                enable_camera_control = self.get_sentry_mode()
                logger.info(f"  - 哨兵模式: {'启用' if enable_camera_control else '禁用'}")
                
                # 执行异步图像推理
                result = await self.vlm_client.analyze_image_async(
                    media_path, 
                    prompt=None,  # 使用配置文件中的默认提示词
                    user_question=user_question,
                    enable_camera_control=enable_camera_control  # 传递哨兵模式状态
                )
            else:
                logger.info(f"  - 源视频时间范围: {media_info.get('start_relative_timestamp', 'N/A'):.2f}s - {media_info.get('end_relative_timestamp', 'N/A'):.2f}s")
                
                # 执行异步视频推理（暂时不支持用户问题，因为视频分析方法还没修改）
                result = await self.vlm_client.analyze_video_async(
                    media_path, 
                    prompt=None,  # 使用配置文件中的默认提示词
                    fps=2
                )
            
            # 记录推理结束时间
            inference_end_time = time.time()
            inference_end_timestamp = datetime.now().isoformat()
            inference_duration = inference_end_time - inference_start_time
            
            logger.info(f"异步VLM推理完成: {os.path.basename(media_path)} ({media_type})")
            logger.info(f"  - 推理结束时间: {inference_end_timestamp}")
            logger.info(f"  - 推理耗时: {inference_duration:.2f}s")
            logger.info(f"  - 结果长度: {len(result) if result else 0}字符")
            
            # 将结果放入结果队列
            result_data = {
                'media_path': media_path,
                'media_type': media_type,
                'result': result,
                'media_info': media_info,
                'inference_start_time': inference_start_time,
                'inference_end_time': inference_end_time,
                'inference_start_timestamp': inference_start_timestamp,
                'inference_end_timestamp': inference_end_timestamp,
                'inference_duration': inference_duration,
                'result_received_at': time.time(),
                'user_question': user_question,  # 添加用户问题
                'task_id': task_id,  # 添加任务ID
                'raw_result': result  # 添加原始结果（兼容性）
            }
            
            # 为了向后兼容，保留video_path字段
            if 'video_path' not in result_data:
                result_data['video_path'] = media_path
            if 'video_info' not in result_data:
                result_data['video_info'] = media_info
            
            # 记录到实验日志
            self.experiment_log.append(result_data.copy())
            self.total_inferences_completed += 1
            
            # 保存推理结果到媒体详情文件夹
            self._save_inference_result_to_details(result_data)
            
            # 如果有用户问题，释放问题（无论推理是否成功）
            if user_question and task_id and self.question_manager:
                success = result is not None and len(str(result).strip()) > 0
                self.question_manager.release_question(task_id, success)
                if success:
                    logger.info(f"推理成功，任务 {task_id} 已释放用户问题: {user_question}")
                else:
                    logger.warning(f"推理失败，任务 {task_id} 已释放用户问题: {user_question}")
            
            try:
                self.result_queue.put(result_data, timeout=1)
                logger.info(f"异步推理结果已入队: {os.path.basename(media_path)} ({media_type})")
            except queue.Full:
                logger.warning("结果队列已满，丢弃结果")
                
        except Exception as e:
            logger.error(f"异步推理失败: {str(e)}")
            self.total_inferences_completed += 1  # 即使失败也计入完成数
            
            # 如果有用户问题，确保释放问题（推理失败）
            if 'user_question' in locals() and 'task_id' in locals() and user_question and task_id and self.question_manager:
                self.question_manager.release_question(task_id, success=False)
                logger.warning(f"推理异常，任务 {task_id} 已释放用户问题: {user_question}")
        
        finally:
            # 🆕 同步推理模式：推理完成后的处理
            if self.sync_inference_mode:
                with self.current_inference_lock:
                    if self.current_inference_active and self.current_inference_details:
                        inference_duration = time.time() - self.current_inference_details['start_time']
                        logger.info(f"✅ 同步推理完成: {os.path.basename(self.current_inference_details['media_path'])} "
                                  f"(帧号: {self.current_inference_details['frame_number']}, 耗时: {inference_duration:.2f}s)")
                        
                        self.current_inference_active = False
                        self.current_inference_details = None
                        self.last_inference_completion_time = time.time()
                
                # 🔧 修复：不再调用_process_pending_frame，避免处理过时的缓存帧
                # 让add_frame方法中的新帧检测到推理空闲后自然处理最新帧
                logger.debug("🔄 同步推理完成，等待新的实时帧...")
            
        # 注意：不删除临时文件，保留用于调试
        logger.debug(f"保留媒体文件用于调试: {media_path}")

    def _process_pending_frame(self):
        """
        处理待处理的帧（同步推理模式）
        
        ⚠️ 已废弃：此方法存在时序竞争问题，会导致处理过时的缓存帧
        现在改为让add_frame方法直接处理最新的实时帧
        """
        logger.warning("⚠️ _process_pending_frame方法已废弃，不应被调用")
        # 保留方法体以避免破坏现有调用，但不执行任何操作
        pass

    def _sample_frames_by_time(self, frames_data: List[Dict]) -> List[Dict]:
        """
        按时间间隔抽帧：每秒抽取指定数量的帧
        
        Args:
            frames_data: 帧数据列表
            
        Returns:
            抽取的帧数据列表
        """
        if len(frames_data) < self.target_frames_per_video:
            logger.warning(f"帧数不足: {len(frames_data)} < {self.target_frames_per_video}")
            return frames_data
        
        sampled_frames = []
        
        # 计算时间范围
        start_time = frames_data[0]['relative_timestamp']
        end_time = frames_data[-1]['relative_timestamp']
        total_duration = end_time - start_time
        
        logger.info(f"开始抽帧: 总帧数={len(frames_data)}, 时间范围={start_time:.2f}s-{end_time:.2f}s")
        
        # 按时间均匀分布抽帧
        for second in range(int(self.target_video_duration)):
            # 计算这一秒的时间范围
            second_start = start_time + second
            second_end = second_start + 1.0
            
            # 找到这一秒内的所有帧
            second_frames = [f for f in frames_data 
                           if second_start <= f['relative_timestamp'] < second_end]
            
            logger.debug(f"第{second+1}秒 ({second_start:.2f}s-{second_end:.2f}s): 找到{len(second_frames)}帧")
            
            if len(second_frames) >= self.frames_per_second:
                # 从这一秒的帧中均匀抽取指定数量的帧
                indices = np.linspace(0, len(second_frames) - 1, self.frames_per_second, dtype=int)
                for idx in indices:
                    sampled_frames.append(second_frames[idx])
                    logger.debug(f"  抽取帧: 索引{idx}, 帧号{second_frames[idx]['frame_number']}")
            elif second_frames:
                # 如果这一秒的帧数不足，全部使用
                sampled_frames.extend(second_frames)
                logger.debug(f"  使用全部{len(second_frames)}帧")
        
        # 如果抽取的帧数不足，从剩余帧中补充
        if len(sampled_frames) < self.target_frames_per_video:
            remaining_needed = self.target_frames_per_video - len(sampled_frames)
            used_frame_numbers = {f['frame_number'] for f in sampled_frames}
            remaining_frames = [f for f in frames_data if f['frame_number'] not in used_frame_numbers]
            
            if remaining_frames:
                step = max(1, len(remaining_frames) // remaining_needed)
                additional_frames = remaining_frames[::step][:remaining_needed]
                sampled_frames.extend(additional_frames)
                logger.debug(f"补充{len(additional_frames)}帧")
        
        # 按时间戳排序
        sampled_frames.sort(key=lambda x: x['timestamp'])
        
        # 记录抽帧详情
        if sampled_frames:
            original_time_range = (frames_data[0]['relative_timestamp'], frames_data[-1]['relative_timestamp'])
            sampled_time_range = (sampled_frames[0]['relative_timestamp'], sampled_frames[-1]['relative_timestamp'])
            
            logger.info(f"抽帧完成: {len(frames_data)}帧 -> {len(sampled_frames)}帧")
            logger.info(f"原始时间范围: {original_time_range[0]:.2f}s - {original_time_range[1]:.2f}s")
            logger.info(f"抽取时间范围: {sampled_time_range[0]:.2f}s - {sampled_time_range[1]:.2f}s")
            logger.info(f"抽取帧详情: {[f['frame_number'] for f in sampled_frames]}")
        else:
            logger.error("抽帧失败：没有抽取到任何帧")
        
        return sampled_frames

    def _video_writer_worker(self):
        """视频写入工作线程"""
        try:
            while not self.stop_event.is_set():
                try:
                    frame_data = self.frame_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                if self.image_mode:
                    # 图像模式：直接处理单帧
                    self._process_single_frame(frame_data)
                else:
                    # 视频模式：收集帧并创建视频
                    self._process_video_frames(frame_data)
                    
        except Exception as e:
            logger.error(f"视频写入线程错误: {str(e)}")
    
    def _process_single_frame(self, frame_data: Dict):
        """处理单帧图像（图像模式）"""
        try:
            # 检查是否需要抽帧（按间隔）
            if self.total_frames_received % self.frames_per_interval != 0:
                return
            
            # 创建图像文件
            image_creation_start = time.time()
            image_path = self._create_image_from_frame(frame_data)
            image_creation_time = time.time() - image_creation_start
            
            if image_path:
                # 保存图像详情到实验目录
                image_info = self._save_image_details(frame_data, image_path, image_creation_time)
                
                # 使用保存后的图像路径
                final_image_path = image_info.get('image_path', image_path)
                
                image_info.update({
                    'media_path': final_image_path,  # 统一使用media_path字段
                    'video_path': final_image_path,  # 为了向后兼容，添加video_path字段
                    'media_type': 'image',
                    'frame_count': 1,
                    'timestamp': frame_data['timestamp'],
                    'relative_timestamp': frame_data['relative_timestamp'],
                    'frame_number': frame_data['frame_number'],
                    'image_creation_time': image_creation_time,
                    'image_creation_timestamp': datetime.fromtimestamp(image_creation_start).isoformat(),
                    'created_at': time.time()
                })
                
                self.total_images_created += 1
                logger.info(f"图像已生成: {os.path.basename(image_path)}")
                logger.info(f"  - 帧号: {frame_data['frame_number']}")
                logger.info(f"  - 时间戳: {frame_data['relative_timestamp']:.2f}s")
                logger.info(f"  - 图像创建耗时: {image_creation_time:.3f}s")
                
                # 立即提交异步推理任务
                self._submit_inference_task(image_info)
                
        except Exception as e:
            logger.error(f"处理单帧图像失败: {str(e)}")
    
    def _process_video_frames(self, frame_data: Dict):
        """处理视频帧（视频模式）"""
        # 添加到缓冲区
        self.frame_buffer.append(frame_data)
        
        # 当缓冲区达到一个视频所需的帧数时，进行抽帧并创建视频
        if len(self.frame_buffer) >= self.frames_to_collect_per_video:
            # 抽取帧
            sampled_frames = self._sample_frames_by_time(self.frame_buffer[:self.frames_to_collect_per_video])
            
            # 创建视频
            video_creation_start = time.time()
            video_path = self._create_video_from_frames(sampled_frames)
            video_creation_time = time.time() - video_creation_start
            
            if video_path:
                # 计算时间范围
                start_timestamp = sampled_frames[0]['timestamp']
                end_timestamp = sampled_frames[-1]['timestamp']
                start_relative = sampled_frames[0]['relative_timestamp']
                end_relative = sampled_frames[-1]['relative_timestamp']
                
                # 保存抽帧详情到实验目录
                video_info = self._save_video_details(sampled_frames, video_path, video_creation_time)
                
                # 使用保存后的视频路径（可能已被移动到details文件夹）
                final_video_path = video_info.get('video_path', video_path)
                
                video_info.update({
                    'media_path': final_video_path,  # 统一使用media_path字段
                    'media_type': 'video',
                    'frame_count': len(sampled_frames),
                    'start_timestamp': start_timestamp,
                    'end_timestamp': end_timestamp,
                    'start_relative_timestamp': start_relative,
                    'end_relative_timestamp': end_relative,
                    'duration': end_timestamp - start_timestamp,
                    'relative_duration': end_relative - start_relative,
                    'original_frame_range': (
                        sampled_frames[0]['frame_number'],
                        sampled_frames[-1]['frame_number']
                    ),
                    'video_creation_time': video_creation_time,
                    'video_creation_timestamp': datetime.fromtimestamp(video_creation_start).isoformat(),
                    'created_at': time.time()
                })
                
                self.total_videos_created += 1
                logger.info(f"视频片段已生成: {os.path.basename(video_path)}")
                logger.info(f"  - 帧范围: {video_info['original_frame_range']}")
                logger.info(f"  - 源视频时间: {start_relative:.2f}s - {end_relative:.2f}s")
                logger.info(f"  - 视频创建耗时: {video_creation_time:.3f}s")
                
                # 立即提交异步推理任务
                self._submit_inference_task(video_info)
            
            # 移除已处理的帧，保留25%重叠以确保连续性
            overlap_frames = self.frames_to_collect_per_video // 4
            self.frame_buffer = self.frame_buffer[self.frames_to_collect_per_video - overlap_frames:]
    
    def _create_image_from_frame(self, frame_data: Dict) -> Optional[str]:
        """从单帧创建图像文件"""
        try:
            # 创建图像文件路径
            timestamp = datetime.fromtimestamp(frame_data['timestamp'])
            image_name = f"frame_{frame_data['frame_number']:06d}_{timestamp.strftime('%H%M%S_%f')[:-3]}.jpg"
            image_path = os.path.join(self.temp_dir, image_name)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            
            # 保存图像
            success = cv2.imwrite(image_path, frame_data['frame'])
            
            if success:
                logger.debug(f"图像已保存: {image_path}")
                return image_path
            else:
                logger.error(f"保存图像失败: {image_path}")
                return None
                
        except Exception as e:
            logger.error(f"创建图像文件失败: {str(e)}")
            return None
    
    def _save_image_details(self, frame_data: Dict, image_path: str, creation_time: float) -> Dict:
        """保存图像详情到实验目录"""
        try:
            # 创建图像详情目录
            image_name = os.path.splitext(os.path.basename(image_path))[0]
            details_dir = os.path.join(self.temp_dir, f"{image_name}_details")
            os.makedirs(details_dir, exist_ok=True)
            
            # 将图像文件移动到details文件夹内
            new_image_path = os.path.join(details_dir, os.path.basename(image_path))
            if os.path.exists(image_path) and image_path != new_image_path:
                import shutil
                shutil.move(image_path, new_image_path)
                logger.debug(f"图像文件已移动到: {new_image_path}")
            else:
                new_image_path = image_path
            
            # 获取图像尺寸信息
            original_width, original_height = get_image_dimensions(new_image_path)
            
            # 计算模型resize后的尺寸
            model_height, model_width = 0, 0
            if original_width > 0 and original_height > 0:
                try:
                    model_height, model_width = smart_resize(original_height, original_width)
                    logger.debug(f"图像尺寸信息: 原始({original_width}x{original_height}) -> 模型({model_width}x{model_height})")
                except Exception as e:
                    logger.warning(f"计算模型resize尺寸失败: {e}")
            
            # 保存详情JSON
            details = {
                'image_path': new_image_path,
                'creation_time': creation_time,
                'creation_timestamp': datetime.fromtimestamp(time.time()).isoformat(),
                'frame_number': frame_data['frame_number'],
                'timestamp': frame_data['timestamp'],
                'timestamp_iso': datetime.fromtimestamp(frame_data['timestamp']).isoformat(),
                'relative_timestamp': frame_data['relative_timestamp'],
                'frame_info': {
                    'width': frame_data['frame'].shape[1],
                    'height': frame_data['frame'].shape[0],
                    'channels': frame_data['frame'].shape[2] if len(frame_data['frame'].shape) > 2 else 1
                },
                'image_dimensions': {
                    'original_width': original_width,
                    'original_height': original_height,
                    'model_width': model_width,
                    'model_height': model_height,
                    'scale_x': model_width / original_width if original_width > 0 else 1.0,
                    'scale_y': model_height / original_height if original_height > 0 else 1.0
                }
            }
            
            details_file = os.path.join(details_dir, 'image_details.json')
            with open(details_file, 'w', encoding='utf-8') as f:
                json.dump(details, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"图像详情已保存: {details_dir}")
            return {
                'details_dir': details_dir, 
                'details_file': details_file,
                'image_path': new_image_path,
                'image_dimensions': details['image_dimensions']
            }
            
        except Exception as e:
            logger.error(f"保存图像详情失败: {str(e)}")
            return {'image_path': image_path}

    def _create_video_from_frames(self, frames_data: List[Dict]) -> Optional[str]:
        """从帧数据创建视频文件"""
        if not frames_data:
            return None
            
        try:
            video_path = self._create_temp_video_path()
            
            # 确保目录存在
            video_dir = os.path.dirname(video_path)
            os.makedirs(video_dir, exist_ok=True)
            
            # 获取第一帧的尺寸
            first_frame = frames_data[0]['frame']
            height, width = first_frame.shape[:2]
            
            # 创建视频写入器，使用目标帧率
            output_fps = self.frames_per_second  # 输出视频的帧率等于每秒抽取的帧数
            
            # 尝试多种编码器，按优先级排序
            codecs_to_try = [
                ('mp4v', 'MP4V'),  # 最兼容的编码器
                ('XVID', 'XVID'),  # 广泛支持的编码器
                ('avc1', 'H.264'), # H.264编码器
                ('H264', 'H.264'), # 另一种H.264编码器
                ('MJPG', 'MJPG'),  # Motion JPEG
            ]
            
            writer = None
            used_codec = None
            temp_video_path = video_path  # 临时视频路径
            
            for codec_name, codec_desc in codecs_to_try:
                try:
                    fourcc = cv2.VideoWriter.fourcc(*codec_name)
                    writer = cv2.VideoWriter(temp_video_path, fourcc, output_fps, (width, height))
                    
                    # 测试写入器是否正常工作
                    if writer.isOpened():
                        used_codec = codec_desc
                        logger.debug(f"成功使用编码器: {codec_desc} ({codec_name})")
                        break
                    else:
                        writer.release()
                        writer = None
                        logger.debug(f"编码器 {codec_desc} ({codec_name}) 不可用")
                except Exception as e:
                    logger.debug(f"编码器 {codec_desc} ({codec_name}) 初始化失败: {str(e)}")
                    if writer:
                        writer.release()
                        writer = None
            
            if writer is None or not writer.isOpened():
                logger.error("所有视频编码器都不可用")
                return None
            
            # 写入所有帧
            frames_written = 0
            for frame_data in frames_data:
                try:
                    writer.write(frame_data['frame'])
                    frames_written += 1
                except Exception as e:
                    logger.warning(f"写入帧失败: {str(e)}")
                    
            writer.release()
            
            if frames_written == 0:
                logger.error("没有成功写入任何帧")
                if os.path.exists(temp_video_path):
                    os.remove(temp_video_path)
                return None
            
            # 检查文件是否存在且有内容
            if not os.path.exists(temp_video_path):
                logger.error(f"视频文件创建失败，文件不存在: {temp_video_path}")
                return None
            
            file_size_mb = os.path.getsize(temp_video_path) / (1024 * 1024)
            
            if file_size_mb == 0:
                logger.error("视频文件大小为0，删除文件")
                os.remove(temp_video_path)
                return None
            
            if file_size_mb > 95:  # 如果超过95MB，删除文件
                os.remove(temp_video_path)
                logger.warning(f"视频文件过大 ({file_size_mb:.2f}MB)，已删除")
                return None
            
            # 如果使用的不是H.264编码器，尝试用FFmpeg转换为H.264
            final_video_path = temp_video_path
            if used_codec != 'H.264' and self._is_ffmpeg_available():
                h264_video_path = temp_video_path.replace('.mp4', '_h264.mp4')
                if self._convert_to_h264_with_ffmpeg(temp_video_path, h264_video_path):
                    # 转换成功，使用H.264版本
                    final_video_path = h264_video_path
                    used_codec = 'H.264 (FFmpeg)'
                    
                    # 删除原始文件
                    try:
                        os.remove(temp_video_path)
                    except:
                        pass
                    
                    # 更新文件大小
                    file_size_mb = os.path.getsize(final_video_path) / (1024 * 1024)
                    logger.debug(f"FFmpeg转换成功，新文件大小: {file_size_mb:.2f}MB")
                else:
                    logger.debug("FFmpeg转换失败，使用原始文件")
                    
            logger.debug(f"视频文件创建成功: {final_video_path}")
            logger.debug(f"  - 编码器: {used_codec}")
            logger.debug(f"  - 文件大小: {file_size_mb:.2f}MB")
            logger.debug(f"  - 帧率: {output_fps}fps")
            logger.debug(f"  - 写入帧数: {frames_written}/{len(frames_data)}")
            
            return final_video_path
            
        except Exception as e:
            logger.error(f"创建视频文件失败: {str(e)}")
            # 清理可能创建的文件
            for path_var in ['temp_video_path', 'final_video_path', 'h264_video_path']:
                if path_var in locals():
                    path = locals()[path_var]
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except:
                            pass
            return None

    def _is_ffmpeg_available(self) -> bool:
        """检查FFmpeg是否可用"""
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    def _convert_to_h264_with_ffmpeg(self, input_path: str, output_path: str) -> bool:
        """使用FFmpeg将视频转换为H.264格式"""
        try:
            import subprocess
            
            # FFmpeg命令：转换为H.264，保持原始帧率和分辨率
            cmd = [
                'ffmpeg',
                '-i', input_path,           # 输入文件
                '-c:v', 'libx264',          # 使用H.264编码器
                '-preset', 'fast',          # 快速编码预设
                '-crf', '23',               # 质量设置（18-28，越小质量越好）
                '-movflags', '+faststart',  # 优化网络播放
                '-y',                       # 覆盖输出文件
                output_path                 # 输出文件
            ]
            
            logger.debug(f"执行FFmpeg转换: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(output_path):
                output_size = os.path.getsize(output_path)
                if output_size > 0:
                    logger.debug(f"FFmpeg转换成功: {output_path} ({output_size} bytes)")
                    return True
                else:
                    logger.warning("FFmpeg转换后文件大小为0")
                    return False
            else:
                logger.warning(f"FFmpeg转换失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg转换超时")
            return False
        except Exception as e:
            logger.warning(f"FFmpeg转换异常: {str(e)}")
            return False

    def _save_and_sort_experiment_log(self):
        """保存并自动排序实验日志"""
        try:
            # 按original_frame_range排序inference_log，方便调试
            sorted_experiment_log = sorted(
                self.experiment_log, 
                key=lambda x: x.get('video_info', {}).get('original_frame_range', [0, 0])[0]
            )
            
            log_file = os.path.join(self.temp_dir, 'experiment_log.json')
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'processor_config': {
                        'target_video_duration': self.target_video_duration,
                        'frames_per_second': self.frames_per_second,
                        'original_fps': self.original_fps,
                        'target_frames_per_video': self.target_frames_per_video,
                        'frames_to_collect_per_video': self.frames_to_collect_per_video,
                        'max_concurrent_inferences': self.max_concurrent_inferences
                    },
                    'statistics': {
                        'total_frames_received': self.total_frames_received,
                        'total_videos_created': self.total_videos_created,
                        'total_images_created': self.total_images_created,
                        'total_inferences_started': self.total_inferences_started,
                        'total_inferences_completed': self.total_inferences_completed,
                        'start_time': self.start_time,
                        'start_timestamp': datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
                        'total_duration': time.time() - (self.start_time or time.time())
                    },
                    'inference_log': sorted_experiment_log  # 使用排序后的日志
                }, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"实验日志已保存并自动排序: {log_file}")
            logger.info(f"推理日志已按帧范围排序，共 {len(sorted_experiment_log)} 条记录")
            
        except Exception as e:
            logger.error(f"保存实验日志失败: {str(e)}")

    def _create_temp_video_path(self) -> str:
        """创建临时视频文件路径"""
        timestamp = int(time.time() * 1000)
        filename = f"sampled_video_{timestamp}.mp4"
        return os.path.join(self.temp_dir, filename)

    def _save_inference_result_to_details(self, result_data: Dict):
        """保存推理结果到视频详情文件夹"""
        try:
            # 提取视频信息和推理结果
            video_info = result_data.get('video_info', {})
            details_dir = video_info.get('details_dir')
            
            if not details_dir or not os.path.exists(details_dir):
                logger.warning(f"视频详情目录不存在: {details_dir}")
                return
            
            # 创建推理结果文件路径
            inference_result_file = os.path.join(details_dir, 'inference_result.json')
            
            # 准备要保存的推理结果数据
            inference_data = {
                'video_path': result_data['video_path'],
                'inference_start_time': result_data['inference_start_time'],
                'inference_end_time': result_data['inference_end_time'],
                'inference_start_timestamp': result_data['inference_start_timestamp'],
                'inference_end_timestamp': result_data['inference_end_timestamp'],
                'inference_duration': result_data['inference_duration'],
                'result_received_at': result_data['result_received_at'],
                'raw_result': result_data['result'],  # 原始结果字符串
                'user_question': result_data.get('user_question')  # 用户问题
            }
            
            # 尝试解析JSON结果
            try:
                result_text = result_data['result']
                if result_text:
                    # 如果结果包含```json标记，提取JSON部分
                    if '```json' in result_text:
                        start_idx = result_text.find('```json') + 7
                        end_idx = result_text.find('```', start_idx)
                        if end_idx > start_idx:
                            json_text = result_text[start_idx:end_idx].strip()
                        else:
                            json_text = result_text
                    else:
                        json_text = result_text.strip()
                    
                    # 尝试解析JSON
                    import json
                    parsed_result = json.loads(json_text)
                    inference_data['parsed_result'] = parsed_result
                    logger.debug(f"成功解析推理结果JSON")
                    
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"无法解析推理结果为JSON: {str(e)}")
                inference_data['parse_error'] = str(e)
            
            # 保存推理结果到文件
            with open(inference_result_file, 'w', encoding='utf-8') as f:
                json.dump(inference_data, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"推理结果已保存到: {inference_result_file}")
            
        except Exception as e:
            logger.error(f"保存推理结果失败: {str(e)}") 

    def _save_video_details(self, sampled_frames: List[Dict], video_path: str, creation_time: float) -> Dict:
        """保存视频详情到实验目录"""
        try:
            # 创建视频详情目录
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            details_dir = os.path.join(self.temp_dir, f"{video_name}_details")
            os.makedirs(details_dir, exist_ok=True)
            
            # 将视频文件移动到details文件夹内
            new_video_path = os.path.join(details_dir, os.path.basename(video_path))
            if os.path.exists(video_path) and video_path != new_video_path:
                import shutil
                shutil.move(video_path, new_video_path)
                logger.debug(f"视频文件已移动到: {new_video_path}")
            else:
                new_video_path = video_path
            
            # 保存抽取的帧
            frame_paths = []
            for i, frame_data in enumerate(sampled_frames):
                frame_path = os.path.join(details_dir, f"frame_{i:02d}_orig_{frame_data['frame_number']:04d}.jpg")
                cv2.imwrite(frame_path, frame_data['frame'])
                frame_paths.append(frame_path)
            
            # 保存详情JSON
            details = {
                'video_path': new_video_path,  # 使用新的视频路径
                'creation_time': creation_time,
                'creation_timestamp': datetime.fromtimestamp(time.time()).isoformat(),
                'total_frames': len(sampled_frames),
                'frames_per_second': self.frames_per_second,
                'target_duration': self.target_video_duration,
                'sampled_frames': [
                    {
                        'index': i,
                        'original_frame_number': frame['frame_number'],
                        'timestamp': frame['timestamp'],
                        'timestamp_iso': datetime.fromtimestamp(frame['timestamp']).isoformat(),
                        'relative_timestamp': frame['relative_timestamp'],
                        'saved_path': frame_paths[i]
                    }
                    for i, frame in enumerate(sampled_frames)
                ]
            }
            
            details_file = os.path.join(details_dir, 'video_details.json')
            with open(details_file, 'w', encoding='utf-8') as f:
                json.dump(details, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"视频详情已保存: {details_dir}")
            return {
                'details_dir': details_dir, 
                'details_file': details_file,
                'video_path': new_video_path  # 返回新的视频路径
            }
            
        except Exception as e:
            logger.error(f"保存视频详情失败: {str(e)}")
            return {'video_path': video_path}  # 失败时返回原路径 

    def set_sentry_mode(self, enabled: bool):
        """
        设置哨兵模式状态
        
        Args:
            enabled: True启用哨兵模式，False禁用哨兵模式
        """
        with self._sentry_mode_lock:
            old_state = self.sentry_mode_enabled
            self.sentry_mode_enabled = enabled
            
            if old_state != enabled:
                mode_text = "启用" if enabled else "禁用"
                logger.info(f"🛡️ 哨兵模式已{mode_text}")
                
                # 如果有用户问题管理器，也通知它
                if self.question_manager:
                    logger.info(f"通知用户问题管理器：哨兵模式{mode_text}")
    
    def get_sentry_mode(self) -> bool:
        """
        获取当前哨兵模式状态
        
        Returns:
            bool: True表示启用，False表示禁用
        """
        with self._sentry_mode_lock:
            return self.sentry_mode_enabled
    
    def toggle_sentry_mode(self) -> bool:
        """
        切换哨兵模式状态
        
        Returns:
            bool: 切换后的状态
        """
        with self._sentry_mode_lock:
            self.sentry_mode_enabled = not self.sentry_mode_enabled
            mode_text = "启用" if self.sentry_mode_enabled else "禁用"
            logger.info(f"🛡️ 哨兵模式已{mode_text}")
            return self.sentry_mode_enabled
    
    def _update_sentry_mode_from_backend(self):
        """
        从后端API更新哨兵模式状态
        """
        try:
            import requests
            
            current_time = time.time()
            
            # 检查是否需要更新（避免频繁请求）
            if current_time - self._last_sentry_mode_check < self._sentry_mode_check_interval:
                return
            
            self._last_sentry_mode_check = current_time
            
            # 请求后端API获取哨兵模式状态
            response = requests.get(
                f"{self.backend_api_url}/api/sentry-mode",
                timeout=2.0  # 短超时，避免阻塞推理
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and 'data' in data:
                    new_enabled = data['data'].get('enabled', True)
                    
                    with self._sentry_mode_lock:
                        if self.sentry_mode_enabled != new_enabled:
                            self.sentry_mode_enabled = new_enabled
                            mode_text = "启用" if new_enabled else "禁用"
                            logger.info(f"🛡️ 从后端同步哨兵模式状态: {mode_text}")
            else:
                logger.debug(f"获取哨兵模式状态失败: HTTP {response.status_code}")
                
        except Exception as e:
            # 静默处理错误，避免影响推理流程
            logger.debug(f"更新哨兵模式状态失败: {str(e)}")
    
    def set_backend_api_url(self, url: str):
        """
        设置后端API URL
        
        Args:
            url: 后端API的URL
        """
        self.backend_api_url = url.rstrip('/')
        logger.info(f"设置后端API URL: {self.backend_api_url}")
    
    def set_sync_inference_mode(self, enabled: bool):
        """
        设置同步推理模式
        
        Args:
            enabled: True启用同步推理模式，False禁用（使用异步模式）
        """
        with self.current_inference_lock:
            old_mode = self.sync_inference_mode
            self.sync_inference_mode = enabled
            
            if old_mode != enabled:
                mode_text = "同步" if enabled else "异步"
                logger.info(f"🔄 推理模式已切换为: {mode_text}模式")
                
                # 如果切换到异步模式，清理同步模式状态
                if not enabled:
                    self.current_inference_active = False
                    self.current_inference_details = None
                    with self.pending_frame_lock:
                        if self.pending_frame_data:
                            logger.info("切换到异步模式，处理待处理帧")
                            try:
                                self.frame_queue.put(self.pending_frame_data, timeout=1)
                            except queue.Full:
                                logger.warning("帧队列已满，丢弃待处理帧")
                            self.pending_frame_data = None
    
    def get_sync_inference_mode(self) -> bool:
        """
        获取当前推理模式
        
        Returns:
            bool: True表示同步模式，False表示异步模式
        """
        return self.sync_inference_mode
    
    def get_inference_status(self) -> Dict[str, Any]:
        """
        获取推理状态信息
        
        Returns:
            包含推理状态的字典
        """
        with self.current_inference_lock:
            status = {
                'sync_mode': self.sync_inference_mode,
                'inference_active': self.current_inference_active,
                'active_tasks': len(self.active_inference_tasks),
                'max_concurrent': self.max_concurrent_inferences,
                'total_started': self.total_inferences_started,
                'total_completed': self.total_inferences_completed,
                'frames_skipped_sync': self.frames_skipped_sync_mode,
                'user_questions_processed': self.user_questions_processed
            }
            
            if self.current_inference_details:
                status['current_inference'] = {
                    'media_path': self.current_inference_details['media_path'],
                    'media_type': self.current_inference_details['media_type'],
                    'frame_number': self.current_inference_details['frame_number'],
                    'duration': time.time() - self.current_inference_details['start_time']
                }
        
        with self.pending_frame_lock:
            status['has_pending_frame'] = self.pending_frame_data is not None
            if self.pending_frame_data:
                status['pending_frame_number'] = self.pending_frame_data['frame_number']
        
        return status
    
    def _user_question_monitor_worker(self):
        """
        用户问题主动监听工作线程
        
        主动检测用户问题的到达，不依赖于新帧的输入
        当检测到用户问题时，立即处理pending_frame或触发推理中断
        """
        logger.info("用户问题监听线程启动")
        
        try:
            while not self.stop_event.is_set():
                try:
                    current_time = time.time()
                    
                    # 检查是否需要检查用户问题
                    if current_time - self.last_question_check_time >= self.question_check_interval:
                        self.last_question_check_time = current_time
                        
                        # 检查是否有用户问题
                        has_user_question = False
                        if self.question_manager:
                            has_user_question = self.question_manager.has_available_question()
                        
                        if has_user_question:
                            logger.info("🚨 用户问题监听器检测到新问题，立即处理")
                            
                            # 🔧 原子性获取用户问题，避免重复处理
                            if not self.question_manager:
                                logger.warning("用户问题管理器不存在，跳过处理")
                                continue
                                
                            user_question, task_id = self.question_manager.acquire_question()
                            if not user_question or not task_id:
                                logger.debug("用户问题已被其他任务获取，跳过")
                                continue
                            
                            logger.info(f"🚨 用户问题监听器获取到问题: {user_question} (任务ID: {task_id})")
                            
                            # 🔧 用户问题强制中断：如果有推理在进行，强制重置推理状态
                            with self.current_inference_lock:
                                if self.current_inference_active:
                                    logger.warning("🚨 用户问题监听器强制中断当前推理，重置推理状态")
                                    self.current_inference_active = False
                                    self.current_inference_details = None
                            
                            # 🔧 检查是否有pending_frame可以立即处理
                            with self.pending_frame_lock:
                                if self.pending_frame_data is not None:
                                    # 有pending_frame，立即处理
                                    pending_frame = self.pending_frame_data
                                    self.pending_frame_data = None  # 清空pending_frame
                                    
                                    logger.info(f"🚨 用户问题监听器使用pending帧 {pending_frame['frame_number']} 立即处理用户问题")
                                    
                                    # 直接将pending_frame放入队列处理
                                    try:
                                        self.frame_queue.put(pending_frame, timeout=1)
                                        self.user_questions_processed += 1
                                        logger.info("✅ 用户问题已通过监听器立即处理")
                                    except queue.Full:
                                        logger.warning("帧队列已满，用户问题处理失败")
                                        # 如果队列满了，重新放回pending_frame，并释放问题
                                        self.pending_frame_data = pending_frame
                                        if self.question_manager:
                                            self.question_manager.release_question(task_id, success=False)
                                            logger.warning(f"队列满，已释放问题: {user_question}")
                                else:
                                    # 没有pending_frame，释放问题并等待下一个帧
                                    if self.question_manager:
                                        self.question_manager.release_question(task_id, success=False)
                                    logger.info("🚨 用户问题监听器检测到问题，但无pending帧，已释放问题等待下一个帧")
                    
                    # 短暂休眠
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"用户问题监听器错误: {str(e)}")
                    time.sleep(1)  # 出错时等待更长时间
                    
        except Exception as e:
            logger.error(f"用户问题监听线程异常: {str(e)}")
        finally:
            logger.info("用户问题监听线程结束") 