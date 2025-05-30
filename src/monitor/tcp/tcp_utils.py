#!/usr/bin/env python3
"""
TCP工具函数
提供TCP连接测试和视频信息检测功能
"""

import socket
import time
import cv2
import pickle
import struct
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def detect_tcp_fps(host: str, port: int, config: Dict[str, Any], sample_duration: float = 3.0) -> float:
    """
    动态检测TCP视频服务器的真实帧率
    
    Args:
        host: TCP服务器地址
        port: TCP服务器端口
        config: 配置字典，包含tcp配置项
        sample_duration: 采样时长（秒）
        
    Returns:
        检测到的帧率，如果检测失败则返回默认帧率
    """
    tcp_config = config.get('stream', {}).get('tcp', {})
    
    if not tcp_config.get('auto_detect_fps', True):
        fps = tcp_config.get('fps', 25.0)
        logger.info(f"🔧 使用配置的默认帧率: {fps}fps")
        return fps
    
    logger.info(f"🔍 正在检测TCP服务器的真实帧率 ({host}:{port})...")
    
    sock = None
    try:
        # 连接到TCP服务器
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        
        # 记录开始时间和帧数
        start_time = time.time()
        frame_count = 0
        frame_timestamps = []
        
        while time.time() - start_time < sample_duration:
            try:
                # 接收帧大小（4字节）
                size_data = _receive_exact(sock, 4)
                if not size_data:
                    break
                
                frame_size = struct.unpack('!I', size_data)[0]
                
                # 验证帧大小合理性
                if frame_size > 50 * 1024 * 1024:  # 50MB限制
                    logger.warning(f"帧大小异常: {frame_size} bytes，跳过")
                    continue
                
                # 接收帧数据
                frame_data = _receive_exact(sock, frame_size)
                if not frame_data:
                    break
                
                # 记录帧时间戳
                frame_timestamps.append(time.time())
                frame_count += 1
                
                # 反序列化验证（可选，这里只是为了确保数据完整性）
                try:
                    pickle.loads(frame_data)
                except:
                    logger.warning("帧数据反序列化失败，但继续计数")
                
            except socket.timeout:
                logger.warning("接收帧超时")
                break
            except Exception as e:
                logger.warning(f"接收帧时出错: {str(e)}")
                break
        
        # 计算帧率
        if frame_count >= 2 and len(frame_timestamps) >= 2:
            total_duration = frame_timestamps[-1] - frame_timestamps[0]
            if total_duration > 0:
                detected_fps = (frame_count - 1) / total_duration
                logger.info(f"✅ 检测到TCP服务器帧率: {detected_fps:.2f}fps (采样{frame_count}帧，耗时{total_duration:.2f}s)")
                return detected_fps
        
        # 如果检测失败，使用默认值
        default_fps = tcp_config.get('fps', 25.0)
        logger.warning(f"⚠️ 无法检测帧率（采样{frame_count}帧），使用默认值: {default_fps}fps")
        return default_fps
        
    except socket.timeout:
        default_fps = tcp_config.get('fps', 25.0)
        logger.error(f"❌ 连接TCP服务器超时，使用默认帧率: {default_fps}fps")
        return default_fps
    except ConnectionRefusedError:
        default_fps = tcp_config.get('fps', 25.0)
        logger.error(f"❌ TCP服务器连接被拒绝，使用默认帧率: {default_fps}fps")
        return default_fps
    except Exception as e:
        default_fps = tcp_config.get('fps', 25.0)
        logger.error(f"❌ 帧率检测失败: {str(e)}，使用默认值: {default_fps}fps")
        return default_fps
    finally:
        if sock:
            try:
                sock.close()
            except:
                pass

def _receive_exact(sock: socket.socket, size: int) -> Optional[bytes]:
    """精确接收指定字节数的数据"""
    data = b''
    while len(data) < size:
        try:
            remaining = size - len(data)
            chunk = sock.recv(min(remaining, 8192))  # 每次最多接收8KB
            if not chunk:
                return None
            data += chunk
        except Exception:
            return None
    
    return data if len(data) == size else None

def test_tcp_connection(host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
    """
    测试TCP连接
    
    Args:
        host: 服务器地址
        port: 服务器端口
        timeout: 连接超时时间
        
    Returns:
        连接测试结果
    """
    result = {
        'connected': False,
        'host': host,
        'port': port,
        'response_time': None,
        'error': None
    }
    
    try:
        start_time = time.time()
        
        # 创建socket并连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        
        response_time = time.time() - start_time
        result['connected'] = True
        result['response_time'] = response_time
        
        # 关闭连接
        sock.close()
        
        logger.info(f"TCP连接测试成功: {host}:{port}, 响应时间: {response_time:.3f}s")
        
    except socket.timeout:
        result['error'] = f"连接超时 ({timeout}s)"
        logger.warning(f"TCP连接超时: {host}:{port}")
    except ConnectionRefusedError:
        result['error'] = "连接被拒绝"
        logger.warning(f"TCP连接被拒绝: {host}:{port}")
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"TCP连接测试失败: {host}:{port}, 错误: {str(e)}")
    
    return result

