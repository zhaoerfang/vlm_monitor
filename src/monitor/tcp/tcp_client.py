#!/usr/bin/env python3
"""
TCP视频流客户端 - 超高性能版本
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
                 frame_rate: int = 60, timeout: int = 10, buffer_size: int = 1000):
        """
        初始化TCP视频客户端 - 超高性能版本
        
        Args:
            host: 服务器地址
            port: 服务器端口
            frame_rate: 目标帧率（提高到60fps）
            timeout: 连接超时时间
            buffer_size: 缓冲区大小（大幅增加）
        """
        self.host = host
        self.port = port
        self.frame_rate = frame_rate
        self.timeout = timeout
        self.buffer_size = buffer_size
        
        # 网络相关 - 优化设置
        self.socket = None
        self.connected = False
        
        # 帧处理相关 - 移除限制，追求最高性能
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
        
        # 性能优化参数 - 激进设置
        self.min_frame_interval = 0.005  # 最小帧间隔5ms（200fps理论上限）
        self.socket_recv_size = 65536    # 64KB接收缓冲区
        self.tcp_nodelay = True          # 禁用Nagle算法
        
        logger.info(f"TCP视频客户端初始化: {host}:{port}, 目标帧率: {frame_rate}fps (超高性能模式)")

    def connect(self) -> bool:
        """连接到TCP服务器 - 优化版本"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # 优化TCP设置
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 禁用Nagle算法
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)  # 1MB接收缓冲区
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)  # 1MB发送缓冲区
            
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            
            # 连接后设置为非阻塞模式以提高性能
            self.socket.settimeout(0.1)  # 100ms超时，更快响应
            
            self.connected = True
            logger.info(f"✅ 已连接到TCP服务器: {self.host}:{self.port} (优化模式)")
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
        
        logger.info("TCP连接已断开")
    
    def _reconnect(self) -> bool:
        """尝试重新连接"""
        logger.info("尝试重新连接TCP服务器...")
        self.disconnect()
        time.sleep(0.5)  # 减少等待时间
        return self.connect()

    def run(self, callback: Callable[[Any], bool]) -> bool:
        """
        运行客户端并接收视频帧 - 超高性能版本
        
        Args:
            callback: 帧处理回调函数，返回False时停止接收
            
        Returns:
            是否成功运行
        """
        if not self.connect():
            return False
        
        self.running = True
        self.start_time = time.time()
        logger.info("开始接收视频帧 (超高性能模式)")
        
        try:
            while self.running:
                current_time = time.time()
                
                # 接收帧
                frame = self._receive_frame()
                if frame is None:
                    if self.running:
                        logger.warning("接收帧失败，尝试重连...")
                        if not self._reconnect():
                            break
                    continue
                
                self.frames_received += 1
                
                # 移除复杂的跳帧逻辑，只保留最基本的帧率控制
                time_since_last = current_time - self.last_frame_time
                should_process = True
                
                # 只在帧率过高时进行最小限制
                if time_since_last < self.min_frame_interval:
                    # 只有在极端情况下才跳帧（>200fps）
                    should_process = (self.frames_received % 2 == 0)
                
                if should_process:
                    # 调用回调处理帧
                    try:
                        if not callback(frame):
                            logger.info("回调函数返回False，停止接收")
                            break
                        self.last_frame_time = current_time
                    except Exception as e:
                        logger.error(f"帧处理回调异常: {e}")
                        continue
                
                # 性能统计（降低频率）
                if self.frames_received % 500 == 0:  # 每500帧统计一次
                    elapsed = current_time - self.start_time
                    fps = self.frames_received / elapsed if elapsed > 0 else 0
                    logger.info(f"TCP客户端性能: {fps:.1f}fps, 已接收{self.frames_received}帧")
                
        except Exception as e:
            logger.error(f"TCP客户端运行异常: {e}")
            return False
        finally:
            self.disconnect()
            logger.info(f"TCP客户端停止，总计接收{self.frames_received}帧")
        
        return True

    def _receive_frame(self) -> Optional[np.ndarray]:
        """接收单个视频帧（优化版本：8字节长度 + JPEG数据）"""
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
            
            # 接收JPEG数据 - 优化版本
            jpeg_data = self._receive_exact_optimized(int(length))
            if not jpeg_data:
                return None
            
            # 解码JPEG数据为图像 - 优化版本
            try:
                # 使用更快的解码方式
                data = np.frombuffer(jpeg_data, dtype=np.uint8)
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
        """精确接收指定字节数的数据 - 基础版本"""
        data = b''
        while len(data) < size and self.running and self.socket:
            try:
                remaining = size - len(data)
                chunk = self.socket.recv(min(remaining, self.socket_recv_size))
                if not chunk:
                    logger.warning("TCP连接已关闭")
                    return None
                data += chunk
            except socket.timeout:
                # 超时不是错误，继续尝试
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"接收数据失败: {str(e)}")
                return None
        
        return data if len(data) == size else None

    def _receive_exact_optimized(self, size: int) -> Optional[bytes]:
        """精确接收指定字节数的数据 - 优化版本（大数据块）"""
        if size <= self.socket_recv_size:
            # 小数据块，使用基础版本
            return self._receive_exact(size)
        
        # 大数据块，使用优化接收
        data = bytearray(size)
        view = memoryview(data)
        pos = 0
        
        while pos < size and self.running and self.socket:
            try:
                remaining = size - pos
                chunk_size = min(remaining, self.socket_recv_size)
                bytes_received = self.socket.recv_into(view[pos:pos + chunk_size])
                
                if bytes_received == 0:
                    logger.warning("TCP连接已关闭")
                    return None
                    
                pos += bytes_received
                
            except socket.timeout:
                # 超时不是错误，继续尝试
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"接收大数据块失败: {str(e)}")
                return None
        
        return bytes(data) if pos == size else None

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
            'decode_errors': self.decode_errors,
            'bytes_per_second': self.bytes_received / elapsed_time if elapsed_time > 0 else 0
        } 