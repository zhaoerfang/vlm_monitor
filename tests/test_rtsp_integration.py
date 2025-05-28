import cv2
import time
import os
import sys
import threading

from monitor.rtsp_server import RTSPServer
from monitor.rtsp_client import RTSPClient

def test_rtsp_server(video_file_path):
    """测试伪RTSP服务器"""
    print("启动伪RTSP服务器...")
    server = RTSPServer(
        video_path=video_file_path,
        port=8554,
        stream_name="test_stream"
    )
    rtsp_url = server.start()
    print(f"RTSP服务已启动: {rtsp_url}")
    return server

def test_rtsp_client(rtsp_url):
    """测试RTSP客户端"""
    print("\n启动RTSP客户端...")
    client = RTSPClient(
        rtsp_url=rtsp_url,
        frame_rate=5,
        timeout=20,
        buffer_size=5
    )
    
    stop_flag = threading.Event()

    def frame_callback(frame):
        """简单的帧回调函数"""
        if frame is None:
            print("Received None frame in callback")
            return True
        try:
            cv2.imshow('Test Stream', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("'q' pressed, stopping client...")
                stop_flag.set()
                return False
        except Exception as e:
            print(f"Error in frame_callback: {e}")
            stop_flag.set()
            return False
        return True
    
    print("开始接收视频流... 按 'q' 在视频窗口停止.")
    try:
        client.run(callback=frame_callback)
    except KeyboardInterrupt:
        print("\n客户端被用户中断 (Ctrl+C)")
    except TimeoutError as e:
        print(f"\n客户端超时: {e}")
    except Exception as e:
        print(f"\n客户端运行时发生错误: {e}")
    finally:
        print("客户端处理循环结束.")
        cv2.destroyAllWindows()

if __name__ == "__main__":
    test_video_relative_path = os.path.join('data', 'test.avi')
    test_video_abs_path = os.path.abspath(test_video_relative_path)

    if not os.path.exists(test_video_abs_path):
        print(f"测试视频文件未找到: {test_video_abs_path}")
        print("请确保 'data/test.avi' 文件存在于项目根目录下的data文件夹中.")
        exit(1)

    print(f"使用测试视频: {test_video_abs_path}")

    server = None
    try:
        # 1. 测试服务器
        server = test_rtsp_server(test_video_abs_path)
        
        # 2. 测试客户端
        print("等待2秒让RTSP服务器完全启动...")
        time.sleep(2)
        test_rtsp_client("rtsp://localhost:8554/test_stream")
        
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
    finally:
        if server:
            print("\n正在停止RTSP服务器...")
            server.stop()
            print("RTSP服务器已停止.")
        print("测试完成.")