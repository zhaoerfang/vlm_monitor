#!/usr/bin/env python3
"""
FastAPI后端服务器
提供WebSocket视频流和REST API接口
作为唯一的TCP客户端，内部分发视频流给推理服务
"""

import os
import sys
import json
import time
import asyncio
import base64
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import logging
import queue
import threading
import io

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

from monitor.tcp.tcp_client import TCPVideoClient
from monitor.core.config import load_config

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_relative_path(path: Path, base: Optional[Path] = None) -> str:
    """
    安全地计算相对路径，如果无法计算则返回绝对路径
    
    Args:
        path: 要计算相对路径的路径
        base: 基准路径，默认为当前工作目录
        
    Returns:
        相对路径字符串，如果无法计算则返回绝对路径字符串
    """
    if base is None:
        base = Path.cwd()
    
    try:
        # 尝试计算相对路径
        return str(path.relative_to(base))
    except ValueError:
        # 如果无法计算相对路径，返回绝对路径
        logger.warning(f"无法计算相对路径: {path} 相对于 {base}，使用绝对路径")
        return str(path.resolve())

# 创建FastAPI应用
app = FastAPI(
    title="VLM监控系统API",
    description="基于大模型的视频监控系统后端API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic模型
class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: float

class VideoFrame(BaseModel):
    data: str  # base64编码的图像数据
    timestamp: float
    frame_number: int

class SystemStatus(BaseModel):
    streaming: bool
    connected_clients: int
    frame_count: int
    has_experiment_log: bool
    temp_dir: Optional[str]

# 内部视频流分发器 - 简化版本（回到正常工作的架构）
class SimpleVideoDistributor:
    def __init__(self):
        # 订阅者管理
        self.subscribers = []
        self.subscribers_lock = threading.Lock()
        
        # 性能统计
        self.total_frames = 0
        self.display_frames = 0
        self.inference_frames = 0
        
        # 最新帧缓存
        self.latest_frame = None
        self.latest_frame_timestamp = None
        self.latest_frame_lock = threading.Lock()
        
        # WebSocket视频帧队列
        self.websocket_frame_queue = queue.Queue(maxsize=5)  # 限制队列大小避免内存占用过多
        
        logger.info("简化视频分发器初始化完成")
    
    def distribute_frame(self, frame: np.ndarray, timestamp: float):
        """直接分发帧 - 简单高效"""
        self.total_frames += 1
        
        # 更新最新帧缓存
        with self.latest_frame_lock:
            self.latest_frame = frame
            self.latest_frame_timestamp = timestamp
        
        # 立即编码为JPEG（在主线程中，避免延迟）
        try:
            encode_params = [
                cv2.IMWRITE_JPEG_QUALITY, 85,
                cv2.IMWRITE_JPEG_OPTIMIZE, 0,
                cv2.IMWRITE_JPEG_PROGRESSIVE, 0,
            ]
            
            _, buffer = cv2.imencode('.jpg', frame, encode_params)
            jpeg_data = buffer.tobytes()
            
            # 直接更新最新JPEG帧（原子操作）
            state.latest_jpeg_frame = jpeg_data
            self.display_frames += 1
            
            # 将视频帧数据放入队列，供WebSocket处理
            try:
                frame_data = {
                    'jpeg_data': jpeg_data,
                    'timestamp': timestamp,
                    'frame_number': self.total_frames
                }
                self.websocket_frame_queue.put_nowait(frame_data)
            except queue.Full:
                # 队列满了，丢弃最老的帧
                try:
                    self.websocket_frame_queue.get_nowait()
                    self.websocket_frame_queue.put_nowait(frame_data)
                except queue.Empty:
                    pass
            
        except Exception as e:
            logger.error(f"JPEG编码失败: {e}")
        
        # 推理处理（跳帧）
        if self.total_frames % 8 == 0:  # 每8帧处理一次推理
            try:
                with self.subscribers_lock:
                    for subscriber in self.subscribers[:]:
                        if subscriber.get('active', True):
                            try:
                                should_continue = subscriber['callback'](frame.copy(), timestamp)
                                if not should_continue:
                                    subscriber['active'] = False
                            except Exception as e:
                                logger.error(f"推理订阅者错误: {e}")
                                subscriber['active'] = False
                
                self.inference_frames += 1
                
            except Exception as e:
                logger.error(f"推理处理错误: {e}")
    
    def get_websocket_frame(self):
        """获取待发送的WebSocket帧数据"""
        try:
            return self.websocket_frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def subscribe(self, callback: Callable[[np.ndarray, float], bool]) -> str:
        """订阅推理流"""
        subscriber_id = f"subscriber_{int(time.time() * 1000)}_{len(self.subscribers)}"
        subscriber = {
            'id': subscriber_id,
            'callback': callback,
            'active': True
        }
        
        with self.subscribers_lock:
            self.subscribers.append(subscriber)
        
        logger.info(f"新推理订阅者: {subscriber_id}")
        return subscriber_id
    
    def unsubscribe(self, subscriber_id: str):
        """取消订阅"""
        with self.subscribers_lock:
            self.subscribers = [s for s in self.subscribers if s['id'] != subscriber_id]
        logger.info(f"取消订阅: {subscriber_id}")
    
    def get_subscriber_count(self) -> int:
        """获取订阅者数量"""
        with self.subscribers_lock:
            return len([s for s in self.subscribers if s.get('active', True)])
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return {
            'total_frames': self.total_frames,
            'display_frames': self.display_frames,
            'inference_frames': self.inference_frames,
            'drop_rate': 0,  # 简化版本不计算丢帧率
        }
    
    def get_latest_frame(self) -> Optional[tuple]:
        """获取最新帧"""
        with self.latest_frame_lock:
            if self.latest_frame is not None:
                return (self.latest_frame, self.latest_frame_timestamp)
            return None

# 全局状态管理
class AppState:
    def __init__(self):
        self.config = load_config()
        self.tcp_client: Optional[TCPVideoClient] = None
        self.streaming = False
        self.connected_clients: List[WebSocket] = []
        self.frame_count = 0
        self.last_frame: Optional[Dict] = None
        self.experiment_log_path: Optional[Path] = None
        self.temp_dir: Optional[Path] = None
        self.latest_session_dir: Optional[Path] = None
        
        # 视频帧队列（保留兼容性）
        self.frame_queue = queue.Queue(maxsize=10)
        self.queue_processor_task: Optional[asyncio.Task] = None
        
        # 简化视频流分发器
        self.video_distributor = SimpleVideoDistributor()
        
        # 查找最新的实验目录
        self._find_latest_session_dir()
        
        # HTTP流媒体相关
        self.mjpeg_clients = []
        self.mjpeg_clients_lock = threading.Lock()
        self.latest_jpeg_frame: Optional[bytes] = None
        
        # 哨兵模式状态管理
        self.sentry_mode_enabled = True  # 默认启用哨兵模式
        self._sentry_mode_lock = threading.Lock()  # 线程安全锁
    
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
            logger.info(f"🛡️ 哨兵模式已切换为{mode_text}")
            return self.sentry_mode_enabled
    
    def _find_latest_session_dir(self):
        """查找最新的实验会话目录"""
        tmp_dir = Path('tmp')
        if tmp_dir.exists():
            # 查找最新的session目录
            session_dirs = [d for d in tmp_dir.iterdir() if d.is_dir() and d.name.startswith('session_')]
            if session_dirs:
                latest_session = max(session_dirs, key=lambda x: x.stat().st_mtime)
                self.latest_session_dir = latest_session
                self.temp_dir = latest_session
                logger.info(f"找到最新实验目录: {latest_session}")
                
                # 检查是否有experiment_log.json
                experiment_log = latest_session / 'experiment_log.json'
                if experiment_log.exists():
                    self.experiment_log_path = experiment_log
                    logger.info(f"找到实验日志: {experiment_log}")
                else:
                    logger.info("实验日志文件尚未生成，将从sampled_video目录读取推理结果")
    
    def get_latest_inference_results(self, limit: int = 10):
        """从sampled_video目录获取最新的推理结果"""
        # 每次调用时都刷新最新的session目录
        self._find_latest_session_dir()
        
        if not self.latest_session_dir or not self.latest_session_dir.exists():
            logger.warning(f"最新session目录不存在: {self.latest_session_dir}")
            return []
        
        inference_results = []
        
        # 查找所有sampled_video目录
        sampled_dirs = [d for d in self.latest_session_dir.iterdir() 
                       if d.is_dir() and d.name.startswith('sampled_video_') and d.name.endswith('_details')]
        
        logger.info(f"找到 {len(sampled_dirs)} 个推理结果目录")
        
        # 按时间戳排序（从目录名中提取时间戳）
        sampled_dirs.sort(key=lambda x: int(x.name.split('_')[2]), reverse=True)
        
        # 分别收集有AI结果和没有AI结果的推理
        results_with_ai = []
        results_without_ai = []
        
        # 获取推理结果
        for i, sampled_dir in enumerate(sampled_dirs):
            try:
                video_details_file = sampled_dir / 'video_details.json'
                inference_result_file = sampled_dir / 'inference_result.json'
                
                if not video_details_file.exists():
                    continue
                
                with open(video_details_file, 'r', encoding='utf-8') as f:
                    video_details = json.load(f)
                
                # 构造基础推理结果格式
                inference_result = {
                    "timestamp": video_details.get("creation_timestamp"),
                    "creation_timestamp": video_details.get("creation_timestamp"),
                    "video_path": video_details.get("video_path"),
                    "total_frames": video_details.get("total_frames"),
                    "frames_per_second": video_details.get("frames_per_second"),
                    "target_duration": video_details.get("target_duration"),
                    "sampled_frames": video_details.get("sampled_frames", []),
                    "creation_time": video_details.get("creation_time"),
                    "session_dir": str(state.latest_session_dir.relative_to(Path.cwd())) if state.latest_session_dir else None,
                    "video_id": sampled_dir.name.replace('_details', ''),
                    "has_inference_result": False
                }
                
                # 如果存在inference_result.json，读取详细推理结果
                if inference_result_file.exists():
                    try:
                        with open(inference_result_file, 'r', encoding='utf-8') as f:
                            inference_data = json.load(f)
                        
                        # 添加推理结果数据
                        inference_result.update({
                            "has_inference_result": True,
                            "inference_start_time": inference_data.get("inference_start_time"),
                            "inference_end_time": inference_data.get("inference_end_time"),
                            "inference_duration": inference_data.get("inference_duration"),
                            "result_received_at": inference_data.get("result_received_at"),
                            "raw_result": inference_data.get("raw_result"),
                            "parsed_result": inference_data.get("parsed_result"),
                            "people_count": inference_data.get("parsed_result", {}).get("people_count", 0),
                            "vehicle_count": inference_data.get("parsed_result", {}).get("vehicle_count", 0),
                            "people": inference_data.get("parsed_result", {}).get("people", []),
                            "vehicles": inference_data.get("parsed_result", {}).get("vehicles", []),
                            "summary": inference_data.get("parsed_result", {}).get("summary", ""),
                            "user_question": inference_data.get("user_question"),  # 用户问题
                            "response": inference_data.get("parsed_result", {}).get("response") or inference_data.get("parsed_result", {}).get("answer")  # AI回答
                        })
                        
                        # 添加到有AI结果的列表
                        results_with_ai.append(inference_result)
                        logger.debug(f"推理结果(有AI): {inference_result['video_id']}, 时间: {inference_result['creation_timestamp']}")
                    
                    except Exception as e:
                        logger.warning(f"读取推理结果文件失败 {inference_result_file}: {e}")
                        # 即使读取失败，也添加到没有AI结果的列表
                        results_without_ai.append(inference_result)
                else:
                    # 添加到没有AI结果的列表
                    results_without_ai.append(inference_result)
                    logger.debug(f"推理结果(无AI): {inference_result['video_id']}, 时间: {inference_result['creation_timestamp']}")
                    
            except Exception as e:
                logger.warning(f"读取推理结果失败 {sampled_dir}: {e}")
                continue
        
        # 优先返回有AI结果的推理，然后是没有AI结果的推理
        # 每个列表内部按时间戳倒序排列（最新的在前）
        inference_results = results_with_ai + results_without_ai
        
        # 限制返回数量
        inference_results = inference_results[:limit]
        
        # 记录最新的推理结果信息
        if inference_results:
            latest = inference_results[0]
            logger.info(f"最新推理结果: {latest['video_id']}, 时间: {latest['creation_timestamp']}, 有AI结果: {latest['has_inference_result']}")
            logger.info(f"总计: 有AI结果={len(results_with_ai)}, 无AI结果={len(results_without_ai)}, 返回={len(inference_results)}")
        
        logger.info(f"成功获取 {len(inference_results)} 个推理结果")
        return inference_results

    async def add_client(self, websocket: WebSocket):
        """添加WebSocket客户端"""
        self.connected_clients.append(websocket)
        logger.info(f"客户端连接，当前连接数: {len(self.connected_clients)}")
        
        # 启动队列处理器（如果还没有启动）
        if self.queue_processor_task is None or self.queue_processor_task.done():
            self.queue_processor_task = asyncio.create_task(self._process_frame_queue())

    async def remove_client(self, websocket: WebSocket):
        """移除WebSocket客户端"""
        if websocket in self.connected_clients:
            self.connected_clients.remove(websocket)
        logger.info(f"客户端断开，当前连接数: {len(self.connected_clients)}")

    async def broadcast_message(self, message_type: str, data: Any):
        """广播消息给所有连接的客户端"""
        message = {
            "type": message_type,
            "data": data,
            "timestamp": time.time()
        }
        
        # 移除已断开的连接
        disconnected = []
        for client in self.connected_clients:
            try:
                await client.send_json(message)
            except Exception as e:
                logger.warning(f"发送消息失败: {e}")
                disconnected.append(client)
        
        # 清理断开的连接
        for client in disconnected:
            await self.remove_client(client)
    
    def add_frame_to_queue(self, frame_data: Dict):
        """添加帧数据到队列"""
        try:
            self.frame_queue.put_nowait(frame_data)
        except queue.Full:
            # 队列满了，丢弃最老的帧
            try:
                self.frame_queue.get_nowait()
                self.frame_queue.put_nowait(frame_data)
            except queue.Empty:
                pass
    
    async def _process_frame_queue(self):
        """处理帧队列（现在主要用于状态更新和WebSocket视频帧发送）"""
        logger.info("启动状态队列处理器")
        while True:
            try:
                # 检查是否有状态数据
                if not self.frame_queue.empty():
                    status_data = self.frame_queue.get_nowait()
                    if len(self.connected_clients) > 0:
                        await self.broadcast_message("stream_status", status_data)
                        logger.debug(f"广播状态更新 #{status_data.get('frame_number', 0)}")
                
                # 处理WebSocket视频帧发送
                if self.video_distributor and len(self.connected_clients) > 0:
                    frame_data = self.video_distributor.get_websocket_frame()
                    if frame_data:
                        try:
                            # 将JPEG数据编码为base64
                            frame_base64 = base64.b64encode(frame_data['jpeg_data']).decode('utf-8')
                            
                            # 构造视频帧消息
                            video_frame_data = {
                                "data": frame_base64,
                                "timestamp": frame_data['timestamp'],
                                "frame_number": frame_data['frame_number']
                            }
                            
                            # 发送给所有连接的WebSocket客户端
                            await self.broadcast_message("video_frame", video_frame_data)
                            
                        except Exception as e:
                            logger.error(f"WebSocket发送视频帧失败: {e}")
                
                # 短暂休眠避免CPU占用过高
                await asyncio.sleep(0.01)  # 提高频率来处理视频帧，100fps的理论上限
                
            except Exception as e:
                logger.error(f"处理状态队列异常: {e}")
                await asyncio.sleep(0.1)

# 创建全局状态实例
state = AppState()

# WebSocket处理
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await state.add_client(websocket)
    
    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "status_update",
            "data": {
                "message": "WebSocket连接成功",
                "connected": True
            },
            "timestamp": time.time()
        })
        
        # 保持连接并处理消息
        while True:
            message = await websocket.receive_json()
            await handle_websocket_message(websocket, message)
            
    except WebSocketDisconnect:
        await state.remove_client(websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        await state.remove_client(websocket)

async def handle_websocket_message(websocket: WebSocket, message: Dict):
    """处理WebSocket消息"""
    message_type = message.get("type")
    
    if message_type == "start_stream":
        await start_video_stream(websocket)
    elif message_type == "stop_stream":
        await stop_video_stream(websocket)
    elif message_type == "get_latest_inference":
        await send_latest_inference(websocket)
    else:
        await websocket.send_json({
            "type": "error",
            "data": f"未知消息类型: {message_type}",
            "timestamp": time.time()
        })

async def start_video_stream(websocket: WebSocket):
    """启动视频流"""
    logger.info("收到启动视频流请求")
    
    if state.streaming:
        logger.warning("视频流已在运行中")
        await websocket.send_json({
            "type": "error",
            "data": "视频流已在运行中",
            "timestamp": time.time()
        })
        return
    
    try:
        # 创建TCP客户端 - 使用优化参数
        tcp_config = state.config['stream']['tcp']
        logger.info(f"创建TCP客户端: {tcp_config['host']}:{tcp_config['port']}")
        
        state.tcp_client = TCPVideoClient(
            host=tcp_config['host'],
            port=tcp_config['port'],
            frame_rate=60,  # 设置高帧率，确保不限制接收
            timeout=tcp_config.get('connection_timeout', 10),
            buffer_size=2000  # 进一步增加缓冲区
        )
        
        # 启动视频流任务
        logger.info("启动视频流任务...")
        task = asyncio.create_task(run_video_stream())
        
        # 等待一小段时间确保任务启动
        await asyncio.sleep(0.1)
        
        logger.info("视频流任务已启动")
        await websocket.send_json({
            "type": "status_update",
            "data": {
                "message": "视频流已启动",
                "streaming": True
            },
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"启动视频流失败: {str(e)}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "data": f"启动视频流失败: {str(e)}",
            "timestamp": time.time()
        })

async def stop_video_stream(websocket: WebSocket):
    """停止视频流"""
    state.streaming = False
    if state.tcp_client:
        state.tcp_client.disconnect()
        state.tcp_client = None
    
    await websocket.send_json({
        "type": "status_update",
        "data": {
            "message": "视频流已停止",
            "streaming": False
        },
        "timestamp": time.time()
    })

async def send_latest_inference(websocket: WebSocket):
    """发送最新推理结果"""
    try:
        # 刷新最新的实验目录
        state._find_latest_session_dir()
        
        # 获取最新推理结果
        inference_results = state.get_latest_inference_results(limit=1)
        if inference_results:
            latest_inference = inference_results[0]
            await websocket.send_json({
                "type": "inference_result",
                "data": latest_inference,
                "timestamp": time.time()
            })
            logger.info(f"发送最新推理结果: {latest_inference.get('video_id', 'unknown')}")
        else:
            await websocket.send_json({
                "type": "inference_result",
                "data": None,
                "error": "没有找到推理结果",
                "timestamp": time.time()
            })
            logger.debug("没有找到推理结果")
            
    except Exception as e:
        logger.error(f"发送推理结果失败: {e}")
        await websocket.send_json({
            "type": "error",
            "data": {"message": f"获取推理结果失败: {str(e)}"},
            "timestamp": time.time()
        })

async def run_video_stream():
    """运行视频流（异步版本）- 零延迟多管道架构"""
    logger.info("开始运行视频流 - 零延迟多管道架构")
    state.streaming = True
    state.frame_count = 0
    
    # 简化版本不需要启动分发器
    
    def frame_callback(frame):
        """超简化的帧回调 - 只负责快速分发"""
        if not state.streaming:
            return False
        
        try:
            current_timestamp = time.time()
            state.frame_count += 1
            
            # 零延迟分发到各个管道
            state.video_distributor.distribute_frame(frame, current_timestamp)
            
            # 简单的性能监控
            if state.frame_count % 1000 == 0:
                stats = state.video_distributor.get_stats()
                logger.info(f"性能统计 - 总帧: {stats['total_frames']}, "
                          f"显示: {stats['display_frames']}, 推理: {stats['inference_frames']}, "
                          f"丢帧率: {stats['drop_rate']:.1f}%")
            
            return True
            
        except Exception as e:
            logger.error(f"帧分发失败: {str(e)}")
            return False
    
    try:
        if state.tcp_client:
            logger.info("开始连接TCP客户端...")
            # 在线程池中运行同步的TCP客户端
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                logger.info("在线程池中运行TCP客户端")
                result = await asyncio.get_event_loop().run_in_executor(
                    executor, 
                    lambda: state.tcp_client.run(frame_callback) if state.tcp_client else None
                )
                logger.info(f"TCP客户端运行结果: {result}")
        else:
            logger.error("TCP客户端未初始化")
    except Exception as e:
        logger.error(f"视频流运行异常: {str(e)}", exc_info=True)
        await state.broadcast_message("error", f"视频流异常: {str(e)}")
    finally:
        state.streaming = False
        # 简化版本不需要停止分发器
        logger.info("视频流已停止")

# REST API路由
@app.get("/api/status", response_model=ApiResponse)
async def get_system_status():
    """获取系统状态"""
    status = SystemStatus(
        streaming=state.streaming,
        connected_clients=len(state.connected_clients),
        frame_count=state.frame_count,
        has_experiment_log=state.experiment_log_path is not None,
        temp_dir=str(state.temp_dir) if state.temp_dir else None
    )
    
    return ApiResponse(
        success=True,
        data=status.dict(),
        timestamp=time.time()
    )

@app.get("/api/experiment-log", response_model=ApiResponse)
async def get_experiment_log():
    """获取实验日志"""
    try:
        # 首先尝试从experiment_log.json读取
        if state.experiment_log_path and state.experiment_log_path.exists():
            with open(state.experiment_log_path, 'r', encoding='utf-8') as f:
                experiment_log = json.load(f)
            
            return ApiResponse(
                success=True,
                data=experiment_log,
                timestamp=time.time()
            )
        
        # 如果没有experiment_log.json，从sampled_video目录构造实验日志
        inference_results = state.get_latest_inference_results(limit=50)
        if not inference_results:
            return ApiResponse(
                success=False,
                error="实验日志文件不存在且没有找到推理结果",
                timestamp=time.time()
            )
        
        # 构造实验日志格式
        experiment_log = {
            "session_id": state.latest_session_dir.name if state.latest_session_dir else "unknown",
            "start_time": inference_results[-1]["timestamp"] if inference_results else None,
            "inference_log": inference_results,
            "total_inferences": len(inference_results),
            "status": "running"
        }
        
        return ApiResponse(
            success=True,
            data=experiment_log,
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"读取实验日志失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/inference-history", response_model=ApiResponse)
async def get_inference_history(limit: int = 50):
    """获取推理历史"""
    try:
        # 首先尝试从experiment_log.json读取
        if state.experiment_log_path and state.experiment_log_path.exists():
            with open(state.experiment_log_path, 'r', encoding='utf-8') as f:
                experiment_log = json.load(f)
            
            inference_log = experiment_log.get('inference_log', [])
            recent_inferences = inference_log[-limit:] if limit > 0 else inference_log
            
            return ApiResponse(
                success=True,
                data=recent_inferences,
                timestamp=time.time()
            )
        
        # 如果没有experiment_log.json，从sampled_video目录读取
        inference_results = state.get_latest_inference_results(limit=limit)
        
        return ApiResponse(
            success=True,
            data=inference_results,
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"获取推理历史失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/latest-inference", response_model=ApiResponse)
async def get_latest_inference():
    """获取最新推理结果"""
    try:
        # 首先尝试从experiment_log.json读取
        if state.experiment_log_path and state.experiment_log_path.exists():
            with open(state.experiment_log_path, 'r', encoding='utf-8') as f:
                experiment_log = json.load(f)
            
            inference_log = experiment_log.get('inference_log', [])
            if not inference_log:
                return ApiResponse(
                    success=False,
                    error="没有推理结果",
                    timestamp=time.time()
                )
            
            latest_inference = inference_log[-1]
            
            return ApiResponse(
                success=True,
                data=latest_inference,
                timestamp=time.time()
            )
        
        # 如果没有experiment_log.json，从sampled_video目录读取最新结果
        inference_results = state.get_latest_inference_results(limit=1)
        if not inference_results:
            return ApiResponse(
                success=False,
                error="没有找到推理结果",
                timestamp=time.time()
            )
        
        latest_inference = inference_results[0]
        
        return ApiResponse(
            success=True,
            data=latest_inference,
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"获取最新推理结果失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/latest-inference-with-ai", response_model=ApiResponse)
async def get_latest_inference_with_ai():
    """获取最新的已完成AI分析且有MCP结果的推理结果"""
    try:
        # 获取媒体历史记录（包含图像和视频）
        media_response = await get_media_history(limit=50)
        if not media_response.success or not media_response.data:
            return ApiResponse(
                success=False,
                error="没有找到媒体历史记录",
                timestamp=time.time()
            )
        
        media_items = media_response.data.get('media_items', [])
        
        # 筛选出同时有AI分析结果和MCP结果的推理
        complete_results = [
            item for item in media_items 
            if item.get('has_inference_result', False) and item.get('has_mcp_result', False)
        ]
        
        if not complete_results:
            return ApiResponse(
                success=False,
                error="没有找到同时具有AI分析和MCP结果的推理结果",
                timestamp=time.time()
            )
        
        # 返回最新的完整推理结果
        latest_complete_result = complete_results[0]
        
        return ApiResponse(
            success=True,
            data=latest_complete_result,
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"获取最新完整推理结果失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/videos/{filename}")
@app.head("/api/videos/{filename}")
async def serve_video(filename: str, request: Request):
    """提供视频文件"""
    try:
        logger.info(f"请求视频文件: {filename}")
        
        # 刷新最新的session目录
        state._find_latest_session_dir()
        
        if not state.latest_session_dir:
            raise HTTPException(status_code=404, detail="临时目录不存在")
        
        video_file = None
        
        # 在当前session目录下查找视频文件
        for item in state.latest_session_dir.iterdir():
            if item.is_dir() and item.name.endswith('_details'):
                # 查找匹配的视频文件
                for video_path in item.glob('*.mp4'):
                    if video_path.name == filename:
                        video_file = video_path
                        logger.info(f"找到视频文件: {video_file}")
                        break
                if video_file:
                    break
        
        if not video_file:
            logger.error(f"视频文件不存在: {filename}")
            logger.info(f"当前session目录: {state.latest_session_dir}")
            
            # 列出所有可用的视频文件用于调试
            available_videos = []
            if state.latest_session_dir:
                for item in state.latest_session_dir.iterdir():
                    if item.is_dir() and item.name.endswith('_details'):
                        for video in item.glob('*.mp4'):
                            available_videos.append(video.name)
            logger.info(f"可用的视频文件: {available_videos}")
            raise HTTPException(status_code=404, detail=f"视频文件不存在: {filename}")
        
        # 检查文件是否真的存在且可读
        if not video_file.exists():
            raise HTTPException(status_code=404, detail=f"视频文件不存在: {video_file}")
        
        if not video_file.is_file():
            raise HTTPException(status_code=404, detail=f"路径不是文件: {video_file}")
        
        file_size = video_file.stat().st_size
        logger.info(f"返回视频文件: {video_file}, 大小: {file_size} bytes")
        
        # 处理Range请求
        range_header = request.headers.get('range')
        if range_header:
            logger.info(f"处理Range请求: {range_header}")
            # 解析Range头
            range_match = range_header.replace('bytes=', '').split('-')
            start = int(range_match[0]) if range_match[0] else 0
            end = int(range_match[1]) if range_match[1] else file_size - 1
            
            # 确保范围有效
            start = max(0, start)
            end = min(file_size - 1, end)
            content_length = end - start + 1
            
            def iter_file():
                with open(video_file, 'rb') as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(8192, remaining)
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            return StreamingResponse(
                iter_file(),
                status_code=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(content_length),
                    "Content-Type": "video/mp4",
                    "Cache-Control": "no-cache"
                }
            )
        
        # 普通请求，返回整个文件
        return FileResponse(
            str(video_file), 
            media_type='video/mp4',
            headers={
                "Cache-Control": "no-cache",
                "Accept-Ranges": "bytes",
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取视频文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取视频文件失败: {str(e)}")

@app.get("/api/videos", response_model=ApiResponse)
async def list_videos():
    """列出所有视频文件"""
    try:
        if not state.temp_dir:
            return ApiResponse(
                success=True,
                data=[],
                timestamp=time.time()
            )
        
        videos = []
        for item in state.temp_dir.iterdir():
            if item.is_dir() and item.name.endswith('_details'):
                for video_file in item.glob('*.mp4'):
                    videos.append(video_file.name)
        
        return ApiResponse(
            success=True,
            data=videos,
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"列出视频文件失败: {str(e)}",
            timestamp=time.time()
        )

@app.post("/api/stream/start", response_model=ApiResponse)
async def start_stream_api():
    """通过API启动视频流"""
    # 创建一个虚拟WebSocket来复用现有逻辑
    class DummyWebSocket:
        async def send_json(self, data):
            pass
    
    dummy_ws = DummyWebSocket()
    # 直接调用启动逻辑而不是通过WebSocket函数
    try:
        if state.streaming:
            return ApiResponse(
                success=False,
                error="视频流已在运行中",
                timestamp=time.time()
            )
        
        # 创建TCP客户端 - 使用优化参数
        tcp_config = state.config['stream']['tcp']
        logger.info(f"创建TCP客户端: {tcp_config['host']}:{tcp_config['port']}")
        
        state.tcp_client = TCPVideoClient(
            host=tcp_config['host'],
            port=tcp_config['port'],
            frame_rate=60,  # 提高到60fps
            timeout=tcp_config['connection_timeout'],
            buffer_size=1000  # 增加缓冲区
        )
        
        # 启动视频流任务
        logger.info("启动视频流任务...")
        asyncio.create_task(run_video_stream())
        
        return ApiResponse(
            success=True,
            data={"message": "视频流启动请求已发送"},
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.error(f"启动视频流失败: {str(e)}")
        return ApiResponse(
            success=False,
            error=f"启动视频流失败: {str(e)}",
            timestamp=time.time()
        )

@app.post("/api/stream/stop", response_model=ApiResponse)
async def stop_stream_api():
    """通过API停止视频流"""
    try:
        state.streaming = False
        if state.tcp_client:
            state.tcp_client.disconnect()
            state.tcp_client = None
        
        return ApiResponse(
            success=True,
            data={"message": "视频流停止请求已发送"},
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.error(f"停止视频流失败: {str(e)}")
        return ApiResponse(
            success=False,
            error=f"停止视频流失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/stream/status", response_model=ApiResponse)
async def get_stream_status():
    """获取视频流状态"""
    return ApiResponse(
        success=True,
        data={
            "streaming": state.streaming,
            "frame_count": state.frame_count,
            "has_client": state.tcp_client is not None
        },
        timestamp=time.time()
    )

@app.delete("/api/history", response_model=ApiResponse)
async def clear_history():
    """清空历史数据"""
    try:
        # 这里只是模拟清空，实际可能需要删除文件或重置状态
        state.frame_count = 0
        
        return ApiResponse(
            success=True,
            data={"message": "历史数据已清空"},
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"清空历史数据失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/refresh-session", response_model=ApiResponse)
async def refresh_session():
    """刷新实验会话目录"""
    try:
        old_session = state.latest_session_dir.name if state.latest_session_dir else "none"
        state._find_latest_session_dir()
        new_session = state.latest_session_dir.name if state.latest_session_dir else "none"
        
        return ApiResponse(
            success=True,
            data={
                "old_session": old_session,
                "new_session": new_session,
                "changed": old_session != new_session
            },
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"刷新会话目录失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/inference-count", response_model=ApiResponse)
async def get_inference_count():
    """获取推理结果数量"""
    try:
        # 刷新最新的实验目录
        state._find_latest_session_dir()
        
        inference_results = state.get_latest_inference_results(limit=1000)  # 获取所有结果来计数
        
        return ApiResponse(
            success=True,
            data={
                "count": len(inference_results),
                "session_dir": safe_relative_path(state.latest_session_dir) if state.latest_session_dir else None,
                "has_experiment_log": state.experiment_log_path is not None and state.experiment_log_path.exists()
            },
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"获取推理数量失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/debug/videos", response_model=ApiResponse)
async def debug_videos():
    """调试视频文件信息"""
    try:
        state._find_latest_session_dir()
        
        debug_info = {
            "latest_session_dir": str(state.latest_session_dir) if state.latest_session_dir else None,
            "session_exists": state.latest_session_dir.exists() if state.latest_session_dir else False,
            "current_working_dir": str(Path.cwd()),
            "videos": []
        }
        
        if state.latest_session_dir and state.latest_session_dir.exists():
            for item in state.latest_session_dir.iterdir():
                if item.is_dir() and item.name.endswith('_details'):
                    for video_path in item.glob('*.mp4'):
                        try:
                            # 安全地计算相对路径
                            try:
                                relative_path = str(video_path.relative_to(Path.cwd()))
                            except ValueError:
                                # 如果无法计算相对路径，使用绝对路径
                                relative_path = str(video_path.resolve())
                            
                            video_info = {
                                "filename": video_path.name,
                                "full_path": str(video_path.resolve()),
                                "relative_path": relative_path,
                                "exists": video_path.exists(),
                                "is_file": video_path.is_file(),
                                "size": video_path.stat().st_size if video_path.exists() else 0,
                                "parent_dir": video_path.parent.name
                            }
                            debug_info["videos"].append(video_info)
                        except Exception as e:
                            logger.warning(f"处理视频文件信息失败 {video_path}: {e}")
                            # 添加基本信息即使出错
                            video_info = {
                                "filename": video_path.name,
                                "full_path": str(video_path),
                                "relative_path": str(video_path),
                                "exists": video_path.exists(),
                                "is_file": video_path.is_file(),
                                "size": 0,
                                "parent_dir": video_path.parent.name,
                                "error": str(e)
                            }
                            debug_info["videos"].append(video_info)
        
        return ApiResponse(
            success=True,
            data=debug_info,
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.error(f"调试视频信息失败: {str(e)}", exc_info=True)
        return ApiResponse(
            success=False,
            error=f"调试视频信息失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/media-history", response_model=ApiResponse)
async def get_media_history(limit: int = 50):
    """获取媒体历史记录（图像和视频）"""
    try:
        # 刷新最新的session目录
        state._find_latest_session_dir()
        
        if not state.latest_session_dir or not state.latest_session_dir.exists():
            return ApiResponse(
                success=False,
                error="没有找到session目录",
                timestamp=time.time()
            )
        
        media_items = []
        
        # 遍历session目录下的所有details文件夹
        for item in state.latest_session_dir.iterdir():
            if item.is_dir() and item.name.endswith('_details'):
                try:
                    # 检查是否是图像模式（frame_xxx_details）
                    if item.name.startswith('frame_'):
                        # 图像模式
                        image_details_file = item / 'image_details.json'
                        inference_result_file = item / 'inference_result.json'
                        mcp_result_file = item / 'mcp_result.json'
                        
                        if image_details_file.exists():
                            with open(image_details_file, 'r', encoding='utf-8') as f:
                                image_details = json.load(f)
                            
                            # 查找图像文件
                            image_files = list(item.glob('*.jpg')) + list(item.glob('*.png'))
                            if image_files:
                                image_file = image_files[0]
                                
                                # 检查是否同时有inference_result.json和mcp_result.json
                                has_inference_result = inference_result_file.exists()
                                has_mcp_result = mcp_result_file.exists()
                                
                                # 🆕 检查是否有用户问题结果
                                user_question_file = item / 'user_question.json'
                                has_user_question_result = user_question_file.exists()
                                
                                media_item = {
                                    'type': 'image',
                                    'media_path': safe_relative_path(image_file),
                                    'filename': image_file.name,
                                    'frame_number': image_details.get('frame_number'),
                                    'timestamp': image_details.get('timestamp'),
                                    'timestamp_iso': image_details.get('timestamp_iso'),
                                    'relative_timestamp': image_details.get('relative_timestamp'),
                                    'creation_time': image_details.get('creation_time'),
                                    'has_inference_result': has_inference_result,
                                    'has_mcp_result': has_mcp_result,
                                    'has_user_question_result': has_user_question_result,  # 🆕 新增字段
                                    'details_dir': safe_relative_path(item),
                                    'image_dimensions': image_details.get('image_dimensions', {})
                                }
                                
                                # 🆕 优先处理用户问题结果
                                if has_user_question_result:
                                    with open(user_question_file, 'r', encoding='utf-8') as f:
                                        user_question_result = json.load(f)
                                    
                                    media_item.update({
                                        'user_question': user_question_result.get('user_question', ''),  # 用户问题
                                        'response': user_question_result.get('response', ''),  # 用户问题回答
                                        'user_question_timestamp': user_question_result.get('timestamp_iso', ''),  # 用户问题时间戳
                                        'analysis_type': 'user_question'  # 标记为用户问题类型
                                    })
                                
                                # 如果有推理结果，添加推理信息
                                if has_inference_result:
                                    with open(inference_result_file, 'r', encoding='utf-8') as f:
                                        inference_result = json.load(f)
                                    
                                    parsed_result = inference_result.get('parsed_result', {})
                                    media_item.update({
                                        'people_count': parsed_result.get('people_count', 0),
                                        'vehicle_count': parsed_result.get('vehicle_count', 0),
                                        'people': parsed_result.get('people', []),
                                        'vehicles': parsed_result.get('vehicles', []),
                                        'summary': parsed_result.get('summary', ''),
                                        'inference_duration': inference_result.get('inference_duration'),
                                        'inference_start_timestamp': inference_result.get('inference_start_timestamp'),
                                        'inference_end_timestamp': inference_result.get('inference_end_timestamp'),
                                        'raw_result': inference_result.get('raw_result')  # 原始结果
                                    })
                                    
                                    # 🔄 如果没有用户问题结果，使用推理结果中的response字段
                                    if not has_user_question_result:
                                        media_item.update({
                                            'user_question': inference_result.get('user_question'),  # 用户问题
                                            'response': parsed_result.get('response') or parsed_result.get('answer'),  # AI回答
                                            'analysis_type': 'vlm_inference'  # 标记为VLM推理类型
                                        })
                                
                                # 如果有MCP结果，添加思考与行动信息
                                if has_mcp_result:
                                    with open(mcp_result_file, 'r', encoding='utf-8') as f:
                                        mcp_result = json.load(f)
                                    
                                    mcp_data = mcp_result.get('mcp_response_data', {}).get('data', {})
                                    control_result = mcp_data.get('control_result', {})
                                    
                                    media_item.update({
                                        'mcp_reason': control_result.get('reason', ''),  # 思考原因
                                        'mcp_result': control_result.get('result', ''),  # 执行结果
                                        'mcp_tool_name': control_result.get('tool_name', ''),  # 工具名称
                                        'mcp_arguments': control_result.get('arguments', {}),  # 工具参数
                                        'mcp_success': control_result.get('success', False),  # 执行是否成功
                                        'mcp_duration': mcp_result.get('mcp_duration', 0),  # MCP执行时长
                                        'mcp_start_timestamp': mcp_result.get('mcp_start_timestamp', ''),  # MCP开始时间
                                        'mcp_end_timestamp': mcp_result.get('mcp_end_timestamp', '')  # MCP结束时间
                                    })
                                
                                media_items.append(media_item)
                    
                    else:
                        # 视频模式（sampled_video_xxx_details）
                        video_details_file = item / 'video_details.json'
                        inference_result_file = item / 'inference_result.json'
                        mcp_result_file = item / 'mcp_result.json'
                        
                        if video_details_file.exists():
                            with open(video_details_file, 'r', encoding='utf-8') as f:
                                video_details = json.load(f)
                            
                            # 查找视频文件
                            video_files = list(item.glob('*.mp4'))
                            if video_files:
                                video_file = video_files[0]
                                
                                # 检查是否同时有inference_result.json和mcp_result.json
                                has_inference_result = inference_result_file.exists()
                                has_mcp_result = mcp_result_file.exists()
                                
                                # 🆕 检查是否有用户问题结果
                                user_question_file = item / 'user_question.json'
                                has_user_question_result = user_question_file.exists()
                                
                                media_item = {
                                    'type': 'video',
                                    'media_path': safe_relative_path(video_file),
                                    'filename': video_file.name,
                                    'total_frames': video_details.get('total_frames'),
                                    'frames_per_second': video_details.get('frames_per_second'),
                                    'target_duration': video_details.get('target_duration'),
                                    'creation_time': video_details.get('creation_time'),
                                    'creation_timestamp': video_details.get('creation_timestamp'),
                                    'sampled_frames': video_details.get('sampled_frames', []),
                                    'has_inference_result': has_inference_result,
                                    'has_mcp_result': has_mcp_result,
                                    'has_user_question_result': has_user_question_result,  # 🆕 新增字段
                                    'details_dir': safe_relative_path(item)
                                }
                                
                                # 计算视频的时间范围
                                sampled_frames = video_details.get('sampled_frames', [])
                                if sampled_frames:
                                    media_item.update({
                                        'start_timestamp': sampled_frames[0].get('timestamp'),
                                        'end_timestamp': sampled_frames[-1].get('timestamp'),
                                        'start_relative_timestamp': sampled_frames[0].get('relative_timestamp'),
                                        'end_relative_timestamp': sampled_frames[-1].get('relative_timestamp'),
                                        'original_frame_range': [
                                            sampled_frames[0].get('original_frame_number'),
                                            sampled_frames[-1].get('original_frame_number')
                                        ]
                                    })
                                
                                # 🆕 优先处理用户问题结果
                                if has_user_question_result:
                                    with open(user_question_file, 'r', encoding='utf-8') as f:
                                        user_question_result = json.load(f)
                                    
                                    media_item.update({
                                        'user_question': user_question_result.get('user_question', ''),  # 用户问题
                                        'response': user_question_result.get('response', ''),  # 用户问题回答
                                        'user_question_timestamp': user_question_result.get('timestamp_iso', ''),  # 用户问题时间戳
                                        'analysis_type': 'user_question'  # 标记为用户问题类型
                                    })
                                
                                # 如果有推理结果，添加推理信息
                                if has_inference_result:
                                    with open(inference_result_file, 'r', encoding='utf-8') as f:
                                        inference_result = json.load(f)
                                    
                                    parsed_result = inference_result.get('parsed_result', {})
                                    media_item.update({
                                        'people_count': parsed_result.get('people_count', 0),
                                        'vehicle_count': parsed_result.get('vehicle_count', 0),
                                        'people': parsed_result.get('people', []),
                                        'vehicles': parsed_result.get('vehicles', []),
                                        'summary': parsed_result.get('summary', ''),
                                        'inference_duration': inference_result.get('inference_duration'),
                                        'inference_start_timestamp': inference_result.get('inference_start_timestamp'),
                                        'inference_end_timestamp': inference_result.get('inference_end_timestamp'),
                                        'raw_result': inference_result.get('raw_result')  # 原始结果
                                    })
                                    
                                    # 🔄 如果没有用户问题结果，使用推理结果中的response字段
                                    if not has_user_question_result:
                                        media_item.update({
                                            'user_question': inference_result.get('user_question'),  # 用户问题
                                            'response': parsed_result.get('response') or parsed_result.get('answer'),  # AI回答
                                            'analysis_type': 'vlm_inference'  # 标记为VLM推理类型
                                        })
                                
                                # 如果有MCP结果，添加思考与行动信息
                                if has_mcp_result:
                                    with open(mcp_result_file, 'r', encoding='utf-8') as f:
                                        mcp_result = json.load(f)
                                    
                                    mcp_data = mcp_result.get('mcp_response_data', {}).get('data', {})
                                    control_result = mcp_data.get('control_result', {})
                                    
                                    media_item.update({
                                        'mcp_reason': control_result.get('reason', ''),  # 思考原因
                                        'mcp_result': control_result.get('result', ''),  # 执行结果
                                        'mcp_tool_name': control_result.get('tool_name', ''),  # 工具名称
                                        'mcp_arguments': control_result.get('arguments', {}),  # 工具参数
                                        'mcp_success': control_result.get('success', False),  # 执行是否成功
                                        'mcp_duration': mcp_result.get('mcp_duration', 0),  # MCP执行时长
                                        'mcp_start_timestamp': mcp_result.get('mcp_start_timestamp', ''),  # MCP开始时间
                                        'mcp_end_timestamp': mcp_result.get('mcp_end_timestamp', '')  # MCP结束时间
                                    })
                                
                                media_items.append(media_item)
                
                except Exception as e:
                    logger.warning(f"处理媒体项目失败 {item}: {e}")
                    continue
        
        # 按时间戳排序（最新的在前）
        media_items.sort(key=lambda x: x.get('timestamp', 0) or x.get('creation_timestamp', ''), reverse=True)
        
        # 限制返回数量
        if limit > 0:
            media_items = media_items[:limit]
        
        return ApiResponse(
            success=True,
            data={
                'media_items': media_items,
                'total_count': len(media_items),
                'session_dir': safe_relative_path(state.latest_session_dir) if state.latest_session_dir else None
            },
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.error(f"获取媒体历史记录失败: {e}")
        return ApiResponse(
            success=False,
            error=f"获取媒体历史记录失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/api/media/{filename}")
@app.head("/api/media/{filename}")
async def serve_media(filename: str, request: Request):
    """提供媒体文件（图像或视频）"""
    try:
        logger.info(f"请求媒体文件: {filename}")
        
        # 刷新最新的session目录
        state._find_latest_session_dir()
        
        if not state.latest_session_dir:
            raise HTTPException(status_code=404, detail="临时目录不存在")
        
        media_file = None
        
        # 在当前session目录下查找媒体文件
        for item in state.latest_session_dir.iterdir():
            if item.is_dir() and item.name.endswith('_details'):
                # 查找匹配的媒体文件（视频或图像）
                for media_path in item.glob('*'):
                    if media_path.is_file() and media_path.name == filename:
                        # 检查是否是支持的媒体格式
                        if media_path.suffix.lower() in ['.mp4', '.jpg', '.jpeg', '.png']:
                            media_file = media_path
                            logger.info(f"找到媒体文件: {media_file}")
                            break
                if media_file:
                    break
        
        if not media_file:
            logger.error(f"媒体文件不存在: {filename}")
            logger.info(f"当前session目录: {state.latest_session_dir}")
            
            # 列出所有可用的媒体文件用于调试
            available_media = []
            if state.latest_session_dir:
                for item in state.latest_session_dir.iterdir():
                    if item.is_dir() and item.name.endswith('_details'):
                        for media in item.glob('*'):
                            if media.is_file() and media.suffix.lower() in ['.mp4', '.jpg', '.jpeg', '.png']:
                                available_media.append(media.name)
            logger.info(f"可用的媒体文件: {available_media}")
            raise HTTPException(status_code=404, detail=f"媒体文件不存在: {filename}")
        
        # 检查文件是否真的存在且可读
        if not media_file.exists():
            raise HTTPException(status_code=404, detail=f"媒体文件不存在: {media_file}")
        
        if not media_file.is_file():
            raise HTTPException(status_code=404, detail=f"路径不是文件: {media_file}")
        
        file_size = media_file.stat().st_size
        logger.info(f"返回媒体文件: {media_file}, 大小: {file_size} bytes")
        
        # 根据文件类型设置Content-Type
        content_type = "application/octet-stream"
        if media_file.suffix.lower() == '.mp4':
            content_type = "video/mp4"
        elif media_file.suffix.lower() in ['.jpg', '.jpeg']:
            content_type = "image/jpeg"
        elif media_file.suffix.lower() == '.png':
            content_type = "image/png"
        
        # 对于图像文件，直接返回
        if media_file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
            return FileResponse(
                path=str(media_file),
                media_type=content_type,
                filename=media_file.name
            )
        
        # 对于视频文件，处理Range请求
        range_header = request.headers.get('range')
        if range_header:
            logger.info(f"处理Range请求: {range_header}")
            # 解析Range头
            range_match = range_header.replace('bytes=', '').split('-')
            start = int(range_match[0]) if range_match[0] else 0
            end = int(range_match[1]) if range_match[1] else file_size - 1
            
            # 确保范围有效
            start = max(0, start)
            end = min(file_size - 1, end)
            content_length = end - start + 1
            
            def iter_file():
                with open(media_file, 'rb') as f:
                    f.seek(start)
                    remaining = content_length
                    while remaining > 0:
                        chunk_size = min(8192, remaining)
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            
            return StreamingResponse(
                iter_file(),
                status_code=206,
                headers={
                    'Content-Range': f'bytes {start}-{end}/{file_size}',
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(content_length),
                    'Content-Type': content_type,
                },
                media_type=content_type
            )
        else:
            # 完整文件响应
            return FileResponse(
                path=str(media_file),
                media_type=content_type,
                filename=media_file.name
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提供媒体文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": time.time()}

# 内部视频流API - 供推理服务使用
@app.post("/internal/video/subscribe", response_model=ApiResponse)
async def subscribe_to_video_stream(request: Request):
    """内部API：订阅视频流"""
    try:
        # 这里我们返回一个订阅ID，实际的回调需要通过其他方式设置
        # 在实际实现中，推理服务会通过其他方式注册回调
        subscriber_id = f"internal_{int(time.time() * 1000)}"
        
        return ApiResponse(
            success=True,
            data={
                "subscriber_id": subscriber_id,
                "message": "订阅成功，请通过内部接口设置回调"
            },
            timestamp=time.time()
        )
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"订阅视频流失败: {str(e)}",
            timestamp=time.time()
        )

@app.get("/internal/video/latest-frame")
async def get_latest_frame():
    """内部API：获取最新帧"""
    try:
        latest_frame = state.video_distributor.get_latest_frame()
        if latest_frame is None:
            return JSONResponse(
                status_code=404,
                content={"error": "没有可用的视频帧"}
            )
        
        frame, timestamp = latest_frame
        
        # 将帧编码为JPEG并转换为base64
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
        
        return {
            "frame_data": frame_base64,
            "timestamp": timestamp,
            "frame_number": state.frame_count
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"获取最新帧失败: {str(e)}"}
        )

@app.get("/internal/video/status")
async def get_internal_video_status():
    """内部API：获取视频流状态"""
    return {
        "streaming": state.streaming,
        "subscriber_count": state.video_distributor.get_subscriber_count(),
        "frame_count": state.frame_count,
        "has_latest_frame": state.video_distributor.get_latest_frame() is not None
    }

# 提供给推理服务的直接接口
def register_inference_callback(callback: Callable[[np.ndarray, float], bool]) -> str:
    """
    为推理服务注册视频帧回调
    这个函数会被推理服务直接调用
    
    Args:
        callback: 帧处理回调函数
        
    Returns:
        订阅ID
    """
    return state.video_distributor.subscribe(callback)

def unregister_inference_callback(subscriber_id: str):
    """取消推理服务的视频帧订阅"""
    state.video_distributor.unsubscribe(subscriber_id)

# 添加新的HTTP流媒体端点
@app.get("/api/video-stream")
async def video_stream():
    """提供MJPEG视频流 - 极致性能版本"""
    
    def generate_mjpeg_stream():
        """生成MJPEG流 - 极致性能优化版本"""
        boundary = "frame"
        frame_count = 0
        last_frame_time = time.time()
        last_fps_log = time.time()
        
        # 预分配空白帧，避免重复创建
        blank_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        _, blank_jpeg = cv2.imencode('.jpg', blank_frame, [cv2.IMWRITE_JPEG_QUALITY, 30])
        blank_jpeg_data = blank_jpeg.tobytes()
        
        # 性能优化变量
        consecutive_same_frames = 0
        last_frame_data = None
        no_frame_count = 0
        
        # 预计算固定的边界字符串
        boundary_bytes = boundary.encode()
        content_type_header = b'Content-Type: image/jpeg\r\n'
        
        logger.info("MJPEG流生成器启动")
        
        while True:
            current_time = time.time()
            
            # 获取最新的JPEG帧（原子操作，无锁）
            jpeg_data = state.latest_jpeg_frame
            if jpeg_data is None:
                no_frame_count += 1
                if no_frame_count % 100 == 1:  # 每100次记录一次
                    logger.warning(f"没有可用的视频帧，使用空白帧 (第{no_frame_count}次)")
                jpeg_data = blank_jpeg_data
            else:
                if no_frame_count > 0:
                    logger.info(f"恢复视频帧，之前缺失{no_frame_count}次")
                    no_frame_count = 0
            
            # 检测重复帧，避免发送相同数据
            if jpeg_data == last_frame_data:
                consecutive_same_frames += 1
                # 如果连续相同帧超过5帧，稍微延迟以避免浪费带宽
                if consecutive_same_frames > 5:
                    time.sleep(0.008)  # 8ms延迟
                    continue
            else:
                consecutive_same_frames = 0
                last_frame_data = jpeg_data
            
            # 预计算帧头，减少字符串操作
            content_length = str(len(jpeg_data)).encode()
            frame_header = (
                b'--' + boundary_bytes + b'\r\n' +
                content_type_header +
                b'Content-Length: ' + content_length + b'\r\n\r\n'
            )
            
            # 一次性发送完整帧（减少系统调用）
            yield frame_header + jpeg_data + b'\r\n'
            
            frame_count += 1
            
            # 动态帧率控制 - 根据是否有新帧调整
            if state.latest_jpeg_frame is not None:
                # 有新帧时，高速发送
                time.sleep(0.008)  # ~125fps
            else:
                # 没有新帧时，降低发送频率
                time.sleep(0.033)  # ~30fps
            
            # 性能监控（每10秒记录一次）
            if current_time - last_fps_log > 10.0:
                elapsed = current_time - last_frame_time
                if elapsed > 0:
                    fps = (frame_count - (frame_count - 200 if frame_count > 200 else 0)) / elapsed
                    logger.info(f"MJPEG流性能: {fps:.1f}fps, 帧大小: {len(jpeg_data)/1024:.1f}KB, 重复帧: {consecutive_same_frames}, 缺失帧: {no_frame_count}")
                last_fps_log = current_time
                if frame_count > 200:
                    last_frame_time = current_time
                    frame_count = 200  # 重置计数器
    
    return StreamingResponse(generate_mjpeg_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

# 哨兵模式相关API端点
@app.get("/api/sentry-mode", response_model=ApiResponse)
async def get_sentry_mode():
    """获取哨兵模式状态"""
    try:
        enabled = state.get_sentry_mode()
        return ApiResponse(
            success=True,
            data={
                "enabled": enabled,
                "status": "启用" if enabled else "禁用"
            },
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"获取哨兵模式状态失败: {str(e)}")
        return ApiResponse(
            success=False,
            error=f"获取哨兵模式状态失败: {str(e)}",
            timestamp=time.time()
        )

@app.post("/api/sentry-mode", response_model=ApiResponse)
async def set_sentry_mode(request: Request):
    """设置哨兵模式状态"""
    try:
        data = await request.json()
        enabled = data.get("enabled", True)
        
        if not isinstance(enabled, bool):
            return ApiResponse(
                success=False,
                error="enabled参数必须是布尔值",
                timestamp=time.time()
            )
        
        state.set_sentry_mode(enabled)
        mode_text = "启用" if enabled else "禁用"
        
        return ApiResponse(
            success=True,
            data={
                "enabled": enabled,
                "status": mode_text,
                "message": f"哨兵模式已{mode_text}"
            },
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"设置哨兵模式失败: {str(e)}")
        return ApiResponse(
            success=False,
            error=f"设置哨兵模式失败: {str(e)}",
            timestamp=time.time()
        )

@app.post("/api/sentry-mode/toggle", response_model=ApiResponse)
async def toggle_sentry_mode():
    """切换哨兵模式状态"""
    try:
        new_state = state.toggle_sentry_mode()
        mode_text = "启用" if new_state else "禁用"
        
        return ApiResponse(
            success=True,
            data={
                "enabled": new_state,
                "status": mode_text,
                "message": f"哨兵模式已切换为{mode_text}"
            },
            timestamp=time.time()
        )
    except Exception as e:
        logger.error(f"切换哨兵模式失败: {str(e)}")
        return ApiResponse(
            success=False,
            error=f"切换哨兵模式失败: {str(e)}",
            timestamp=time.time()
        )

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 启动FastAPI后端服务器...")
    logger.info(f"📊 实验日志路径: {state.experiment_log_path}")
    logger.info(f"📁 临时目录: {state.temp_dir}")
    logger.info("🌐 服务地址: http://localhost:8080")
    logger.info("🔌 WebSocket: ws://localhost:8080/ws")
    logger.info("📚 API文档: http://localhost:8080/docs")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    ) 