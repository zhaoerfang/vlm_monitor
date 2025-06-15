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

# 配置日志 - 输出到主项目的 logs 目录
def setup_logger():
    """设置日志配置"""
    # 获取主项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    logs_dir = os.path.join(project_root, 'logs')
    
    # 确保 logs 目录存在
    os.makedirs(logs_dir, exist_ok=True)
    
    # 配置日志
    log_file = os.path.join(logs_dir, 'mcp_camera_server.log')
    
    # 创建 logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # 避免重复添加 handler
    if not logger.handlers:
        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 控制台处理器（输出到 stderr，避免干扰 MCP 协议）
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.INFO)
        
        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger

logger = setup_logger()


class CameraManager:
    """摄像头管理器 - 统一管理摄像头实例和状态"""
    
    def __init__(self):
        self.camera_instance: Optional[Camera] = None
        self.current_pan_position: float = 0.0  # 当前水平位置，范围 -180 到 +180 度
        self.PAN_MIN_LIMIT = -180.0  # 最左极限
        self.PAN_MAX_LIMIT = 180.0   # 最右极限
        self.is_initialized = False
        
        # 摄像头配置 - 从环境变量或配置文件读取，否则使用默认值
        self.camera_config = {
            'ip': os.getenv('CAMERA_IP', '192.168.1.64'),
            'admin': os.getenv('CAMERA_ADMIN', 'admin'),
            'password': os.getenv('CAMERA_PASSWORD', 'pw4hkcamera')
        }
    
    def initialize_camera(self) -> bool:
        """
        初始化摄像头实例并移动到中心位置
        
        Returns:
            初始化是否成功
        """
        if self.is_initialized:
            logger.info("摄像头已经初始化，跳过重复初始化")
            return True
            
        try:
            logger.info(f"正在初始化摄像头连接: IP={self.camera_config['ip']}")
            self.camera_instance = Camera(
                ip=self.camera_config['ip'],
                admin=self.camera_config['admin'], 
                password=self.camera_config['password']
            )
            
            # 初始化摄像头到中心位置
            logger.info("正在将摄像头移动到中心位置...")
            self.camera_instance.goto_preset_point(point_id=1)  # 假设预设点1是中心位置
            self.current_pan_position = 0.0
            
            self.is_initialized = True
            logger.info("✅ 摄像头初始化完成，已移动到中心位置")
            return True
            
        except Exception as e:
            logger.error(f"❌ 摄像头初始化失败: {e}")
            self.camera_instance = None
            self.is_initialized = False
            return False
    
    def get_camera(self) -> Camera:
        """
        获取摄像头实例
        
        Returns:
            摄像头实例
            
        Raises:
            RuntimeError: 如果摄像头未初始化
        """
        if not self.is_initialized or self.camera_instance is None:
            raise RuntimeError("摄像头未初始化，服务器启动时初始化失败")
        return self.camera_instance
    
    def update_position(self, new_position: float):
        """更新当前位置"""
        self.current_pan_position = new_position
    
    def get_position_info(self) -> Dict[str, float]:
        """获取位置信息"""
        remaining_left = self.current_pan_position - self.PAN_MIN_LIMIT
        remaining_right = self.PAN_MAX_LIMIT - self.current_pan_position
        
        return {
            'current_position': self.current_pan_position,
            'remaining_left': remaining_left,
            'remaining_right': remaining_right,
            'min_limit': self.PAN_MIN_LIMIT,
            'max_limit': self.PAN_MAX_LIMIT
        }
    
    def check_position_limits(self, target_position: float) -> Dict[str, Any]:
        """
        检查目标位置是否在限制范围内
        
        Args:
            target_position: 目标位置
            
        Returns:
            包含检查结果的字典
        """
        if target_position > self.PAN_MAX_LIMIT:
            remaining_right = self.PAN_MAX_LIMIT - self.current_pan_position
            return {
                'valid': False,
                'error_type': 'right_limit',
                'remaining': remaining_right,
                'message': f"目标位置 {target_position:.1f}° 超出右极限 {self.PAN_MAX_LIMIT}°"
            }
        elif target_position < self.PAN_MIN_LIMIT:
            remaining_left = self.current_pan_position - self.PAN_MIN_LIMIT
            return {
                'valid': False,
                'error_type': 'left_limit',
                'remaining': remaining_left,
                'message': f"目标位置 {target_position:.1f}° 超出左极限 {self.PAN_MIN_LIMIT}°"
            }
        else:
            return {'valid': True}
    
    def reset_to_center(self) -> bool:
        """
        重置摄像头到中心位置
        
        Returns:
            重置是否成功
        """
        try:
            camera = self.get_camera()
            camera.goto_preset_point(point_id=1)  # 假设预设点1是中心位置
            self.current_pan_position = 0.0
            logger.info("摄像头已重置到中心位置")
            return True
        except Exception as e:
            logger.error(f"重置摄像头位置失败: {e}")
            return False


