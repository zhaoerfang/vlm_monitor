import argparse
import time
import cv2
import logging
import queue
import threading
import concurrent.futures
from .rtsp_server import RTSPServer
from .rtsp_client import RTSPClient
from .qwen_vl_client import QwenVLClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vlm_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VLMVideoAnalyzer:
    def __init__(self, config):
        self.config = config
        self.rtsp_server = None
        self.rtsp_client = None
        self.vl_client = QwenVLClient(
            api_url=config["qwen_api_url"],
            api_key=config["qwen_api_key"]
        )
        self.result_queue = queue.Queue()
        self.frame_buffer = []
        self.batch_size = config.get("batch_size", 3)
        self.frame_counter = 0
        self.processing_max_workers = config.get("processing_max_workers", 2)
        self.processing_executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.processing_max_workers)
        self.qwen_max_workers = config.get("qwen_max_workers", 5)

    def start_rtsp_server(self):
        """启动伪RTSP服务器(开发阶段)"""
        if self.config["use_mock_rtsp"]:
            self.rtsp_server = RTSPServer(
                self.config["mock_video_path"],
                self.config["rtsp_port"],
                self.config["rtsp_stream_name"]
            )
            return self.rtsp_server.start()
        return self.config["rtsp_url"]

    def process_frames(self, frames_to_process, start_frame_idx):
        """批量处理多帧图像"""
        try:
            all_results = self.vl_client.analyze_images(
                frames_to_process,
                tasks=["object_detection"],
                confidence_threshold=self.config["confidence_threshold"],
                max_workers=self.qwen_max_workers 
            )
            
            for idx, results in enumerate(all_results):
                if results and not results.get("error") and "objects" in results:
                    self.result_queue.put((start_frame_idx + idx, results, frames_to_process[idx]))
                elif results and results.get("error"):
                    logger.error(f"Error processing frame {start_frame_idx + idx}: {results.get('error')}")
                else:
                    logger.warning(f"No valid results or objects for frame {start_frame_idx + idx}")
        except Exception as e:
            logger.error(f"批量处理帧时出错 (frames {start_frame_idx} to {start_frame_idx + len(frames_to_process) - 1}): {str(e)}", exc_info=True)

    def frame_callback(self, frame):
        """帧回调函数"""
        current_frame_idx = self.frame_counter
        self.frame_buffer.append((frame, current_frame_idx))
        self.frame_counter += 1
        
        while not self.result_queue.empty():
            processed_frame_idx, results, original_frame_for_result = self.result_queue.get()
            
            visualized = self.vl_client.draw_results(original_frame_for_result, results)
            cv2.imshow("VLM Analysis", visualized)
            object_labels = [obj.get('label', 'N/A') for obj in results.get('objects', [])]
            logger.info(f"帧 {processed_frame_idx} 检测到 {len(results.get('objects', []))} 个对象: {object_labels}")

        if len(self.frame_buffer) >= self.batch_size:
            batch_to_process = self.frame_buffer[:self.batch_size]
            self.frame_buffer = self.frame_buffer[self.batch_size:]
            
            frames_for_api = [item[0] for item in batch_to_process]
            start_idx_of_batch = batch_to_process[0][1]

            self.processing_executor.submit(self.process_frames, frames_for_api, start_idx_of_batch)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            return False
            
        return True

    def run(self):
        """主运行循环"""
        rtsp_url = self.start_rtsp_server()
        logger.info(f"使用RTSP流: {rtsp_url}")
        logger.info(f"分析帧率: {self.config['frame_rate']} FPS")
        logger.info(f"置信度阈值: {self.config['confidence_threshold']}")

        self.rtsp_client = RTSPClient(
            rtsp_url,
            frame_rate=self.config["frame_rate"],
            timeout=self.config["timeout"]
        )

        try:
            self.rtsp_client.run(callback=self.frame_callback)
        except KeyboardInterrupt:
            print("正在停止...")
        finally:
            if self.rtsp_server:
                self.rtsp_server.stop()
            self.processing_executor.shutdown(wait=True)
            logger.info("Processing executor shut down.")
            cv2.destroyAllWindows()

if __name__ == "__main__":
    # 配置参数
    config = {
        "use_mock_rtsp": True,  # 开发阶段使用伪RTSP服务器
        "mock_video_path": "test.mp4",  # 测试视频文件
        "rtsp_port": 8554,
        "rtsp_stream_name": "stream",
        "rtsp_url": "rtsp://real-camera/stream",  # 真实摄像头URL
        "qwen_api_url": "https://api.qwen-vl.example.com/v1/analyze",
        "qwen_api_key": "your_api_key_here",
        "frame_rate": 5,  # 目标帧率(FPS)
        "timeout": 30,  # 超时时间(秒)
        "confidence_threshold": 0.7,  # 置信度阈值
        "batch_size": 3, # Number of frames to batch for VLM processing
        "processing_max_workers": 2, # Max workers for the VLMVideoAnalyzer's processing executor
        "qwen_max_workers": 5 # Max workers for QwenVLClient's ThreadPoolExecutor
    }

    # 从命令行参数覆盖配置
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock_video", help="测试视频文件路径")
    parser.add_argument("--api_key", help="Qwen-VL-Max API密钥")
    parser.add_argument("--real_rtsp", help="使用真实RTSP流URL", action="store_true")
    args = parser.parse_args()

    if args.mock_video:
        config["mock_video_path"] = args.mock_video
    if args.api_key:
        config["qwen_api_key"] = args.api_key
    if args.real_rtsp:
        config["use_mock_rtsp"] = False

    analyzer = VLMVideoAnalyzer(config)
    analyzer.run()