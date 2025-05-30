#!/usr/bin/env python3
"""
TCP视频流服务器
从视频文件读取帧并通过TCP协议发送给客户端
"""

import cv2
import socket
import threading
import time
import pickle
import struct
import logging
from pathlib import Path
from typing import Optional, List, Callable

logger = logging.getLogger(__name__)

class TCPVideoServer:
    def __init__(self, video_path: str, port: int = 9999, fps: float = 25.0):
        """
        初始化TCP视频服务器
        
        Args:
            video_path: 视频文件路径
            port: TCP端口
            fps: 发送帧率
        """
        self.video_path = video_path
        self.port = port
        self.fps = fps
        self.frame_interval = 1.0 / fps
        
        # 验证视频文件
        if not Path(video_path).exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        # 网络相关
        self.server_socket = None
        self.clients = []  # 连接的客户端列表
        self.running = False
        self.clients_lock = threading.Lock()  # 保护客户端列表的锁
        
        # 视频相关
        self.cap = None
        self.total_frames = 0
        self.current_frame = 0
        
        # 线程
        self.server_thread = None
        self.broadcast_thread = None
        
        logger.info(f"TCP视频服务器初始化: {video_path}, 端口: {port}, 帧率: {fps}fps")

    def start(self) -> str:
        """启动TCP视频服务器"""
        try:
            # 打开视频文件
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                raise RuntimeError(f"无法打开视频文件: {self.video_path}")
            
            # 获取视频信息
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            original_fps = self.cap.get(cv2.CAP_PROP_FPS)
            width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            logger.info(f"视频信息: {width}x{height}, {original_fps:.2f}fps, {self.total_frames}帧")
            
            # 创建服务器socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            
            self.running = True
            
            # 启动服务器线程
            self.server_thread = threading.Thread(target=self._accept_clients, name="TCPVideoServer")
            self.server_thread.daemon = True
            self.server_thread.start()
            
            # 启动广播线程
            self.broadcast_thread = threading.Thread(target=self._broadcast_frames, name="TCPVideoBroadcast")
            self.broadcast_thread.daemon = True
            self.broadcast_thread.start()
            
            tcp_url = f"tcp://localhost:{self.port}"
            logger.info(f"✅ TCP视频服务器已启动: {tcp_url}")
            return tcp_url
            
        except Exception as e:
            logger.error(f"启动TCP视频服务器失败: {str(e)}")
            self.stop()
            raise

    def stop(self):
        """停止TCP视频服务器"""
        self.running = False
        
        # 关闭所有客户端连接
        with self.clients_lock:
            for client_socket in self.clients[:]:
                try:
                    client_socket.close()
                except:
                    pass
            self.clients.clear()
        
        # 关闭服务器socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # 关闭视频捕获
        if self.cap:
            self.cap.release()
        
        # 等待线程结束
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2)
        if self.broadcast_thread and self.broadcast_thread.is_alive():
            self.broadcast_thread.join(timeout=2)
        
        logger.info("TCP视频服务器已停止")

    def _accept_clients(self):
        """接受客户端连接"""
        while self.running:
            try:
                if self.server_socket:
                    client_socket, client_address = self.server_socket.accept()
                    with self.clients_lock:
                        self.clients.append(client_socket)
                    logger.info(f"客户端已连接: {client_address}, 当前客户端数: {len(self.clients)}")
                
            except Exception as e:
                if self.running:
                    logger.error(f"接受客户端连接失败: {str(e)}")
                break

    def _broadcast_frames(self):
        """广播视频帧给所有客户端"""
        frame_count = 0
        start_time = time.time()
        consecutive_failures = 0
        max_failures = 10
        
        while self.running:
            try:
                # 读取帧
                if self.cap:
                    ret, frame = self.cap.read()
                    if not ret:
                        consecutive_failures += 1
                        logger.warning(f"读取帧失败 ({consecutive_failures}/{max_failures})")
                        
                        if consecutive_failures >= max_failures:
                            logger.error("连续读取帧失败次数过多，可能是视频文件损坏")
                            break
                        
                        # 尝试重新打开视频文件
                        try:
                            self.cap.release()
                            self.cap = cv2.VideoCapture(self.video_path)
                            if not self.cap.isOpened():
                                logger.error("无法重新打开视频文件")
                                break
                            
                            # 重置位置
                            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            self.current_frame = 0
                            time.sleep(0.1)  # 短暂等待
                            continue
                            
                        except Exception as e:
                            logger.error(f"重新打开视频文件失败: {str(e)}")
                            break
                    
                    # 成功读取帧，重置失败计数
                    consecutive_failures = 0
                    self.current_frame += 1
                    frame_count += 1
                    
                    # 序列化帧数据
                    frame_data = {
                        'frame': frame,
                        'timestamp': time.time(),
                        'frame_number': self.current_frame,
                        'total_frames': self.total_frames if self.total_frames > 0 else frame_count
                    }
                    
                    # 使用pickle序列化
                    try:
                        serialized_data = pickle.dumps(frame_data)
                        frame_size = len(serialized_data)
                        
                        # 发送给所有连接的客户端
                        with self.clients_lock:
                            disconnected_clients = []
                            for client_socket in self.clients[:]:
                                try:
                                    # 发送帧大小（4字节）
                                    client_socket.sendall(struct.pack('!I', frame_size))
                                    # 发送帧数据
                                    client_socket.sendall(serialized_data)
                                except Exception as e:
                                    logger.warning(f"发送帧到客户端失败: {str(e)}")
                                    disconnected_clients.append(client_socket)
                            
                            # 移除断开的客户端
                            for client_socket in disconnected_clients:
                                if client_socket in self.clients:
                                    self.clients.remove(client_socket)
                                try:
                                    client_socket.close()
                                except:
                                    pass
                            
                            if disconnected_clients:
                                logger.info(f"移除 {len(disconnected_clients)} 个断开的客户端，剩余: {len(self.clients)}")
                    
                    except Exception as e:
                        logger.error(f"序列化帧数据失败: {str(e)}")
                        continue
                    
                    # 控制帧率
                    elapsed_time = time.time() - start_time
                    expected_time = frame_count * self.frame_interval
                    sleep_time = expected_time - elapsed_time
                    
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    
                    # 每100帧报告一次状态
                    if frame_count % 100 == 0:
                        actual_fps = frame_count / elapsed_time if elapsed_time > 0 else 0
                        with self.clients_lock:
                            client_count = len(self.clients)
                        logger.info(f"已广播 {frame_count} 帧, 实际fps: {actual_fps:.2f}, 连接客户端: {client_count}")
                
            except Exception as e:
                if self.running:
                    logger.error(f"广播帧失败: {str(e)}")
                    time.sleep(0.1)

    def get_status(self) -> dict:
        """获取服务器状态"""
        with self.clients_lock:
            client_count = len(self.clients)
        
        return {
            'running': self.running,
            'clients_count': client_count,
            'current_frame': self.current_frame,
            'total_frames': self.total_frames,
            'video_path': self.video_path,
            'port': self.port,
            'fps': self.fps
        } 