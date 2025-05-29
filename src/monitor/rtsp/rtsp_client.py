import cv2
import time
import argparse
import queue
import threading
import logging
from typing import Callable, Optional, Dict, Any
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)

class RTSPClient:
    def __init__(self, rtsp_url, frame_rate=5, timeout=10, buffer_size=10):
        self.rtsp_url = rtsp_url
        self.frame_rate = frame_rate
        self.timeout = timeout
        self.cap = None
        self.last_frame_time = 0
        self.frame_interval = 1.0 / frame_rate
        self.frame_queue = queue.Queue(maxsize=buffer_size)
        self.stop_event = threading.Event()
        
        # 新增：原始流信息
        self.original_fps = None
        self.original_width = None
        self.original_height = None
        self.total_frames_received = 0
        self.start_timestamp = None
        
        # 帧时间戳记录
        self.frame_timestamps = []

    def connect(self):
        """连接到RTSP流"""
        self.cap = cv2.VideoCapture(self.rtsp_url)
        if not self.cap.isOpened():
            raise ConnectionError(f"无法连接到RTSP流: {self.rtsp_url}")
            
        # 获取原始流信息
        self.original_fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.original_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.original_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        logger.info(f"RTSP流信息: {self.original_width}x{self.original_height}, "
                   f"原始帧率: {self.original_fps:.2f}fps, 目标帧率: {self.frame_rate}fps")
        
        if self.start_timestamp is None:
            self.start_timestamp = time.time()

    def get_stream_info(self) -> Dict[str, Any]:
        """获取流信息"""
        return {
            'original_fps': self.original_fps,
            'target_fps': self.frame_rate,
            'width': self.original_width,
            'height': self.original_height,
            'total_frames_received': self.total_frames_received,
            'start_timestamp': self.start_timestamp
        }

    def read_frame(self):
        """读取下一帧图像"""
        if self.cap is None:
            return None
            
        current_time = time.time()
        if current_time - self.last_frame_time < self.frame_interval:
            return None

        ret, frame = self.cap.read()
        if not ret:
            # 尝试重新连接
            logger.warning("读取帧失败，尝试重新连接...")
            self.cap.release()
            time.sleep(1)
            self.connect()
            return None

        self.last_frame_time = current_time
        self.total_frames_received += 1
        
        # 记录帧时间戳（相对于开始时间的秒数）
        if self.start_timestamp is not None:
            relative_timestamp = current_time - self.start_timestamp
            self.frame_timestamps.append(relative_timestamp)
        else:
            relative_timestamp = 0.0
        
        # 添加帧元数据
        frame_info = {
            'frame': frame,
            'timestamp': current_time,
            'relative_timestamp': relative_timestamp,
            'frame_number': self.total_frames_received
        }
        
        if self.total_frames_received % 100 == 0:
            logger.info(f"已接收 {self.total_frames_received} 帧, "
                       f"当前时间戳: {relative_timestamp:.2f}s")
        
        return frame_info

    def _frame_reader(self):
        """独立线程读取帧到队列"""
        self.connect()
        while not self.stop_event.is_set():
            frame_info = self.read_frame()
            if frame_info is not None:
                try:
                    self.frame_queue.put(frame_info, timeout=1)
                except queue.Full:
                    continue

    def run(self, callback=None, batch_size=1):
        """持续读取帧并处理"""
        reader_thread = threading.Thread(target=self._frame_reader)
        reader_thread.start()
        start_time = time.time()
        
        try:
            while not self.stop_event.is_set():
                if time.time() - start_time > self.timeout:
                    raise TimeoutError("RTSP客户端超时")

                frame_infos = []
                for _ in range(batch_size):
                    try:
                        frame_infos.append(self.frame_queue.get(timeout=1))
                    except queue.Empty:
                        break

                if frame_infos and callback:
                    # 为了兼容性，如果batch_size=1，只传递帧数据
                    if batch_size == 1:
                        if not callback(frame_infos[0]['frame']):
                            self.stop_event.set()
                            break
                    else:
                        if not callback(frame_infos):
                            self.stop_event.set()
                            break

                if not callback:
                    for frame_info in frame_infos:
                        cv2.imshow('RTSP Stream', frame_info['frame'])
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            self.stop_event.set()
                            break
        finally:
            self.stop_event.set()
            reader_thread.join()
            if self.cap is not None:
                self.cap.release()
            cv2.destroyAllWindows()
            
            logger.info(f"RTSP客户端停止，总共接收 {self.total_frames_received} 帧")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTSP客户端")
    parser.add_argument("rtsp_url", help="RTSP流地址")
    parser.add_argument("--frame_rate", type=int, default=5, 
                       help="目标帧率(帧/秒)")
    parser.add_argument("--timeout", type=int, default=10,
                       help="连接超时时间(秒)")
    
    args = parser.parse_args()
    
    client = RTSPClient(args.rtsp_url, args.frame_rate, args.timeout)
    try:
        client.run()
    except Exception as e:
        print(f"错误: {str(e)}")