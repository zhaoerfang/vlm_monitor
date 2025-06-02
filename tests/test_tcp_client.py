#!/usr/bin/env python3
"""
TCP客户端测试脚本
用于测试TCP视频服务是否正常发送数据
"""

import socket
import struct
import time
import cv2
import numpy as np

def test_tcp_connection():
    host = 'localhost'
    port = 1234
    
    try:
        # 连接到TCP服务器
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        print(f"✅ 成功连接到TCP服务器 {host}:{port}")
        
        frame_count = 0
        max_frames = 5
        
        while frame_count < max_frames:
            try:
                # 接收数据长度（8字节，小端序）
                length_bytes = sock.recv(8)
                if len(length_bytes) != 8:
                    print(f"❌ 接收长度数据失败，只收到 {len(length_bytes)} 字节")
                    break
                
                # 解析长度
                length = struct.unpack('<Q', length_bytes)[0]
                print(f"📏 数据长度: {length} 字节")
                
                if length > 100 * 1024 * 1024:  # 100MB限制
                    print(f"❌ 数据长度异常: {length} bytes")
                    break
                
                # 接收JPEG数据
                jpeg_data = b''
                remaining = length
                while remaining > 0:
                    chunk = sock.recv(min(remaining, 8192))
                    if not chunk:
                        print("❌ 连接断开")
                        return
                    jpeg_data += chunk
                    remaining -= len(chunk)
                
                print(f"📦 接收到JPEG数据: {len(jpeg_data)} 字节")
                
                # 尝试解码图像
                try:
                    data = np.frombuffer(jpeg_data, dtype='uint8')
                    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        height, width = frame.shape[:2]
                        print(f"🖼️  成功解码图像: {width}x{height}")
                        frame_count += 1
                    else:
                        print("❌ 图像解码失败")
                        
                except Exception as e:
                    print(f"❌ 图像解码异常: {e}")
                    
            except socket.timeout:
                print("⏰ 接收数据超时")
                break
            except Exception as e:
                print(f"❌ 接收数据异常: {e}")
                break
        
        print(f"✅ 测试完成，总共接收到 {frame_count} 帧")
        
    except Exception as e:
        print(f"❌ TCP连接测试失败: {e}")
    finally:
        try:
            sock.close()
        except:
            pass

if __name__ == "__main__":
    test_tcp_connection() 