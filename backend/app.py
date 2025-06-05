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

# 内部视频流分发器
class InternalVideoDistributor:
    def __init__(self):
        self.subscribers = []  # 订阅者列表
        self.subscribers_lock = threading.Lock()
        self.latest_frame = None
        self.latest_frame_lock = threading.Lock()
        
    def subscribe(self, callback: Callable[[np.ndarray, float], bool]) -> str:
        """
        订阅视频流
        
        Args:
            callback: 帧处理回调函数 (frame, timestamp) -> bool
            
        Returns:
            订阅ID
        """
        subscriber_id = f"subscriber_{int(time.time() * 1000)}_{len(self.subscribers)}"
        subscriber = {
            'id': subscriber_id,
            'callback': callback,
            'active': True
        }
        
        with self.subscribers_lock:
            self.subscribers.append(subscriber)
        
        logger.info(f"新订阅者: {subscriber_id}, 总订阅者: {len(self.subscribers)}")
        return subscriber_id
    
    def unsubscribe(self, subscriber_id: str):
        """取消订阅"""
        with self.subscribers_lock:
            self.subscribers = [s for s in self.subscribers if s['id'] != subscriber_id]
        logger.info(f"取消订阅: {subscriber_id}, 剩余订阅者: {len(self.subscribers)}")
    
    def distribute_frame(self, frame: np.ndarray, timestamp: float):
        """分发帧给所有订阅者"""
        # 更新最新帧
        with self.latest_frame_lock:
            self.latest_frame = (frame.copy(), timestamp)
        
        # 分发给所有订阅者
        with self.subscribers_lock:
            inactive_subscribers = []
            for subscriber in self.subscribers:
                if subscriber['active']:
                    try:
                        should_continue = subscriber['callback'](frame, timestamp)
                        if not should_continue:
                            subscriber['active'] = False
                            inactive_subscribers.append(subscriber['id'])
                    except Exception as e:
                        logger.error(f"订阅者 {subscriber['id']} 回调失败: {e}")
                        subscriber['active'] = False
                        inactive_subscribers.append(subscriber['id'])
            
            # 移除不活跃的订阅者
            if inactive_subscribers:
                self.subscribers = [s for s in self.subscribers if s['id'] not in inactive_subscribers]
                logger.info(f"移除不活跃订阅者: {inactive_subscribers}")
    
    def get_latest_frame(self) -> Optional[tuple]:
        """获取最新帧"""
        with self.latest_frame_lock:
            return self.latest_frame
    
    def get_subscriber_count(self) -> int:
        """获取订阅者数量"""
        with self.subscribers_lock:
            return len([s for s in self.subscribers if s['active']])

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
        
        # 视频帧队列
        self.frame_queue = queue.Queue(maxsize=10)
        self.queue_processor_task: Optional[asyncio.Task] = None
        
        # 内部视频流分发器
        self.video_distributor = InternalVideoDistributor()
        
        # 查找最新的实验目录
        self._find_latest_session_dir()
    
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
                    "session_dir": str(sampled_dir),
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
                            "summary": inference_data.get("parsed_result", {}).get("summary", "")
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
        """处理帧队列"""
        logger.info("启动帧队列处理器")
        while True:
            try:
                # 检查是否有帧数据
                if not self.frame_queue.empty():
                    frame_data = self.frame_queue.get_nowait()
                    if len(self.connected_clients) > 0:
                        await self.broadcast_message("video_frame", frame_data)
                        logger.debug(f"广播帧 #{frame_data.get('frame_number', 0)}")
                
                # 短暂休眠避免CPU占用过高
                await asyncio.sleep(0.01)
                
            except Exception as e:
                logger.error(f"处理帧队列异常: {e}")
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
        # 创建TCP客户端
        tcp_config = state.config['stream']['tcp']
        logger.info(f"创建TCP客户端: {tcp_config['host']}:{tcp_config['port']}")
        
        state.tcp_client = TCPVideoClient(
            host=tcp_config['host'],
            port=tcp_config['port'],
            frame_rate=25,  # 实时流不抽帧
            timeout=tcp_config['connection_timeout']
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
    """运行视频流（异步版本）"""
    logger.info("开始运行视频流")
    state.streaming = True
    state.frame_count = 0
    
    def frame_callback(frame):
        if not state.streaming:
            logger.info("视频流已停止，退出帧回调")
            return False
        
        try:
            logger.debug(f"收到视频帧，尺寸: {frame.shape}")
            
            current_timestamp = time.time()
            state.frame_count += 1
            
            # 分发帧给内部订阅者（推理服务等）
            state.video_distributor.distribute_frame(frame, current_timestamp)
            
            # 将OpenCV帧转换为JPEG并编码为base64（用于WebSocket）
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            frame_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
            
            frame_data = {
                'data': frame_base64,
                'timestamp': current_timestamp,
                'frame_number': state.frame_count
            }
            state.last_frame = frame_data
            
            # 每帧都输出日志（前10帧）
            if state.frame_count <= 10:
                logger.info(f"处理第 {state.frame_count} 帧，当前连接客户端: {len(state.connected_clients)}, 内部订阅者: {state.video_distributor.get_subscriber_count()}")
            elif state.frame_count % 10 == 0:
                logger.info(f"已处理 {state.frame_count} 帧，当前连接客户端: {len(state.connected_clients)}, 内部订阅者: {state.video_distributor.get_subscriber_count()}")
            
            # 检查是否有连接的客户端
            if len(state.connected_clients) == 0:
                logger.debug("没有连接的WebSocket客户端，跳过广播")
            else:
                # 将帧数据添加到队列
                state.add_frame_to_queue(frame_data)
                logger.debug(f"已添加第 {state.frame_count} 帧到队列")
            
            return True
            
        except Exception as e:
            logger.error(f"处理视频帧失败: {str(e)}", exc_info=True)
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
    """获取最新的已完成AI分析的推理结果"""
    try:
        # 获取所有推理结果
        inference_results = state.get_latest_inference_results(limit=50)
        
        # 筛选出有AI分析结果的推理
        ai_completed_results = [r for r in inference_results if r.get('has_inference_result', False)]
        
        if not ai_completed_results:
            return ApiResponse(
                success=False,
                error="没有找到已完成AI分析的推理结果",
                timestamp=time.time()
            )
        
        # 返回最新的已完成AI分析的推理结果
        latest_ai_result = ai_completed_results[0]
        
        return ApiResponse(
            success=True,
            data=latest_ai_result,
            timestamp=time.time()
        )
        
    except Exception as e:
        return ApiResponse(
            success=False,
            error=f"获取最新AI推理结果失败: {str(e)}",
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
        
        # 创建TCP客户端
        tcp_config = state.config['stream']['tcp']
        logger.info(f"创建TCP客户端: {tcp_config['host']}:{tcp_config['port']}")
        
        state.tcp_client = TCPVideoClient(
            host=tcp_config['host'],
            port=tcp_config['port'],
            frame_rate=25,
            timeout=tcp_config['connection_timeout']
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
                "session_dir": state.latest_session_dir.name if state.latest_session_dir else None,
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