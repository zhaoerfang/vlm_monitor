#!/usr/bin/env python3
"""
测试同步推理模式功能
验证同步推理模式下的帧处理逻辑和用户问题优先级
"""

import os
import sys
import time
import logging
import threading
import numpy as np
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.monitor.vlm.async_video_processor import AsyncVideoProcessor
from src.monitor.vlm.vlm_client import DashScopeVLMClient

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_test_frame(width=640, height=360, color=(128, 128, 128)):
    """创建测试帧"""
    frame = np.full((height, width, 3), color, dtype=np.uint8)
    return frame

def test_sync_inference_mode():
    """测试同步推理模式"""
    logger.info("🧪 开始测试同步推理模式")
    
    # 创建临时目录
    temp_dir = project_root / "tmp" / f"sync_test_{int(time.time())}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 测试目录: {temp_dir}")
    
    try:
        # 初始化VLM客户端
        vlm_client = DashScopeVLMClient()
        
        # 创建异步视频处理器（启用同步推理模式）
        processor = AsyncVideoProcessor(
            vlm_client=vlm_client,
            temp_dir=str(temp_dir),
            target_video_duration=1.0,
            frames_per_second=1,
            original_fps=25.0,
            max_concurrent_inferences=1
        )
        
        # 确保启用同步推理模式
        processor.set_sync_inference_mode(True)
        
        # 启动处理器
        processor.start()
        logger.info("✅ 异步视频处理器已启动")
        
        # 测试1: 基本同步推理
        logger.info("\n📋 测试1: 基本同步推理")
        test_basic_sync_inference(processor)
        
        # 测试2: 帧跳过逻辑
        logger.info("\n📋 测试2: 帧跳过逻辑")
        test_frame_skipping(processor)
        
        # 测试3: 实时帧处理逻辑
        logger.info("\n📋 测试3: 实时帧处理逻辑")
        test_real_time_frame_processing(processor)
        
        # 测试4: 推理状态监控
        logger.info("\n📋 测试4: 推理状态监控")
        test_inference_status(processor)
        
        # 测试5: 模式切换
        logger.info("\n📋 测试5: 模式切换")
        test_mode_switching(processor)
        
        # 等待所有推理完成
        logger.info("\n⏳ 等待所有推理完成...")
        time.sleep(10)
        
        # 获取最终状态
        final_status = processor.get_inference_status()
        logger.info(f"📊 最终状态: {final_status}")
        
        # 停止处理器
        processor.stop()
        logger.info("✅ 测试完成")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {str(e)}")
        raise
    finally:
        # 清理临时目录
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.info(f"🗑️ 清理测试目录: {temp_dir}")

def test_basic_sync_inference(processor):
    """测试基本同步推理功能"""
    logger.info("测试基本同步推理功能...")
    
    # 添加第一帧
    frame1 = create_test_frame(color=(255, 0, 0))  # 红色
    processor.add_frame(frame1, time.time())
    logger.info("📸 添加第一帧（红色）")
    
    # 等待一段时间，确保推理开始
    time.sleep(2)
    
    # 检查推理状态
    status = processor.get_inference_status()
    logger.info(f"📊 推理状态: 活跃={status['inference_active']}, 模式={status['sync_mode']}")
    
    # 添加第二帧（应该被缓存）
    frame2 = create_test_frame(color=(0, 255, 0))  # 绿色
    processor.add_frame(frame2, time.time())
    logger.info("📸 添加第二帧（绿色）- 应该被缓存")
    
    # 检查是否有待处理帧
    status = processor.get_inference_status()
    logger.info(f"📊 待处理帧: {status['has_pending_frame']}")
    
    # 等待推理完成
    time.sleep(5)

def test_frame_skipping(processor):
    """测试帧跳过逻辑"""
    logger.info("测试帧跳过逻辑...")
    
    # 快速添加多个帧
    colors = [(255, 255, 0), (255, 0, 255), (0, 255, 255), (128, 255, 128)]
    for i, color in enumerate(colors):
        frame = create_test_frame(color=color)
        processor.add_frame(frame, time.time())
        logger.info(f"📸 快速添加帧 {i+1} (颜色: {color})")
        time.sleep(0.1)  # 很短的间隔
    
    # 检查跳过的帧数
    status = processor.get_inference_status()
    logger.info(f"📊 跳过的帧数: {status['frames_skipped_sync']}")