# 创建全局摄像头管理器实例
camera_manager = CameraManager()

# 创建 FastMCP 实例
mcp = FastMCP("Camera Control Server")


@mcp.tool()
def pan_tilt_move(pan_angle: float = 0) -> str:
    """
    控制摄像头水平转动，转动角度是相对当前位置的，系统会自动检查是否超出极限范围，如果超出极限，系统会返回错误信息和剩余可转动角度。
    
    Args:
        pan_angle: 水平转动角度，正数右转，负数左转，范围 -180 到 180 度，中心位置为0度
    
    Returns:
        操作结果信息
    """
    logger.info(f"🔧 [TOOL] pan_tilt_move() 被调用，参数: pan_angle={pan_angle}")
    
    try:
        camera = camera_manager.get_camera()
        
        # 水平转动处理
        if pan_angle != 0:
            # 计算目标位置
            target_position = camera_manager.current_pan_position + pan_angle
            
            # 检查是否超出极限
            limit_check = camera_manager.check_position_limits(target_position)
            if not limit_check['valid']:
                if limit_check['error_type'] == 'right_limit':
                    remaining = limit_check['remaining']
                    if remaining <= 0:
                        return f"❌ 超出极限位置！当前位置: {camera_manager.current_pan_position:.1f}°，已到达右极限 {camera_manager.PAN_MAX_LIMIT}°，现在只能向左旋转"
                    else:
                        return f"❌ 超出极限位置！{limit_check['message']}，最多只能右转 {remaining:.1f}°"
                else:  # left_limit
                    remaining = limit_check['remaining']
                    if remaining <= 0:
                        return f"❌ 超出极限位置！当前位置: {camera_manager.current_pan_position:.1f}°，已到达左极限 {camera_manager.PAN_MIN_LIMIT}°，现在只能向右旋转"
                    else:
                        return f"❌ 超出极限位置！{limit_check['message']}，最多只能左转 {remaining:.1f}°"
            
            # 在安全范围内，执行转动
            # 计算转动时间：角度转换为时间
            # 360度对应400个单位，速度50，所以360度需要 400/50 = 8秒
            pan_duration = abs(pan_angle) / 360 * 8
            
            # 确定转动方向和速度
            pan_speed = 50 if pan_angle > 0 else -50
            
            # 执行水平转动
            camera.pan_tilt_move(pan_speed=pan_speed, tilt_speed=0, second=pan_duration)
            
            # 更新当前位置
            camera_manager.update_position(target_position)
        
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
            result_msg += f"，水平转动时间: {pan_duration:.2f}秒，当前位置: {camera_manager.current_pan_position:.1f}°"
            
        return result_msg
    except RuntimeError as e:
        return f"❌ {str(e)}"
    except Exception as e:
        logger.error(f"摄像头转动失败: {e}")
        return f"❌ 摄像头转动失败: {str(e)}"


# @mcp.tool()
# def capture_image(img_name: str = "") -> str:
#     """
#     摄像头拍照
    
#     Args:
#         img_name: 图片名称，为空则自动生成
    
#     Returns:
#         拍照结果信息
#     """
#     logger.info(f"🔧 [TOOL] capture_image() 被调用，参数: img_name='{img_name}'")
    
#     try:
#         camera = camera_manager.get_camera()
#         result = camera.catch(img_name=img_name)
#         if result:
#             return f"✅ 拍照成功，图片名称: {result}"
#         else:
#             return "❌ 拍照失败"
#     except RuntimeError as e:
#         return f"❌ {str(e)}"
#     except Exception as e:
#         logger.error(f"拍照失败: {e}")
#         return f"❌ 拍照失败: {str(e)}"