def test_tcp_video_stream(host: str, port: int, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    测试TCP视频流并获取流信息
    
    Args:
        host: TCP服务器地址
        port: TCP服务器端口
        config: 配置字典
        
    Returns:
        包含连接状态和流信息的字典
    """
    logger.info(f"🔗 测试TCP视频流: {host}:{port}")
    
    result = {
        'connected': False,
        'error': None,
        'stream_info': {}
    }
    
    try:
        # 首先测试基本连接
        connection_result = test_tcp_connection(host, port, timeout=5)
        
        if not connection_result['connected']:
            result['error'] = connection_result['error']
            return result
        
        # 检测帧率
        detected_fps = detect_tcp_fps(host, port, config, sample_duration=2.0)
        
        result['connected'] = True
        result['stream_info'] = {
            'fps': detected_fps,
            'host': host,
            'port': port,
            'protocol': 'tcp'
        }
        
        logger.info("✅ TCP视频流连接成功")
        logger.info(f"📊 流信息: {detected_fps:.2f}fps")
        
    except Exception as e:
        result['error'] = f"TCP视频流测试失败: {str(e)}"
        logger.error(f"❌ TCP视频流测试失败: {str(e)}")
    
    return result

def create_tcp_client_config(host: str, port: int, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据配置和TCP服务器信息创建客户端配置
    
    Args:
        host: TCP服务器地址
        port: TCP服务器端口
        config: 配置字典
        
    Returns:
        客户端配置字典
    """
    tcp_config = config.get('stream', {}).get('tcp', {})
    
    # 检测帧率
    detected_fps = detect_tcp_fps(host, port, config)
    
    # 创建客户端配置
    client_config = {
        'host': host,
        'port': port,
        'frame_rate': detected_fps,  # 使用检测到的帧率
        'timeout': tcp_config.get('connection_timeout', 10),
        'buffer_size': tcp_config.get('client_buffer_size', 100),
        'original_fps': detected_fps
    }
    
    logger.info(f"🔧 创建TCP客户端配置:")
    logger.info(f"  - 目标帧率: {client_config['frame_rate']:.2f}fps")
    logger.info(f"  - 原始帧率: {client_config['original_fps']:.2f}fps")
    logger.info(f"  - 超时时间: {client_config['timeout']}s")
    logger.info(f"  - 缓冲区大小: {client_config['buffer_size']}")
    
    return client_config

def detect_video_info(video_path: str) -> Dict[str, Any]:
    """
    检测视频文件信息
    
    Args:
        video_path: 视频文件路径
        
    Returns:
        视频信息字典
    """
    result = {
        'exists': False,
        'readable': False,
        'fps': None,
        'frame_count': None,
        'duration': None,
        'resolution': None,
        'file_size_mb': None,
        'error': None
    }
    
    try:
        video_file = Path(video_path)
        
        # 检查文件是否存在
        if not video_file.exists():
            result['error'] = f"视频文件不存在: {video_path}"
            return result
        
        result['exists'] = True
        result['file_size_mb'] = video_file.stat().st_size / (1024 * 1024)
        
        # 使用OpenCV读取视频信息
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            result['error'] = f"无法打开视频文件: {video_path}"
            return result
        
        result['readable'] = True
        
        # 获取视频属性
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        result['fps'] = fps
        result['frame_count'] = frame_count
        result['resolution'] = f"{width}x{height}"
        result['duration'] = frame_count / fps if fps > 0 else None
        
        cap.release()
        
        logger.info(f"视频信息检测成功: {video_path}")
        logger.info(f"  - 分辨率: {width}x{height}")
        logger.info(f"  - 帧率: {fps:.2f}fps")
        logger.info(f"  - 总帧数: {frame_count}")
        logger.info(f"  - 时长: {result['duration']:.2f}s" if result['duration'] else "  - 时长: 未知")
        logger.info(f"  - 文件大小: {result['file_size_mb']:.2f}MB")
        
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"视频信息检测失败: {video_path}, 错误: {str(e)}")
    
    return result

def check_tcp_server_status(host: str, port: int) -> Dict[str, Any]:
    """
    检查TCP服务器状态
    
    Args:
        host: 服务器地址
        port: 服务器端口
        
    Returns:
        服务器状态信息
    """
    status = {
        'running': False,
        'reachable': False,
        'response_time': None,
        'error': None
    }
    
    try:
        # 测试连接
        connection_result = test_tcp_connection(host, port, timeout=3)
        
        if connection_result['connected']:
            status['running'] = True
            status['reachable'] = True
            status['response_time'] = connection_result['response_time']
        else:
            status['error'] = connection_result['error']
            
    except Exception as e:
        status['error'] = str(e)
        logger.error(f"检查TCP服务器状态失败: {str(e)}")
    
    return status 