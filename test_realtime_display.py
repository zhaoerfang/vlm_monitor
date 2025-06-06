#!/usr/bin/env python3
"""
实时显示性能测试工具
专门测试优化后的双流架构性能
"""

import requests
import time
import cv2
import numpy as np
import threading
import statistics
from collections import deque

class RealtimeDisplayTester:
    def __init__(self):
        self.frame_times = deque(maxlen=100)  # 只保留最近100帧
        self.frame_sizes = deque(maxlen=100)
        self.decode_times = deque(maxlen=100)
        self.total_frames = 0
        self.start_time = None
        self.running = False
        self.last_report_time = 0
        
    def test_realtime_performance(self, duration=60):
        """测试实时显示性能"""
        url = "http://localhost:8080/api/video-stream"
        
        print(f"🚀 开始实时显示性能测试: {duration}秒")
        print(f"🔗 测试URL: {url}")
        print("📊 实时性能指标:")
        print("   - 目标: >25fps, <40ms延迟")
        print("   - 帧大小: <50KB")
        print("   - 解码时间: <5ms")
        print("-" * 50)
        
        self.start_time = time.time()
        self.running = True
        self.last_report_time = self.start_time
        
        try:
            response = requests.get(url, stream=True, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ HTTP错误: {response.status_code}")
                return False
            
            print("✅ 连接成功，开始实时性能监控...")
            
            boundary = b'--frame'
            buffer = b''
            
            for chunk in response.iter_content(chunk_size=16384):  # 增大chunk size
                if not self.running:
                    break
                    
                current_time = time.time()
                if current_time - self.start_time > duration:
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
                        
                        self._process_frame_realtime(frame_data, current_time)
            
            self.running = False
            self._print_realtime_results()
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
    
    def _process_frame_realtime(self, frame_data, current_time):
        """实时处理帧"""
        try:
            # 查找JPEG数据
            jpeg_start = frame_data.find(b'\r\n\r\n')
            if jpeg_start == -1:
                return
            
            jpeg_data = frame_data[jpeg_start + 4:]
            if len(jpeg_data) < 100:
                return
            
            # 记录帧大小
            frame_size = len(jpeg_data)
            self.frame_sizes.append(frame_size)
            
            # 解码性能测试
            decode_start = time.time()
            try:
                img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                if img is not None:
                    decode_time = (time.time() - decode_start) * 1000  # 毫秒
                    self.decode_times.append(decode_time)
                    
                    self.frame_times.append(current_time)
                    self.total_frames += 1
                    
                    # 实时报告（每2秒一次）
                    if current_time - self.last_report_time >= 2.0:
                        self._print_realtime_stats(current_time)
                        self.last_report_time = current_time
                        
            except Exception as e:
                print(f"⚠️ 解码失败: {e}")
                
        except Exception as e:
            print(f"⚠️ 处理帧失败: {e}")
    
    def _print_realtime_stats(self, current_time):
        """打印实时统计信息"""
        if len(self.frame_times) < 2:
            return
        
        # 计算最近的FPS
        recent_frames = list(self.frame_times)
        if len(recent_frames) >= 2:
            time_span = recent_frames[-1] - recent_frames[0]
            fps = (len(recent_frames) - 1) / time_span if time_span > 0 else 0
        else:
            fps = 0
        
        # 计算平均帧大小
        avg_size = statistics.mean(self.frame_sizes) if self.frame_sizes else 0
        
        # 计算平均解码时间
        avg_decode = statistics.mean(self.decode_times) if self.decode_times else 0
        
        # 计算延迟（帧间隔）
        if len(recent_frames) >= 2:
            intervals = [(recent_frames[i] - recent_frames[i-1]) * 1000 
                        for i in range(1, len(recent_frames))]
            avg_latency = statistics.mean(intervals) if intervals else 0
        else:
            avg_latency = 0
        
        # 实时状态评估
        fps_status = "✅" if fps >= 25 else "⚠️" if fps >= 15 else "❌"
        latency_status = "✅" if avg_latency <= 40 else "⚠️" if avg_latency <= 80 else "❌"
        size_status = "✅" if avg_size <= 50*1024 else "⚠️" if avg_size <= 100*1024 else "❌"
        decode_status = "✅" if avg_decode <= 5 else "⚠️" if avg_decode <= 10 else "❌"
        
        elapsed = current_time - self.start_time
        print(f"[{elapsed:6.1f}s] {fps_status}FPS:{fps:5.1f} {latency_status}延迟:{avg_latency:5.1f}ms "
              f"{size_status}大小:{avg_size/1024:4.1f}KB {decode_status}解码:{avg_decode:4.1f}ms "
              f"总帧:{self.total_frames}")
    
    def _print_realtime_results(self):
        """打印最终测试结果"""
        if not self.frame_times:
            print("❌ 没有收到有效帧")
            return
        
        frame_list = list(self.frame_times)
        total_time = frame_list[-1] - frame_list[0] if len(frame_list) > 1 else 0
        avg_fps = (len(frame_list) - 1) / total_time if total_time > 0 else 0
        
        # 计算帧间隔统计
        intervals = []
        for i in range(1, len(frame_list)):
            intervals.append((frame_list[i] - frame_list[i-1]) * 1000)
        
        print("\n" + "="*60)
        print("📈 实时显示性能测试结果")
        print("="*60)
        print(f"测试时长: {total_time:.1f}秒")
        print(f"总帧数: {self.total_frames}")
        print(f"平均FPS: {avg_fps:.1f}")
        
        # FPS评估
        if avg_fps >= 25:
            print("✅ FPS评估: 优秀 (≥25fps)")
        elif avg_fps >= 15:
            print("⚠️ FPS评估: 良好 (15-25fps)")
        else:
            print("❌ FPS评估: 需要优化 (<15fps)")
        
        if self.frame_sizes:
            avg_size = statistics.mean(self.frame_sizes)
            max_size = max(self.frame_sizes)
            print(f"帧大小: 平均{avg_size/1024:.1f}KB, 最大{max_size/1024:.1f}KB")
            
            if avg_size <= 50*1024:
                print("✅ 帧大小评估: 优秀 (≤50KB)")
            elif avg_size <= 100*1024:
                print("⚠️ 帧大小评估: 良好 (50-100KB)")
            else:
                print("❌ 帧大小评估: 需要优化 (>100KB)")
        
        if intervals:
            avg_interval = statistics.mean(intervals)
            max_interval = max(intervals)
            min_interval = min(intervals)
            print(f"帧间隔: 平均{avg_interval:.1f}ms, 最小{min_interval:.1f}ms, 最大{max_interval:.1f}ms")
            
            if avg_interval <= 40:
                print("✅ 延迟评估: 优秀 (≤40ms)")
            elif avg_interval <= 80:
                print("⚠️ 延迟评估: 良好 (40-80ms)")
            else:
                print("❌ 延迟评估: 需要优化 (>80ms)")
            
            # 稳定性评估
            jitter = statistics.stdev(intervals) if len(intervals) > 1 else 0
            print(f"帧率稳定性: {jitter:.1f}ms抖动")
            
            if jitter <= 10:
                print("✅ 稳定性评估: 优秀 (≤10ms抖动)")
            elif jitter <= 20:
                print("⚠️ 稳定性评估: 良好 (10-20ms抖动)")
            else:
                print("❌ 稳定性评估: 需要优化 (>20ms抖动)")
        
        if self.decode_times:
            avg_decode = statistics.mean(self.decode_times)
            max_decode = max(self.decode_times)
            print(f"解码性能: 平均{avg_decode:.1f}ms, 最大{max_decode:.1f}ms")
            
            if avg_decode <= 5:
                print("✅ 解码性能评估: 优秀 (≤5ms)")
            elif avg_decode <= 10:
                print("⚠️ 解码性能评估: 良好 (5-10ms)")
            else:
                print("❌ 解码性能评估: 需要优化 (>10ms)")
        
        print("="*60)

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
    print("🎯 实时显示性能测试工具")
    print("=" * 60)
    print("🎮 双流架构测试 - 实时显示优先")
    print("=" * 60)
    
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
    
    # 开始实时性能测试
    print("\n3. 开始实时显示性能测试...")
    tester = RealtimeDisplayTester()
    
    try:
        success = tester.test_realtime_performance(duration=30)
        if success:
            print("\n✅ 实时显示性能测试完成！")
            print("\n💡 优化建议:")
            print("   - 如果FPS<25，考虑降低JPEG质量或分辨率")
            print("   - 如果延迟>40ms，检查网络和编码性能")
            print("   - 如果抖动>20ms，优化帧率控制算法")
        else:
            print("\n❌ 实时显示性能测试失败")
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        tester.running = False 