# @mcp.tool()
# def get_camera_position() -> str:
#     """
#     获取摄像头当前位置信息
    
#     Returns:
#         当前位置信息
#     """
#     logger.info(f"🔧 [TOOL] get_camera_position() 被调用")
    
#     try:
#         # 确保摄像头已初始化
#         camera_manager.get_camera()
        
#         position_info = camera_manager.get_position_info()
        
#         return f"📍 摄像头当前位置: {position_info['current_position']:.1f}°\n" \
#                f"   可向左转动: {position_info['remaining_left']:.1f}° (极限: {position_info['min_limit']}°)\n" \
#                f"   可向右转动: {position_info['remaining_right']:.1f}° (极限: {position_info['max_limit']}°)"
#     except RuntimeError as e:
#         return f"❌ {str(e)}"
#     except Exception as e:
#         logger.error(f"获取摄像头位置失败: {e}")
#         return f"❌ 获取摄像头位置失败: {str(e)}"


# @mcp.tool()
# def reset_camera_position() -> str:
#     """
#     重置摄像头到中心位置
    
#     Returns:
#         重置结果信息
#     """
#     logger.info(f"🔧 [TOOL] reset_camera_position() 被调用")
    
#     try:
#         if camera_manager.reset_to_center():
#             return f"✅ 摄像头已重置到中心位置 (0°)"@mcp.tool()
# def reset_camera_position() -> str:
#     """
#     重置摄像头到中心位置
    
#     Returns:
#         重置结果信息
#     """
#     logger.info(f"🔧 [TOOL] reset_camera_position() 被调用")
    
#     try:
#         if camera_manager.reset_to_center():
#             return f"✅ 摄像头已重置到中心位置 (0°)"
#         else:
#             return f"❌ 重置摄像头位置失败"
#     except RuntimeError as e:
#         return f"❌ {str(e)}"
#     except Exception as e:
#         logger.error(f"重置摄像头位置失败: {e}")
#         return f"❌ 重置摄像头位置失败: {str(e)}"
#         else:
#             return f"❌ 重置摄像头位置失败"
#     except RuntimeError as e:
#         return f"❌ {str(e)}"
#     except Exception as e:
#         logger.error(f"重置摄像头位置失败: {e}")
#         return f"❌ 重置摄像头位置失败: {str(e)}"


@mcp.tool()
def goto_preset(point: int) -> str:
    """
    移动到预设点位
    
    Args:
        point: 预设点位编号 (1=中心位置0°, 其他点位位置未知)
    
    Returns:
        操作结果信息
    """
    logger.info(f"🔧 [TOOL] goto_preset() 被调用，参数: point={point}")
    
    try:
        camera = camera_manager.get_camera()
        camera.goto_preset_point(point_id=point)
        
        # 如果是预设点1，假设是中心位置
        if point == 1:
            camera_manager.update_position(0.0)
            return f"✅ 摄像头移动到预设点位 {point} (中心位置 0°)"
        else:
            # 其他预设点位置未知，提醒用户
            return f"✅ 摄像头移动到预设点位 {point}，⚠️ 位置跟踪已失效，建议使用 reset_camera_position 重新校准"
    except RuntimeError as e:
        return f"❌ {str(e)}"
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
    logger.info(f"🔧 [TOOL] zoom_control() 被调用，参数: zoom_level={zoom_level}, duration={duration}")
    
    try:
        camera = camera_manager.get_camera()
        camera.change_zoom(zoom=zoom_level, second=duration)
        
        action = "放大" if zoom_level > 0 else "缩小" if zoom_level < 0 else "停止变焦"
        return f"✅ 摄像头{action}，变焦级别: {zoom_level}，持续时间: {duration}秒"
    except RuntimeError as e:
        return f"❌ {str(e)}"
    except Exception as e:
        logger.error(f"变焦控制失败: {e}")
        return f"❌ 变焦控制失败: {str(e)}"


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
    logger.info(f"🔧 [TOOL] adjust_image_settings() 被调用，参数: brightness={brightness}, contrast={contrast}, saturation={saturation}")
    
    try:
        camera = camera_manager.get_camera()
        camera.change_color(brightness=brightness, contrast=contrast, saturation=saturation)
        return f"✅ 图像设置调整成功: 亮度={brightness}, 对比度={contrast}, 饱和度={saturation}"
    except RuntimeError as e:
        return f"❌ {str(e)}"
    except Exception as e:
        logger.error(f"调整图像设置失败: {e}")
        return f"❌ 调整图像设置失败: {str(e)}"


