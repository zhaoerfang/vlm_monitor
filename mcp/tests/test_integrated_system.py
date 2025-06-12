#!/usr/bin/env python3
"""
集成系统测试脚本
测试 VLM 客户端与摄像头控制的集成功能
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root / "mcp" / "src"))

from monitor.vlm.vlm_client import DashScopeVLMClient
from camera_mcp.cores.camera_inference_service import CameraInferenceService

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IntegratedSystemTester:
    """集成系统测试器"""
    
    def __init__(self):
        self.vlm_client = None
        self.camera_service = None
        
    async def setup(self):
        """设置测试环境"""
        try:
            # 初始化 VLM 客户端
            self.vlm_client = DashScopeVLMClient()
            logger.info("✅ VLM 客户端初始化成功")
            
            # 初始化摄像头推理服务
            self.camera_service = CameraInferenceService()
            if await self.camera_service.start_service():
                logger.info("✅ 摄像头推理服务启动成功")
            else:
                logger.warning("⚠️ 摄像头推理服务启动失败，将跳过相关测试")
                
        except Exception as e:
            logger.error(f"❌ 设置测试环境失败: {e}")
            raise
    
    async def cleanup(self):
        """清理测试环境"""
        try:
            if self.camera_service:
                await self.camera_service.stop_service()
                logger.info("✅ 摄像头推理服务已停止")
        except Exception as e:
            logger.error(f"❌ 清理测试环境失败: {e}")
    
    async def test_vlm_basic_analysis(self):
        """测试基本的 VLM 图像分析"""
        logger.info("🧪 测试基本 VLM 图像分析...")
        
        # 创建一个测试图像路径（这里假设有测试图像）
        test_image_path = project_root / "mcp" / "img" / "test_image.jpg"
        
        if not test_image_path.exists():
            logger.warning(f"⚠️ 测试图像不存在: {test_image_path}，跳过此测试")
            return
        
        try:
            result = await self.vlm_client.analyze_image_async(
                str(test_image_path),
                user_question="请描述这张图像的内容"
            )
            
            if result:
                logger.info(f"✅ VLM 分析成功，结果长度: {len(result)} 字符")
                logger.info(f"分析结果预览: {result[:200]}...")
            else:
                logger.error("❌ VLM 分析失败")
                
        except Exception as e:
            logger.error(f"❌ VLM 分析测试失败: {e}")
    
    async def test_camera_control_only(self):
        """测试纯摄像头控制功能"""
        if not self.camera_service or not self.camera_service.is_connected:
            logger.warning("⚠️ 摄像头服务未连接，跳过摄像头控制测试")
            return
            
        logger.info("🧪 测试摄像头控制功能...")
        
        try:
            # 测试获取摄像头位置
            result = await self.camera_service.simple_control("获取摄像头当前位置")
            logger.info(f"✅ 摄像头位置查询成功: {result}")
            
            # 测试摄像头转动
            result = await self.camera_service.simple_control("向左转动10度")
            logger.info(f"✅ 摄像头转动控制成功: {result}")
            
            # 等待一下
            await asyncio.sleep(2)
            
            # 测试回到中心位置
            result = await self.camera_service.simple_control("重置摄像头到中心位置")
            logger.info(f"✅ 摄像头重置成功: {result}")
            
        except Exception as e:
            logger.error(f"❌ 摄像头控制测试失败: {e}")
    
    async def test_integrated_analysis_and_control(self):
        """测试集成的图像分析和摄像头控制"""
        if not self.camera_service or not self.camera_service.is_connected:
            logger.warning("⚠️ 摄像头服务未连接，跳过集成测试")
            return
            
        logger.info("🧪 测试集成的图像分析和摄像头控制...")
        
        # 创建一个测试图像路径
        test_image_path = project_root / "mcp" / "img" / "test_image.jpg"
        
        if not test_image_path.exists():
            logger.warning(f"⚠️ 测试图像不存在: {test_image_path}，跳过此测试")
            return
        
        try:
            # 测试带摄像头控制的图像分析
            result = await self.vlm_client.analyze_image_async(
                str(test_image_path),
                user_question="如果图像中有人物在右侧，请向右转动摄像头20度",
                enable_camera_control=True
            )
            
            if result:
                logger.info(f"✅ 集成分析成功，结果长度: {len(result)} 字符")
                logger.info(f"分析结果预览: {result[:300]}...")
            else:
                logger.error("❌ 集成分析失败")
                
        except Exception as e:
            logger.error(f"❌ 集成分析测试失败: {e}")
    
    async def test_camera_inference_service_direct(self):
        """直接测试摄像头推理服务"""
        if not self.camera_service or not self.camera_service.is_connected:
            logger.warning("⚠️ 摄像头服务未连接，跳过推理服务测试")
            return
            
        logger.info("🧪 测试摄像头推理服务...")
        
        # 创建一个测试图像路径
        test_image_path = project_root / "mcp" / "img" / "test_image.jpg"
        
        if not test_image_path.exists():
            logger.warning(f"⚠️ 测试图像不存在: {test_image_path}，跳过此测试")
            return
        
        try:
            # 测试图像分析和控制
            result = await self.camera_service.analyze_and_control(
                str(test_image_path),
                "请分析图像内容，如果需要更好的视角，请调整摄像头位置"
            )
            
            logger.info(f"✅ 摄像头推理服务测试成功")
            logger.info(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
            
        except Exception as e:
            logger.error(f"❌ 摄像头推理服务测试失败: {e}")
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始集成系统测试")
        logger.info("=" * 60)
        
        try:
            await self.setup()
            
            # 运行各项测试
            await self.test_vlm_basic_analysis()
            await asyncio.sleep(1)
            
            await self.test_camera_control_only()
            await asyncio.sleep(1)
            
            await self.test_camera_inference_service_direct()
            await asyncio.sleep(1)
            
            await self.test_integrated_analysis_and_control()
            
            logger.info("=" * 60)
            logger.info("✅ 所有测试完成")
            
        except Exception as e:
            logger.error(f"❌ 测试过程中出现错误: {e}")
            
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    tester = IntegratedSystemTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main()) 