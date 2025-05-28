import os
import cv2
import time
import threading
import queue
import tempfile
import asyncio
from pathlib import Path
from typing import Optional, Dict, List, Callable
from dashscope import MultiModalConversation
import logging
import numpy as np
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DashScopeVLMClient:
    def __init__(self, api_key: Optional[str] = None, model: str = 'qwen-vl-max-latest'):
        """
        初始化DashScope VLM客户端
        
        Args:
            api_key: API密钥，如果为None则从环境变量DASHSCOPE_API_KEY获取
            model: 使用的模型名称
        """
        self.api_key = api_key or os.getenv('DASHSCOPE_API_KEY')
        if not self.api_key:
            raise ValueError("API密钥未设置，请设置DASHSCOPE_API_KEY环境变量或传入api_key参数")
        
        self.model = model
        
    def analyze_video(self, video_path: str, prompt: str = "这段视频描绘的是什么景象?", fps: int = 2) -> Optional[str]:
        """
        分析视频内容
        
        Args:
            video_path: 视频文件路径
            prompt: 分析提示词
            fps: 视频帧率（用于控制分析的帧数）
            
        Returns:
            分析结果文本，如果失败返回None
        """
        try:
            # 检查文件大小
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            if file_size_mb > 100:
                logger.error(f"视频文件过大: {file_size_mb:.2f}MB，超过100MB限制")
                return None
                
            logger.info(f"开始分析视频: {video_path} ({file_size_mb:.2f}MB)")
            
            # 构建消息
            messages = [
                {
                    'role': 'user',
                    'content': [
                        {
                            'video': f"file://{video_path}"
                        },
                        {
                            'text': prompt
                        }
                    ]
                }
            ]
            
            # 调用API
            if not self.api_key:
                logger.error("API密钥未设置")
                return None
                
            response = MultiModalConversation.call(
                model=self.model,
                messages=messages,
                api_key=self.api_key
            )
            
            # 处理响应
            if hasattr(response, 'output') and 'choices' in response.output:
                result = response.output['choices'][0]['message']['content']
                logger.info(f"视频分析完成，结果长度: {len(result)} 字符")
                return result
            else:
                logger.error(f"API响应格式异常: {response}")
                return None
                
        except Exception as e:
            logger.error(f"视频分析失败: {str(e)}")
            return None

