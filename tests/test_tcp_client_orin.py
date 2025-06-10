#!/usr/bin/env python3
"""
TCP摄像头客户端测试脚本（无GUI版本）
专注于测试连接状态和视频流性能
"""

import socket  
import cv2 
import numpy as np  
import time 
import struct
import argparse
  
def recvall(sock, count):  
    buf = b''  
    while count:  
        newbuf = sock.recv(count)  
        if not newbuf:  
            return None  
        buf += newbuf  
        count -= len(newbuf)  
    return buf  

def test_tcp_stream(host='172.20.10.4', port=1234, duration=30, show_gui=False):
    """
    测试TCP视频流
    
    Args:
        host: TCP服务器地址
        port: TCP服务器端口
        duration: 测试时长（秒）
        show_gui: 是否显示GUI（默认False）
    """
    print(f"🚀 开始测试TCP摄像头连接")
    print(f"📡 服务器地址: {host}:{port}")
    print(f"⏱️  测试时长: {duration}秒")
    print(f"🖥️  GUI显示: {'开启' if show_gui else '关闭'}")
    print("-" * 50)
    
    # 统计变量
    frames_received = 0
    bytes_received = 0
    decode_errors = 0
    start_time = time.time()
    last_report_time = start_time
    frame_times = []
    
    # 创建socket连接
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        print(f"🔌 正在连接到 {host}:{port}...")
        sock.connect((host, port))
        print("✅ TCP连接成功！")
        
        # 设置超时
        sock.settimeout(1.0)
        
        while (time.time() - start_time) < duration:
            try:
                # 接收图像数据的长度  
                length_bytes = recvall(sock, 8)  
                
                if not length_bytes:
                    print("⚠️  服务器断开连接，尝试重连...")
                    sock.close()
                    
                    # 重新连接
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
                    sock.connect((host, port))
                    sock.settimeout(1.0)
                    time.sleep(1)
                    continue
                    
                # 解析为一个无符号长整数  
                length = struct.unpack('<Q', length_bytes)[0]  
                stringData = recvall(sock, int(length))  
                
                # 检查stringData是否为None
                if stringData is None:
                    print("⚠️  接收帧数据失败，跳过...")
                    continue
                    
                # 记录接收时间和数据量
                receive_time = time.time()
                frame_times.append(receive_time)
                bytes_received += len(stringData) + 8
                
                # 尝试解码图像（验证数据完整性）
                try:
                    data = np.frombuffer(stringData, dtype='uint8')  
                    img = cv2.imdecode(data, 1)
                    
                    if img is None:
                        decode_errors += 1
                        print("❌ 图像解码失败")
                        continue
                    
                    frames_received += 1
                    
                    # 如果启用GUI，显示图像
                    if show_gui:
                        h, w = img.shape[:2]
                        img_resized = cv2.resize(img, (w//2, h//2))
                        cv2.imshow('TCP Stream Test', img_resized)
                        
                        # 检查退出键
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            print("👋 用户按下'q'键，退出测试")
                            break
                    
                    # 每5秒报告一次进度
                    if receive_time - last_report_time >= 5.0:
                        elapsed = receive_time - start_time
                        fps = frames_received / elapsed if elapsed > 0 else 0
                        bandwidth = (bytes_received * 8) / (elapsed * 1024 * 1024) if elapsed > 0 else 0
                        
                        print(f"📊 进度报告: {frames_received}帧, {fps:.1f}FPS, {bandwidth:.1f}Mbps, 错误:{decode_errors}")
                        last_report_time = receive_time
                        
                except Exception as e:
                    decode_errors += 1
                    print(f"❌ 解码异常: {e}")
                    continue
                    
            except socket.timeout:
                print("⏰ 接收超时，继续等待...")
                continue
            except Exception as e:
                print(f"❌ 接收异常: {e}")
                break
                
    except ConnectionRefusedError:
        print(f"❌ 连接被拒绝: {host}:{port}")
        print("💡 请检查:")
        print("   1. TCP摄像头服务是否运行")
        print("   2. IP地址和端口是否正确")
        print("   3. 网络连接是否正常")
        return False
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
        
    finally:
        sock.close()
        if show_gui:
            cv2.destroyAllWindows()
    
    # 计算最终统计
    total_time = time.time() - start_time
    print("\n" + "="*60)
    print("📊 测试结果统计")
    print("="*60)
    print(f"⏱️  总测试时间: {total_time:.2f}秒")
    print(f"📦 接收帧数: {frames_received}")
    print(f"❌ 解码错误: {decode_errors}")
    print(f"💾 总接收数据: {bytes_received / (1024*1024):.2f} MB")
    
    if total_time > 0:
        avg_fps = frames_received / total_time
        bandwidth = (bytes_received * 8) / (total_time * 1024 * 1024)
        print(f"📈 平均FPS: {avg_fps:.2f}")
        print(f"🌐 平均带宽: {bandwidth:.2f} Mbps")
        
        if frames_received > 0:
            avg_frame_size = bytes_received / frames_received
            print(f"📏 平均帧大小: {avg_frame_size/1024:.1f} KB")
    
    # 计算帧间隔统计
    if len(frame_times) > 1:
        intervals = []
        for i in range(1, len(frame_times)):
            interval = (frame_times[i] - frame_times[i-1]) * 1000  # 转换为毫秒
            intervals.append(interval)
        
        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            max_interval = max(intervals)
            min_interval = min(intervals)
            print(f"⏰ 平均帧间隔: {avg_interval:.1f}ms")
            print(f"⏰ 最大帧间隔: {max_interval:.1f}ms")
            print(f"⏰ 最小帧间隔: {min_interval:.1f}ms")
    
    # 性能评估
    print("\n" + "="*60)
    print("🎯 性能评估")
    print("="*60)
    
    if frames_received == 0:
        print("❌ 未接收到任何帧")
        return False
    
    success_rate = (frames_received / (frames_received + decode_errors)) * 100 if (frames_received + decode_errors) > 0 else 0
    avg_fps = frames_received / total_time if total_time > 0 else 0
    
    if avg_fps >= 20:
        print("✅ 帧率优秀 (≥20 FPS)")
    elif avg_fps >= 15:
        print("⚠️  帧率良好 (15-20 FPS)")
    elif avg_fps >= 10:
        print("⚠️  帧率一般 (10-15 FPS)")
    else:
        print("❌ 帧率较低 (<10 FPS)")
    
    if success_rate >= 99:
        print("✅ 数据完整性优秀 (≥99%)")
    elif success_rate >= 95:
        print("⚠️  数据完整性良好 (≥95%)")
    else:
        print("❌ 数据完整性较差 (<95%)")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='TCP摄像头连接测试')
    parser.add_argument('--host', default='172.20.10.4', help='TCP服务器地址')
    parser.add_argument('--port', type=int, default=1234, help='TCP服务器端口')
    parser.add_argument('--duration', type=int, default=30, help='测试时长（秒）')
    parser.add_argument('--gui', action='store_true', help='显示GUI窗口')
    
    args = parser.parse_args()
    
    success = test_tcp_stream(
        host=args.host,
        port=args.port,
        duration=args.duration,
        show_gui=args.gui
    )
    
    if success:
        print("\n🎉 测试完成！")
    else:
        print("\n💥 测试失败！")
        exit(1)

if __name__ == "__main__":
    main() 