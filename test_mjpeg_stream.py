#!/usr/bin/env python3
"""
测试MJPEG流的简单脚本
"""

import requests
import time
import cv2
import numpy as np
from io import BytesIO

def test_mjpeg_stream():
    """测试MJPEG流"""
    url = "http://localhost:8080/api/video-stream"
    
    print(f"🔗 测试MJPEG流: {url}")
    
    try:
        # 发送请求
        response = requests.get(url, stream=True, timeout=10)
        
        if response.status_code == 200:
            print("✅ MJPEG流连接成功")
            print(f"Content-Type: {response.headers.get('content-type')}")
            
            # 读取前几帧进行测试
            boundary = None
            frame_count = 0
            max_frames = 5
            
            buffer = b''
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    buffer += chunk
                    
                    # 查找边界
                    if boundary is None:
                        if b'--frame' in buffer:
                            boundary = b'--frame'
                            print(f"📋 找到边界: {boundary}")
                    
                    # 处理帧
                    if boundary and boundary in buffer:
                        parts = buffer.split(boundary)
                        
                        for part in parts[:-1]:  # 保留最后一部分用于下次处理
                            if b'Content-Type: image/jpeg' in part:
                                # 提取JPEG数据
                                jpeg_start = part.find(b'\r\n\r\n')
                                if jpeg_start != -1:
                                    jpeg_data = part[jpeg_start + 4:]
                                    
                                    if len(jpeg_data) > 100:  # 确保有足够的数据
                                        try:
                                            # 尝试解码JPEG
                                            img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                                            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                                            
                                            if img is not None:
                                                frame_count += 1
                                                print(f"📸 成功解码第 {frame_count} 帧: {img.shape}")
                                                
                                                if frame_count >= max_frames:
                                                    print(f"✅ 测试完成，成功接收 {frame_count} 帧")
                                                    return True
                                        except Exception as e:
                                            print(f"⚠️ 解码帧失败: {e}")
                        
                        # 保留最后一部分
                        buffer = boundary + parts[-1] if parts else b''
                    
                    # 防止缓冲区过大
                    if len(buffer) > 1024 * 1024:  # 1MB
                        buffer = buffer[-512 * 1024:]  # 保留后512KB
            
            print(f"⚠️ 流结束，总共接收 {frame_count} 帧")
            return frame_count > 0
            
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            print(f"响应内容: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败：后端服务器未运行")
        return False
    except requests.exceptions.Timeout:
        print("❌ 连接超时")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

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
            return True
        else:
            print(f"❌ 状态API错误: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 状态检查失败: {e}")
        return False

if __name__ == "__main__":
    print("🚀 开始测试MJPEG流...")
    
    # 首先检查后端状态
    print("\n1. 检查后端状态...")
    if not test_backend_status():
        print("请确保后端服务器正在运行: python backend/app.py")
        exit(1)
    
    # 测试MJPEG流
    print("\n2. 测试MJPEG流...")
    success = test_mjpeg_stream()
    
    if success:
        print("\n✅ MJPEG流测试成功！")
        print("💡 现在可以在浏览器中访问: http://localhost:5173")
        print("💡 视频流将通过MJPEG显示，不再依赖WebSocket传输视频数据")
    else:
        print("\n❌ MJPEG流测试失败")
        print("💡 请检查后端服务器是否正确启动视频流") 