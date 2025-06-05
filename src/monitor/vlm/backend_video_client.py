#!/usr/bin/env python3
"""
后端视频客户端
从后端服务获取视频流，替代直接TCP连接
"""

import sys
import time
import logging
import requests
import base64
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import threading

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

logger = logging.getLogger(__name__)

class BackendVideoClient:
    def __init__(self, backend_url: str = "http://localhost:8080", 
                 frame_rate: int = 5, timeout: int = 10):
        """
        初始化后端视频客户端
        
        Args:
            backend_url: 后端服务URL
            frame_rate: 目标帧率
            timeout: 请求超时时间
        """
        self.backend_url = backend_url.rstrip('/')
        self.frame_rate = frame_rate
        self.timeout = timeout
        self.frame_interval = 1.0 / frame_rate if frame_rate > 0 else 0
        
        # 统计信息
        self.frames_received = 0
        self.start_time = None
        self.decode_errors = 0
        
        # 运行控制
        self.running = False
        
        logger.info(f"后端视频客户端初始化: {backend_url}, 目标帧率: {frame_rate}fps")

    def connect(self) -> bool:
        """测试与后端服务的连接"""
        try:
            response = requests.get(
                f"{self.backend_url}/internal/video/status",
                timeout=self.timeout
            )
            if response.status_code == 200:
                status = response.json()
                logger.info(f"✅ 后端连接成功，视频流状态: {status}")
                return True
            else:
                logger.error(f"后端连接失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"连接后端服务失败: {str(e)}")
            return False

    def run(self, callback: Callable[[Any], bool]) -> bool:
        """
        运行客户端，接收视频帧
        
        Args:
            callback: 帧处理回调函数，返回False时停止接收
            
        Returns:
            是否成功运行
        """
        if not self.connect():
            return False
        
        self.running = True
        self.start_time = time.time()
        last_frame_time = 0
        
        logger.info("开始从后端获取视频帧...")
        
        try:
            while self.running:
                try:
                    # 控制帧率
                    current_time = time.time()
                    if self.frame_interval > 0:
                        time_since_last = current_time - last_frame_time
                        if time_since_last < self.frame_interval:
                            time.sleep(self.frame_interval - time_since_last)
                    
                    # 从后端获取最新帧
                    frame = self._get_latest_frame()
                    if frame is None:
                        # 如果没有帧，短暂等待后继续
                        time.sleep(0.1)
                        continue
                    
                    # 调用回调函数
                    try:
                        should_continue = callback(frame)
                        if not should_continue:
                            logger.info("回调函数返回False，停止接收")
                            break
                    except Exception as e:
                        logger.error(f"回调函数执行失败: {str(e)}")
                        break
                    
                    self.frames_received += 1
                    last_frame_time = time.time()
                    
                    # 每50帧报告一次状态
                    if self.frames_received % 50 == 0:
                        elapsed_time = time.time() - (self.start_time or time.time())
                        actual_fps = self.frames_received / elapsed_time if elapsed_time > 0 else 0
                        logger.info(f"已接收 {self.frames_received} 帧, 实际fps: {actual_fps:.2f}")
                        if self.decode_errors > 0:
                            logger.info(f"解码错误: {self.decode_errors}")
                
                except Exception as e:
                    logger.error(f"获取视频帧失败: {str(e)}")
                    time.sleep(1)  # 出错时等待1秒
            
            return True
            
        except Exception as e:
            logger.error(f"后端视频客户端运行失败: {str(e)}")
            return False
        finally:
            self.running = False

    def disconnect(self):
        """断开连接"""
        self.running = False
        logger.info("后端视频客户端已断开")

    def _get_latest_frame(self) -> Optional[np.ndarray]:
        """从后端获取最新帧"""
        try:
            response = requests.get(
                f"{self.backend_url}/internal/video/latest-frame",
                timeout=self.timeout
            )
            
            if response.status_code == 404:
                # 没有可用帧
                return None
            elif response.status_code != 200:
                logger.warning(f"获取帧失败，状态码: {response.status_code}")
                return None
            
            data = response.json()
            frame_base64 = data['frame_data']
            
            # 解码base64为图像
            try:
                frame_bytes = base64.b64decode(frame_base64)
                frame_array = np.frombuffer(frame_bytes, dtype='uint8')
                frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                
                if frame is None:
                    logger.error("图像解码失败")
                    self.decode_errors += 1
                    return None
                
                return frame
                
            except Exception as e:
                logger.error(f"帧解码失败: {str(e)}")
                self.decode_errors += 1
                return None
                
        except requests.exceptions.Timeout:
            logger.warning("获取帧超时")
            return None
        except Exception as e:
            logger.error(f"获取帧异常: {str(e)}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        elapsed_time = time.time() - (self.start_time or time.time()) if self.start_time else 0
        return {
            'connected': True,  # 基于HTTP请求，连接状态难以准确判断
            'frames_received': self.frames_received,
            'elapsed_time': elapsed_time,
            'average_fps': self.frames_received / elapsed_time if elapsed_time > 0 else 0,
            'target_fps': self.frame_rate,
            'decode_errors': self.decode_errors,
            'backend_url': self.backend_url
        } 