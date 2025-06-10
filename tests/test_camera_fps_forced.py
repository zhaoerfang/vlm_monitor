#!/usr/bin/env python3
"""
测试摄像头强制高帧率
不进行帧率限制，尽可能快地接收帧
"""

import cv2
import socket
import numpy as np  
import time 
import struct
import threading
  
def recvall(sock, count):  
    buf = b''  
    while count:  
        newbuf = sock.recv(count)  
        if not newbuf:  
            return None  
        buf += newbuf  
        count -= len(newbuf)  
    return buf  

class ForcedFPSTest:
    def __init__(self, host='172.20.10.4', port=1234):
        self.host = host
        self.port = port
        self.frame_count = 0
        self.start_time = None
        self.last_fps_time = None
        self.running = False
        self.frame_intervals = []
        
    def connect(self):
        """连接到摄像头"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
        # 设置socket选项以获得最佳性能
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 禁用Nagle算法
        self.sock.settimeout(1.0)  # 1秒超时
        
        try:
            print(f"连接到摄像头: {self.host}:{self.port}")
            self.sock.connect((self.host, self.port))
            print("✅ 连接成功")
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def test_max_fps(self, duration=30):
        """测试最大可能的帧数"""
        if not self.connect():
            return
            
        self.running = True
        self.start_time = time.time()
        self.last_fps_time = self.start_time
        last_frame_time = self.start_time
        
        print(f"开始测试最大帧率 {duration} 秒...")
        print("尽可能快地接收所有帧，不进行任何限制")
        print("按 Ctrl+C 可提前结束测试")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        try:
            while self.running and (time.time() - self.start_time) < duration:
                current_time = time.time()
                
                try:
                    # 接收图像数据的长度  
                    length_bytes = recvall(self.sock, 8)  
                    
                    if not length_bytes:
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            print(f"连续 {consecutive_errors} 次接收失败，重新连接...")
                            self.sock.close()  
                            if not self.connect():
                                break
                            consecutive_errors = 0
                        continue
                    
                    consecutive_errors = 0  # 成功接收，重置错误计数
                    
                    # 解析为一个无符号长整数  
                    length = struct.unpack('<Q', length_bytes)[0]  
                    stringData = recvall(self.sock, int(length))  
                    
                    if stringData is None:
                        print("接收数据失败")
                        continue
                        
                    data = np.frombuffer(stringData, dtype='uint8')  
                    
                    # 快速验证是否为有效JPEG（不解码以节省时间）
                    if len(data) > 2 and data[0] == 0xFF and data[1] == 0xD8:
                        self.frame_count += 1
                        
                        # 记录帧间隔
                        frame_interval = current_time - last_frame_time
                        self.frame_intervals.append(frame_interval * 1000)  # 转换为毫秒
                        last_frame_time = current_time
                        
                        # 每秒显示一次当前FPS
                        if current_time - self.last_fps_time >= 1.0:
                            elapsed = current_time - self.start_time
                            if elapsed > 0:
                                current_fps = self.frame_count / elapsed
                                recent_intervals = self.frame_intervals[-10:] if len(self.frame_intervals) >= 10 else self.frame_intervals
                                avg_interval = sum(recent_intervals) / len(recent_intervals) if recent_intervals else 0
                                
                                print(f"📊 当前统计: 帧数={self.frame_count}, 耗时={elapsed:.1f}s, "
                                      f"平均FPS={current_fps:.2f}, 最近10帧平均间隔={avg_interval:.1f}ms")
                            self.last_fps_time = current_time
                    else:
                        print("接收到的数据不是有效的JPEG格式")
                        
                except socket.timeout:
                    # 超时不是错误，继续尝试
                    continue
                except Exception as e:
                    consecutive_errors += 1
                    if consecutive_errors <= 3:  # 只记录前几次错误
                        print(f"接收异常: {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        print(f"连续错误过多，尝试重连...")
                        break
                        
        except KeyboardInterrupt:
            print("\n用户中断测试")
        except Exception as e:
            print(f"❌ 测试出错: {e}")
        finally:
            self.running = False
            self.sock.close()
            
        # 计算最终结果
        total_time = time.time() - self.start_time
        if total_time > 0:
            final_fps = self.frame_count / total_time
            
            print(f"\n🎯 最大帧率测试结果:")
            print(f"   总帧数: {self.frame_count}")
            print(f"   总时间: {total_time:.2f}s")
            print(f"   平均FPS: {final_fps:.2f}")
            print(f"   平均帧间隔: {1000/final_fps:.1f}ms")
            
            if self.frame_intervals:
                min_interval = min(self.frame_intervals)
                max_interval = max(self.frame_intervals)
                avg_interval = sum(self.frame_intervals) / len(self.frame_intervals)
                
                print(f"   帧间隔统计: 最小={min_interval:.1f}ms, 最大={max_interval:.1f}ms, 平均={avg_interval:.1f}ms")
                print(f"   理论最大FPS: {1000/min_interval:.2f}")
                
                # 分析帧间隔分布
                fast_frames = len([i for i in self.frame_intervals if i < 50])  # 小于50ms的帧
                slow_frames = len([i for i in self.frame_intervals if i > 500])  # 大于500ms的帧
                
                print(f"   快速帧(<50ms): {fast_frames}/{len(self.frame_intervals)} ({fast_frames/len(self.frame_intervals)*100:.1f}%)")
                print(f"   慢速帧(>500ms): {slow_frames}/{len(self.frame_intervals)} ({slow_frames/len(self.frame_intervals)*100:.1f}%)")
        else:
            print("测试时间太短，无法计算FPS")

def main():
    tester = ForcedFPSTest(host='localhost', port=1234)
    tester.test_max_fps(duration=30)  # 测试30秒

if __name__ == "__main__":
    main() 