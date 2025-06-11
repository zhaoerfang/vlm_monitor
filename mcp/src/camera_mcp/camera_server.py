#!/usr/bin/env python3
"""
摄像头控制 MCP Server
提供摄像头转动、拍照、变焦等功能的 MCP 服务
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
import sys
import os

# 使用相对导入 Camera 类
from .utils.Camera import Camera

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 FastMCP 实例
mcp = FastMCP("Camera Control Server")

# 全局摄像头实例
camera_instance: Optional[Camera] = None


def get_camera() -> Camera:
    """获取摄像头实例，如果不存在则创建"""
    global camera_instance
    if camera_instance is None:
        # 默认摄像头配置，可以通过工具调用来设置
        camera_instance = Camera(
            ip='192.168.1.64',
            admin='admin', 
            password='pw4hkcamera'
        )
    return camera_instance


@mcp.tool()
def setup_camera(ip: str, admin: str, password: str) -> str:
    """
    设置摄像头连接参数
    
    Args:
        ip: 摄像头IP地址
        admin: 用户名
        password: 密码
    
    Returns:
        设置结果信息
    """
    global camera_instance
    try:
        camera_instance = Camera(ip=ip, admin=admin, password=password)
        return f"摄像头连接参数设置成功: IP={ip}, 用户名={admin}"
    except Exception as e:
        logger.error(f"设置摄像头参数失败: {e}")
        return f"设置摄像头参数失败: {str(e)}"


@mcp.tool()
def pan_tilt_move(pan_speed: int = 0, tilt_speed: int = 0, duration: float = 1.0) -> str:
    """
    控制摄像头水平和垂直转动
    
    Args:
        pan_speed: 水平转动速度，正数右转，负数左转，范围 -100 到 100
        tilt_speed: 垂直转动速度，正数上升，负数下降，范围 -100 到 100  
        duration: 转动持续时间（秒）
    
    Returns:
        操作结果信息
    """
    try:
        camera = get_camera()
        camera.pan_tilt_move(pan_speed=pan_speed, tilt_speed=tilt_speed, second=duration)
        
        direction = []
        if pan_speed > 0:
            direction.append("右转")
        elif pan_speed < 0:
            direction.append("左转")
            
        if tilt_speed > 0:
            direction.append("上升")
        elif tilt_speed < 0:
            direction.append("下降")
            
        if not direction:
            direction.append("停止")
            
        return f"摄像头{'/'.join(direction)}，速度: 水平={pan_speed}, 垂直={tilt_speed}，持续时间: {duration}秒"
    except Exception as e:
        logger.error(f"摄像头转动失败: {e}")
        return f"摄像头转动失败: {str(e)}"


@mcp.tool()
def capture_image(img_name: str = "") -> str:
    """
    摄像头拍照
    
    Args:
        img_name: 图片名称，为空则自动生成
    
    Returns:
        拍照结果信息
    """
    try:
        camera = get_camera()
        result = camera.catch(img_name=img_name)
        if result:
            return f"拍照成功，图片名称: {result}"
        else:
            return "拍照失败"
    except Exception as e:
        logger.error(f"拍照失败: {e}")
        return f"拍照失败: {str(e)}"


@mcp.tool()
def goto_preset(point: int) -> str:
    """
    移动到预设点位
    
    Args:
        point: 预设点位编号
    
    Returns:
        操作结果信息
    """
    try:
        camera = get_camera()
        camera.preset_point(point)
        return f"摄像头移动到预设点位 {point}"
    except Exception as e:
        logger.error(f"移动到预设点位失败: {e}")
        return f"移动到预设点位失败: {str(e)}"


@mcp.tool()
def zoom_control(zoom_level: int, duration: float = 1.0) -> str:
    """
    控制摄像头变焦
    
    Args:
        zoom_level: 变焦级别，正数放大，负数缩小
        duration: 变焦持续时间（秒）
    
    Returns:
        操作结果信息
    """
    try:
        camera = get_camera()
        camera.change_zoom(zoom=zoom_level, second=duration)
        
        action = "放大" if zoom_level > 0 else "缩小" if zoom_level < 0 else "停止变焦"
        return f"摄像头{action}，变焦级别: {zoom_level}，持续时间: {duration}秒"
    except Exception as e:
        logger.error(f"变焦控制失败: {e}")
        return f"变焦控制失败: {str(e)}"


@mcp.tool()
def adjust_image_settings(brightness: int = 50, contrast: int = 50, saturation: int = 50) -> str:
    """
    调整图像设置
    
    Args:
        brightness: 亮度 (0-100)
        contrast: 对比度 (0-100)
        saturation: 饱和度 (0-100)
    
    Returns:
        操作结果信息
    """
    try:
        camera = get_camera()
        camera.change_color(brightness=brightness, contrast=contrast, saturation=saturation)
        return f"图像设置调整成功: 亮度={brightness}, 对比度={contrast}, 饱和度={saturation}"
    except Exception as e:
        logger.error(f"调整图像设置失败: {e}")
        return f"调整图像设置失败: {str(e)}"


@mcp.resource("camera://status")
def get_camera_status() -> str:
    """获取摄像头状态信息"""
    global camera_instance
    if camera_instance:
        return json.dumps({
            "status": "connected",
            "ip": camera_instance.ip,
            "admin": camera_instance.admin,
            "message": "摄像头已连接"
        }, ensure_ascii=False, indent=2)
    else:
        return json.dumps({
            "status": "disconnected", 
            "message": "摄像头未连接"
        }, ensure_ascii=False, indent=2)


@mcp.prompt()
def camera_control_prompt(action: str = "move", **kwargs) -> str:
    """
    生成摄像头控制提示词
    
    Args:
        action: 操作类型 (move, capture, zoom, preset)
        **kwargs: 其他参数
    """
    if action == "move":
        return f"请控制摄像头转动。可用参数: pan_speed (水平速度), tilt_speed (垂直速度), duration (持续时间)"
    elif action == "capture":
        return f"请控制摄像头拍照。可用参数: img_name (图片名称，可选)"
    elif action == "zoom":
        return f"请控制摄像头变焦。可用参数: zoom_level (变焦级别), duration (持续时间)"
    elif action == "preset":
        return f"请移动摄像头到预设点位。可用参数: point (点位编号)"
    else:
        return f"摄像头控制系统支持以下操作: move (转动), capture (拍照), zoom (变焦), preset (预设点位)"


def main():
    """启动 MCP server"""
    logger.info("启动摄像头控制 MCP Server...")
    
    # 运行 FastMCP server
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        logger.error(f"Server 运行失败: {e}")
        raise


if __name__ == "__main__":
    main() 