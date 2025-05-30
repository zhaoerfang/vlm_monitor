#!/usr/bin/env python3
"""
图像处理工具函数
提供图像缩放、格式转换等功能
"""

import cv2
import numpy as np
import logging
from typing import Tuple, Optional, Union

logger = logging.getLogger(__name__)

def smart_resize_frame(frame: np.ndarray, 
                      target_width: int = 640, 
                      target_height: int = 360,
                      max_size_mb: float = 5.0,
                      maintain_aspect_ratio: bool = True) -> np.ndarray:
    """
    智能缩放视频帧
    
    Args:
        frame: 输入帧 (numpy数组)
        target_width: 目标宽度
        target_height: 目标高度  
        max_size_mb: 最大帧大小限制(MB)
        maintain_aspect_ratio: 是否保持宽高比
        
    Returns:
        缩放后的帧
    """
    if frame is None or frame.size == 0:
        logger.warning("输入帧为空，返回None")
        return None
    
    try:
        # 获取原始尺寸
        original_height, original_width = frame.shape[:2]
        original_size_mb = frame.nbytes / (1024 * 1024)
        
        logger.debug(f"原始帧尺寸: {original_width}x{original_height}, 大小: {original_size_mb:.2f}MB")
        
        # 如果原始帧已经很小且大小合适，直接返回
        if (original_width <= target_width and 
            original_height <= target_height and 
            original_size_mb <= max_size_mb):
            logger.debug("帧尺寸已符合要求，无需缩放")
            return frame
        
        # 计算缩放比例
        if maintain_aspect_ratio:
            # 保持宽高比，选择较小的缩放比例
            scale_w = target_width / original_width
            scale_h = target_height / original_height
            scale = min(scale_w, scale_h)
            
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
        else:
            # 不保持宽高比，直接缩放到目标尺寸
            new_width = target_width
            new_height = target_height
        
        # 确保尺寸为偶数（某些编码器要求）
        new_width = new_width if new_width % 2 == 0 else new_width - 1
        new_height = new_height if new_height % 2 == 0 else new_height - 1
        
        # 执行缩放
        resized_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
        # 检查缩放后的大小
        new_size_mb = resized_frame.nbytes / (1024 * 1024)
        
        logger.debug(f"缩放后帧尺寸: {new_width}x{new_height}, 大小: {new_size_mb:.2f}MB")
        
        # 如果缩放后仍然太大，进一步缩放
        if new_size_mb > max_size_mb:
            # 计算需要进一步缩放的比例
            size_ratio = max_size_mb / new_size_mb
            additional_scale = np.sqrt(size_ratio)  # 面积缩放，所以开平方
            
            final_width = int(new_width * additional_scale)
            final_height = int(new_height * additional_scale)
            
            # 确保尺寸为偶数
            final_width = final_width if final_width % 2 == 0 else final_width - 1
            final_height = final_height if final_height % 2 == 0 else final_height - 1
            
            resized_frame = cv2.resize(resized_frame, (final_width, final_height), interpolation=cv2.INTER_AREA)
            final_size_mb = resized_frame.nbytes / (1024 * 1024)
            
            logger.info(f"进一步缩放: {final_width}x{final_height}, 最终大小: {final_size_mb:.2f}MB")
        
        return resized_frame
        
    except Exception as e:
        logger.error(f"帧缩放失败: {str(e)}")
        return frame  # 失败时返回原始帧


def validate_frame(frame: np.ndarray) -> bool:
    """
    验证帧是否有效
    
    Args:
        frame: 输入帧
        
    Returns:
        是否有效
    """
    if frame is None:
        return False
    
    if not isinstance(frame, np.ndarray):
        return False
    
    if frame.size == 0:
        return False
    
    if len(frame.shape) < 2:
        return False
    
    # 检查尺寸是否合理
    height, width = frame.shape[:2]
    if width < 1 or height < 1 or width > 10000 or height > 10000:
        return False
    
    return True


def get_frame_info(frame: np.ndarray) -> dict:
    """
    获取帧的详细信息
    
    Args:
        frame: 输入帧
        
    Returns:
        帧信息字典
    """
    if not validate_frame(frame):
        return {'valid': False}
    
    height, width = frame.shape[:2]
    channels = frame.shape[2] if len(frame.shape) > 2 else 1
    
    return {
        'valid': True,
        'width': width,
        'height': height,
        'channels': channels,
        'resolution': f"{width}x{height}",
        'size_bytes': frame.nbytes,
        'size_mb': frame.nbytes / (1024 * 1024),
        'dtype': str(frame.dtype),
        'shape': frame.shape
    } 