# @mcp.resource("camera://status")
# def get_camera_status() -> str:
#     """获取摄像头状态信息"""
#     logger.info(f"🔧 [RESOURCE] get_camera_status() 被调用")
    
#     try:
#         if camera_manager.is_initialized and camera_manager.camera_instance:
#             position_info = camera_manager.get_position_info()
#             return json.dumps({
#                 "status": "connected",
#                 "ip": camera_manager.camera_instance.ip,
# @mcp.resource("camera://status")
# def get_camera_status() -> str:
#     """获取摄像头状态信息"""
#     logger.info(f"🔧 [RESOURCE] get_camera_status() 被调用")
    
#     try:
#         if camera_manager.is_initialized and camera_manager.camera_instance:
#             position_info = camera_manager.get_position_info()
#             return json.dumps({
#                 "status": "connected",
#                 "ip": camera_manager.camera_instance.ip,
#                 "admin": camera_manager.camera_instance.admin,
#                 "initialized": camera_manager.is_initialized,
#                 "current_position": position_info['current_position'],
#                 "position_limits": {
#                     "min": position_info['min_limit'],
#                     "max": position_info['max_limit']
#                 },
#                 "remaining_movement": {
#                     "left": position_info['remaining_left'],
#                     "right": position_info['remaining_right']
#                 },
#                 "message": "摄像头已连接并初始化"
#             }, ensure_ascii=False, indent=2)
#         else:
#             return json.dumps({
#                 "status": "disconnected", 
#                 "initialized": False,
#                 "message": "摄像头未连接或未初始化"
#             }, ensure_ascii=False, indent=2)
#     except Exception as e:
#         logger.error(f"获取摄像头状态失败: {e}")
#         return json.dumps({
#             "status": "error",
#             "message": f"获取状态失败: {str(e)}"
#         }, ensure_ascii=False, indent=2)
#                 "admin": camera_manager.camera_instance.admin,
#                 "initialized": camera_manager.is_initialized,
#                 "current_position": position_info['current_position'],
#                 "position_limits": {
#                     "min": position_info['min_limit'],
#                     "max": position_info['max_limit']
#                 },
#                 "remaining_movement": {
#                     "left": position_info['remaining_left'],
#                     "right": position_info['remaining_right']
#                 },
#                 "message": "摄像头已连接并初始化"
#             }, ensure_ascii=False, indent=2)
#         else:
#             return json.dumps({
#                 "status": "disconnected", 
#                 "initialized": False,
#                 "message": "摄像头未连接或未初始化"
#             }, ensure_ascii=False, indent=2)
#     except Exception as e:
#         logger.error(f"获取摄像头状态失败: {e}")
#         return json.dumps({
#             "status": "error",
#             "message": f"获取状态失败: {str(e)}"
#         }, ensure_ascii=False, indent=2)


@mcp.prompt()
def camera_control_prompt(action: str = "move", **kwargs) -> str:
    """
    生成摄像头控制提示词
    
    Args:
        action: 操作类型 (move, capture, zoom, preset)
        **kwargs: 其他参数
    """
    if action == "move":
        return f"请控制摄像头转动。可用参数: pan_angle (水平转动角度，正数右转，负数左转)"
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
    logger.info(f"🚀 [SERVER] 摄像头配置: IP={camera_manager.camera_config['ip']}, 用户={camera_manager.camera_config['admin']}")
    logger.info("=" * 80)
    
    # 自动初始化摄像头
    logger.info("🚀 [SERVER] 正在自动初始化摄像头...")
    if camera_manager.initialize_camera():
        logger.info("🚀 [SERVER] ✅ 摄像头自动初始化成功，服务器就绪")
    else:
        logger.error("🚀 [SERVER] ❌ 摄像头自动初始化失败，服务器将无法正常工作")
        logger.error("🚀 [SERVER] 请检查摄像头连接参数和网络连接")
        # 不退出服务器，让用户能看到错误信息
    
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