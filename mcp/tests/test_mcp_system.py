#!/usr/bin/env python3
"""
MCP 摄像头控制系统测试脚本
用于验证 MCP Server 和 Client 的基本功能
"""

import asyncio
import json
import logging
import sys
import os
from typing import Dict, Any

# 添加 src 目录到路径
src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')
sys.path.append(src_path)

from camera_mcp.camera_client import CameraClient

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPSystemTester:
    """MCP 系统测试器"""
    
    def __init__(self):
        self.client = CameraClient()
        self.test_results = []
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🧪 开始 MCP 摄像头控制系统测试")
        print("=" * 50)
        
        # 测试连接
        await self.test_connection()
        
        if self.client.mcp_session:
            # 测试工具列表
            await self.test_list_tools()
            
            # 测试摄像头状态
            await self.test_camera_status()
            
            # 测试基本工具调用
            await self.test_basic_tool_calls()
            
            # 测试 AI 控制（如果配置了 OpenAI）
            await self.test_ai_control()
            
            # 断开连接
            await self.client.disconnect_from_mcp_server()
        
        # 显示测试结果
        self.show_test_results()
    
    async def test_connection(self):
        """测试 MCP 连接"""
        print("\n📡 测试 MCP Server 连接...")
        try:
            success = await self.client.connect_to_mcp_server()
            if success:
                self.test_results.append(("MCP 连接", "✅ 成功"))
                print("✅ MCP Server 连接成功")
            else:
                self.test_results.append(("MCP 连接", "❌ 失败"))
                print("❌ MCP Server 连接失败")
        except Exception as e:
            self.test_results.append(("MCP 连接", f"❌ 异常: {e}"))
            print(f"❌ 连接异常: {e}")
    
    async def test_list_tools(self):
        """测试工具列表"""
        print("\n🔧 测试工具列表...")
        try:
            tools = await self.client.list_available_tools()
            if tools:
                self.test_results.append(("工具列表", f"✅ 成功 ({len(tools)} 个工具)"))
                print(f"✅ 发现 {len(tools)} 个可用工具:")
                for tool in tools:
                    print(f"  - {tool.name}: {tool.description}")
            else:
                self.test_results.append(("工具列表", "⚠️ 无工具"))
                print("⚠️ 未发现可用工具")
        except Exception as e:
            self.test_results.append(("工具列表", f"❌ 异常: {e}"))
            print(f"❌ 获取工具列表失败: {e}")
    
    async def test_camera_status(self):
        """测试摄像头状态"""
        print("\n📊 测试摄像头状态...")
        try:
            status = await self.client.get_camera_status()
            self.test_results.append(("摄像头状态", "✅ 成功"))
            print(f"✅ 摄像头状态: {status}")
        except Exception as e:
            self.test_results.append(("摄像头状态", f"❌ 异常: {e}"))
            print(f"❌ 获取摄像头状态失败: {e}")
    
    async def test_basic_tool_calls(self):
        """测试基本工具调用"""
        print("\n🔧 测试基本工具调用...")
        
        # 测试摄像头设置
        await self.test_tool_call(
            "setup_camera",
            {"ip": "192.168.1.64", "admin": "admin", "password": "pw4hkcamera"},
            "摄像头设置"
        )
        
        # 测试摄像头转动（小幅度测试）
        await self.test_tool_call(
            "pan_tilt_move",
            {"pan_speed": 10, "tilt_speed": 0, "duration": 0.5},
            "摄像头转动"
        )
        
        # 测试变焦（小幅度测试）
        await self.test_tool_call(
            "zoom_control",
            {"zoom_level": 1, "duration": 0.5},
            "摄像头变焦"
        )
        
        # 测试图像设置
        await self.test_tool_call(
            "adjust_image_settings",
            {"brightness": 50, "contrast": 50, "saturation": 50},
            "图像设置"
        )
    
    async def test_tool_call(self, tool_name: str, arguments: Dict[str, Any], test_name: str):
        """测试单个工具调用"""
        try:
            result = await self.client.call_camera_tool(tool_name, arguments)
            self.test_results.append((test_name, "✅ 成功"))
            print(f"✅ {test_name}: {result}")
        except Exception as e:
            self.test_results.append((test_name, f"❌ 异常: {e}"))
            print(f"❌ {test_name} 失败: {e}")
    
    async def test_ai_control(self):
        """测试 AI 控制"""
        print("\n🤖 测试 AI 智能控制...")
        
        # 检查是否配置了有效的 OpenAI API
        mcp_config = self.client.config.get('mcp_model', {})
        api_key = mcp_config.get('api_key', '')
        
        if not api_key or api_key == 'your-api-key':
            self.test_results.append(("AI 控制", "⚠️ 跳过 (未配置 API)"))
            print("⚠️ 跳过 AI 控制测试 (未配置 OpenAI API)")
            return
        
        # 测试简单的 AI 指令
        test_instructions = [
            "停止摄像头转动",
            "调整亮度到60"
        ]
        
        for instruction in test_instructions:
            try:
                result = await self.client.ai_control_camera(instruction)
                self.test_results.append((f"AI: {instruction}", "✅ 成功"))
                print(f"✅ AI 指令 '{instruction}': {result}")
            except Exception as e:
                self.test_results.append((f"AI: {instruction}", f"❌ 异常: {e}"))
                print(f"❌ AI 指令 '{instruction}' 失败: {e}")
    
    def show_test_results(self):
        """显示测试结果"""
        print("\n" + "=" * 50)
        print("📋 测试结果汇总")
        print("=" * 50)
        
        success_count = 0
        total_count = len(self.test_results)
        
        for test_name, result in self.test_results:
            print(f"{test_name:<20} {result}")
            if result.startswith("✅"):
                success_count += 1
        
        print("-" * 50)
        print(f"总计: {success_count}/{total_count} 项测试通过")
        
        if success_count == total_count:
            print("🎉 所有测试通过！系统运行正常。")
        elif success_count > 0:
            print("⚠️ 部分测试通过，请检查失败项目。")
        else:
            print("❌ 所有测试失败，请检查系统配置。")


async def main():
    """主函数"""
    tester = MCPSystemTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 测试被用户中断")
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        sys.exit(1) 