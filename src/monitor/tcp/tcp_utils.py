#!/usr/bin/env python3
"""
TCP工具函数
提供TCP连接测试和视频信息检测功能
"""

import socket
import time
import cv2
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

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