#!/usr/bin/env python3
"""
测试用户问题和帧处理的时序逻辑
验证修复后的pending_frame机制是否正确工作
"""

import sys
import os
import time
import threading
import logging
import numpy as np
from unittest.mock import Mock, MagicMock

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

def test_user_question_frame_timing():
    """测试用户问题和帧处理的时序逻辑"""
    logger.info("=== 开始测试用户问题和帧处理的时序逻辑 ===")
    
    # 创建模拟的VLM客户端
    mock_vlm_client = Mock()
    mock_vlm_client.analyze_image_async = MagicMock(return_value="模拟分析结果")
    
    # 创建模拟的用户问题管理器
    mock_question_manager = Mock()
    mock_question_manager.has_available_question = MagicMock(return_value=False)
    mock_question_manager.acquire_question = MagicMock(return_value=(None, None))
    mock_question_manager.start = MagicMock()
    mock_question_manager.stop = MagicMock()
    
    # 创建异步视频处理器（图像模式，同步推理模式）
    processor = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_timing",
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
        
        logger.info("\n--- 阶段1: 正常帧处理（无用户问题） ---")
        
        # 发送几个正常帧
        for i in range(3):
            frame = create_mock_frame(i + 1)
            processor.add_frame(frame, time.time())
            logger.info(f"发送帧 {i + 1}")
            time.sleep(0.5)
        
        # 等待第一个推理开始
        time.sleep(2)
        
        logger.info("\n--- 阶段2: 推理进行中，发送更多帧（应该被缓存） ---")
        
        # 模拟推理正在进行
        with processor.current_inference_lock:
            processor.current_inference_active = True
            processor.current_inference_details = {
                'media_path': '/tmp/test.jpg',
                'media_type': 'image',
                'start_time': time.time(),
                'frame_number': 1
            }
        
        # 发送更多帧（应该被缓存）
        for i in range(3, 6):
            frame = create_mock_frame(i + 1)
            processor.add_frame(frame, time.time())
            logger.info(f"发送帧 {i + 1}（推理进行中，应该被缓存）")
            time.sleep(0.2)
        
        # 检查pending_frame状态
        with processor.pending_frame_lock:
            if processor.pending_frame_data:
                logger.info(f"✅ 确认有缓存帧: 帧号 {processor.pending_frame_data['frame_number']}")
            else:
                logger.warning("❌ 没有缓存帧，这可能是个问题")
        
        logger.info("\n--- 阶段3: 模拟用户问题到达 ---")
        
        # 模拟用户问题到达
        mock_question_manager.has_available_question.return_value = True
        mock_question_manager.acquire_question.return_value = ("帮我找一个穿红色衣服的人", "task123")
        
        # 发送新帧（应该触发用户问题处理）
        frame = create_mock_frame(10)
        processor.add_frame(frame, time.time())
        logger.info("发送帧 10（有用户问题，应该立即处理）")
        
        # 检查用户问题处理统计
        logger.info(f"用户问题处理次数: {processor.user_questions_processed}")
        
        time.sleep(1)
        
        logger.info("\n--- 阶段4: 推理完成，处理缓存帧 ---")
        
        # 模拟推理完成
        with processor.current_inference_lock:
            processor.current_inference_active = False
            processor.current_inference_details = None
        
        # 重置用户问题状态
        mock_question_manager.has_available_question.return_value = False
        mock_question_manager.acquire_question.return_value = (None, None)
        
        # 发送新帧（应该处理之前的缓存帧）
        frame = create_mock_frame(11)
        processor.add_frame(frame, time.time())
        logger.info("发送帧 11（推理空闲，应该处理缓存帧）")
        
        time.sleep(2)
        
        # 打印最终统计
        logger.info("\n--- 最终统计 ---")
        logger.info(f"总接收帧数: {processor.total_frames_received}")
        logger.info(f"同步跳过帧数: {processor.frames_skipped_sync_mode}")
        logger.info(f"用户问题处理次数: {processor.user_questions_processed}")
        logger.info(f"推理启动次数: {processor.total_inferences_started}")
        
        # 检查最终的pending_frame状态
        with processor.pending_frame_lock:
            if processor.pending_frame_data:
                logger.info(f"最终缓存帧: 帧号 {processor.pending_frame_data['frame_number']}")
            else:
                logger.info("最终无缓存帧")
        
        logger.info("✅ 测试完成")
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        raise
    finally:
        # 停止处理器
        processor.stop()

def test_concurrent_user_questions():
    """测试并发用户问题的处理"""
    logger.info("\n=== 测试并发用户问题处理 ===")
    
    # 创建模拟的VLM客户端
    mock_vlm_client = Mock()
    mock_vlm_client.analyze_image_async = MagicMock(return_value="模拟分析结果")
    
    # 创建模拟的用户问题管理器
    mock_question_manager = Mock()
    mock_question_manager.start = MagicMock()
    mock_question_manager.stop = MagicMock()
    
    # 模拟问题状态变化
    question_states = [
        (False, (None, None)),  # 初始无问题
        (True, ("问题1", "task1")),  # 问题1到达
        (False, (None, None)),  # 问题1被处理
        (True, ("问题2", "task2")),  # 问题2到达
        (False, (None, None)),  # 问题2被处理
    ]
    
    state_index = 0
    
    def mock_has_question():
        nonlocal state_index
        if state_index < len(question_states):
            return question_states[state_index][0]
        return False
    
    def mock_acquire_question():
        nonlocal state_index
        if state_index < len(question_states):
            result = question_states[state_index][1]
            state_index += 1
            return result
        return (None, None)
    
    mock_question_manager.has_available_question = MagicMock(side_effect=mock_has_question)
    mock_question_manager.acquire_question = MagicMock(side_effect=mock_acquire_question)
    
    # 创建处理器
    processor = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="/tmp/test_concurrent",
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
        
        # 快速发送多个帧，测试用户问题的优先处理
        for i in range(10):
            frame = create_mock_frame(i + 1)
            processor.add_frame(frame, time.time())
            logger.info(f"发送帧 {i + 1}")
            time.sleep(0.1)  # 快速发送
        
        time.sleep(3)  # 等待处理完成
        
        logger.info(f"并发测试完成 - 用户问题处理次数: {processor.user_questions_processed}")
        
    finally:
        processor.stop()

if __name__ == "__main__":
    try:
        test_user_question_frame_timing()
        test_concurrent_user_questions()
        logger.info("🎉 所有测试通过！")
    except Exception as e:
        logger.error(f"❌ 测试失败: {str(e)}")
        sys.exit(1) 