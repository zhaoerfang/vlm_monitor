#!/usr/bin/env python3
"""
测试异步视频处理器初始化
验证日志输出和配置加载
"""

import sys
import os
import logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitor.vlm.async_video_processor import AsyncVideoProcessor

def test_processor_initialization():
    """测试异步视频处理器初始化"""
    print("🎬 测试异步视频处理器初始化...")
    
    # 设置日志级别为INFO以查看初始化日志
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    print(f"\n📋 创建异步视频处理器（查看初始化日志）:")
    print("=" * 60)
    
    # 创建异步视频处理器，这会触发初始化日志
    processor = AsyncVideoProcessor()
    
    print("=" * 60)
    print(f"\n✅ 异步视频处理器初始化完成！")
    print(f"📊 关键配置验证:")
    print(f"  - 图像缩放: {'启用' if processor.enable_frame_resize else '禁用'}")
    print(f"  - 目标尺寸: {processor.target_width}x{processor.target_height}")
    print(f"  - 最大帧大小: {processor.max_frame_size_mb}MB")
    print(f"  - 保持宽高比: {processor.maintain_aspect_ratio}")
    print(f"  - 目标视频时长: {processor.target_video_duration}s")
    print(f"  - 每秒抽帧数: {processor.frames_per_second}帧")

if __name__ == "__main__":
    test_processor_initialization() 