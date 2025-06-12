#!/usr/bin/env python3
"""
Camera MCP CLI - 命令行接口
提供统一的命令行入口，可以启动 server、client 或运行测试
"""

import asyncio
import sys
import os
import argparse
import logging
from typing import Optional

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def print_banner():
    """打印系统横幅"""
    banner = """
🎥 Camera MCP - 摄像头控制系统
===============================
基于 Model Context Protocol 的智能摄像头控制系统
支持 AI 自然语言控制和直接工具调用
"""
    print(banner)


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="Camera MCP - 摄像头控制系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  camera-mcp server              # 启动 MCP Server
  camera-mcp client              # 启动 MCP Client
  camera-mcp inference_service   # 启动异步MCP推理服务
  camera-mcp test                # 运行系统测试
  camera-mcp --version           # 显示版本信息
        """
    )
    
    parser.add_argument(
        "command",
        choices=["server", "client", "test", "inference_service"],
        help="要执行的命令"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="配置文件路径 (默认: ./config.json)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别 (默认: INFO)"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Camera MCP 0.1.0"
    )
    
    return parser


def run_server(config_path: Optional[str] = None):
    """启动 MCP Server"""
    print("🚀 启动 MCP Server...")
    print("按 Ctrl+C 停止服务器")
    print("-" * 40)
    
    try:
        from .cores.camera_server import main as server_main
        server_main()
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}")
        sys.exit(1)


async def run_client(config_path: Optional[str] = None):
    """启动 MCP Client"""
    print("🎮 启动 MCP Client...")
    print("正在连接到 MCP Server...")
    print("-" * 40)
    
    try:
        from .cores.camera_client import main as client_main
        await client_main()
    except KeyboardInterrupt:
        print("\n🛑 客户端已停止")
    except Exception as e:
        print(f"❌ 客户端启动失败: {e}")
        print("请确保 MCP Server 正在运行")
        sys.exit(1)


async def run_inference_service(config_path: Optional[str] = None):
    """启动异步MCP推理服务"""
    print("🤖 启动异步MCP推理服务...")
    print("正在初始化推理服务...")
    print("-" * 40)
    
    try:
        from .cores.camera_inference_service import main as inference_main
        await inference_main()
    except KeyboardInterrupt:
        print("\n🛑 推理服务已停止")
    except Exception as e:
        print(f"❌ 推理服务启动失败: {e}")
        print("请确保 MCP Server 正在运行")
        sys.exit(1)


async def run_test(config_path: Optional[str] = None):
    """运行系统测试"""
    print("🧪 运行系统测试...")
    print("-" * 40)
    
    try:
        # 导入测试模块
        test_module_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            'tests', 
            'test_mcp_system.py'
        )
        
        if os.path.exists(test_module_path):
            sys.path.append(os.path.dirname(test_module_path))
            from test_mcp_system import main as test_main
            await test_main()
        else:
            print(f"❌ 测试文件未找到: {test_module_path}")
            print("请确保测试文件存在")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ 测试运行失败: {e}")
        sys.exit(1)


def check_dependencies():
    """检查依赖是否安装"""
    required_modules = ['mcp', 'openai', 'requests', 'cv2']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print("❌ 缺少以下依赖模块:")
        for module in missing_modules:
            print(f"  - {module}")
        print("\n请运行以下命令安装依赖:")
        print("  uv sync")
        print("或")
        print("  pip install camera-mcp[dev]")
        sys.exit(1)


def check_config(config_path: Optional[str] = None):
    """检查配置文件"""
    if config_path is None:
        # 默认使用主项目根目录的配置文件
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.json')
    
    if not os.path.exists(config_path):
        print(f"⚠️ 未找到配置文件: {config_path}")
        print("请确保配置文件存在")
        return False
    
    try:
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 检查 mcp_model 配置
        mcp_config = config.get('mcp_model', {})
        api_key = mcp_config.get('api_key', '')
        
        if not api_key or api_key == 'your-api-key':
            print("⚠️ 未配置 MCP 模型 API 密钥")
            print("AI 功能将不可用，但基本功能仍可正常使用")
            print("请在配置文件中设置正确的 mcp_model.api_key")
        
        # 检查摄像头配置
        camera_config = config.get('camera', {})
        if not camera_config:
            print("⚠️ 未找到摄像头配置")
            print("请在配置文件中添加 camera 配置项")
        
        # 检查推理服务配置
        inference_config = config.get('camera_inference_service', {})
        if not inference_config:
            print("⚠️ 未找到推理服务配置")
            print("请在配置文件中添加 camera_inference_service 配置项")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置文件格式错误: {e}")
        return False


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 设置日志级别
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    print_banner()
    
    # 检查依赖和配置
    print("🔍 检查系统环境...")
    check_dependencies()
    check_config(args.config)
    print("✅ 环境检查完成\n")
    
    # 执行相应命令
    if args.command == 'server':
        run_server(args.config)
    elif args.command == 'client':
        # 对于异步命令，使用 asyncio.run
        asyncio.run(run_client(args.config))
    elif args.command == 'test':
        # 对于异步命令，使用 asyncio.run
        asyncio.run(run_test(args.config))
    elif args.command == 'inference_service':
        # 对于异步命令，使用 asyncio.run
        asyncio.run(run_inference_service(args.config))


def cli_main():
    """CLI 入口点"""
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 程序被用户中断")
    except Exception as e:
        print(f"❌ 程序运行错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli_main() 