class AsyncVideoProcessor:
    def __init__(self, vlm_client: DashScopeVLMClient, temp_dir: Optional[str] = None,
                 target_video_duration: float = 3.0, frames_per_second: int = 2,
                 original_fps: float = 25.0):
        """
        异步视频处理器
        
        Args:
            vlm_client: VLM客户端
            temp_dir: 临时目录
            target_video_duration: 目标视频时长（秒）
            frames_per_second: 每秒抽取的帧数
            original_fps: 原始视频帧率
        """
        self.vlm_client = vlm_client
        self.temp_dir = temp_dir or tempfile.gettempdir()
        
        # 抽帧参数
        self.target_video_duration = target_video_duration
        self.frames_per_second = frames_per_second
        self.original_fps = original_fps
        self.target_frames_per_video = int(target_video_duration * frames_per_second)  # 3秒 × 2帧/秒 = 6帧
        self.frames_per_interval = int(original_fps / frames_per_second)  # 25fps / 2 = 12.5，每12-13帧抽1帧
        
        # 计算需要收集的总帧数（3秒的原始帧数）
        self.frames_to_collect_per_video = int(target_video_duration * original_fps)  # 3秒 × 25fps = 75帧
        
        # 缓冲区和队列
        self.frame_buffer = []
        self.frame_queue = queue.Queue(maxsize=100)
        self.video_queue = queue.Queue(maxsize=10)
        self.result_queue = queue.Queue(maxsize=20)
        
        # 线程控制
        self.stop_event = threading.Event()
        self.video_writer_thread = None
        self.inference_thread = None
        
        # 统计信息
        self.total_frames_received = 0
        self.total_videos_created = 0
        self.start_time = None
        
        # 实验日志
        self.experiment_log = []
        
        logger.info(f"异步视频处理器初始化:")
        logger.info(f"  - 目标视频时长: {target_video_duration}s")
        logger.info(f"  - 每秒抽帧数: {frames_per_second}帧")
        logger.info(f"  - 原始帧率: {original_fps}fps")
        logger.info(f"  - 每个视频总帧数: {self.target_frames_per_video}帧")
        logger.info(f"  - 抽帧间隔: 每{self.frames_per_interval:.1f}帧抽1帧")
        logger.info(f"  - 每个视频收集原始帧数: {self.frames_to_collect_per_video}帧")

    def start(self):
        """启动异步处理"""
        self.stop_event.clear()
        self.start_time = time.time()
        
        # 启动视频写入线程
        self.video_writer_thread = threading.Thread(target=self._video_writer_worker)
        self.video_writer_thread.start()
        
        # 启动推理线程
        self.inference_thread = threading.Thread(target=self._inference_worker)
        self.inference_thread.start()
        
        logger.info("异步视频处理器已启动")

    def stop(self):
        """停止异步处理"""
        self.stop_event.set()
        
        if self.video_writer_thread:
            self.video_writer_thread.join()
        if self.inference_thread:
            self.inference_thread.join()
            
        logger.info(f"异步视频处理器已停止，总共处理{self.total_frames_received}帧，"
                   f"生成{self.total_videos_created}个视频片段")
        
        # 保存实验日志
        self._save_experiment_log()

    def add_frame(self, frame, timestamp: Optional[float] = None):
        """添加帧到处理队列"""
        try:
            frame_data = {
                'frame': frame,
                'timestamp': timestamp or time.time(),
                'frame_number': self.total_frames_received + 1,
                'relative_timestamp': (timestamp or time.time()) - (self.start_time or time.time())
            }
            self.frame_queue.put(frame_data, timeout=1)
            self.total_frames_received += 1
            
            if self.total_frames_received % 50 == 0:
                logger.info(f"已接收 {self.total_frames_received} 帧")
                
        except queue.Full:
            logger.warning("帧队列已满，丢弃帧")

    def get_result(self, timeout: float = 1.0) -> Optional[Dict]:
        """获取推理结果"""
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None

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
                        
                        video_info.update({
                            'video_path': video_path,
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
                            'created_at': time.time()
                        })
                        
                        try:
                            self.video_queue.put(video_info, timeout=1)
                            self.total_videos_created += 1
                            logger.info(f"视频片段已生成: {os.path.basename(video_path)}")
                            logger.info(f"  - 帧范围: {video_info['original_frame_range']}")
                            logger.info(f"  - 源视频时间: {start_relative:.2f}s - {end_relative:.2f}s")
                            logger.info(f"  - 视频创建耗时: {video_creation_time:.3f}s")
                        except queue.Full:
                            logger.warning("视频队列已满，删除视频文件")
                            os.remove(video_path)
                    
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
            
            # 保存抽取的帧
            frame_paths = []
            for i, frame_data in enumerate(sampled_frames):
                frame_path = os.path.join(details_dir, f"frame_{i:02d}_orig_{frame_data['frame_number']:04d}.jpg")
                cv2.imwrite(frame_path, frame_data['frame'])
                frame_paths.append(frame_path)
            
            # 保存详情JSON
            details = {
                'video_path': video_path,
                'creation_time': creation_time,
                'total_frames': len(sampled_frames),
                'frames_per_second': self.frames_per_second,
                'target_duration': self.target_video_duration,
                'sampled_frames': [
                    {
                        'index': i,
                        'original_frame_number': frame['frame_number'],
                        'timestamp': frame['timestamp'],
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
            return {'details_dir': details_dir, 'details_file': details_file}
            
        except Exception as e:
            logger.error(f"保存视频详情失败: {str(e)}")
            return {}

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
            fourcc = cv2.VideoWriter.fourcc(*'mp4v')
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

    def _inference_worker(self):
        """推理工作线程 - 真正的异步推理"""
        while not self.stop_event.is_set():
            try:
                video_info = self.video_queue.get(timeout=1)
            except queue.Empty:
                continue
                
            try:
                # 记录推理开始时间
                inference_start_time = time.time()
                inference_start_timestamp = datetime.now().isoformat()
                
                logger.info(f"开始VLM推理: {os.path.basename(video_info['video_path'])}")
                logger.info(f"  - 推理开始时间: {inference_start_timestamp}")
                logger.info(f"  - 源视频时间范围: {video_info['start_relative_timestamp']:.2f}s - {video_info['end_relative_timestamp']:.2f}s")
                
                # 执行推理
                result = self.vlm_client.analyze_video(
                    video_info['video_path'], 
                    prompt=f"请详细描述这段视频中发生的事件。这段视频包含{video_info['frame_count']}帧，"
                           f"代表源视频中{video_info['start_relative_timestamp']:.2f}s到{video_info['end_relative_timestamp']:.2f}s的内容，"
                           f"每秒抽取了{self.frames_per_second}帧。",
                    fps=2
                )
                
                # 记录推理结束时间
                inference_end_time = time.time()
                inference_end_timestamp = datetime.now().isoformat()
                inference_duration = inference_end_time - inference_start_time
                
                logger.info(f"VLM推理完成: {os.path.basename(video_info['video_path'])}")
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
                
                try:
                    self.result_queue.put(result_data, timeout=1)
                except queue.Full:
                    logger.warning("结果队列已满，丢弃结果")
                    
            except Exception as e:
                logger.error(f"推理失败: {str(e)}")
                
            finally:
                # 清理临时文件
                try:
                    video_path = video_info['video_path']
                    if os.path.exists(video_path):
                        os.remove(video_path)
                        logger.debug(f"已删除临时文件: {video_path}")
                except Exception as e:
                    logger.error(f"删除临时文件失败: {str(e)}")

    def _save_experiment_log(self):
        """保存实验日志"""
        try:
            log_file = os.path.join(self.temp_dir, 'experiment_log.json')
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'processor_config': {
                        'target_video_duration': self.target_video_duration,
                        'frames_per_second': self.frames_per_second,
                        'original_fps': self.original_fps,
                        'target_frames_per_video': self.target_frames_per_video,
                        'frames_to_collect_per_video': self.frames_to_collect_per_video
                    },
                    'statistics': {
                        'total_frames_received': self.total_frames_received,
                        'total_videos_created': self.total_videos_created,
                        'start_time': self.start_time,
                        'total_duration': time.time() - (self.start_time or time.time())
                    },
                    'inference_log': self.experiment_log
                }, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"实验日志已保存: {log_file}")
            
        except Exception as e:
            logger.error(f"保存实验日志失败: {str(e)}")

    def _create_temp_video_path(self) -> str:
        """创建临时视频文件路径"""
        timestamp = int(time.time() * 1000)
        filename = f"sampled_video_{timestamp}.mp4"
        return os.path.join(self.temp_dir, filename)

class RTSPVLMMonitor:
    def __init__(self, rtsp_client, vlm_client: DashScopeVLMClient, 
                 result_callback: Optional[Callable] = None):
        """
        RTSP VLM监控器
        
        Args:
            rtsp_client: RTSP客户端实例
            vlm_client: VLM客户端实例
            result_callback: 结果回调函数
        """
        self.rtsp_client = rtsp_client
        self.vlm_client = vlm_client
        self.result_callback = result_callback
        
        self.video_processor = AsyncVideoProcessor(vlm_client)
        self.monitor_thread = None
        self.stop_event = threading.Event()
        
    def start_monitoring(self):
        """开始监控"""
        self.stop_event.clear()
        self.video_processor.start()
        
        # 启动结果监控线程
        self.monitor_thread = threading.Thread(target=self._result_monitor)
        self.monitor_thread.start()
        
        # 设置RTSP客户端的回调函数
        def frame_callback(frame):
            if not self.stop_event.is_set():
                self.video_processor.add_frame(frame)
                return True
            return False
            
        # 启动RTSP客户端
        try:
            self.rtsp_client.run(callback=frame_callback)
        except Exception as e:
            logger.error(f"RTSP客户端错误: {str(e)}")
        finally:
            self.stop_monitoring()
            
    def stop_monitoring(self):
        """停止监控"""
        self.stop_event.set()
        self.rtsp_client.stop_event.set()
        self.video_processor.stop()
        
        if self.monitor_thread:
            self.monitor_thread.join()
            
        logger.info("VLM监控已停止")
        
    def _result_monitor(self):
        """结果监控线程"""
        while not self.stop_event.is_set():
            result = self.video_processor.get_result(timeout=1.0)
            if result and self.result_callback:
                try:
                    self.result_callback(result)
                except Exception as e:
                    logger.error(f"结果回调函数错误: {str(e)}") 