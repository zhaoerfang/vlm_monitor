#!/usr/bin/env python3
"""
测试用户问题修复
验证用户问题监听器不会重复获取问题
"""

import sys
import os
import time
import logging
from unittest.mock import MagicMock, AsyncMock
import asyncio

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(project_root, 'src'))

from monitor.vlm.async_video_processor import AsyncVideoProcessor
from monitor.vlm.user_question_manager import UserQuestionManager
from monitor.vlm.vlm_client import DashScopeVLMClient

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_mock_frame(frame_number: int):
    """创建模拟帧数据"""
    import numpy as np
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    return frame

async def mock_vlm_analysis(image_path, prompt=None, user_question=None, enable_camera_control=True):
    """模拟VLM分析，记录接收到的参数"""
    logger.info(f"🔍 模拟VLM分析开始")
    logger.info(f"  - 图像路径: {image_path}")
    logger.info(f"  - 用户问题: {user_question}")
    logger.info(f"  - 启用摄像头控制: {enable_camera_control}")
    
    # 模拟处理时间
    await asyncio.sleep(0.5)
    
    if user_question:
        return f"回答用户问题: {user_question}"
    else:
        return "常规图像分析结果"

def test_user_question_fix():
    """测试用户问题修复"""
    logger.info("=" * 60)
    logger.info("开始测试用户问题修复")
    logger.info("=" * 60)
    
    # 创建模拟VLM客户端
    mock_vlm_client = MagicMock(spec=DashScopeVLMClient)
    mock_vlm_client.analyze_image_async = AsyncMock(side_effect=mock_vlm_analysis)
    
    # 创建真实的用户问题管理器
    question_manager = UserQuestionManager()
    
    # 创建视频处理器
    processor = AsyncVideoProcessor(
        vlm_client=mock_vlm_client,
        temp_dir="tmp/test_fix",
        max_concurrent_inferences=1
    )
    processor.question_manager = question_manager
    processor.set_sync_inference_mode(True)  # 使用同步模式便于测试
    
    try:
        processor.start()
        time.sleep(1)
        
        # 手动设置用户问题（模拟ASR服务器）
        logger.info("设置测试用户问题...")
        with question_manager.question_lock:
            question_manager.current_question = "有戴眼镜的人吗"
            question_manager.question_timestamp = time.time()
            question_manager.question_assigned = True  # 预分配状态
            question_manager.assigned_task_id = "pending"  # 预分配标记
            question_manager.assignment_time = time.time()
        
        logger.info(f"问题状态: {question_manager.get_question_info()}")
        logger.info(f"has_available_question: {question_manager.has_available_question()}")
        
        # 发送一个帧
        frame = create_mock_frame(1)
        processor.add_frame(frame, time.time())
        
        # 等待处理完成
        logger.info("等待推理完成...")
        time.sleep(3)
        
        # 检查VLM客户端是否被正确调用
        mock_vlm_client.analyze_image_async.assert_called()
        
        # 获取调用参数
        call_args = mock_vlm_client.analyze_image_async.call_args
        if call_args:
            args, kwargs = call_args
            user_question_param = kwargs.get('user_question')
            
            logger.info(f"VLM客户端调用参数:")
            logger.info(f"  - user_question: {user_question_param}")
            logger.info(f"  - enable_camera_control: {kwargs.get('enable_camera_control')}")
            
            if user_question_param:
                logger.info("✅ 用户问题修复成功！VLM客户端收到了用户问题")
            else:
                logger.error("❌ 用户问题修复失败！VLM客户端没有收到用户问题")
        else:
            logger.error("❌ VLM客户端没有被调用")
        
        # 检查问题状态
        final_question_info = question_manager.get_question_info()
        logger.info(f"最终问题状态: {final_question_info}")
        
    finally:
        processor.stop()
        logger.info("测试完成")

if __name__ == "__main__":
    test_user_question_fix() 