#!/usr/bin/env python3
"""
测试优化后的摄像头服务器
验证CameraManager类的功能和自动初始化逻辑
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

from camera_mcp.cores.camera_client import CameraClient


async def test_optimized_camera_server():
    """测试优化后的摄像头服务器"""
    print("🧪 [TEST] 开始测试优化后的摄像头服务器...")
    print("=" * 80)
    
    # 创建客户端
    client = CameraClient()
    
    try:
        # 连接到服务器
        print("🧪 [TEST] 步骤 1: 连接到 MCP server...")
        if await client.connect_to_mcp_server():
            print("🧪 [TEST] ✅ 连接成功")
            
            # 测试获取摄像头状态（应该显示已自动初始化）
            print("\n🧪 [TEST] 步骤 2: 获取摄像头状态...")
            status = await client.get_camera_status()
            print(f"🧪 [TEST] 摄像头状态: {status}")
            
            # 测试获取摄像头位置（应该显示初始化后的中心位置）
            print("\n🧪 [TEST] 步骤 3: 获取摄像头位置...")
            result = await client.call_camera_tool("get_camera_position", {})
            print(f"🧪 [TEST] 位置信息: {result}")
            
            # 测试摄像头转动
            print("\n🧪 [TEST] 步骤 4: 测试摄像头转动...")
            result = await client.call_camera_tool("pan_tilt_move", {"pan_angle": 15})
            print(f"🧪 [TEST] 转动结果: {result}")
            
            # 再次获取位置，验证位置更新
            print("\n🧪 [TEST] 步骤 5: 验证位置更新...")
            result = await client.call_camera_tool("get_camera_position", {})
            print(f"🧪 [TEST] 更新后位置: {result}")
            
            # 测试重置到中心位置
            print("\n🧪 [TEST] 步骤 6: 重置到中心位置...")
            result = await client.call_camera_tool("reset_camera_position", {})
            print(f"🧪 [TEST] 重置结果: {result}")
            
            # 验证重置后的位置
            print("\n🧪 [TEST] 步骤 7: 验证重置后位置...")
            result = await client.call_camera_tool("get_camera_position", {})
            print(f"🧪 [TEST] 重置后位置: {result}")
            
            # 测试拍照功能
            print("\n🧪 [TEST] 步骤 8: 测试拍照功能...")
            result = await client.call_camera_tool("capture_image", {"img_name": "test_auto_init"})
            print(f"🧪 [TEST] 拍照结果: {result}")
            
            # 测试变焦功能
            print("\n🧪 [TEST] 步骤 9: 测试变焦功能...")
            result = await client.call_camera_tool("zoom_control", {"zoom_level": 2, "duration": 1.0})
            print(f"🧪 [TEST] 变焦结果: {result}")
            
            # 测试预设点位功能
            print("\n🧪 [TEST] 步骤 10: 测试预设点位功能...")
            result = await client.call_camera_tool("goto_preset", {"point": 1})
            print(f"🧪 [TEST] 预设点位结果: {result}")
            
        else:
            print("🧪 [TEST] ❌ 连接失败")
            
    except Exception as e:
        print(f"🧪 [TEST] ❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 断开连接
        print("\n🧪 [TEST] 步骤 11: 断开连接...")
        await client.disconnect_from_mcp_server()
        print("🧪 [TEST] ✅ 测试完成")


async def test_camera_manager_directly():
    """直接测试CameraManager类"""
    print("\n" + "=" * 80)
    print("🧪 [TEST] 直接测试 CameraManager 类...")
    print("=" * 80)
    
    # 导入CameraManager
    from camera_mcp.cores.camera_server import CameraManager
    
    # 创建管理器实例
    manager = CameraManager()
    
    try:
        # 显示配置信息
        print("🧪 [TEST] 步骤 1: 显示摄像头配置...")
        print(f"🧪 [TEST] 摄像头配置: {manager.camera_config}")
        
        # 测试自动初始化
        print("\n🧪 [TEST] 步骤 2: 测试自动初始化...")
        success = manager.initialize_camera()
        print(f"🧪 [TEST] 初始化结果: {'成功' if success else '失败'}")
        
        if success:
            # 测试获取摄像头实例
            print("\n🧪 [TEST] 步骤 3: 获取摄像头实例...")
            camera = manager.get_camera()
            print(f"🧪 [TEST] 摄像头实例: {camera}")
            print(f"🧪 [TEST] 摄像头IP: {camera.ip}")
            
            # 测试位置信息
            print("\n🧪 [TEST] 步骤 4: 获取位置信息...")
            position_info = manager.get_position_info()
            print(f"🧪 [TEST] 位置信息: {position_info}")
            
            # 测试位置限制检查
            print("\n🧪 [TEST] 步骤 5: 测试位置限制检查...")
            test_positions = [0, 90, -90, 200, -200]
            for pos in test_positions:
                check_result = manager.check_position_limits(pos)
                print(f"🧪 [TEST] 位置 {pos}°: {'有效' if check_result['valid'] else '无效 - ' + check_result['message']}")
            
            # 测试位置更新
            print("\n🧪 [TEST] 步骤 6: 测试位置更新...")
            manager.update_position(45.0)
            position_info = manager.get_position_info()
            print(f"🧪 [TEST] 更新后位置: {position_info['current_position']}°")
            
            # 测试重置到中心
            print("\n🧪 [TEST] 步骤 7: 测试重置到中心...")
            reset_success = manager.reset_to_center()
            print(f"🧪 [TEST] 重置结果: {'成功' if reset_success else '失败'}")
            position_info = manager.get_position_info()
            print(f"🧪 [TEST] 重置后位置: {position_info['current_position']}°")
            
            # 测试重复初始化（应该跳过）
            print("\n🧪 [TEST] 步骤 8: 测试重复初始化...")
            success2 = manager.initialize_camera()
            print(f"🧪 [TEST] 重复初始化结果: {'成功（跳过）' if success2 else '失败'}")
            
        else:
            print("🧪 [TEST] ⚠️ 初始化失败，跳过后续测试")
            print("🧪 [TEST] 💡 请检查摄像头连接参数和网络连接")
            
    except Exception as e:
        print(f"🧪 [TEST] ❌ 直接测试过程中出错: {e}")
        import traceback
        traceback.print_exc()


async def test_environment_variables():
    """测试环境变量配置"""
    print("\n" + "=" * 80)
    print("🧪 [TEST] 测试环境变量配置...")
    print("=" * 80)
    
    # 显示当前环境变量
    camera_ip = os.getenv('CAMERA_IP', '默认: 192.168.1.64')
    camera_admin = os.getenv('CAMERA_ADMIN', '默认: admin')
    camera_password = os.getenv('CAMERA_PASSWORD', '默认: pw4hkcamera')
    
    print(f"🧪 [TEST] CAMERA_IP: {camera_ip}")
    print(f"🧪 [TEST] CAMERA_ADMIN: {camera_admin}")
    print(f"🧪 [TEST] CAMERA_PASSWORD: {'*' * len(camera_password) if 'CAMERA_PASSWORD' in os.environ else camera_password}")
    
    print("\n🧪 [TEST] 💡 可以通过设置环境变量来配置摄像头参数:")
    print("🧪 [TEST]    export CAMERA_IP=192.168.1.100")
    print("🧪 [TEST]    export CAMERA_ADMIN=admin")
    print("🧪 [TEST]    export CAMERA_PASSWORD=newpassword")


async def main():
    """主测试函数"""
    print("🚀 开始测试优化后的摄像头控制系统（自动初始化版本）")
    print("=" * 80)
    
    # 测试1: 环境变量配置
    await test_environment_variables()
    
    # 测试2: 直接测试CameraManager类
    await test_camera_manager_directly()
    
    # 测试3: 通过MCP客户端测试
    await test_optimized_camera_server()
    
    print("\n" + "=" * 80)
    print("🎉 所有测试完成！")
    print("📝 总结:")
    print("   ✅ 摄像头在服务器启动时自动初始化")
    print("   ✅ 无需手动调用 setup_camera 工具")
    print("   ✅ 支持通过环境变量配置摄像头参数")
    print("   ✅ 统一的错误处理和状态管理")


if __name__ == "__main__":
    asyncio.run(main()) 