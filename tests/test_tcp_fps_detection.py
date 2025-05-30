#!/usr/bin/env python3
"""
测试TCP帧率检测功能
"""

import sys
import logging
from pathlib import Path

# 添加src目录到Python路径
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from monitor.core.config import load_config
from monitor.tcp.tcp_utils import detect_tcp_fps, create_tcp_client_config, test_tcp_video_stream

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_tcp_fps_detection():
    """测试TCP帧率检测"""
    print("🧪 测试TCP帧率检测功能")
    print("=" * 50)
    
    try:
        # 加载配置
        config = load_config()
        tcp_config = config['stream']['tcp']
        
        host = tcp_config['host']
        port = tcp_config['port']
        
        print(f"📡 TCP服务器: {host}:{port}")
        
        # 1. 测试基本连接
        print("\n1. 测试TCP视频流连接...")
        stream_result = test_tcp_video_stream(host, port, config)
        
        if stream_result['connected']:
            print("✅ TCP视频流连接成功")
            stream_info = stream_result['stream_info']
            print(f"📊 检测到的帧率: {stream_info['fps']:.2f}fps")
        else:
            print(f"❌ TCP视频流连接失败: {stream_result['error']}")
            return False
        
        # 2. 测试帧率检测
        print("\n2. 测试帧率检测...")
        detected_fps = detect_tcp_fps(host, port, config, sample_duration=2.0)
        print(f"📈 检测到的帧率: {detected_fps:.2f}fps")
        
        # 3. 测试客户端配置创建
        print("\n3. 测试客户端配置创建...")
        client_config = create_tcp_client_config(host, port, config)
        
        print("🔧 客户端配置:")
        for key, value in client_config.items():
            print(f"  - {key}: {value}")
        
        print("\n✅ 所有测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_tcp_fps_detection()
    sys.exit(0 if success else 1) 