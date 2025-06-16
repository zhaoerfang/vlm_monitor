#!/usr/bin/env python3
"""
用户问题优化功能测试脚本
测试并行推理、用户问题专用提示词和新的文件结构
"""

import os
import sys
import json
import time
import logging
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.monitor.vlm.vlm_client import DashScopeVLMClient
from src.monitor.vlm.user_question_manager import init_question_manager
from tools.tts_service import TTSService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UserQuestionOptimizationTester:
    def __init__(self):
        """初始化测试器"""
        self.vlm_client = DashScopeVLMClient()
        self.temp_dir = tempfile.mkdtemp(prefix="user_question_test_")
        logger.info(f"测试临时目录: {self.temp_dir}")
        
    def create_test_image(self) -> str:
        """创建测试图像文件"""
        # 使用项目中的测试图像，如果不存在则创建一个简单的图像
        test_image_path = project_root / "data" / "test_image.jpg"
        
        if test_image_path.exists():
            return str(test_image_path)
        
        # 如果没有测试图像，创建一个简单的图像
        try:
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
            
            # 创建一个640x360的测试图像
            img = Image.new('RGB', (640, 360), color='lightblue')
            draw = ImageDraw.Draw(img)
            
            # 绘制一些测试内容
            draw.rectangle([100, 100, 200, 200], fill='red', outline='black')
            draw.rectangle([300, 150, 400, 250], fill='green', outline='black')
            draw.text((50, 50), "Test Image for VLM", fill='black')
            draw.text((50, 300), "Two rectangles: red and green", fill='black')
            
            # 保存到临时目录
            test_image_path = Path(self.temp_dir) / "test_image.jpg"
            img.save(test_image_path)
            logger.info(f"创建测试图像: {test_image_path}")
            return str(test_image_path)
            
        except ImportError:
            logger.error("PIL库未安装，无法创建测试图像")
            return None
    
    def create_test_frame_details_dir(self, image_path: str) -> str:
        """创建测试的frame details目录结构"""
        # 创建frame details目录
        frame_name = f"frame_{int(time.time() * 1000):06d}"
        details_dir = Path(self.temp_dir) / f"{frame_name}_details"
        details_dir.mkdir(exist_ok=True)
        
        # 复制图像到details目录
        import shutil
        image_file = details_dir / "frame.jpg"
        shutil.copy2(image_path, image_file)
        
        # 创建image_details.json
        image_details = {
            'image_path': str(image_file),
            'creation_time': time.time(),
            'creation_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'frame_number': 1,
            'timestamp': time.time(),
            'timestamp_iso': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'relative_timestamp': 0.0,
            'image_dimensions': {
                'original_width': 640,
                'original_height': 360,
                'model_width': 640,
                'model_height': 360
            }
        }
        
        with open(details_dir / 'image_details.json', 'w', encoding='utf-8') as f:
            json.dump(image_details, f, ensure_ascii=False, indent=2)
        
        logger.info(f"创建测试frame details目录: {details_dir}")
        return str(image_file)
    
    async def test_vlm_analysis_without_user_question(self, image_path: str):
        """测试没有用户问题的VLM分析"""
        logger.info("🔍 测试1: VLM分析（无用户问题）")
        
        start_time = time.time()
        result = await self.vlm_client.analyze_image_async(
            image_path=image_path,
            user_question=None,
            enable_camera_control=False  # 禁用MCP控制以简化测试
        )
        duration = time.time() - start_time
        
        logger.info(f"✅ VLM分析完成，耗时: {duration:.2f}s")
        logger.info(f"结果长度: {len(result) if result else 0} 字符")
        
        if result:
            logger.info(f"结果预览: {result[:200]}...")
        
        return result
    
    async def test_user_question_analysis(self, image_path: str, user_question: str):
        """测试用户问题分析"""
        logger.info(f"🤔 测试2: 用户问题分析")
        logger.info(f"用户问题: {user_question}")
        
        start_time = time.time()
        result = await self.vlm_client.analyze_image_async(
            image_path=image_path,
            user_question=user_question,
            enable_camera_control=False  # 禁用MCP控制以简化测试
        )
        duration = time.time() - start_time
        
        logger.info(f"✅ 用户问题分析完成，耗时: {duration:.2f}s")
        logger.info(f"VLM结果长度: {len(result) if result else 0} 字符")
        
        if result:
            logger.info(f"VLM结果预览: {result[:200]}...")
        
        # 检查是否生成了user_question.json文件
        details_dir = Path(image_path).parent
        user_question_file = details_dir / 'user_question.json'
        
        if user_question_file.exists():
            with open(user_question_file, 'r', encoding='utf-8') as f:
                user_question_data = json.load(f)
            
            logger.info("✅ 用户问题结果文件已生成")
            logger.info(f"用户问题: {user_question_data.get('user_question', 'N/A')}")
            logger.info(f"回答: {user_question_data.get('response', 'N/A')}")
            
            return user_question_data.get('response')
        else:
            logger.warning("❌ 用户问题结果文件未生成")
            return None
    
    def test_tts_service_integration(self):
        """测试TTS服务集成"""
        logger.info("🎵 测试3: TTS服务集成")
        
        # 创建TTS服务实例（但不实际发送请求）
        tts_service = TTSService()
        tts_service.output_dir = self.temp_dir
        
        # 模拟检查新结果
        session_dir = Path(self.temp_dir)
        frame_dirs = [d for d in session_dir.iterdir() if d.is_dir() and d.name.endswith('_details')]
        
        if not frame_dirs:
            logger.warning("没有找到frame details目录")
            return
        
        frame_dir = frame_dirs[0]
        logger.info(f"检查目录: {frame_dir}")
        
        # 检查user_question.json
        user_question_file = frame_dir / 'user_question.json'
        if user_question_file.exists():
            user_question_data = tts_service._load_user_question_result(frame_dir)
            if user_question_data:
                response = tts_service._extract_response_from_user_question_result(user_question_data)
                if response:
                    logger.info(f"✅ TTS服务成功提取用户问题回答: {response}")
                else:
                    logger.warning("❌ TTS服务无法提取用户问题回答")
            else:
                logger.warning("❌ TTS服务无法加载用户问题结果")
        else:
            logger.info("ℹ️ 没有用户问题结果文件")
        
        # 检查inference_result.json
        inference_result_file = frame_dir / 'inference_result.json'
        if inference_result_file.exists():
            inference_data = tts_service._load_inference_result(frame_dir)
            if inference_data:
                summary = tts_service._extract_summary_from_inference_result(inference_data)
                if summary:
                    logger.info(f"✅ TTS服务成功提取推理结果summary: {summary}")
                else:
                    logger.warning("❌ TTS服务无法提取推理结果summary")
            else:
                logger.warning("❌ TTS服务无法加载推理结果")
        else:
            logger.info("ℹ️ 没有推理结果文件")
    
    def test_config_validation(self):
        """测试配置验证"""
        logger.info("⚙️ 测试4: 配置验证")
        
        # 检查VLM客户端配置
        logger.info(f"VLM客户端配置:")
        logger.info(f"  - 默认系统提示词长度: {len(self.vlm_client.system_prompt)} 字符")
        logger.info(f"  - 用户问题系统提示词长度: {len(self.vlm_client.user_question_system_prompt)} 字符")
        logger.info(f"  - 用户问题模板: {self.vlm_client.user_question_template}")
        
        # 验证配置文件
        config_path = project_root / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            vlm_config = config.get('vlm', {})
            user_question_prompt = vlm_config.get('user_question_prompt', {})
            
            if user_question_prompt:
                logger.info("✅ 配置文件中包含用户问题专用提示词配置")
                logger.info(f"  - 系统提示词长度: {len(user_question_prompt.get('system', ''))} 字符")
                logger.info(f"  - 用户模板: {user_question_prompt.get('user_template', 'N/A')}")
            else:
                logger.warning("❌ 配置文件中缺少用户问题专用提示词配置")
        else:
            logger.warning("❌ 配置文件不存在")
    
    async def run_all_tests(self):
        """运行所有测试"""
        logger.info("🚀 开始用户问题优化功能测试")
        
        try:
            # 测试4: 配置验证
            self.test_config_validation()
            
            # 创建测试图像
            image_path = self.create_test_image()
            if not image_path:
                logger.error("无法创建测试图像，跳过后续测试")
                return
            
            # 创建frame details目录结构
            frame_image_path = self.create_test_frame_details_dir(image_path)
            
            # 测试1: VLM分析（无用户问题）
            vlm_result = await self.test_vlm_analysis_without_user_question(frame_image_path)
            
            # 测试2: 用户问题分析
            test_question = "图像中有什么颜色的矩形？"
            user_answer = await self.test_user_question_analysis(frame_image_path, test_question)
            
            # 测试3: TTS服务集成
            self.test_tts_service_integration()
            
            logger.info("✅ 所有测试完成")
            
            # 总结
            logger.info("\n📊 测试总结:")
            logger.info(f"  - VLM分析结果: {'✅ 成功' if vlm_result else '❌ 失败'}")
            logger.info(f"  - 用户问题回答: {'✅ 成功' if user_answer else '❌ 失败'}")
            logger.info(f"  - 临时目录: {self.temp_dir}")
            
        except Exception as e:
            logger.error(f"测试过程中出错: {str(e)}", exc_info=True)
    
    def cleanup(self):
        """清理测试资源"""
        try:
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info(f"已清理临时目录: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"清理临时目录失败: {str(e)}")

async def main():
    """主函数"""
    tester = UserQuestionOptimizationTester()
    
    try:
        await tester.run_all_tests()
    finally:
        tester.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 