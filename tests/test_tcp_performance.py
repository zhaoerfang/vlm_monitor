#!/usr/bin/env python3
"""
TCP视频流性能测试脚本
测试TCP视频流的实际帧率和延迟
"""

import socket
import cv2
import numpy as np
import time
import struct
import threading
from typing import List, Dict, Any

class TCPPerformanceTester:
    def __init__(self, host: str = '172.20.10.4', port: int = 1234):
        self.host = host
        self.port = port
        self.frames_received = 0
        self.bytes_received = 0
        self.start_time = None
        self.frame_times: List[float] = []
        self.frame_sizes: List[int] = []
        self.decode_errors = 0
        self.running = False
        
    def recvall(self, sock: socket.socket, count: int) -> bytes | None:
        """精确接收指定字节数的数据"""
        buf = b''
        while count:
            newbuf = sock.recv(count)
            if not newbuf:
                return None
            buf += newbuf
            count -= len(newbuf)
        return buf
    
    def test_performance(self, duration: int = 30) -> Dict[str, Any]:
        """测试TCP视频流性能"""
        print(f"🚀 开始TCP性能测试 - 连接到 {self.host}:{self.port}")
        print(f"⏱️  测试时长: {duration}秒")
        
        self.running = True
        self.start_time = time.time()
        
        try:
            # 创建socket连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((self.host, self.port))
            print("✅ TCP连接成功")
            
            # 设置接收超时
            sock.settimeout(0.1)
            
            while self.running and (time.time() - self.start_time) < duration:
                try:
                    # 接收帧长度
                    length_bytes = self.recvall(sock, 8)
                    if not length_bytes:
                        print("❌ 接收长度数据失败")
                        break
                    
                    # 解析长度
                    length = struct.unpack('<Q', length_bytes)[0]
                    
                    # 接收JPEG数据
                    jpeg_data = self.recvall(sock, int(length))
                    if not jpeg_data:
                        print("❌ 接收JPEG数据失败")
                        break
                    
                    # 记录接收时间
                    receive_time = time.time()
                    self.frame_times.append(receive_time)
                    self.frame_sizes.append(len(jpeg_data))
                    self.bytes_received += len(jpeg_data) + 8
                    
                    # 尝试解码（测试数据完整性）
                    try:
                        data = np.frombuffer(jpeg_data, dtype='uint8')
                        frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
                        if frame is None:
                            self.decode_errors += 1
                        else:
                            self.frames_received += 1
                    except Exception:
                        self.decode_errors += 1
                    
                    # 每100帧输出一次进度
                    if self.frames_received % 100 == 0:
                        elapsed = time.time() - self.start_time
                        fps = self.frames_received / elapsed if elapsed > 0 else 0
                        print(f"📊 已接收 {self.frames_received} 帧, 当前FPS: {fps:.1f}")
                
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"❌ 接收数据异常: {e}")
                    break
            
            sock.close()
            
        except Exception as e:
            print(f"❌ TCP连接失败: {e}")
            return {}
        
        # 计算统计信息
        return self._calculate_stats()
    
    def _calculate_stats(self) -> Dict[str, Any]:
        """计算性能统计信息"""
        if not self.frame_times or self.start_time is None:
            return {}
        
        total_time = time.time() - self.start_time
        avg_fps = self.frames_received / total_time if total_time > 0 else 0
        
        # 计算帧间隔
        frame_intervals = []
        for i in range(1, len(self.frame_times)):
            interval = self.frame_times[i] - self.frame_times[i-1]
            frame_intervals.append(interval * 1000)  # 转换为毫秒
        
        # 计算统计信息
        stats = {
            'total_time': total_time,
            'frames_received': self.frames_received,
            'decode_errors': self.decode_errors,
            'bytes_received': self.bytes_received,
            'average_fps': avg_fps,
            'average_frame_size': np.mean(self.frame_sizes) if self.frame_sizes else 0,
            'max_frame_size': max(self.frame_sizes) if self.frame_sizes else 0,
            'min_frame_size': min(self.frame_sizes) if self.frame_sizes else 0,
            'bandwidth_mbps': (self.bytes_received * 8) / (total_time * 1024 * 1024) if total_time > 0 else 0,
        }
        
        if frame_intervals:
            stats.update({
                'average_frame_interval_ms': np.mean(frame_intervals),
                'max_frame_interval_ms': max(frame_intervals),
                'min_frame_interval_ms': min(frame_intervals),
                'frame_interval_std_ms': np.std(frame_intervals),
            })
        
        return stats
    
    def print_results(self, stats: Dict[str, Any]):
        """打印测试结果"""
        if not stats:
            print("❌ 没有统计数据")
            return
        
        print("\n" + "="*60)
        print("📊 TCP视频流性能测试结果")
        print("="*60)
        print(f"⏱️  总测试时间: {stats['total_time']:.2f}秒")
        print(f"📦 接收帧数: {stats['frames_received']}")
        print(f"❌ 解码错误: {stats['decode_errors']}")
        print(f"📈 平均FPS: {stats['average_fps']:.2f}")
        print(f"💾 总接收数据: {stats['bytes_received'] / (1024*1024):.2f} MB")
        print(f"🌐 平均带宽: {stats['bandwidth_mbps']:.2f} Mbps")
        print(f"📏 平均帧大小: {stats['average_frame_size']/1024:.1f} KB")
        print(f"📏 最大帧大小: {stats['max_frame_size']/1024:.1f} KB")
        print(f"📏 最小帧大小: {stats['min_frame_size']/1024:.1f} KB")
        
        if 'average_frame_interval_ms' in stats:
            print(f"⏰ 平均帧间隔: {stats['average_frame_interval_ms']:.1f}ms")
            print(f"⏰ 最大帧间隔: {stats['max_frame_interval_ms']:.1f}ms")
            print(f"⏰ 最小帧间隔: {stats['min_frame_interval_ms']:.1f}ms")
            print(f"📊 帧间隔标准差: {stats['frame_interval_std_ms']:.1f}ms")
        
        # 性能评估
        print("\n" + "="*60)
        print("🎯 性能评估")
        print("="*60)
        
        if stats['average_fps'] >= 20:
            print("✅ 帧率优秀 (≥20 FPS)")
        elif stats['average_fps'] >= 15:
            print("⚠️  帧率良好 (15-20 FPS)")
        elif stats['average_fps'] >= 10:
            print("⚠️  帧率一般 (10-15 FPS)")
        else:
            print("❌ 帧率较低 (<10 FPS)")
        
        if stats['decode_errors'] == 0:
            print("✅ 数据完整性优秀 (无解码错误)")
        elif stats['decode_errors'] < stats['frames_received'] * 0.01:
            print("⚠️  数据完整性良好 (<1% 错误)")
        else:
            print("❌ 数据完整性较差 (≥1% 错误)")
        
        if 'frame_interval_std_ms' in stats:
            if stats['frame_interval_std_ms'] < 10:
                print("✅ 帧率稳定性优秀 (标准差<10ms)")
            elif stats['frame_interval_std_ms'] < 20:
                print("⚠️  帧率稳定性良好 (标准差<20ms)")
            else:
                print("❌ 帧率稳定性较差 (标准差≥20ms)")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='TCP视频流性能测试')
    parser.add_argument('--host', default='172.20.10.4', help='TCP服务器地址')
    parser.add_argument('--port', type=int, default=1234, help='TCP服务器端口')
    parser.add_argument('--duration', type=int, default=30, help='测试时长（秒）')
    
    args = parser.parse_args()
    
    tester = TCPPerformanceTester(args.host, args.port)
    stats = tester.test_performance(args.duration)
    tester.print_results(stats)

if __name__ == "__main__":
    main() 