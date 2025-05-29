#!/usr/bin/env python3
"""
RTSP工具模块
提供RTSP流相关的工具函数，如帧率检测、连接测试等
"""

import cv2
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def detect_rtsp_fps(rtsp_url: str, config: Dict[str, Any]) -> float:
    """
    动态检测RTSP流的真实帧率
    
    Args:
        rtsp_url: RTSP流地址
        config: 配置字典，包含rtsp配置项
        
    Returns:
        检测到的帧率，如果检测失败则返回默认帧率
    """
    rtsp_config = config.get('rtsp', {})
    
    if not rtsp_config.get('auto_detect_fps', True):
        fps = rtsp_config.get('default_fps', 25.0)
        logger.info(f"🔧 使用配置的默认帧率: {fps}fps")
        return fps
    
    logger.info("🔍 正在检测RTSP流的真实帧率...")
    try:
        test_cap = cv2.VideoCapture(rtsp_url)
        if test_cap.isOpened():
            detected_fps = test_cap.get(cv2.CAP_PROP_FPS)
            test_cap.release()
            
            if detected_fps and detected_fps > 0:
                logger.info(f"✅ 检测到RTSP流帧率: {detected_fps}fps")
                return detected_fps
            else:
                default_fps = rtsp_config.get('default_fps', 25.0)
                logger.warning(f"⚠️ 无法检测帧率，使用默认值: {default_fps}fps")
                return default_fps
        else:
            default_fps = rtsp_config.get('default_fps', 25.0)
            logger.error(f"❌ 无法连接RTSP流，使用默认帧率: {default_fps}fps")
            return default_fps
    except Exception as e:
        default_fps = rtsp_config.get('default_fps', 25.0)
        logger.error(f"❌ 帧率检测失败: {str(e)}，使用默认值: {default_fps}fps")
        return default_fps

def test_rtsp_connection(rtsp_url: str) -> Dict[str, Any]:
    """
    测试RTSP连接并获取流信息
    
    Args:
        rtsp_url: RTSP流地址
        
    Returns:
        包含连接状态和流信息的字典
    """
    logger.info(f"🔗 测试RTSP连接: {rtsp_url}")
    
    result = {
        'connected': False,
        'error': None,
        'stream_info': {}
    }
    
    try:
        test_cap = cv2.VideoCapture(rtsp_url)
        
        if test_cap.isOpened():
            # 尝试读取一帧
            ret, frame = test_cap.read()
            if ret and frame is not None:
                # 获取流信息
                fps = test_cap.get(cv2.CAP_PROP_FPS)
                width = int(test_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(test_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
                result['connected'] = True
                result['stream_info'] = {
                    'fps': fps,
                    'width': width,
                    'height': height,
                    'resolution': f"{width}x{height}"
                }
                
                logger.info("✅ RTSP连接成功")
                logger.info(f"📊 流信息: {width}x{height}, {fps:.2f}fps")
                
                test_cap.release()
            else:
                result['error'] = "无法从RTSP流读取帧"
                logger.error("❌ 无法从RTSP流读取帧")
                test_cap.release()
        else:
            result['error'] = "无法连接到RTSP流"
            logger.error("❌ 无法连接到RTSP流")
            
    except Exception as e:
        result['error'] = f"RTSP连接测试失败: {str(e)}"
        logger.error(f"❌ RTSP连接测试失败: {str(e)}")
    
    return result

def get_rtsp_stream_info(rtsp_url: str) -> Optional[Dict[str, Any]]:
    """
    获取RTSP流的详细信息
    
    Args:
        rtsp_url: RTSP流地址
        
    Returns:
        流信息字典，如果失败返回None
    """
    try:
        cap = cv2.VideoCapture(rtsp_url)
        
        if not cap.isOpened():
            logger.error(f"无法打开RTSP流: {rtsp_url}")
            return None
        
        # 获取基本信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # 尝试获取编解码器信息
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
        
        cap.release()
        
        stream_info = {
            'fps': fps,
            'width': width,
            'height': height,
            'resolution': f"{width}x{height}",
            'frame_count': frame_count,
            'codec': codec.strip(),
            'url': rtsp_url
        }
        
        logger.info(f"📊 RTSP流信息: {stream_info}")
        return stream_info
        
    except Exception as e:
        logger.error(f"获取RTSP流信息失败: {str(e)}")
        return None

def validate_rtsp_url(rtsp_url: str) -> bool:
    """
    验证RTSP URL格式
    
    Args:
        rtsp_url: 要验证的RTSP URL
        
    Returns:
        URL是否有效
    """
    if not rtsp_url:
        return False
    
    # 基本格式检查
    if not rtsp_url.lower().startswith('rtsp://'):
        logger.error("❌ URL必须以rtsp://开头")
        return False
    
    # 更详细的验证可以在这里添加
    logger.info(f"✅ RTSP URL格式验证通过: {rtsp_url}")
    return True

def create_rtsp_client_config(rtsp_url: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据配置和RTSP流信息创建客户端配置
    
    Args:
        rtsp_url: RTSP流地址
        config: 配置字典
        
    Returns:
        客户端配置字典
    """
    rtsp_config = config.get('rtsp', {})
    
    # 检测帧率
    detected_fps = detect_rtsp_fps(rtsp_url, config)
    
    # 创建客户端配置
    client_config = {
        'rtsp_url': rtsp_url,
        'frame_rate': min(rtsp_config.get('client_target_fps', 10), detected_fps),
        'timeout': rtsp_config.get('connection_timeout', 60),
        'buffer_size': rtsp_config.get('client_buffer_size', 100),
        'original_fps': detected_fps
    }
    
    logger.info(f"🔧 创建RTSP客户端配置:")
    logger.info(f"  - 目标帧率: {client_config['frame_rate']}fps")
    logger.info(f"  - 原始帧率: {client_config['original_fps']}fps")
    logger.info(f"  - 超时时间: {client_config['timeout']}s")
    logger.info(f"  - 缓冲区大小: {client_config['buffer_size']}")
    
    return client_config 