#!/usr/bin/env python3
"""
TCP流信息检测测试
检测TCP流的帧率、分辨率、数据格式等信息
"""

import sys
import os
import time
import cv2
import socket
import struct
import pickle
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

class TCPStreamAnalyzer:
    def __init__(self, host: str = "localhost", port: int = 1234):
        """
        TCP流分析器
        
        Args:
            host: TCP服务器地址
            port: TCP服务器端口
        """
        self.host = host
        self.port = port
        self.analysis_results = {
            'connection_info': {},
            'frame_info': {},
            'stream_stats': {},
            'error_info': {},
            'sample_frames': []
        }
        
    def analyze_stream(self, max_frames: int = 100, timeout: int = 30) -> Dict[str, Any]:
        """
        分析TCP流
        
        Args:
            max_frames: 最大分析帧数
            timeout: 超时时间（秒）
            
        Returns:
            分析结果字典
        """
        print(f"🔍 开始分析TCP流: {self.host}:{self.port}")
        print(f"📊 分析参数: 最大帧数={max_frames}, 超时={timeout}s")
        
        # 记录开始时间
        start_time = time.time()
        
        # 连接信息
        self.analysis_results['connection_info'] = {
            'host': self.host,
            'port': self.port,
            'start_time': datetime.now().isoformat(),
            'start_timestamp': start_time
        }
        
        try:
            # 使用原始socket连接进行低级分析
            raw_analysis = self._analyze_raw_connection(max_frames, timeout)
            
            # 如果原始分析成功，再使用TCP客户端进行高级分析
            if raw_analysis['success']:
                client_analysis = self._analyze_with_client(max_frames, timeout)
                self.analysis_results.update(client_analysis)
            else:
                self.analysis_results['error_info']['raw_connection_failed'] = raw_analysis['error']
                
        except Exception as e:
            self.analysis_results['error_info']['analysis_exception'] = str(e)
            print(f"❌ 分析过程中出现异常: {str(e)}")
        
        # 计算总耗时
        total_time = time.time() - start_time
        self.analysis_results['connection_info']['total_analysis_time'] = total_time
        self.analysis_results['connection_info']['end_time'] = datetime.now().isoformat()
        
        return self.analysis_results
    
    def _analyze_raw_connection(self, max_frames: int, timeout: int) -> Dict[str, Any]:
        """使用原始socket连接分析TCP流"""
        print("\n📡 阶段1: 原始socket连接分析")
        
        result = {'success': False, 'error': None}
        
        try:
            # 创建socket连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            print(f"🔌 尝试连接到 {self.host}:{self.port}...")
            sock.connect((self.host, self.port))
            print("✅ 原始socket连接成功")
            
            # 尝试接收第一个数据包
            print("📦 尝试接收第一个数据包...")
            
            # 接收帧大小（4字节）
            size_data = self._receive_exact_raw(sock, 4)
            if size_data:
                frame_size = struct.unpack('!I', size_data)[0]
                print(f"📏 接收到帧大小: {frame_size} bytes ({frame_size/1024/1024:.2f} MB)")
                
                # 检查帧大小是否合理
                if frame_size > 100 * 1024 * 1024:  # 100MB
                    print(f"⚠️ 帧大小异常: {frame_size} bytes，可能是数据格式错误")
                    result['error'] = f"Frame size too large: {frame_size} bytes"
                elif frame_size == 0:
                    print("⚠️ 帧大小为0，可能是连接问题")
                    result['error'] = "Frame size is 0"
                else:
                    print(f"✅ 帧大小正常: {frame_size} bytes")
                    result['success'] = True
                    
                self.analysis_results['frame_info']['first_frame_size'] = frame_size
            else:
                print("❌ 无法接收帧大小数据")
                result['error'] = "Cannot receive frame size data"
                
            sock.close()
            
        except socket.timeout:
            print(f"⏰ 连接超时 ({timeout}s)")
            result['error'] = f"Connection timeout ({timeout}s)"
        except ConnectionRefusedError:
            print("❌ 连接被拒绝，TCP服务器可能未运行")
            result['error'] = "Connection refused - TCP server may not be running"
        except Exception as e:
            print(f"❌ 原始连接分析失败: {str(e)}")
            result['error'] = str(e)
            
        return result
    
    def _receive_exact_raw(self, sock: socket.socket, size: int) -> Optional[bytes]:
        """精确接收指定字节数的数据"""
        data = b''
        while len(data) < size:
            try:
                chunk = sock.recv(size - len(data))
                if not chunk:
                    return None
                data += chunk
            except Exception:
                return None
        return data
    
    def _analyze_with_client(self, max_frames: int, timeout: int) -> Dict[str, Any]:
        """使用TCP客户端进行高级分析"""
        print("\n🎥 阶段2: TCP客户端高级分析")
        
        result = {
            'frame_info': {},
            'stream_stats': {},
            'sample_frames': []
        }
        
        try:
            # 创建TCP客户端
            client = TCPVideoClient(
                host=self.host,
                port=self.port,
                frame_rate=30,  # 设置较高的帧率以获取更多数据
                timeout=timeout,
                buffer_size=50
            )
            
            # 收集帧信息
            frames_info = []
            frame_sizes = []
            frame_timestamps = []
            resolutions = set()
            
            def frame_callback(frame):
                nonlocal frames_info, frame_sizes, frame_timestamps, resolutions
                
                current_time = time.time()
                frame_timestamps.append(current_time)
                
                # 分析帧信息
                if isinstance(frame, np.ndarray):
                    height, width = frame.shape[:2]
                    channels = frame.shape[2] if len(frame.shape) > 2 else 1
                    resolution = f"{width}x{height}"
                    resolutions.add(resolution)
                    
                    # 计算帧大小（估算）
                    frame_size = frame.nbytes
                    frame_sizes.append(frame_size)
                    
                    frame_info = {
                        'frame_number': len(frames_info) + 1,
                        'timestamp': current_time,
                        'resolution': resolution,
                        'width': width,
                        'height': height,
                        'channels': channels,
                        'frame_size_bytes': frame_size,
                        'frame_size_mb': frame_size / 1024 / 1024
                    }
                    frames_info.append(frame_info)
                    
                    # 保存前几帧作为样本
                    if len(frames_info) <= 5:
                        result['sample_frames'].append({
                            'frame_number': len(frames_info),
                            'resolution': resolution,
                            'size_mb': frame_size / 1024 / 1024,
                            'timestamp': datetime.fromtimestamp(current_time).isoformat()
                        })
                    
                    # 每10帧报告一次进度
                    if len(frames_info) % 10 == 0:
                        elapsed = current_time - frame_timestamps[0] if frame_timestamps else 0
                        fps = len(frames_info) / elapsed if elapsed > 0 else 0
                        print(f"📊 已接收 {len(frames_info)} 帧, 当前fps: {fps:.2f}, 分辨率: {resolution}")
                
                return len(frames_info) < max_frames
            
            print(f"🎬 开始收集最多 {max_frames} 帧...")
            
            # 在单独线程中运行客户端
            client_thread = threading.Thread(
                target=lambda: client.run(callback=frame_callback)
            )
            client_thread.daemon = True
            client_thread.start()
            
            # 等待收集完成
            start_time = time.time()
            while len(frames_info) < max_frames and time.time() - start_time < timeout:
                time.sleep(0.5)
            
            # 分析收集到的数据
            if frames_info:
                # 计算统计信息
                total_time = frame_timestamps[-1] - frame_timestamps[0] if len(frame_timestamps) > 1 else 0
                avg_fps = len(frames_info) / total_time if total_time > 0 else 0
                avg_frame_size = np.mean(frame_sizes) if frame_sizes else 0
                
                # 帧信息
                result['frame_info'] = {
                    'total_frames_received': len(frames_info),
                    'resolutions_detected': list(resolutions),
                    'primary_resolution': max(resolutions, key=lambda r: sum(1 for f in frames_info if f['resolution'] == r)) if resolutions else None,
                    'average_frame_size_bytes': avg_frame_size,
                    'average_frame_size_mb': avg_frame_size / 1024 / 1024,
                    'frame_size_range': {
                        'min_mb': min(frame_sizes) / 1024 / 1024 if frame_sizes else 0,
                        'max_mb': max(frame_sizes) / 1024 / 1024 if frame_sizes else 0
                    }
                }
                
                # 流统计
                result['stream_stats'] = {
                    'collection_duration': total_time,
                    'average_fps': avg_fps,
                    'total_data_mb': sum(frame_sizes) / 1024 / 1024,
                    'data_rate_mbps': (sum(frame_sizes) / 1024 / 1024) / total_time if total_time > 0 else 0,
                    'frame_interval_ms': (total_time * 1000) / len(frames_info) if len(frames_info) > 1 else 0
                }
                
                print(f"✅ 分析完成:")
                print(f"  - 总帧数: {len(frames_info)}")
                print(f"  - 主要分辨率: {result['frame_info']['primary_resolution']}")
                print(f"  - 平均帧率: {avg_fps:.2f} fps")
                print(f"  - 平均帧大小: {avg_frame_size/1024/1024:.2f} MB")
                print(f"  - 数据传输率: {result['stream_stats']['data_rate_mbps']:.2f} MB/s")
                
            else:
                print("❌ 未收集到任何帧数据")
                result['error_info'] = {'no_frames_received': True}
                
        except Exception as e:
            print(f"❌ TCP客户端分析失败: {str(e)}")
            result['error_info'] = {'client_analysis_error': str(e)}
            
        return result
    
    def save_analysis_report(self, output_dir: Path):
        """保存分析报告"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存JSON报告
        import json
        report_file = output_dir / f"tcp_stream_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.analysis_results, f, ensure_ascii=False, indent=2, default=str)
        
        # 生成文本报告
        text_report = self._generate_text_report()
        text_file = output_dir / f"tcp_stream_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(text_report)
        
        print(f"📄 分析报告已保存:")
        print(f"  - JSON报告: {report_file}")
        print(f"  - 文本报告: {text_file}")
        
        return report_file, text_file
    
    def _generate_text_report(self) -> str:
        """生成文本格式的分析报告"""
        report = []
        report.append("=" * 60)
        report.append("TCP视频流分析报告")
        report.append("=" * 60)
        report.append("")
        
        # 连接信息
        conn_info = self.analysis_results.get('connection_info', {})
        report.append("📡 连接信息:")
        report.append(f"  服务器地址: {conn_info.get('host', 'N/A')}:{conn_info.get('port', 'N/A')}")
        report.append(f"  分析开始时间: {conn_info.get('start_time', 'N/A')}")
        report.append(f"  总分析耗时: {conn_info.get('total_analysis_time', 0):.2f}秒")
        report.append("")
        
        # 帧信息
        frame_info = self.analysis_results.get('frame_info', {})
        if frame_info:
            report.append("🎥 帧信息:")
            report.append(f"  总接收帧数: {frame_info.get('total_frames_received', 0)}")
            report.append(f"  检测到的分辨率: {', '.join(frame_info.get('resolutions_detected', []))}")
            report.append(f"  主要分辨率: {frame_info.get('primary_resolution', 'N/A')}")
            report.append(f"  平均帧大小: {frame_info.get('average_frame_size_mb', 0):.2f} MB")
            
            frame_range = frame_info.get('frame_size_range', {})
            report.append(f"  帧大小范围: {frame_range.get('min_mb', 0):.2f} - {frame_range.get('max_mb', 0):.2f} MB")
        report.append("")
        
        # 流统计
        stream_stats = self.analysis_results.get('stream_stats', {})
        if stream_stats:
            report.append("📊 流统计:")
            report.append(f"  数据收集时长: {stream_stats.get('collection_duration', 0):.2f}秒")
            report.append(f"  平均帧率: {stream_stats.get('average_fps', 0):.2f} fps")
            report.append(f"  总数据量: {stream_stats.get('total_data_mb', 0):.2f} MB")
            report.append(f"  数据传输率: {stream_stats.get('data_rate_mbps', 0):.2f} MB/s")
            report.append(f"  帧间隔: {stream_stats.get('frame_interval_ms', 0):.2f} ms")
        report.append("")
        
        # 错误信息
        error_info = self.analysis_results.get('error_info', {})
        if error_info:
            report.append("❌ 错误信息:")
            for key, value in error_info.items():
                report.append(f"  {key}: {value}")
        report.append("")
        
        # 样本帧
        sample_frames = self.analysis_results.get('sample_frames', [])
        if sample_frames:
            report.append("🖼️ 样本帧信息:")
            for frame in sample_frames:
                report.append(f"  帧{frame['frame_number']}: {frame['resolution']}, {frame['size_mb']:.2f}MB, {frame['timestamp']}")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)


def main():
    """主函数"""
    print("🚀 TCP视频流分析工具")
    print("=" * 50)
    
    # 创建输出目录
    output_dir = Path(__file__).parent / "tcp_analysis_results"
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
    
    # 创建分析器
    analyzer = TCPStreamAnalyzer(host=host, port=port)
    
    # 执行分析
    print(f"\n🔍 开始分析TCP流...")
    results = analyzer.analyze_stream(max_frames=50, timeout=30)
    
    # 保存报告
    print(f"\n💾 保存分析报告...")
    analyzer.save_analysis_report(output_dir)
    
    # 显示关键结果
    print(f"\n📋 分析结果摘要:")
    frame_info = results.get('frame_info', {})
    stream_stats = results.get('stream_stats', {})
    
    if frame_info:
        print(f"  ✅ 成功接收 {frame_info.get('total_frames_received', 0)} 帧")
        print(f"  📐 主要分辨率: {frame_info.get('primary_resolution', 'N/A')}")
        print(f"  📏 平均帧大小: {frame_info.get('average_frame_size_mb', 0):.2f} MB")
    
    if stream_stats:
        print(f"  🎬 平均帧率: {stream_stats.get('average_fps', 0):.2f} fps")
        print(f"  📊 数据传输率: {stream_stats.get('data_rate_mbps', 0):.2f} MB/s")
    
    error_info = results.get('error_info', {})
    if error_info:
        print(f"  ❌ 发现错误: {list(error_info.keys())}")
    
    print(f"\n✅ 分析完成，详细报告保存在: {output_dir}")


if __name__ == "__main__":
    main() 