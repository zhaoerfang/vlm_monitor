"""
Camera MCP - 基于 Model Context Protocol 的摄像头控制系统

这个包提供了一个完整的摄像头控制解决方案，包括：
- MCP Server: 提供摄像头控制工具
- MCP Client: 支持 AI 智能控制的客户端
- 工具函数: 摄像头操作的底层实现
"""

__version__ = "0.1.0"
__author__ = "VLM Monitor Team"
__email__ = "admin@example.com"

# 延迟导入，避免在包导入时就加载所有模块
from .utils.Camera import Camera

__all__ = [
    "Camera",
]

# 提供便捷的导入函数，但不在包级别导入
def get_server_main():
    """获取 server main 函数"""
    from .cores.camera_server import main
    return main

def get_client_main():
    """获取 client main 函数"""
    from .cores.camera_client import main
    return main

def get_camera_client():
    """获取 CameraClient 类"""
    from .cores.camera_client import CameraClient
    return CameraClient 