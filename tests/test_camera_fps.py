#!/usr/bin/env python3
"""
测试摄像头实际帧数
基于test_tcp_client_origin.py的连接逻辑，但不显示GUI，只统计帧数
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

class CameraFPSTest:
    def __init__(self, host='172.20.10.4', port=1234):
        self.host = host
        self.port = port
        self.frame_count = 0
        self.start_time = None
        self.last_fps_time = None
        self.running = False
        
    def connect(self):
        """连接到摄像头"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
        try:
            print(f"连接到摄像头: {self.host}:{self.port}")
            self.sock.connect((self.host, self.port))
            print("✅ 连接成功")
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False
    
    def test_fps(self, duration=30):
        """测试指定时间内的帧数"""
        if not self.connect():
            return
            
        self.running = True
        self.start_time = time.time()
        self.last_fps_time = self.start_time
        
        print(f"开始测试 {duration} 秒内的帧数...")
        print("按 Ctrl+C 可提前结束测试")
        
        try:
            while self.running and (time.time() - self.start_time) < duration:
                # 接收图像数据的长度  
                length_bytes = recvall(self.sock, 8)  
                
                if not length_bytes:
                    print("服务器未准备好，重新连接...")
                    self.sock.close()  
                    if not self.connect():
                        break
                    time.sleep(2)
                    continue
                    
                # 解析为一个无符号长整数  
                length = struct.unpack('<Q', length_bytes)[0]  
                stringData = recvall(self.sock, int(length))  
                
                if stringData is None:
                    print("接收数据失败")
                    continue
                    
                data = np.frombuffer(stringData, dtype='uint8')  
                
                # 将数据解码为图像（但不显示）
                img = cv2.imdecode(data, 1)
                if img is None:
                    print("图像解码失败")
                    continue
                
                self.frame_count += 1
                current_time = time.time()
                
                # 每5秒显示一次当前FPS
                if current_time - self.last_fps_time >= 5.0:
                    elapsed = current_time - self.start_time
                    if elapsed > 0:
                        current_fps = self.frame_count / elapsed
                        print(f"📊 当前统计: 帧数={self.frame_count}, 耗时={elapsed:.1f}s, 平均FPS={current_fps:.2f}")
                    self.last_fps_time = current_time
                    
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
            print(f"\n🎯 测试结果:")
            print(f"   总帧数: {self.frame_count}")
            print(f"   总时间: {total_time:.2f}s")
            print(f"   平均FPS: {final_fps:.2f}")
            print(f"   帧间隔: {1000/final_fps:.1f}ms")
        else:
            print("测试时间太短，无法计算FPS")

def main():
    tester = CameraFPSTest()
    tester.test_fps(duration=30)  # 测试30秒

if __name__ == "__main__":
    main() 