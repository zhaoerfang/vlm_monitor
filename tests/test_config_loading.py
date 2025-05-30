#!/usr/bin/env python3
"""
测试配置文件加载
验证图像缩放配置是否正确从配置文件读取
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitor.core.config import load_config
from monitor.vlm.async_video_processor import AsyncVideoProcessor

def test_config_loading():
    """测试配置文件加载"""
    print("🔧 测试配置文件加载...")
    
    # 加载配置
    config = load_config()
    video_config = config.get('video_processing', {})
    
    print(f"📋 配置文件内容:")
    print(f"  - enable_frame_resize: {video_config.get('enable_frame_resize')}")
    print(f"  - target_width: {video_config.get('target_width')}")
    print(f"  - target_height: {video_config.get('target_height')}")
    print(f"  - max_frame_size_mb: {video_config.get('max_frame_size_mb')}")
    print(f"  - maintain_aspect_ratio: {video_config.get('maintain_aspect_ratio')}")
    
    # 创建异步视频处理器（不启动）
    print(f"\n🎬 创建异步视频处理器...")
    processor = AsyncVideoProcessor()
    
    print(f"📊 处理器配置:")
    print(f"  - enable_frame_resize: {processor.enable_frame_resize}")
    print(f"  - target_width: {processor.target_width}")
    print(f"  - target_height: {processor.target_height}")
    print(f"  - max_frame_size_mb: {processor.max_frame_size_mb}")
    print(f"  - maintain_aspect_ratio: {processor.maintain_aspect_ratio}")
    
    # 验证配置是否正确
    assert processor.enable_frame_resize == video_config.get('enable_frame_resize', True)
    assert processor.target_width == video_config.get('target_width', 640)
    assert processor.target_height == video_config.get('target_height', 360)
    assert processor.max_frame_size_mb == video_config.get('max_frame_size_mb', 5.0)
    assert processor.maintain_aspect_ratio == video_config.get('maintain_aspect_ratio', True)
    
    print(f"\n✅ 配置加载测试通过！")
    print(f"   所有图像缩放配置都正确从配置文件读取")

if __name__ == "__main__":
    test_config_loading() 