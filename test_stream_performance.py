#!/usr/bin/env python3
"""
测试优化后的MJPEG流性能
"""

import requests
import time
import cv2
import numpy as np
from io import BytesIO
import threading
import statistics

class StreamPerformanceTester:
    def __init__(self):
        self.frame_times = []
        self.frame_sizes = []
        self.decode_times = []
        self.total_frames = 0
        self.start_time = None
        self.running = False
        
    def test_mjpeg_performance(self, duration=30):
        """测试MJPEG流性能"""
        url = "http://localhost:8080/api/video-stream"
        
        print(f"🚀 开始性能测试: {duration}秒")
        print(f"🔗 测试URL: {url}")
        
        self.start_time = time.time()
        self.running = True
        
        try:
            response = requests.get(url, stream=True, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ HTTP错误: {response.status_code}")
                return False
            
            print("✅ 连接成功，开始接收数据...")
            
            boundary = b'--frame'
            buffer = b''
            
            for chunk in response.iter_content(chunk_size=8192):
                if not self.running:
                    break
                    
                if time.time() - self.start_time > duration:
                    break
                
                if chunk:
                    buffer += chunk
                    
                    # 处理完整的帧
                    while boundary in buffer:
                        parts = buffer.split(boundary, 1)
                        if len(parts) < 2:
                            break
                            
                        frame_data = parts[0]
                        buffer = boundary + parts[1]
                        
                        self._process_frame(frame_data)
            
            self.running = False
            self._print_results()
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def _process_frame(self, frame_data):
        """处理单个帧"""
        try:
            # 查找JPEG数据
            jpeg_start = frame_data.find(b'\r\n\r\n')
            if jpeg_start == -1:
                return
            
            jpeg_data = frame_data[jpeg_start + 4:]
            if len(jpeg_data) < 100:  # 太小的数据跳过
                return
            
            frame_time = time.time()
            
            # 记录帧大小
            self.frame_sizes.append(len(jpeg_data))
            
            # 解码测试
            decode_start = time.time()
            try:
                img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                if img is not None:
                    decode_time = time.time() - decode_start
                    self.decode_times.append(decode_time * 1000)  # 转换为毫秒
                    
                    self.frame_times.append(frame_time)
                    self.total_frames += 1
                    
                    # 每100帧输出一次进度
                    if self.total_frames % 100 == 0:
                        elapsed = frame_time - self.start_time if self.start_time else 0
                        fps = self.total_frames / elapsed if elapsed > 0 else 0
                        avg_size = statistics.mean(self.frame_sizes[-100:]) if self.frame_sizes else 0
                        print(f"📊 进度: {self.total_frames}帧, {fps:.1f}FPS, 平均大小: {avg_size/1024:.1f}KB")
                        
            except Exception as e:
                print(f"⚠️ 解码失败: {e}")
                
        except Exception as e:
            print(f"⚠️ 处理帧失败: {e}")
    
    def _print_results(self):
        """打印测试结果"""
        if not self.frame_times:
            print("❌ 没有收到有效帧")
            return
        
        total_time = self.frame_times[-1] - self.frame_times[0] if len(self.frame_times) > 1 else 0
        avg_fps = len(self.frame_times) / total_time if total_time > 0 else 0
        
        # 计算帧间隔
        intervals = []
        for i in range(1, len(self.frame_times)):
            intervals.append((self.frame_times[i] - self.frame_times[i-1]) * 1000)  # 毫秒
        
        print("\n" + "="*50)
        print("📈 性能测试结果")
        print("="*50)
        print(f"总帧数: {self.total_frames}")
        print(f"测试时长: {total_time:.1f}秒")
        print(f"平均FPS: {avg_fps:.1f}")
        
        if self.frame_sizes:
            avg_size = statistics.mean(self.frame_sizes)
            min_size = min(self.frame_sizes)
            max_size = max(self.frame_sizes)
            print(f"帧大小: 平均{avg_size/1024:.1f}KB, 最小{min_size/1024:.1f}KB, 最大{max_size/1024:.1f}KB")
        
        if intervals:
            avg_interval = statistics.mean(intervals)
            min_interval = min(intervals)
            max_interval = max(intervals)
            print(f"帧间隔: 平均{avg_interval:.1f}ms, 最小{min_interval:.1f}ms, 最大{max_interval:.1f}ms")
        
        if self.decode_times:
            avg_decode = statistics.mean(self.decode_times)
            max_decode = max(self.decode_times)
            print(f"解码时间: 平均{avg_decode:.1f}ms, 最大{max_decode:.1f}ms")
        
        # 延迟评估
        if intervals:
            high_latency_frames = sum(1 for i in intervals if i > 100)  # 超过100ms的帧
            latency_percentage = (high_latency_frames / len(intervals)) * 100
            print(f"高延迟帧(>100ms): {high_latency_frames}/{len(intervals)} ({latency_percentage:.1f}%)")
        
        print("="*50)

def test_backend_status():
    """测试后端状态"""
    try:
        response = requests.get("http://localhost:8080/api/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("📊 后端状态:")
            print(f"  - 流状态: {data['data']['streaming']}")
            print(f"  - 连接客户端: {data['data']['connected_clients']}")
            print(f"  - 帧计数: {data['data']['frame_count']}")
            return data['data']['streaming']
        else:
            print(f"❌ 状态API错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 状态检查失败: {e}")
        return False

def start_stream():
    """启动视频流"""
    try:
        response = requests.post("http://localhost:8080/api/stream/start", timeout=10)
        if response.status_code == 200:
            print("✅ 视频流启动成功")
            return True
        else:
            print(f"❌ 启动失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False

if __name__ == "__main__":
    print("🎯 MJPEG流性能测试工具")
    print("=" * 50)
    
    # 检查后端状态
    print("1. 检查后端状态...")
    streaming = test_backend_status()
    
    if not streaming:
        print("\n2. 启动视频流...")
        if not start_stream():
            print("❌ 无法启动视频流，请检查后端服务")
            exit(1)
        
        # 等待流启动
        print("⏳ 等待视频流启动...")
        time.sleep(3)
    
    # 开始性能测试
    print("\n3. 开始性能测试...")
    tester = StreamPerformanceTester()
    
    try:
        success = tester.test_mjpeg_performance(duration=30)
        if success:
            print("\n✅ 性能测试完成！")
        else:
            print("\n❌ 性能测试失败")
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        tester.running = False 