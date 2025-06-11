#!/usr/bin/env python3
"""
摄像头控制 MCP Server
提供摄像头转动、拍照、变焦等功能的 MCP 服务
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
import sys
import os

# 使用相对导入 Camera 类
from ..utils.Camera import Camera

# 配置日志 - 写入文件而不是标准输出
import os
from datetime import datetime

# 确保日志目录存在
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'logs')
os.makedirs(log_dir, exist_ok=True)

# 生成日志文件名（包含日期时间）
log_filename = f"camera_server.log"
log_filepath = os.path.join(log_dir, log_filename)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filepath, encoding='utf-8'),  # 写入文件
        logging.StreamHandler(sys.stderr),
    ],
    force=True
)
logger = logging.getLogger(__name__)

# 创建 FastMCP 实例
mcp = FastMCP("Camera Control Server")

# 全局摄像头实例
camera_instance: Optional[Camera] = None

# 全局位置跟踪变量
current_pan_position: float = 0.0  # 当前水平位置，范围 -180 到 +180 度
PAN_MIN_LIMIT = -180.0  # 最左极限
PAN_MAX_LIMIT = 180.0   # 最右极限


def get_camera() -> Camera:
    """获取摄像头实例，如果不存在则创建并初始化到中心位置"""
    global camera_instance, current_pan_position
    if camera_instance is None:
        print("初始化摄像头...", file=sys.stderr, flush=True)
        # 默认摄像头配置，可以通过工具调用来设置
        camera_instance = Camera(
            ip='192.168.1.64',
            admin='admin', 
            password='pw4hkcamera'
        )
        # 初始化摄像头到中心位置
        try:
            logger.info("初始化摄像头到中心位置...")
            camera_instance.goto_preset_point(point_id=1)  # 假设预设点1是中心位置
            current_pan_position = 0.0
            logger.info("摄像头已初始化到中心位置")
        except Exception as e:
            logger.warning(f"无法初始化摄像头到中心位置: {e}")
            current_pan_position = 0.0  # 假设当前在中心位置
    print("获取摄像头实例...", file=sys.stderr, flush=True)
    return camera_instance


# @mcp.tool()
# def setup_camera(ip: str, admin: str, password: str) -> str:
#     """
#     设置摄像头连接参数
    
#     Args:
#         ip: 摄像头IP地址
#         admin: 用户名
#         password: 密码
    
#     Returns:
#         设置结果信息
#     """
#     global camera_instance
#     try:
#         camera_instance = Camera(ip=ip, admin=admin, password=password)
#         return f"摄像头连接参数设置成功: IP={ip}, 用户名={admin}"
#     except Exception as e:
#         logger.error(f"设置摄像头参数失败: {e}")
#         return f"设置摄像头参数失败: {str(e)}"


