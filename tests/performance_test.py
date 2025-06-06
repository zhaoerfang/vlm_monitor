#!/usr/bin/env python3
"""
视频流性能测试脚本
测试优化后的TCP客户端和MJPEG流性能
"""

import time
import threading
import requests
import cv2
import numpy as np
import statistics
from pathlib import Path
import sys
import logging

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

from src.monitor.tcp.tcp_client import TCPVideoClient

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceTestSuite:
    def __init__(self, tcp_host="localhost", tcp_port=1234, backend_url="http://localhost:8080"):
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.backend_url = backend_url
        
        # 性能指标
        self.tcp_metrics = {
            'frame_times': [],
            'frame_sizes': [],
            'decode_times': [],
            'total_frames': 0,
            'errors': 0
        }
        
        self.mjpeg_metrics = {
            'frame_times': [],
            'frame_sizes': [],
            'total_frames': 0,
            'errors': 0
        }
    
    def test_tcp_performance(self, duration=30, target_frames=1000):
        """测试TCP客户端性能"""
        print(f"\n{'='*60}")
        print("🚀 TCP客户端性能测试")
        print(f"{'='*60}")
        print(f"测试时长: {duration}秒 或 {target_frames}帧")
        
        try:
            # 创建优化的TCP客户端
            client = TCPVideoClient(
                host=self.tcp_host,
                port=self.tcp_port,
                frame_rate=60,  # 使用优化后的帧率
                timeout=10,
                buffer_size=1000  # 使用优化后的缓冲区
            )
            
            start_time = time.time()
            last_frame_time = start_time
            
            def frame_callback(frame):
                nonlocal last_frame_time
                current_time = time.time()
                
                # 记录帧间隔
                frame_interval = current_time - last_frame_time
                self.tcp_metrics['frame_times'].append(frame_interval)
                
                # 记录帧大小
                if isinstance(frame, np.ndarray):
                    frame_size = frame.nbytes
                    self.tcp_metrics['frame_sizes'].append(frame_size)
                    
                    # 测试解码性能
                    decode_start = time.time()
                    # 模拟一些处理
                    height, width = frame.shape[:2]
                    decode_time = (time.time() - decode_start) * 1000
                    self.tcp_metrics['decode_times'].append(decode_time)
                
                self.tcp_metrics['total_frames'] += 1
                
                # 实时显示进度
                if self.tcp_metrics['total_frames'] % 100 == 0:
                    elapsed = current_time - start_time
                    fps = self.tcp_metrics['total_frames'] / elapsed
                    print(f"📊 TCP: {self.tcp_metrics['total_frames']} 帧, {fps:.1f} fps, "
                          f"帧间隔: {frame_interval*1000:.1f}ms")
                
                last_frame_time = current_time
                
                # 停止条件
                elapsed = current_time - start_time
                return (elapsed < duration and 
                       self.tcp_metrics['total_frames'] < target_frames)
            
            print("🎬 开始TCP性能测试...")
            
            # 在单独线程中运行客户端
            client_thread = threading.Thread(
                target=lambda: client.run(callback=frame_callback)
            )
            client_thread.daemon = True
            client_thread.start()
            
            # 等待测试完成
            client_thread.join(timeout=duration + 10)
            
            # 计算统计信息
            self._analyze_tcp_results()
            
        except Exception as e:
            print(f"❌ TCP性能测试失败: {e}")
            self.tcp_metrics['errors'] += 1
    
    def test_mjpeg_performance(self, duration=30, target_frames=1000):
        """测试MJPEG流性能"""
        print(f"\n{'='*60}")
        print("🎥 MJPEG流性能测试")
        print(f"{'='*60}")
        print(f"测试时长: {duration}秒 或 {target_frames}帧")
        
        try:
            import requests
            from io import BytesIO
            
            # 启动视频流
            start_response = requests.post(f"{self.backend_url}/api/stream/start", timeout=10)
            if start_response.status_code != 200:
                print(f"❌ 启动视频流失败: {start_response.text}")
                return
            
            print("✅ 视频流已启动，等待2秒...")
            time.sleep(2)
            
            # 开始接收MJPEG流
            stream_url = f"{self.backend_url}/api/video-stream"
            
            start_time = time.time()
            last_frame_time = start_time
            
            print("🎬 开始MJPEG性能测试...")
            
            with requests.get(stream_url, stream=True, timeout=duration + 10) as response:
                if response.status_code != 200:
                    print(f"❌ MJPEG流连接失败: {response.status_code}")
                    return
                
                buffer = b""
                boundary = b"--frame"
                
                for chunk in response.iter_content(chunk_size=8192):
                    current_time = time.time()
                    elapsed = current_time - start_time
                    
                    # 停止条件
                    if (elapsed >= duration or 
                        self.mjpeg_metrics['total_frames'] >= target_frames):
                        break
                    
                    buffer += chunk
                    
                    # 查找完整的帧
                    while boundary in buffer:
                        frame_start = buffer.find(boundary)
                        if frame_start == -1:
                            break
                        
                        # 查找下一个边界
                        next_boundary = buffer.find(boundary, frame_start + len(boundary))
                        if next_boundary == -1:
                            break
                        
                        # 提取帧数据
                        frame_data = buffer[frame_start:next_boundary]
                        buffer = buffer[next_boundary:]
                        
                        # 解析JPEG数据
                        jpeg_start = frame_data.find(b'\r\n\r\n')
                        if jpeg_start != -1:
                            jpeg_data = frame_data[jpeg_start + 4:]
                            
                            # 记录性能指标
                            frame_interval = current_time - last_frame_time
                            self.mjpeg_metrics['frame_times'].append(frame_interval)
                            self.mjpeg_metrics['frame_sizes'].append(len(jpeg_data))
                            self.mjpeg_metrics['total_frames'] += 1
                            
                            # 实时显示进度
                            if self.mjpeg_metrics['total_frames'] % 100 == 0:
                                fps = self.mjpeg_metrics['total_frames'] / elapsed
                                print(f"📊 MJPEG: {self.mjpeg_metrics['total_frames']} 帧, {fps:.1f} fps, "
                                      f"帧间隔: {frame_interval*1000:.1f}ms, "
                                      f"帧大小: {len(jpeg_data)/1024:.1f}KB")
                            
                            last_frame_time = current_time
            
            # 计算统计信息
            self._analyze_mjpeg_results()
            
        except Exception as e:
            print(f"❌ MJPEG性能测试失败: {e}")
            self.mjpeg_metrics['errors'] += 1
        finally:
            # 停止视频流
            try:
                requests.post(f"{self.backend_url}/api/stream/stop", timeout=5)
            except:
                pass
    
    def _analyze_tcp_results(self):
        """分析TCP测试结果"""
        print(f"\n{'='*40}")
        print("📈 TCP性能分析结果")
        print(f"{'='*40}")
        
        if self.tcp_metrics['total_frames'] == 0:
            print("❌ 没有接收到任何帧")
            return
        
        # 帧率统计
        total_time = sum(self.tcp_metrics['frame_times'])
        avg_fps = self.tcp_metrics['total_frames'] / total_time if total_time > 0 else 0
        
        # 帧间隔统计
        frame_intervals_ms = [t * 1000 for t in self.tcp_metrics['frame_times']]
        
        # 帧大小统计
        frame_sizes_kb = [s / 1024 for s in self.tcp_metrics['frame_sizes']]
        
        # 解码时间统计
        decode_times = self.tcp_metrics['decode_times']
        
        print(f"总帧数: {self.tcp_metrics['total_frames']}")
        print(f"平均帧率: {avg_fps:.2f} fps")
        print(f"帧间隔: 平均 {statistics.mean(frame_intervals_ms):.1f}ms, "
              f"最小 {min(frame_intervals_ms):.1f}ms, "
              f"最大 {max(frame_intervals_ms):.1f}ms")
        print(f"帧大小: 平均 {statistics.mean(frame_sizes_kb):.1f}KB, "
              f"最小 {min(frame_sizes_kb):.1f}KB, "
              f"最大 {max(frame_sizes_kb):.1f}KB")
        print(f"解码时间: 平均 {statistics.mean(decode_times):.2f}ms, "
              f"最大 {max(decode_times):.2f}ms")
        print(f"错误数: {self.tcp_metrics['errors']}")
        
        # 性能评级
        if avg_fps >= 50:
            print("🏆 TCP性能: 优秀 (≥50fps)")
        elif avg_fps >= 30:
            print("🥈 TCP性能: 良好 (30-50fps)")
        elif avg_fps >= 15:
            print("🥉 TCP性能: 一般 (15-30fps)")
        else:
            print("⚠️  TCP性能: 需要优化 (<15fps)")
    
    def _analyze_mjpeg_results(self):
        """分析MJPEG测试结果"""
        print(f"\n{'='*40}")
        print("📈 MJPEG性能分析结果")
        print(f"{'='*40}")
        
        if self.mjpeg_metrics['total_frames'] == 0:
            print("❌ 没有接收到任何帧")
            return
        
        # 帧率统计
        total_time = sum(self.mjpeg_metrics['frame_times'])
        avg_fps = self.mjpeg_metrics['total_frames'] / total_time if total_time > 0 else 0
        
        # 帧间隔统计
        frame_intervals_ms = [t * 1000 for t in self.mjpeg_metrics['frame_times']]
        
        # 帧大小统计
        frame_sizes_kb = [s / 1024 for s in self.mjpeg_metrics['frame_sizes']]
        
        print(f"总帧数: {self.mjpeg_metrics['total_frames']}")
        print(f"平均帧率: {avg_fps:.2f} fps")
        print(f"帧间隔: 平均 {statistics.mean(frame_intervals_ms):.1f}ms, "
              f"最小 {min(frame_intervals_ms):.1f}ms, "
              f"最大 {max(frame_intervals_ms):.1f}ms")
        print(f"帧大小: 平均 {statistics.mean(frame_sizes_kb):.1f}KB, "
              f"最小 {min(frame_sizes_kb):.1f}KB, "
              f"最大 {max(frame_sizes_kb):.1f}KB")
        print(f"错误数: {self.mjpeg_metrics['errors']}")
        
        # 性能评级
        if avg_fps >= 60:
            print("🏆 MJPEG性能: 优秀 (≥60fps)")
        elif avg_fps >= 30:
            print("🥈 MJPEG性能: 良好 (30-60fps)")
        elif avg_fps >= 15:
            print("🥉 MJPEG性能: 一般 (15-30fps)")
        else:
            print("⚠️  MJPEG性能: 需要优化 (<15fps)")
    
    def run_full_test(self):
        """运行完整的性能测试"""
        print("🎯 开始视频流性能测试套件")
        print(f"TCP服务器: {self.tcp_host}:{self.tcp_port}")
        print(f"后端服务器: {self.backend_url}")
        
        # 检查服务可用性
        print("\n🔍 检查服务状态...")
        
        # 检查后端服务
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=5)
            if response.status_code == 200:
                print("✅ 后端服务正常")
            else:
                print(f"⚠️  后端服务状态异常: {response.status_code}")
        except Exception as e:
            print(f"❌ 后端服务不可用: {e}")
            return
        
        # 检查TCP服务
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.tcp_host, self.tcp_port))
            sock.close()
            if result == 0:
                print("✅ TCP服务正常")
            else:
                print(f"❌ TCP服务不可用")
                return
        except Exception as e:
            print(f"❌ TCP服务检查失败: {e}")
            return
        
        # 运行测试
        self.test_tcp_performance(duration=20, target_frames=800)
        time.sleep(2)  # 短暂休息
        self.test_mjpeg_performance(duration=20, target_frames=800)
        
        # 总结
        print(f"\n{'='*60}")
        print("🎉 性能测试完成")
        print(f"{'='*60}")
        
        if self.tcp_metrics['total_frames'] > 0 and self.mjpeg_metrics['total_frames'] > 0:
            tcp_fps = self.tcp_metrics['total_frames'] / sum(self.tcp_metrics['frame_times'])
            mjpeg_fps = self.mjpeg_metrics['total_frames'] / sum(self.mjpeg_metrics['frame_times'])
            
            print(f"TCP平均帧率: {tcp_fps:.2f} fps")
            print(f"MJPEG平均帧率: {mjpeg_fps:.2f} fps")
            
            if tcp_fps >= 40 and mjpeg_fps >= 50:
                print("🏆 整体性能: 优秀")
            elif tcp_fps >= 25 and mjpeg_fps >= 30:
                print("🥈 整体性能: 良好")
            else:
                print("⚠️  整体性能: 需要进一步优化")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="视频流性能测试")
    parser.add_argument("--tcp-host", default="localhost", help="TCP服务器地址")
    parser.add_argument("--tcp-port", type=int, default=1234, help="TCP服务器端口")
    parser.add_argument("--backend-url", default="http://localhost:8080", help="后端服务器URL")
    parser.add_argument("--duration", type=int, default=20, help="测试时长(秒)")
    parser.add_argument("--frames", type=int, default=800, help="目标帧数")
    
    args = parser.parse_args()
    
    # 创建测试套件
    test_suite = PerformanceTestSuite(
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        backend_url=args.backend_url
    )
    
    # 运行测试
    test_suite.run_full_test()

if __name__ == "__main__":
    main() 