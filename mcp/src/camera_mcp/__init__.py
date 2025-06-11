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

from .camera_server import main as run_server
from .camera_client import CameraClient, main as run_client
from .utils.Camera import Camera

__all__ = [
    "run_server",
    "run_client", 
    "CameraClient",
    "Camera",
] 