def test_real_time_frame_processing(processor):
    """测试实时帧处理逻辑（修复后的核心功能）"""
    logger.info("测试实时帧处理逻辑...")
    
    # 添加第一帧，应该立即开始推理
    frame1 = create_test_frame(color=(255, 100, 100))  # 浅红色
    processor.add_frame(frame1, time.time())
    logger.info("📸 添加第一帧（浅红色）- 应该立即开始推理")
    
    # 等待推理开始
    time.sleep(1)
    status = processor.get_inference_status()
    logger.info(f"📊 推理状态: 活跃={status['inference_active']}")
    
    # 快速添加多个帧，模拟实时视频流
    logger.info("🎬 模拟实时视频流，快速添加多个帧...")
    colors = [
        (100, 255, 100),  # 浅绿色 - 帧2
        (100, 100, 255),  # 浅蓝色 - 帧3
        (255, 255, 100),  # 浅黄色 - 帧4
        (255, 100, 255),  # 浅紫色 - 帧5
        (100, 255, 255),  # 浅青色 - 帧6（最新帧）
    ]
    
    for i, color in enumerate(colors, 2):
        frame = create_test_frame(color=color)
        processor.add_frame(frame, time.time())
        logger.info(f"📸 添加帧 {i} (颜色: {color})")
        time.sleep(0.2)  # 模拟实时流的间隔
    
    # 检查状态
    status = processor.get_inference_status()
    logger.info(f"📊 当前状态: 推理活跃={status['inference_active']}, 有待处理帧={status['has_pending_frame']}")
    if status['has_pending_frame']:
        logger.info(f"📊 待处理帧号: {status['pending_frame_number']}")
    
    # 等待第一个推理完成
    logger.info("⏳ 等待第一个推理完成...")
    max_wait = 15  # 最多等待15秒
    wait_start = time.time()
    
    while time.time() - wait_start < max_wait:
        status = processor.get_inference_status()
        if not status['inference_active']:
            logger.info("✅ 第一个推理已完成")
            break
        time.sleep(1)
        logger.info(f"⏳ 等待中... 推理进行时间: {time.time() - wait_start:.1f}s")
    
    # 检查推理完成后的状态
    time.sleep(2)  # 给一点时间让系统处理
    status = processor.get_inference_status()
    logger.info(f"📊 推理完成后状态: 推理活跃={status['inference_active']}, 有待处理帧={status['has_pending_frame']}")
    
    # 验证关键点：推理完成后应该处理最新的实时帧，而不是过时的缓存帧
    if status['inference_active']:
        logger.info("✅ 推理完成后正确开始处理最新帧")
    else:
        logger.warning("⚠️ 推理完成后没有开始处理待处理帧")
    
    # 等待第二个推理完成
    logger.info("⏳ 等待第二个推理完成...")
    wait_start = time.time()
    while time.time() - wait_start < max_wait:
        status = processor.get_inference_status()
        if not status['inference_active']:
            logger.info("✅ 第二个推理已完成")
            break
        time.sleep(1)
    
    # 最终状态检查
    final_status = processor.get_inference_status()
    logger.info(f"📊 最终状态: 跳过帧数={final_status['frames_skipped_sync']}, "
               f"总推理数={final_status['total_completed']}")
    
    # 验证修复效果
    if final_status['frames_skipped_sync'] > 0:
        logger.info(f"✅ 同步模式正常工作，跳过了 {final_status['frames_skipped_sync']} 个过时帧")
    else:
        logger.warning("⚠️ 没有跳过任何帧，可能存在问题")

def test_inference_status(processor):
    """测试推理状态监控"""
    logger.info("测试推理状态监控...")
    
    # 添加一帧并监控状态变化
    frame = create_test_frame(color=(192, 192, 192))  # 灰色
    processor.add_frame(frame, time.time())
    
    # 监控状态变化
    for i in range(10):
        status = processor.get_inference_status()
        logger.info(f"📊 状态监控 {i+1}: 活跃={status['inference_active']}, "
                   f"任务数={status['active_tasks']}, 待处理={status['has_pending_frame']}")
        time.sleep(1)
        
        if not status['inference_active']:
            logger.info("✅ 推理已完成")
            break

def test_mode_switching(processor):
    """测试模式切换"""
    logger.info("测试模式切换...")
    
    # 当前应该是同步模式
    current_mode = processor.get_sync_inference_mode()
    logger.info(f"📊 当前模式: {'同步' if current_mode else '异步'}")
    
    # 切换到异步模式
    processor.set_sync_inference_mode(False)
    logger.info("🔄 切换到异步模式")
    
    # 添加几帧测试异步模式
    for i in range(3):
        frame = create_test_frame(color=(64 + i*64, 64 + i*64, 64 + i*64))
        processor.add_frame(frame, time.time())
        logger.info(f"📸 异步模式添加帧 {i+1}")
        time.sleep(0.5)
    
    # 等待一段时间
    time.sleep(3)
    
    # 切换回同步模式
    processor.set_sync_inference_mode(True)
    logger.info("🔄 切换回同步模式")
    
    # 添加一帧测试同步模式
    frame = create_test_frame(color=(255, 255, 255))  # 白色
    processor.add_frame(frame, time.time())
    logger.info("📸 同步模式添加帧")

if __name__ == "__main__":
    test_sync_inference_mode() 