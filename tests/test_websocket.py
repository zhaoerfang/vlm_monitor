#!/usr/bin/env python3
"""
WebSocket测试脚本
用于测试视频流功能
"""

import asyncio
import websockets
import json
import time

async def test_websocket():
    uri = "ws://localhost:8080/ws"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket连接成功")
            
            # 发送启动视频流请求
            start_message = {
                "type": "start_stream",
                "data": {},
                "timestamp": time.time()
            }
            
            await websocket.send(json.dumps(start_message))
            print("📤 发送启动视频流请求")
            
            # 接收消息
            frame_count = 0
            timeout_count = 0
            max_timeout = 10
            
            while timeout_count < max_timeout:
                try:
                    # 设置超时时间
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(message)
                    
                    message_type = data.get("type")
                    if message_type == "video_frame":
                        frame_count += 1
                        frame_data = data.get("data", {})
                        frame_number = frame_data.get("frame_number", 0)
                        print(f"📹 收到视频帧 #{frame_number} (总计: {frame_count})")
                        
                        # 收到5帧后停止
                        if frame_count >= 5:
                            print("✅ 成功接收到视频帧，测试完成")
                            break
                    else:
                        print(f"📨 收到消息: {message_type} - {data.get('data', {}).get('message', '')}")
                    
                    timeout_count = 0  # 重置超时计数
                    
                except asyncio.TimeoutError:
                    timeout_count += 1
                    print(f"⏰ 等待消息超时 ({timeout_count}/{max_timeout})")
                    
            if frame_count == 0:
                print("❌ 没有收到视频帧")
            else:
                print(f"✅ 总共收到 {frame_count} 个视频帧")
                
    except Exception as e:
        print(f"❌ WebSocket测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket()) 