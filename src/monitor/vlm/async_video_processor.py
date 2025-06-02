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

from .vlm_client import DashScopeVLMClient
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
        
        # 初始化VLM客户端
        self.vlm_client = vlm_client or DashScopeVLMClient()
        
        # 设置临时目录
        self.temp_dir = temp_dir or tempfile.gettempdir()
        
        # 抽帧参数（优先使用传入参数，否则从配置读取）
        self.target_video_duration = target_video_duration or video_config.get('target_video_duration', 3.0)
        self.frames_per_second = frames_per_second or video_config.get('frames_per_second', 5)
        self.original_fps = original_fps or video_config.get('default_fps', 25.0)
        self.target_frames_per_video = int(self.target_video_duration * self.frames_per_second)
        self.frames_per_interval = int(self.original_fps / self.frames_per_second)
        
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
        
        # 统计信息
        self.total_frames_received = 0
        self.total_videos_created = 0
        self.total_inferences_started = 0
        self.total_inferences_completed = 0
        self.start_time = None
        self.frames_resized = 0
        self.frames_invalid = 0
        
        # 实验日志
        self.experiment_log = []
        
        logger.info(f"异步视频处理器初始化:")
        logger.info(f"  - 目标视频时长: {self.target_video_duration}s")
        logger.info(f"  - 每秒抽帧数: {self.frames_per_second}帧")
        logger.info(f"  - 原始帧率: {self.original_fps}fps")
        logger.info(f"  - 每个视频总帧数: {self.target_frames_per_video}帧")
        logger.info(f"  - 抽帧间隔: 每{self.frames_per_interval:.1f}帧抽1帧")
        logger.info(f"  - 每个视频收集原始帧数: {self.frames_to_collect_per_video}帧")
        logger.info(f"  - 最大并发推理数: {self.max_concurrent_inferences}")
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
            
        logger.info(f"异步视频处理器已停止，总共处理{self.total_frames_received}帧，"
                   f"生成{self.total_videos_created}个视频片段，"
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
            
            self.frame_queue.put(frame_data, timeout=1)
            self.total_frames_received += 1
            
            if self.total_frames_received % 50 == 0:
                logger.info(f"已接收 {self.total_frames_received} 帧 "
                          f"(缩放: {self.frames_resized}, 无效: {self.frames_invalid})")
                
        except queue.Full:
            logger.warning("帧队列已满，丢弃帧")
        except Exception as e:
            logger.error(f"添加帧失败: {str(e)}")

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

    def _submit_inference_task(self, video_info: Dict):
        """提交异步推理任务"""
        if self.inference_event_loop and not self.inference_event_loop.is_closed() and len(self.active_inference_tasks) < self.max_concurrent_inferences:
            try:
                task = asyncio.run_coroutine_threadsafe(
                    self._inference_worker_async(video_info),
                    self.inference_event_loop
                )
                self.active_inference_tasks.append(task)
                self.total_inferences_started += 1
                
                logger.info(f"提交异步推理任务: {os.path.basename(video_info['video_path'])}")
                logger.info(f"  - 当前并发数: {len(self.active_inference_tasks)}/{self.max_concurrent_inferences}")
                logger.info(f"  - 总启动数: {self.total_inferences_started}")
            except Exception as e:
                logger.error(f"提交推理任务失败: {str(e)}")
        else:
            if self.inference_event_loop is None:
                logger.warning("事件循环未就绪，跳过推理")
            elif self.inference_event_loop.is_closed():
                logger.warning("事件循环已关闭，跳过推理")
            elif len(self.active_inference_tasks) >= self.max_concurrent_inferences:
                logger.warning(f"推理任务队列已满 ({len(self.active_inference_tasks)}/{self.max_concurrent_inferences})，跳过推理")
            else:
                logger.warning("推理任务提交失败，原因未知")

    async def _inference_worker_async(self, video_info: Dict):
        """真正的异步推理工作函数"""
        try:
            # 记录推理开始时间
            inference_start_time = time.time()
            inference_start_timestamp = datetime.now().isoformat()
            
            logger.info(f"开始异步VLM推理: {os.path.basename(video_info['video_path'])}")
            logger.info(f"  - 推理开始时间: {inference_start_timestamp}")
            logger.info(f"  - 源视频时间范围: {video_info['start_relative_timestamp']:.2f}s - {video_info['end_relative_timestamp']:.2f}s")
            
            # 执行异步推理
            result = await self.vlm_client.analyze_video_async(
                video_info['video_path'], 
                prompt=None,  # 使用配置文件中的默认提示词
                fps=2
            )
            
            # 记录推理结束时间
            inference_end_time = time.time()
            inference_end_timestamp = datetime.now().isoformat()
            inference_duration = inference_end_time - inference_start_time
            
            logger.info(f"异步VLM推理完成: {os.path.basename(video_info['video_path'])}")
            logger.info(f"  - 推理结束时间: {inference_end_timestamp}")
            logger.info(f"  - 推理耗时: {inference_duration:.2f}s")
            logger.info(f"  - 结果长度: {len(result) if result else 0}字符")
            
            # 将结果放入结果队列
            result_data = {
                'video_path': video_info['video_path'],
                'result': result,
                'video_info': video_info,
                'inference_start_time': inference_start_time,
                'inference_end_time': inference_end_time,
                'inference_start_timestamp': inference_start_timestamp,
                'inference_end_timestamp': inference_end_timestamp,
                'inference_duration': inference_duration,
                'result_received_at': time.time()
            }
            
            # 记录到实验日志
            self.experiment_log.append(result_data.copy())
            self.total_inferences_completed += 1
            
            # 保存推理结果到视频详情文件夹
            self._save_inference_result_to_details(result_data)
            
            try:
                self.result_queue.put(result_data, timeout=1)
                logger.info(f"异步推理结果已入队: {os.path.basename(video_info['video_path'])}")
            except queue.Full:
                logger.warning("结果队列已满，丢弃结果")
                
        except Exception as e:
            logger.error(f"异步推理失败: {str(e)}")
            self.total_inferences_completed += 1  # 即使失败也计入完成数
            
        # 注意：不删除临时文件，保留用于调试
        logger.debug(f"保留视频文件用于调试: {video_info['video_path']}")

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
                            'video_path': final_video_path,  # 使用最终的视频路径
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
                    
        except Exception as e:
            logger.error(f"视频写入线程错误: {str(e)}")

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

    def _create_video_from_frames(self, frames_data: List[Dict]) -> Optional[str]:
        """从帧数据创建视频文件"""
        if not frames_data:
            return None
            
        try:
            video_path = self._create_temp_video_path()
            
            # 获取第一帧的尺寸
            first_frame = frames_data[0]['frame']
            height, width = first_frame.shape[:2]
            
            # 创建视频写入器，使用目标帧率
            output_fps = self.frames_per_second  # 输出视频的帧率等于每秒抽取的帧数
            fourcc = cv2.VideoWriter.fourcc(*'avc1')  # 使用H.264编码，更好的浏览器兼容性
            writer = cv2.VideoWriter(video_path, fourcc, output_fps, (width, height))
            
            # 写入所有帧
            for frame_data in frames_data:
                writer.write(frame_data['frame'])
                
            writer.release()
            
            # 检查文件大小
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            if file_size_mb > 95:  # 如果超过95MB，删除文件
                os.remove(video_path)
                logger.warning(f"视频文件过大 ({file_size_mb:.2f}MB)，已删除")
                return None
                
            logger.debug(f"视频文件创建成功: {video_path} ({file_size_mb:.2f}MB, {output_fps}fps)")
            return video_path
            
        except Exception as e:
            logger.error(f"创建视频文件失败: {str(e)}")
            return None

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
                'raw_result': result_data['result']  # 原始结果字符串
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