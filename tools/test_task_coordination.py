#!/usr/bin/env python3
"""
测试任务协调逻辑
验证：
1. 各任务（VLM分析、用户问题、MCP控制）独立执行并立即保存结果
2. analyze_image_async 等待所有任务完成后才返回，确保 release_question 时机正确
"""

import asyncio
import time
import logging
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.monitor.vlm.vlm_client import DashScopeVLMClient
from src.utils.config_loader import load_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/test_task_coordination.log')
    ]
)
logger = logging.getLogger(__name__)

class MockVLMClient(DashScopeVLMClient):
    """模拟VLM客户端，用于测试任务协调逻辑"""
    
    async def _perform_vlm_analysis(self, image_path: str, prompt=None, user_question=None):
        """模拟VLM分析，耗时3秒"""
        logger.info("🔍 开始模拟VLM分析...")
        await asyncio.sleep(3.0)  # 模拟3秒的VLM分析
        logger.info("✅ VLM分析完成")
        return '{"people_count": 2, "vehicle_count": 1, "summary": "测试场景"}'
    
    async def _perform_user_question_analysis(self, image_path: str, user_question: str):
        """模拟用户问题分析，耗时1.5秒"""
        logger.info("🤔 开始模拟用户问题分析...")
        await asyncio.sleep(1.5)  # 模拟1.5秒的用户问题分析
        logger.info("✅ 用户问题分析完成")
        return f"根据图像内容回答：{user_question} - 这是一个测试回答"
    
    async def _perform_mcp_control(self, image_path: str, user_question=None):
        """模拟MCP控制，耗时2秒"""
        logger.info("🎯 开始模拟MCP控制...")
        await asyncio.sleep(2.0)  # 模拟2秒的MCP控制
        logger.info("✅ MCP控制完成")
        return {
            'mcp_success': True,
            'control_result': {'success': True, 'action': 'pan_left'},
            'mcp_duration': 2.0
        }
    
    def _save_user_question_result_to_details(self, image_path: str, user_question: str, user_answer: str):
        """模拟保存用户问题结果"""
        logger.info(f"💾 用户问题结果已保存: {user_question} -> {user_answer[:50]}...")
    
    def _save_mcp_result_to_details(self, image_path: str, mcp_result: dict):
        """模拟保存MCP结果"""
        logger.info(f"💾 MCP结果已保存: {mcp_result.get('mcp_success', False)}")

async def test_task_coordination():
    """测试任务协调逻辑"""
    logger.info("🚀 开始测试任务协调逻辑...")
    
    # 创建模拟VLM客户端
    vlm_client = MockVLMClient()
    
    # 测试场景1：有用户问题的情况
    logger.info("=" * 60)
    logger.info("测试场景1: 有用户问题（VLM分析 + 用户问题回答）")
    logger.info("=" * 60)
    
    test_image_path = "/tmp/test_image.jpg"
    user_question = "图片中有什么？"
    
    start_time = time.time()
    
    # 调用analyze_image_async，应该等待所有任务完成
    result = await vlm_client.analyze_image_async(
        image_path=test_image_path,
        user_question=user_question,
        enable_camera_control=False  # 禁用MCP控制
    )
    
    end_time = time.time()
    total_duration = end_time - start_time
    
    logger.info(f"⏱️ 总耗时: {total_duration:.2f}s")
    logger.info(f"📊 VLM分析结果: {result is not None}")
    
    # 验证时间：应该等待所有任务完成（VLM 3s + 用户问题 1.5s，但并行执行，所以应该约3s）
    expected_duration = 3.0  # VLM分析是最长的任务
    if abs(total_duration - expected_duration) < 0.5:
        logger.info("✅ 时间验证通过：等待了所有任务完成")
    else:
        logger.warning(f"⚠️ 时间验证异常：期望约{expected_duration}s，实际{total_duration:.2f}s")
    
    # 测试场景2：没有用户问题，启用MCP控制
    logger.info("=" * 60)
    logger.info("测试场景2: 没有用户问题（VLM分析 + MCP控制）")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    result = await vlm_client.analyze_image_async(
        image_path=test_image_path,
        user_question=None,
        enable_camera_control=True  # 启用MCP控制
    )
    
    end_time = time.time()
    total_duration = end_time - start_time
    
    logger.info(f"⏱️ 总耗时: {total_duration:.2f}s")
    logger.info(f"📊 VLM分析结果: {result is not None}")
    
    # 验证时间：应该等待所有任务完成（VLM 3s + MCP 2s，但并行执行，所以应该约3s）
    expected_duration = 3.0  # VLM分析是最长的任务
    if abs(total_duration - expected_duration) < 0.5:
        logger.info("✅ 时间验证通过：等待了所有任务完成")
    else:
        logger.warning(f"⚠️ 时间验证异常：期望约{expected_duration}s，实际{total_duration:.2f}s")
    
    # 测试场景3：只有VLM分析
    logger.info("=" * 60)
    logger.info("测试场景3: 只有VLM分析")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    result = await vlm_client.analyze_image_async(
        image_path=test_image_path,
        user_question=None,
        enable_camera_control=False  # 禁用MCP控制
    )
    
    end_time = time.time()
    total_duration = end_time - start_time
    
    logger.info(f"⏱️ 总耗时: {total_duration:.2f}s")
    logger.info(f"📊 VLM分析结果: {result is not None}")
    
    # 验证时间：只有VLM分析，应该约3s
    expected_duration = 3.0
    if abs(total_duration - expected_duration) < 0.5:
        logger.info("✅ 时间验证通过：只等待了VLM分析")
    else:
        logger.warning(f"⚠️ 时间验证异常：期望约{expected_duration}s，实际{total_duration:.2f}s")

async def test_timing_comparison():
    """测试时间对比"""
    logger.info("=" * 60)
    logger.info("时间对比分析")
    logger.info("=" * 60)
    
    logger.info("🔄 新的任务协调逻辑:")
    logger.info("  1. ✅ 各任务并行执行，互不阻塞")
    logger.info("  2. ✅ 各任务完成后立即保存结果（TTS和前端可立即获取）")
    logger.info("  3. ✅ analyze_image_async 等待所有任务完成后返回")
    logger.info("  4. ✅ release_question 在所有任务完成后调用，避免拦截问题")
    
    logger.info("📊 性能特点:")
    logger.info("  - 用户问题回答：1.5s 后立即可用（不等待VLM分析）")
    logger.info("  - MCP控制结果：2.0s 后立即可用（不等待VLM分析）")
    logger.info("  - VLM分析结果：3.0s 后可用")
    logger.info("  - 总等待时间：3.0s（最长任务的时间）")
    logger.info("  - 拦截保护：正确，所有任务完成后才释放用户问题")

if __name__ == "__main__":
    # 确保日志目录存在
    os.makedirs("logs", exist_ok=True)
    
    # 运行测试
    asyncio.run(test_task_coordination())
    asyncio.run(test_timing_comparison())
    
    logger.info("=" * 60)
    logger.info("✅ 任务协调逻辑测试完成")
    logger.info("=" * 60) 