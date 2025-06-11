#!/usr/bin/env python3
"""
测试摄像头实例创建和日志输出
"""

import asyncio
import sys
import os

# 添加项目路径到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from camera_mcp.cores.camera_client import CameraClient


async def test_camera_logging():
    """测试摄像头日志输出"""
    print("🧪 [TEST] 开始测试摄像头日志输出...")
    print("=" * 80)
    
    # 创建客户端
    client = CameraClient()
    
    try:
        # 连接到服务器
        print("🧪 [TEST] 步骤 1: 连接到 MCP server...")
        if await client.connect_to_mcp_server():
            print("🧪 [TEST] ✅ 连接成功")
            
            # 测试获取摄像头位置（这会触发摄像头实例创建）
            print("\n🧪 [TEST] 步骤 2: 调用 get_camera_position...")
            result = await client.call_camera_tool("get_camera_position", {})
            print(f"🧪 [TEST] 结果: {result}")
            
            # 再次调用，看是否会重新创建实例
            print("\n🧪 [TEST] 步骤 3: 再次调用 get_camera_position...")
            result = await client.call_camera_tool("get_camera_position", {})
            print(f"🧪 [TEST] 结果: {result}")
            
            # 测试拍照功能
            print("\n🧪 [TEST] 步骤 4: 调用 capture_image...")
            result = await client.call_camera_tool("capture_image", {"img_name": "test_image"})
            print(f"🧪 [TEST] 结果: {result}")
            
        else:
            print("🧪 [TEST] ❌ 连接失败")
            
    except Exception as e:
        print(f"🧪 [TEST] ❌ 测试过程中出错: {e}")
        
    finally:
        # 断开连接
        print("\n🧪 [TEST] 步骤 5: 断开连接...")
        await client.disconnect_from_mcp_server()
        print("🧪 [TEST] ✅ 测试完成")


if __name__ == "__main__":
    asyncio.run(test_camera_logging()) 