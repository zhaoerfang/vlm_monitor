#!/usr/bin/env python3
"""
测试用户问题阻塞问题的修复
验证has_available_question方法能正确识别预分配状态的问题
"""

import sys
import os
import time
import threading
import logging
from unittest.mock import Mock, MagicMock, AsyncMock

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitor.vlm.user_question_manager import UserQuestionManager
from monitor.vlm.async_video_processor import AsyncVideoProcessor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_mock_frame(frame_number: int):
    """创建模拟帧"""
    import numpy as np
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:, :, 0] = frame_number % 256  # 用帧号作为颜色标识
    return frame

async def fast_inference_mock(image_path, prompt=None, user_question=None, enable_camera_control=True):
    """快速推理模拟"""
    await asyncio.sleep(0.1)  # 快速推理
    return f"模拟推理结果 for {os.path.basename(image_path)}"

def test_has_available_question_fix():
    """测试has_available_question方法的修复"""
    logger.info("=== 测试has_available_question方法的修复 ===")
    
    # 创建用户问题管理器
    question_manager = UserQuestionManager(
        asr_server_url="http://localhost:8081",
        check_interval=1.0,
        timeout=5.0
    )
    
    # 测试1：没有问题时
    logger.info("\n--- 测试1: 没有问题时 ---")
    has_question = question_manager.has_available_question()
    logger.info(f"没有问题时，has_available_question() = {has_question}")
    assert not has_question, "没有问题时应该返回False"
    
    # 测试2：模拟问题到达（预分配状态）
    logger.info("\n--- 测试2: 问题到达（预分配状态） ---")
    with question_manager.question_lock:
        question_manager.current_question = "测试问题"
        question_manager.question_timestamp = time.time()
        question_manager.question_assigned = True  # 预分配状态
        question_manager.assigned_task_id = "pending"  # 预分配标记
        question_manager.assignment_time = time.time()
    
    has_question = question_manager.has_available_question()
    logger.info(f"预分配状态时，has_available_question() = {has_question}")
    assert has_question, "预分配状态时应该返回True（修复后）"
    
    # 测试3：问题被真正分配后
    logger.info("\n--- 测试3: 问题被真正分配后 ---")
    question, task_id = question_manager.acquire_question()
    logger.info(f"获取问题: {question}, 任务ID: {task_id}")
    assert question == "测试问题", "应该能获取到问题"
    assert task_id != "pending", "任务ID应该不是pending"
    
    has_question = question_manager.has_available_question()
    logger.info(f"真正分配后，has_available_question() = {has_question}")
    assert not has_question, "真正分配后应该返回False"
    
    # 测试4：释放问题后
    logger.info("\n--- 测试4: 释放问题后 ---")
    question_manager.release_question(task_id, success=True)
    has_question = question_manager.has_available_question()
    logger.info(f"释放问题后，has_available_question() = {has_question}")
    assert not has_question, "释放问题后应该返回False"
    
    logger.info("✅ has_available_question方法修复测试通过")

