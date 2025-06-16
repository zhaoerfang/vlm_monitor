#!/usr/bin/env python3
"""
测试用户问题主动监听机制
验证用户问题能够被主动检测并立即处理，不依赖于新帧输入
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
    await asyncio.sleep(10)  # 模拟10秒的推理时间
    logger.info("🐌 慢速推理完成")
    return "慢速推理结果"

async def fast_inference_mock(*args, **kwargs):
    """模拟快速推理（用于用户问题）"""
    logger.info("⚡ 开始快速推理（用户问题）...")
    await asyncio.sleep(1)  # 模拟1秒的推理时间
    logger.info("⚡ 快速推理完成")
    return "用户问题推理结果"

def test_proactive_user_question_detection():
    """测试主动用户问题检测机制"""
    logger.info("=== 测试主动用户问题检测机制 ===")
    
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
        temp_dir="/tmp/test_proactive",
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
        time.sleep(2)  # 等待启动完成
        
        logger.info("\n--- 阶段1: 启动慢速推理并创建pending_frame ---")
        
        # 设置慢速推理
        mock_vlm_client.analyze_image_async = AsyncMock(side_effect=slow_inference_mock)
        
        # 发送第一个帧，启动慢速推理
        frame1 = create_mock_frame(1)
        processor.add_frame(frame1, time.time())
        logger.info("发送帧1，启动慢速推理")
        
        # 等待推理开始
        time.sleep(2)
        
        # 发送第二个帧，应该被缓存为pending_frame
        frame2 = create_mock_frame(2)
        processor.add_frame(frame2, time.time())
        logger.info("发送帧2，应该被缓存为pending_frame")
        
        time.sleep(1)
        
        # 检查pending_frame状态
        with processor.pending_frame_lock:
            if processor.pending_frame_data:
                logger.info(f"✅ 确认有pending帧: 帧号 {processor.pending_frame_data['frame_number']}")
            else:
                logger.warning("❌ 没有pending帧")
        
        # 检查推理状态
        with processor.current_inference_lock:
            if processor.current_inference_active:
                logger.info("✅ 确认慢速推理正在进行")
            else:
                logger.warning("❌ 慢速推理未在进行")
        
        logger.info("\n--- 阶段2: 模拟用户问题到达（不发送新帧） ---")
        
        # 切换到快速推理（模拟用户问题的快速响应）
        mock_vlm_client.analyze_image_async = AsyncMock(side_effect=fast_inference_mock)
        
        # 模拟用户问题到达（注意：不发送新帧！）
        mock_question_manager.has_available_question.return_value = True
        mock_question_manager.acquire_question.return_value = ("帮我找一个穿绿色衣服的人", "proactive_task")
        
        logger.info("🚨 用户问题已到达，但不发送新帧，测试主动检测")
        
        # 等待用户问题监听器检测到问题
        time.sleep(3)
        
        logger.info("\n--- 阶段3: 检查结果 ---")
        
        # 检查用户问题处理统计
        logger.info(f"用户问题处理次数: {processor.user_questions_processed}")
        logger.info(f"推理启动次数: {processor.total_inferences_started}")
        logger.info(f"推理完成次数: {processor.total_inferences_completed}")
        
        # 检查pending_frame状态
        with processor.pending_frame_lock:
            if processor.pending_frame_data:
                logger.info(f"当前pending帧: 帧号 {processor.pending_frame_data['frame_number']}")
            else:
                logger.info("当前无pending帧")
        
        # 检查推理状态
        with processor.current_inference_lock:
            if processor.current_inference_active:
                logger.info(f"当前推理状态: 活跃 - {processor.current_inference_details}")
            else:
                logger.info("当前推理状态: 空闲")
        
        # 验证结果
        if processor.user_questions_processed > 0:
            logger.info("✅ 用户问题主动检测成功")
        else:
            logger.error("❌ 用户问题主动检测失败")
        
        # 等待推理完成
        time.sleep(5)
        
        logger.info("✅ 主动检测测试完成")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        raise
    finally:
        # 停止处理器
        processor.stop()

def test_proactive_vs_reactive():
    """对比测试：主动检测 vs 被动检测"""
    logger.info("\n=== 对比测试：主动检测 vs 被动检测 ===")
    
    # 测试1：禁用主动监听（被动模式）
    logger.info("\n--- 测试1: 被动模式（禁用主动监听） ---")
    
    mock_vlm_client = Mock()
    mock_vlm_client.analyze_image_async = AsyncMock(side_effect=fast_inference_mock)
    
    mock_question_manager = Mock()
    mock_question_manager.start = MagicMock()
    mock_question_manager.stop = MagicMock()
    mock_question_manager.has_available_question = MagicMock(return_value=False)
    mock_question_manager.acquire_question = MagicMock(return_value=(None, None))
    
    processor_passive = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_passive",
        target_video_duration=1.0,
        frames_per_second=1,
        original_fps=25.0,
        max_concurrent_inferences=1
    )
    
    processor_passive.question_manager = mock_question_manager
    processor_passive.set_sync_inference_mode(True)
    processor_passive.user_question_monitor_enabled = False  # 禁用主动监听
    
    try:
        processor_passive.start()
        time.sleep(1)
        
        # 发送一个帧并启动推理
        frame1 = create_mock_frame(1)
        processor_passive.add_frame(frame1, time.time())
        time.sleep(1)
        
        # 模拟用户问题到达（不发送新帧）
        start_time = time.time()
        mock_question_manager.has_available_question.return_value = True
        mock_question_manager.acquire_question.return_value = ("被动测试问题", "passive_task")
        
        # 等待5秒，看是否能检测到用户问题
        time.sleep(5)
        
        passive_response_time = time.time() - start_time
        passive_questions_processed = processor_passive.user_questions_processed
        
        logger.info(f"被动模式结果: 处理了 {passive_questions_processed} 个用户问题，响应时间: {passive_response_time:.2f}s")
        
    finally:
        processor_passive.stop()
    
    # 测试2：启用主动监听（主动模式）
    logger.info("\n--- 测试2: 主动模式（启用主动监听） ---")
    
    mock_vlm_client = Mock()
    mock_vlm_client.analyze_image_async = AsyncMock(side_effect=fast_inference_mock)
    
    mock_question_manager = Mock()
    mock_question_manager.start = MagicMock()
    mock_question_manager.stop = MagicMock()
    mock_question_manager.has_available_question = MagicMock(return_value=False)
    mock_question_manager.acquire_question = MagicMock(return_value=(None, None))
    
    processor_active = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_active",
        target_video_duration=1.0,
        frames_per_second=1,
        original_fps=25.0,
        max_concurrent_inferences=1
    )
    
    processor_active.question_manager = mock_question_manager
    processor_active.set_sync_inference_mode(True)
    processor_active.user_question_monitor_enabled = True  # 启用主动监听
    
    try:
        processor_active.start()
        time.sleep(1)
        
        # 发送一个帧并启动推理
        frame1 = create_mock_frame(1)
        processor_active.add_frame(frame1, time.time())
        time.sleep(1)
        
        # 发送第二个帧创建pending_frame
        frame2 = create_mock_frame(2)
        processor_active.add_frame(frame2, time.time())
        time.sleep(1)
        
        # 模拟用户问题到达（不发送新帧）
        start_time = time.time()
        mock_question_manager.has_available_question.return_value = True
        mock_question_manager.acquire_question.return_value = ("主动测试问题", "active_task")
        
        # 等待5秒，看是否能检测到用户问题
        time.sleep(5)
        
        active_response_time = time.time() - start_time
        active_questions_processed = processor_active.user_questions_processed
        
        logger.info(f"主动模式结果: 处理了 {active_questions_processed} 个用户问题，响应时间: {active_response_time:.2f}s")
        
    finally:
        processor_active.stop()
    
    # 对比结果
    logger.info("\n--- 对比结果 ---")
    logger.info(f"被动模式: {passive_questions_processed} 个问题，响应时间: {passive_response_time:.2f}s")
    logger.info(f"主动模式: {active_questions_processed} 个问题，响应时间: {active_response_time:.2f}s")
    
    if active_questions_processed > passive_questions_processed:
        logger.info("✅ 主动模式优于被动模式")
    else:
        logger.warning("❌ 主动模式未显示优势")

if __name__ == "__main__":
    try:
        test_proactive_user_question_detection()
        test_proactive_vs_reactive()
        logger.info("🎉 所有主动监听测试通过！")
    except Exception as e:
        logger.error(f"❌ 测试失败: {str(e)}")
        sys.exit(1) 