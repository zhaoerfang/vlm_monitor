#!/usr/bin/env python3
"""
TCP视频流客户端
连接到TCP视频服务器并接收视频帧
"""

import socket
import threading
import time
import pickle
import struct
import logging
import cv2
import numpy as np
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)

class TCPVideoClient:
    def __init__(self, host: str = 'localhost', port: int = 9999, 
                 frame_rate: int = 5, timeout: int = 10, buffer_size: int = 100):
        """
        初始化TCP视频客户端
        
        Args:
            host: 服务器地址
            port: 服务器端口
            frame_rate: 目标帧率（用于控制接收频率）
            timeout: 连接超时时间
            buffer_size: 缓冲区大小
        """
        self.host = host
        self.port = port
        self.frame_rate = frame_rate
        self.timeout = timeout
        self.buffer_size = buffer_size
        
        # 网络相关
        self.socket = None
        self.connected = False
        
        # 帧处理相关
        self.frame_interval = 1.0 / frame_rate if frame_rate > 0 else 0
        self.last_frame_time = 0
        
        # 统计信息
        self.frames_received = 0
        self.bytes_received = 0
        self.start_time = None
        self.decode_errors = 0
        
        # 线程控制
        self.running = False
        self.receive_thread = None
        
        logger.info(f"TCP视频客户端初始化: {host}:{port}, 目标帧率: {frame_rate}fps")

    def connect(self) -> bool:
        """连接到TCP服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            self.connected = True
            logger.info(f"✅ 已连接到TCP服务器: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"连接TCP服务器失败: {str(e)}")
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False

    def disconnect(self):
        """断开连接"""
        self.running = False
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)
        
        logger.info("TCP连接已断开")

    def run(self, callback: Callable[[Any], bool]) -> bool:
        """
        运行客户端，接收视频帧
        
        Args:
            callback: 帧处理回调函数，返回False时停止接收
            
        Returns:
            是否成功运行
        """
        if not self.connected:
            if not self.connect():
                return False
        
        self.running = True
        self.start_time = time.time()
        
        try:
            while self.running:
                # 接收帧数据
                frame = self._receive_frame()
                if frame is None:
                    logger.warning("接收帧失败，停止客户端")
                    break
                
                # 控制帧率
                current_time = time.time()
                if self.frame_interval > 0:
                    time_since_last = current_time - self.last_frame_time
                    if time_since_last < self.frame_interval:
                        time.sleep(self.frame_interval - time_since_last)
                
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
                self.last_frame_time = time.time()
                
                # 每50帧报告一次状态
                if self.frames_received % 50 == 0:
                    elapsed_time = time.time() - (self.start_time or time.time())
                    actual_fps = self.frames_received / elapsed_time if elapsed_time > 0 else 0
                    logger.debug(f"已接收 {self.frames_received} 帧, 实际fps: {actual_fps:.2f}")
                    if self.decode_errors > 0:
                        logger.debug(f"解码错误: {self.decode_errors}")
            
            return True
            
        except Exception as e:
            logger.error(f"TCP客户端运行失败: {str(e)}")
            return False
        finally:
            self.disconnect()

    def _receive_frame(self) -> Optional[np.ndarray]:
        """接收单个视频帧（新格式：8字节长度 + JPEG数据）"""
        try:
            # 接收数据长度（8字节，小端序）
            length_bytes = self._receive_exact(8)
            if not length_bytes:
                return None
            
            # 解析长度（小端序无符号长整数）
            length = struct.unpack('<Q', length_bytes)[0]
            
            # 验证数据长度合理性
            if length > 100 * 1024 * 1024:  # 100MB限制
                logger.error(f"数据长度异常: {length} bytes")
                return None
            
            if length == 0:
                logger.warning("数据长度为0")
                return None
            
            # 接收JPEG数据
            jpeg_data = self._receive_exact(int(length))
            if not jpeg_data:
                return None
            
            # 解码JPEG数据为图像
            try:
                data = np.frombuffer(jpeg_data, dtype='uint8')
                frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
                
                if frame is None:
                    logger.error("JPEG解码失败")
                    self.decode_errors += 1
                    return None
                
                self.bytes_received += len(jpeg_data) + 8
                return frame
                
            except Exception as e:
                logger.error(f"图像解码失败: {str(e)}")
                self.decode_errors += 1
                return None
                
        except Exception as e:
            if self.running:
                logger.error(f"接收帧失败: {str(e)}")
            return None

    def _receive_exact(self, size: int) -> Optional[bytes]:
        """精确接收指定字节数的数据"""
        data = b''
        while len(data) < size and self.running and self.socket:
            try:
                remaining = size - len(data)
                chunk = self.socket.recv(min(remaining, 8192))  # 每次最多接收8KB
                if not chunk:
                    logger.warning("TCP连接已关闭")
                    return None
                data += chunk
            except socket.timeout:
                logger.warning("接收数据超时")
                return None
            except Exception as e:
                if self.running:
                    logger.error(f"接收数据失败: {str(e)}")
                return None
        
        return data if len(data) == size else None

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        elapsed_time = time.time() - (self.start_time or time.time()) if self.start_time else 0
        return {
            'connected': self.connected,
            'frames_received': self.frames_received,
            'bytes_received': self.bytes_received,
            'elapsed_time': elapsed_time,
            'average_fps': self.frames_received / elapsed_time if elapsed_time > 0 else 0,
            'target_fps': self.frame_rate,
            'decode_errors': self.decode_errors
        } 