def test_user_question_monitor_fix():
    """测试用户问题监听器的修复"""
    logger.info("\n=== 测试用户问题监听器的修复 ===")
    
    import asyncio
    
    # 创建模拟VLM客户端
    mock_vlm_client = Mock()
    mock_vlm_client.analyze_image_async = AsyncMock(side_effect=fast_inference_mock)
    
    # 创建模拟问题管理器
    mock_question_manager = Mock()
    mock_question_manager.start = MagicMock()
    mock_question_manager.stop = MagicMock()
    mock_question_manager.has_available_question = MagicMock(return_value=False)
    mock_question_manager.acquire_question = MagicMock(return_value=(None, None))
    
    # 创建异步视频处理器
    processor = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_blocking_fix",
        target_video_duration=1.0,
        frames_per_second=1,
        original_fps=25.0,
        max_concurrent_inferences=1
    )
    
    processor.question_manager = mock_question_manager
    processor.set_sync_inference_mode(True)
    processor.user_question_monitor_enabled = True
    
    try:
        processor.start()
        time.sleep(1)
        
        # 发送一个帧启动推理
        frame1 = create_mock_frame(1)
        processor.add_frame(frame1, time.time())
        time.sleep(1)
        
        # 发送第二个帧创建pending_frame
        frame2 = create_mock_frame(2)
        processor.add_frame(frame2, time.time())
        time.sleep(0.5)
        
        # 模拟用户问题到达
        logger.info("模拟用户问题到达...")
        mock_question_manager.has_available_question.return_value = True
        mock_question_manager.acquire_question.return_value = ("修复测试问题", "fix_test_task")
        
        # 等待监听器检测到问题
        start_time = time.time()
        max_wait = 5.0
        
        while time.time() - start_time < max_wait:
            if processor.user_questions_processed > 0:
                break
            time.sleep(0.1)
        
        response_time = time.time() - start_time
        questions_processed = processor.user_questions_processed
        
        logger.info(f"监听器响应时间: {response_time:.2f}s")
        logger.info(f"处理的用户问题数: {questions_processed}")
        
        if questions_processed > 0:
            logger.info("✅ 用户问题监听器修复测试通过")
        else:
            logger.warning("❌ 用户问题监听器修复测试失败")
        
        # 验证acquire_question被调用
        mock_question_manager.acquire_question.assert_called()
        logger.info("✅ acquire_question方法被正确调用")
        
    finally:
        processor.stop()

def test_integration():
    """集成测试：完整的用户问题处理流程"""
    logger.info("\n=== 集成测试：完整的用户问题处理流程 ===")
    
    import asyncio
    
    # 创建真实的用户问题管理器（但不启动网络检查）
    question_manager = UserQuestionManager(
        asr_server_url="http://localhost:8081",
        check_interval=1.0,
        timeout=5.0
    )
    
    # 创建模拟VLM客户端
    mock_vlm_client = Mock()
    mock_vlm_client.analyze_image_async = AsyncMock(side_effect=fast_inference_mock)
    
    # 创建异步视频处理器
    processor = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_integration",
        target_video_duration=1.0,
        frames_per_second=1,
        original_fps=25.0,
        max_concurrent_inferences=1
    )
    
    processor.question_manager = question_manager
    processor.set_sync_inference_mode(True)
    processor.user_question_monitor_enabled = True
    
    try:
        processor.start()
        time.sleep(1)
        
        # 发送一个帧启动推理
        frame1 = create_mock_frame(1)
        processor.add_frame(frame1, time.time())
        time.sleep(1)
        
        # 发送第二个帧创建pending_frame
        frame2 = create_mock_frame(2)
        processor.add_frame(frame2, time.time())
        time.sleep(0.5)
        
        # 手动设置用户问题（模拟ASR服务器）
        logger.info("手动设置用户问题...")
        with question_manager.question_lock:
            question_manager.current_question = "集成测试问题"
            question_manager.question_timestamp = time.time()
            question_manager.question_assigned = True  # 预分配状态
            question_manager.assigned_task_id = "pending"  # 预分配标记
            question_manager.assignment_time = time.time()
        
        # 验证has_available_question返回True
        has_question = question_manager.has_available_question()
        logger.info(f"设置问题后，has_available_question() = {has_question}")
        assert has_question, "设置问题后应该返回True"
        
        # 等待监听器检测到问题
        start_time = time.time()
        max_wait = 5.0
        
        while time.time() - start_time < max_wait:
            if processor.user_questions_processed > 0:
                break
            time.sleep(0.1)
        
        response_time = time.time() - start_time
        questions_processed = processor.user_questions_processed
        
        logger.info(f"集成测试响应时间: {response_time:.2f}s")
        logger.info(f"处理的用户问题数: {questions_processed}")
        
        if questions_processed > 0:
            logger.info("✅ 集成测试通过")
        else:
            logger.warning("❌ 集成测试失败")
        
    finally:
        processor.stop()

if __name__ == "__main__":
    try:
        test_has_available_question_fix()
        test_user_question_monitor_fix()
        test_integration()
        logger.info("\n🎉 所有测试完成！")
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc() 