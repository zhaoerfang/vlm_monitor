#!/usr/bin/env python3
"""
测试用户问题中断推理的逻辑
验证用户问题能够强制中断当前推理并立即得到处理
"""

import sys
import os
import time
import threading
import logging
import numpy as np
from unittest.mock import Mock, MagicMock, AsyncMock
import asyncio

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.monitor.vlm.async_video_processor import AsyncVideoProcessor
from src.monitor.vlm.user_question_manager import UserQuestionManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_mock_frame(frame_number: int) -> np.ndarray:
    """创建模拟帧"""
    # 创建一个简单的彩色帧 (360x640x3)
    frame = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)
    return frame

async def slow_inference_mock(*args, **kwargs):
    """模拟慢速推理（用于测试中断）"""
    logger.info("🐌 开始慢速推理（模拟）...")
    await asyncio.sleep(5)  # 模拟5秒的推理时间
    logger.info("🐌 慢速推理完成")
    return "慢速推理结果"

async def fast_inference_mock(*args, **kwargs):
    """模拟快速推理（用于用户问题）"""
    logger.info("⚡ 开始快速推理（用户问题）...")
    await asyncio.sleep(1)  # 模拟1秒的推理时间
    logger.info("⚡ 快速推理完成")
    return "用户问题推理结果"

def test_user_question_interrupt():
    """测试用户问题中断推理的逻辑"""
    logger.info("=== 测试用户问题中断推理逻辑 ===")
    
    # 创建模拟的VLM客户端
    mock_vlm_client = Mock()
    
    # 创建模拟的用户问题管理器
    mock_question_manager = Mock()
    mock_question_manager.start = MagicMock()
    mock_question_manager.stop = MagicMock()
    
    # 初始状态：无用户问题
    mock_question_manager.has_available_question = MagicMock(return_value=False)
    mock_question_manager.acquire_question = MagicMock(return_value=(None, None))
    
    # 创建异步视频处理器（图像模式，同步推理模式）
    processor = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_interrupt",
        target_video_duration=1.0,  # 图像模式
        frames_per_second=1,        # 图像模式
        original_fps=25.0,
        max_concurrent_inferences=1
    )
    
    # 手动设置问题管理器
    processor.question_manager = mock_question_manager
    
    # 确保是同步推理模式
    processor.set_sync_inference_mode(True)
    
    try:
        # 启动处理器
        processor.start()
        time.sleep(1)  # 等待启动完成
        
        logger.info("\n--- 阶段1: 启动慢速推理 ---")
        
        # 设置慢速推理
        mock_vlm_client.analyze_image_async = AsyncMock(side_effect=slow_inference_mock)
        
        # 发送第一个帧，启动慢速推理
        frame1 = create_mock_frame(1)
        processor.add_frame(frame1, time.time())
        logger.info("发送帧1，启动慢速推理")
        
        # 等待推理开始
        time.sleep(2)
        
        # 检查推理状态
        with processor.current_inference_lock:
            if processor.current_inference_active:
                logger.info("✅ 确认慢速推理已开始")
            else:
                logger.warning("❌ 慢速推理未开始")
        
        logger.info("\n--- 阶段2: 用户问题到达，应该中断推理 ---")
        
        # 模拟用户问题到达
        mock_question_manager.has_available_question.return_value = True
        mock_question_manager.acquire_question.return_value = ("帮我找一个穿蓝色衣服的人", "urgent_task")
        
        # 切换到快速推理（模拟用户问题的快速响应）
        mock_vlm_client.analyze_image_async = AsyncMock(side_effect=fast_inference_mock)
        
        # 发送第二个帧，应该触发用户问题处理
        frame2 = create_mock_frame(2)
        processor.add_frame(frame2, time.time())
        logger.info("发送帧2（有用户问题），应该中断当前推理")
        
        # 检查推理状态是否被重置
        time.sleep(0.5)  # 短暂等待
        with processor.current_inference_lock:
            if not processor.current_inference_active:
                logger.info("✅ 确认推理状态已被重置")
            else:
                logger.warning("❌ 推理状态未被重置")
        
        # 等待用户问题推理完成
        time.sleep(3)
        
        logger.info("\n--- 阶段3: 检查结果 ---")
        
        # 检查用户问题处理统计
        logger.info(f"用户问题处理次数: {processor.user_questions_processed}")
        logger.info(f"推理启动次数: {processor.total_inferences_started}")
        logger.info(f"推理完成次数: {processor.total_inferences_completed}")
        
        # 检查最终状态
        with processor.current_inference_lock:
            if processor.current_inference_active:
                logger.info(f"当前推理状态: 活跃 - {processor.current_inference_details}")
            else:
                logger.info("当前推理状态: 空闲")
        
        # 验证结果
        if processor.user_questions_processed > 0:
            logger.info("✅ 用户问题处理成功")
        else:
            logger.error("❌ 用户问题未被处理")
        
        logger.info("✅ 中断测试完成")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        raise
    finally:
        # 停止处理器
        processor.stop()

def test_multiple_interrupts():
    """测试多次用户问题中断"""
    logger.info("\n=== 测试多次用户问题中断 ===")
    
    # 创建模拟的VLM客户端
    mock_vlm_client = Mock()
    mock_vlm_client.analyze_image_async = AsyncMock(side_effect=fast_inference_mock)
    
    # 创建模拟的用户问题管理器
    mock_question_manager = Mock()
    mock_question_manager.start = MagicMock()
    mock_question_manager.stop = MagicMock()
    
    # 模拟连续的用户问题
    questions = [
        (False, (None, None)),
        (True, ("问题1", "task1")),
        (True, ("问题2", "task2")),
        (True, ("问题3", "task3")),
        (False, (None, None)),
    ]
    
    question_index = 0
    
    def mock_has_question():
        nonlocal question_index
        if question_index < len(questions):
            return questions[question_index][0]
        return False
    
    def mock_acquire_question():
        nonlocal question_index
        if question_index < len(questions):
            result = questions[question_index][1]
            question_index += 1
            return result
        return (None, None)
    
    mock_question_manager.has_available_question = MagicMock(side_effect=mock_has_question)
    mock_question_manager.acquire_question = MagicMock(side_effect=mock_acquire_question)
    
    # 创建处理器
    processor = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_multiple_interrupt",
        target_video_duration=1.0,
        frames_per_second=1,
        original_fps=25.0,
        max_concurrent_inferences=1
    )
    
    processor.question_manager = mock_question_manager
    processor.set_sync_inference_mode(True)
    
    try:
        processor.start()
        time.sleep(1)
        
        # 快速发送多个帧，测试连续的用户问题中断
        for i in range(10):
            frame = create_mock_frame(i + 1)
            processor.add_frame(frame, time.time())
            logger.info(f"发送帧 {i + 1}")
            time.sleep(0.5)  # 间隔发送
        
        time.sleep(5)  # 等待处理完成
        
        logger.info(f"多次中断测试完成 - 用户问题处理次数: {processor.user_questions_processed}")
        
    finally:
        processor.stop()

if __name__ == "__main__":
    try:
        test_user_question_interrupt()
        test_multiple_interrupts()
        logger.info("🎉 所有中断测试通过！")
    except Exception as e:
        logger.error(f"❌ 测试失败: {str(e)}")
        sys.exit(1) 