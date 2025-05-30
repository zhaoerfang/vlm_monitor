#!/usr/bin/env python3
"""
测试改进后的TCP客户端
验证新的数据格式支持和图像缩放功能
"""

import sys
import os
import time
import cv2
import threading
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from monitor.tcp.tcp_client import TCPVideoClient
from monitor.core.config import load_config
from monitor.utils.image_utils import get_frame_info

def test_improved_tcp_client():
    """测试改进后的TCP客户端"""
    print("🚀 测试改进后的TCP客户端")
    print("=" * 50)
    
    # 创建输出目录
    output_dir = Path(__file__).parent / "improved_client_results"
    output_dir.mkdir(exist_ok=True)
    
    # 从配置文件读取TCP设置
    try:
        config = load_config()
        tcp_config = config['stream']['tcp']
        host = tcp_config['host']
        port = tcp_config['port']
        print(f"📋 从配置文件读取TCP设置: {host}:{port}")
    except Exception as e:
        print(f"⚠️ 无法读取配置文件，使用默认设置: {str(e)}")
        host = "localhost"
        port = 1234
    
    # 测试参数
    max_frames = 30
    timeout = 20
    
    print(f"\n🔍 测试参数:")
    print(f"  - 最大帧数: {max_frames}")
    print(f"  - 超时时间: {timeout}s")
    print(f"  - 图像缩放: 启用 (640x360)")
    
    # 创建改进的TCP客户端
    client = TCPVideoClient(
        host=host,
        port=port,
        frame_rate=10,  # 较高的帧率
        timeout=timeout,
        buffer_size=50,
        enable_resize=True,  # 启用图像缩放
        target_width=640,
        target_height=360
    )
    
    # 收集帧信息
    frames_info = []
    frame_data_list = []
    resolutions = set()
    
    def frame_callback(frame):
        nonlocal frames_info, frame_data_list, resolutions
        
        current_time = time.time()
        
        # 分析帧信息
        if isinstance(frame, np.ndarray):
            frame_info = get_frame_info(frame)
            
            if frame_info['valid']:
                resolution = frame_info['resolution']
                resolutions.add(resolution)
                
                frame_data = {
                    'frame_number': len(frames_info) + 1,
                    'timestamp': current_time,
                    'timestamp_iso': datetime.fromtimestamp(current_time).isoformat(),
                    **frame_info
                }
                frames_info.append(frame_data)
                
                # 保存前几帧
                if len(frames_info) <= 5:
                    frame_data_list.append(frame.copy())
                
                # 每5帧报告一次进度
                if len(frames_info) % 5 == 0:
                    print(f"📊 已接收 {len(frames_info)} 帧, 分辨率: {resolution}, "
                          f"大小: {frame_info['size_mb']:.2f}MB")
            else:
                print(f"❌ 接收到无效帧 {len(frames_info) + 1}")
        
        return len(frames_info) < max_frames
    
    print(f"\n🎬 开始收集最多 {max_frames} 帧...")
    start_time = time.time()
    
    # 在单独线程中运行客户端
    client_thread = threading.Thread(
        target=lambda: client.run(callback=frame_callback)
    )
    client_thread.daemon = True
    client_thread.start()
    
    # 等待收集完成
    collection_start = time.time()
    while len(frames_info) < max_frames and time.time() - collection_start < timeout:
        time.sleep(0.5)
    
    collection_time = time.time() - start_time
    
    # 获取客户端统计信息
    stats = client.get_stats()
    
    # 分析结果
    print(f"\n✅ 测试完成!")
    print(f"📊 收集统计:")
    print(f"  - 总帧数: {len(frames_info)}")
    print(f"  - 收集耗时: {collection_time:.2f}s")
    print(f"  - 平均帧率: {stats['average_fps']:.2f} fps")
    print(f"  - 总数据量: {stats['bytes_received']/1024/1024:.2f} MB")
    print(f"  - 解码错误: {stats['decode_errors']}")
    print(f"  - 缩放次数: {stats['resize_count']}")
    
    if frames_info:
        # 分辨率统计
        print(f"\n📐 分辨率统计:")
        for resolution in sorted(resolutions):
            count = sum(1 for f in frames_info if f['resolution'] == resolution)
            print(f"  - {resolution}: {count} 帧")
        
        # 大小统计
        sizes = [f['size_mb'] for f in frames_info]
        print(f"\n📏 帧大小统计:")
        print(f"  - 平均大小: {np.mean(sizes):.2f} MB")
        print(f"  - 大小范围: {min(sizes):.2f} - {max(sizes):.2f} MB")
        
        # 保存样本帧
        print(f"\n💾 保存样本帧...")
        for i, frame in enumerate(frame_data_list):
            frame_path = output_dir / f"sample_frame_{i+1:02d}.jpg"
            cv2.imwrite(str(frame_path), frame)
            print(f"  - 样本帧 {i+1}: {frame_path}")
        
        # 保存详细报告
        import json
        report = {
            'test_info': {
                'timestamp': datetime.now().isoformat(),
                'host': host,
                'port': port,
                'max_frames': max_frames,
                'timeout': timeout,
                'collection_time': collection_time
            },
            'client_stats': stats,
            'frames_info': frames_info,
            'resolutions': list(resolutions),
            'summary': {
                'total_frames': len(frames_info),
                'average_fps': stats['average_fps'],
                'average_frame_size_mb': np.mean(sizes) if sizes else 0,
                'total_data_mb': stats['bytes_received']/1024/1024,
                'decode_errors': stats['decode_errors'],
                'resize_count': stats['resize_count']
            }
        }
        
        report_file = output_dir / f"tcp_client_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"📄 详细报告已保存: {report_file}")
        
        return True
    else:
        print("❌ 未收集到任何有效帧")
        return False


def test_frame_resize_functionality():
    """测试帧缩放功能"""
    print("\n🔧 测试帧缩放功能")
    print("=" * 30)
    
    from monitor.utils.image_utils import smart_resize_frame, get_frame_info
    
    # 创建测试帧
    test_frames = [
        np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8),  # 大帧
        np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),    # 中等帧
        np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8),    # 小帧
    ]
    
    for i, frame in enumerate(test_frames):
        original_info = get_frame_info(frame)
        print(f"\n测试帧 {i+1}:")
        print(f"  原始: {original_info['resolution']}, {original_info['size_mb']:.2f}MB")
        
        # 应用缩放
        resized_frame = smart_resize_frame(frame, target_width=640, target_height=360)
        
        if resized_frame is not None:
            resized_info = get_frame_info(resized_frame)
            print(f"  缩放后: {resized_info['resolution']}, {resized_info['size_mb']:.2f}MB")
            
            if resized_frame is not frame:
                print(f"  ✅ 帧已缩放")
            else:
                print(f"  ℹ️ 帧无需缩放")
        else:
            print(f"  ❌ 缩放失败")


def main():
    """主函数"""
    print("🧪 改进TCP客户端测试套件")
    print("=" * 60)
    
    # 测试1: 帧缩放功能
    test_frame_resize_functionality()
    
    # 测试2: 改进的TCP客户端
    success = test_improved_tcp_client()
    
    print(f"\n{'='*60}")
    if success:
        print("✅ 所有测试完成，TCP客户端工作正常")
    else:
        print("❌ 测试失败，请检查TCP服务器连接")
    print("="*60)


if __name__ == "__main__":
    main() 