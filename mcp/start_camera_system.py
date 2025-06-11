#!/usr/bin/env python3
"""
摄像头控制 MCP 系统启动脚本 (兼容性脚本)
建议使用新的 CLI 接口: camera-mcp
"""

import sys
import os

# 添加 src 目录到路径
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.append(src_path)

from camera_mcp.cli import cli_main

def main():
    """主函数 - 重定向到新的 CLI"""
    print("⚠️  此脚本已弃用，建议使用新的 CLI 接口:")
    print("   camera-mcp server")
    print("   camera-mcp client") 
    print("   camera-mcp test")
    print()
    
    # 兼容旧的调用方式
    if len(sys.argv) >= 2:
        command = sys.argv[1].lower()
        if command in ['server', 'client', 'test']:
            # 修改 sys.argv 以适应新的 CLI
            sys.argv = ['camera-mcp', command] + sys.argv[2:]
            cli_main()
            return
    
    print("使用方法:")
    print("  python start_camera_system.py server")
    print("  python start_camera_system.py client")
    print("  python start_camera_system.py test")

if __name__ == "__main__":
    main() 