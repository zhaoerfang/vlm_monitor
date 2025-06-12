#!/usr/bin/env python3
"""
摄像头控制集成示例
展示如何使用 VLM 客户端的摄像头控制功能
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "mcp" / "src"))

from monitor.vlm.vlm_client import DashScopeVLMClient
from camera_mcp.cores.camera_inference_service import CameraInferenceService

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def example_basic_camera_control():
    """示例1: 基本摄像头控制"""
    print("=" * 60)
    print("示例1: 基本摄像头控制")
    print("=" * 60)
    
    service = CameraInferenceService()
    
    try:
        # 启动服务
        if await service.start_service():
            print("✅ 摄像头控制服务启动成功")
            
            # 基本控制命令
            commands = [
                "获取摄像头当前位置",
                "向左转动15度",
                "向右转动30度", 
                "重置摄像头到中心位置",
                "拍一张照片"
            ]
            
            for command in commands:
                print(f"\n🎮 执行命令: {command}")
                result = await service.simple_control(command)
                print(f"📋 结果: {result}")
                await asyncio.sleep(1)
                
        else:
            print("❌ 摄像头控制服务启动失败")
            
    except Exception as e:
        print(f"❌ 示例执行失败: {e}")
        
    finally:
        await service.stop_service()


async def example_image_analysis_with_camera_control():
    """示例2: 图像分析结合摄像头控制"""
    print("=" * 60)
    print("示例2: 图像分析结合摄像头控制")
    print("=" * 60)
    
    # 创建测试图像（如果不存在）
    test_image_path = project_root / "mcp" / "img" / "test_image.jpg"
    test_image_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not test_image_path.exists():
        print(f"⚠️ 测试图像不存在: {test_image_path}")
        print("请在该路径放置一张测试图像，或使用摄像头拍摄一张图像")
        return
    
    service = CameraInferenceService()
    
    try:
        if await service.start_service():
            print("✅ 摄像头推理服务启动成功")
            
            # 测试场景
            scenarios = [
                "请分析这张图像，如果图像模糊或角度不好，请调整摄像头位置",
                "如果图像中有人物，请将摄像头转向人物方向",
                "如果图像太暗，请调整摄像头设置或位置",
                "请拍摄一张新的照片用于对比分析"
            ]
            
            for i, scenario in enumerate(scenarios, 1):
                print(f"\n🧪 场景 {i}: {scenario}")
                
                result = await service.analyze_and_control(
                    str(test_image_path),
                    scenario
                )
                
                print(f"📊 分析结果:")
                print(f"  - 图像路径: {result.get('image_path', 'N/A')}")
                print(f"  - 用户问题: {result.get('user_question', 'N/A')}")
                print(f"  - 是否执行控制: {result.get('control_executed', False)}")
                if result.get('control_result'):
                    print(f"  - 控制结果: {result.get('control_result')}")
                if result.get('error'):
                    print(f"  - 错误: {result.get('error')}")
                
                await asyncio.sleep(2)
                
        else:
            print("❌ 摄像头推理服务启动失败")
            
    except Exception as e:
        print(f"❌ 示例执行失败: {e}")
        
    finally:
        await service.stop_service()


async def example_vlm_with_camera_integration():
    """示例3: VLM 客户端集成摄像头控制"""
    print("=" * 60)
    print("示例3: VLM 客户端集成摄像头控制")
    print("=" * 60)
    
    test_image_path = project_root / "mcp" / "img" / "test_image.jpg"
    
    if not test_image_path.exists():
        print(f"⚠️ 测试图像不存在: {test_image_path}")
        print("请在该路径放置一张测试图像")
        return
    
    try:
        # 创建 VLM 客户端
        vlm_client = DashScopeVLMClient()
        print("✅ VLM 客户端初始化成功")
        
        # 测试不同的分析和控制场景
        scenarios = [
            {
                "question": "请分析这张图像的内容，并描述主要物体的位置",
                "enable_camera": False,
                "description": "纯图像分析（不控制摄像头）"
            },
            {
                "question": "如果图像中的主要物体在左侧，请向左转动摄像头20度以获得更好的视角",
                "enable_camera": True,
                "description": "图像分析 + 摄像头控制"
            },
            {
                "question": "请评估当前图像质量，如果需要改善，请调整摄像头位置或设置",
                "enable_camera": True,
                "description": "智能图像质量评估和摄像头调整"
            }
        ]
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n🎯 场景 {i}: {scenario['description']}")
            print(f"📝 问题: {scenario['question']}")
            print(f"🎮 摄像头控制: {'启用' if scenario['enable_camera'] else '禁用'}")
            
            result = await vlm_client.analyze_image_async(
                str(test_image_path),
                user_question=scenario['question'],
                enable_camera_control=scenario['enable_camera']
            )
            
            if result:
                print(f"✅ 分析成功，结果长度: {len(result)} 字符")
                print(f"📋 结果预览: {result[:300]}...")
                if len(result) > 300:
                    print("    ...")
            else:
                print("❌ 分析失败")
            
            await asyncio.sleep(2)
            
    except Exception as e:
        print(f"❌ 示例执行失败: {e}")


async def example_interactive_camera_control():
    """示例4: 交互式摄像头控制"""
    print("=" * 60)
    print("示例4: 交互式摄像头控制")
    print("=" * 60)
    
    service = CameraInferenceService()
    
    try:
        if await service.start_service():
            print("✅ 摄像头控制服务启动成功")
            print("\n🎮 交互式摄像头控制模式")
            print("输入命令来控制摄像头，输入 'quit' 退出")
            print("示例命令:")
            print("  - 向左转动30度")
            print("  - 拍一张照片")
            print("  - 获取当前位置")
            print("  - 重置到中心位置")
            print("-" * 40)
            
            while True:
                try:
                    command = input("\n🎯 请输入命令: ").strip()
                    
                    if command.lower() in ['quit', 'exit', 'q']:
                        print("👋 退出交互模式")
                        break
                    
                    if not command:
                        continue
                    
                    print(f"🔄 执行中...")
                    result = await service.simple_control(command)
                    print(f"📋 结果: {result}")
                    
                except KeyboardInterrupt:
                    print("\n👋 用户中断，退出交互模式")
                    break
                except Exception as e:
                    print(f"❌ 命令执行失败: {e}")
                    
        else:
            print("❌ 摄像头控制服务启动失败")
            
    except Exception as e:
        print(f"❌ 交互模式启动失败: {e}")
        
    finally:
        await service.stop_service()


async def main():
    """主函数 - 运行所有示例"""
    print("🎥 摄像头控制集成示例")
    print("基于 MCP 的智能摄像头控制系统")
    print("=" * 60)
    
    examples = [
        ("基本摄像头控制", example_basic_camera_control),
        ("图像分析结合摄像头控制", example_image_analysis_with_camera_control),
        ("VLM 客户端集成摄像头控制", example_vlm_with_camera_integration),
        ("交互式摄像头控制", example_interactive_camera_control)
    ]
    
    print("请选择要运行的示例:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    print(f"  {len(examples) + 1}. 运行所有示例")
    
    try:
        choice = input(f"\n请输入选择 (1-{len(examples) + 1}): ").strip()
        
        if choice == str(len(examples) + 1):
            # 运行所有示例（除了交互式）
            for name, func in examples[:-1]:  # 排除交互式示例
                print(f"\n🚀 运行示例: {name}")
                await func()
                await asyncio.sleep(1)
        elif choice.isdigit() and 1 <= int(choice) <= len(examples):
            idx = int(choice) - 1
            name, func = examples[idx]
            print(f"\n🚀 运行示例: {name}")
            await func()
        else:
            print("❌ 无效选择")
            
    except KeyboardInterrupt:
        print("\n👋 用户中断")
    except Exception as e:
        print(f"❌ 运行示例时出错: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 