@mcp.tool()
def pan_tilt_move(pan_angle: float = 0) -> str:
    """
    控制摄像头水平转动，转动角度是相对当前位置的，系统会自动检查是否超出极限范围，如果超出极限，系统会返回错误信息和剩余可转动角度。
    
    Args:
        pan_angle: 水平转动角度，正数右转，负数左转，范围 -180 到 180 度，中心位置为0度
    
    Returns:
        操作结果信息
    """
    global current_pan_position
    
    logger.info(f"🔧 [TOOL] pan_tilt_move() 被调用，参数: pan_angle={pan_angle}")
    
    try:
        camera = get_camera()
        
        # 水平转动处理
        if pan_angle != 0:
            # 计算目标位置
            target_position = current_pan_position + pan_angle
            
            # 检查是否超出极限
            if target_position > PAN_MAX_LIMIT:
                # 超出右极限
                remaining_right = PAN_MAX_LIMIT - current_pan_position
                if remaining_right <= 0:
                    return f"❌ 超出极限位置！当前位置: {current_pan_position:.1f}°，已到达右极限 {PAN_MAX_LIMIT}°，现在只能向左旋转"
                else:
                    return f"❌ 超出极限位置！目标位置 {target_position:.1f}° 超出右极限 {PAN_MAX_LIMIT}°，最多只能右转 {remaining_right:.1f}°"
            
            elif target_position < PAN_MIN_LIMIT:
                # 超出左极限
                remaining_left = current_pan_position - PAN_MIN_LIMIT
                if remaining_left <= 0:
                    return f"❌ 超出极限位置！当前位置: {current_pan_position:.1f}°，已到达左极限 {PAN_MIN_LIMIT}°，现在只能向右旋转"
                else:
                    return f"❌ 超出极限位置！目标位置 {target_position:.1f}° 超出左极限 {PAN_MIN_LIMIT}°，最多只能左转 {remaining_left:.1f}°"
            
            # 在安全范围内，执行转动
            # 计算转动时间：角度转换为时间
            # 360度对应400个单位，速度50，所以360度需要 400/50 = 8秒
            pan_duration = abs(pan_angle) / 360 * 8
            
            # 确定转动方向和速度
            pan_speed = 50 if pan_angle > 0 else -50
            
            # 执行水平转动
            camera.pan_tilt_move(pan_speed=pan_speed, tilt_speed=0, second=pan_duration)
            
            # 更新当前位置
            current_pan_position = target_position
        
        # 构建返回信息
        direction = []
        if pan_angle > 0:
            direction.append(f"右转{pan_angle}度")
        elif pan_angle < 0:
            direction.append(f"左转{abs(pan_angle)}度")            
            
        if not direction:
            direction.append("停止")
            
        result_msg = f"✅ 摄像头{'/'.join(direction)}"
        if pan_angle != 0:
            result_msg += f"，水平转动时间: {pan_duration:.2f}秒，当前位置: {current_pan_position:.1f}°"
            
        return result_msg
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
    logger.info(f"🔧 [TOOL] capture_image() 被调用，参数: img_name='{img_name}'")
    
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
def get_camera_position() -> str:
    """
    获取摄像头当前位置信息
    
    Returns:
        当前位置信息
    """
    logger.info(f"🔧 [TOOL] get_camera_position() 被调用")
    
    global current_pan_position
    remaining_left = current_pan_position - PAN_MIN_LIMIT
    remaining_right = PAN_MAX_LIMIT - current_pan_position
    
    return f"📍 摄像头当前位置: {current_pan_position:.1f}°\n" \
           f"   可向左转动: {remaining_left:.1f}° (极限: {PAN_MIN_LIMIT}°)\n" \
           f"   可向右转动: {remaining_right:.1f}° (极限: {PAN_MAX_LIMIT}°)"


@mcp.tool()
def reset_camera_position() -> str:
    """
    重置摄像头到中心位置
    
    Returns:
        重置结果信息
    """
    global current_pan_position
    try:
        camera = get_camera()
        camera.goto_preset_point(point_id=1)  # 假设预设点1是中心位置
        current_pan_position = 0.0
        return f"✅ 摄像头已重置到中心位置 (0°)"
    except Exception as e:
        logger.error(f"重置摄像头位置失败: {e}")
        return f"❌ 重置摄像头位置失败: {str(e)}"


@mcp.tool()
def goto_preset(point: int) -> str:
    """
    移动到预设点位
    
    Args:
        point: 预设点位编号 (1=中心位置0°, 其他点位位置未知)
    
    Returns:
        操作结果信息
    """
    global current_pan_position
    try:
        camera = get_camera()
        camera.goto_preset_point(point_id=point)
        
        # 如果是预设点1，假设是中心位置
        if point == 1:
            current_pan_position = 0.0
            return f"✅ 摄像头移动到预设点位 {point} (中心位置 0°)"
        else:
            # 其他预设点位置未知，提醒用户
            return f"✅ 摄像头移动到预设点位 {point}，⚠️ 位置跟踪已失效，建议使用 reset_camera_position 重新校准"
    except Exception as e:
        logger.error(f"移动到预设点位失败: {e}")
        return f"❌ 移动到预设点位失败: {str(e)}"


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
    logger.info(f"🔧 [RESOURCE] get_camera_status() 被调用")
    
    # global camera_instance
    camera = get_camera()
    if camera:
        return json.dumps({
            "status": "connected",
            "ip": camera.ip,
            "admin": camera.admin,
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
    logger.info("=" * 80)
    logger.info("🚀 [SERVER] 摄像头控制 MCP Server 启动中...")
    logger.info(f"🚀 [SERVER] 启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🚀 [SERVER] Python 版本: {sys.version}")
    logger.info(f"🚀 [SERVER] 工作目录: {os.getcwd()}")
    logger.info("=" * 80)
    
    # 运行 FastMCP server
    try:
        logger.info("🚀 [SERVER] 开始运行 FastMCP server (stdio transport)...")
        mcp.run(transport="stdio")
    except Exception as e:
        logger.error(f"🚀 [SERVER] ❌ Server 运行失败: {e}")
        raise


if __name__ == "__main__":
    logger.info("🚀 [SERVER] 脚本直接运行，调用 main()...")
    main() 