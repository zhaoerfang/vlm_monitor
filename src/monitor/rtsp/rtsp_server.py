import subprocess
import argparse
import os

class GstRTSPServer:
    """基于GStreamer的RTSP服务器实现"""
    
    def __init__(self, video_path, port=8554, stream_name="stream"):
        self.video_path = os.path.abspath(video_path)
        self.port = port
        self.stream_name = stream_name
        self.process = None

    def start(self):
        """启动RTSP服务器"""
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"视频文件不存在: {self.video_path}")

        command = [
            "ffmpeg",
            "-re",
            "-stream_loop", "-1",
            "-i", self.video_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-b:v", "1000k",
            "-g", "50",
            "-an",
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            f"rtsp://0.0.0.0:{self.port}/{self.stream_name}"
        ]
        print("执行命令:", " ".join(command))
        
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return f"rtsp://localhost:{self.port}/{self.stream_name}"

    def stop(self):
        """停止RTSP服务器"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None

class RTSPServer(GstRTSPServer):
    """兼容旧接口的RTSP服务器"""
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RTSP视频流服务器")
    parser.add_argument("--video_path", help="输入视频文件路径")
    parser.add_argument("--port", type=int, default=8554, help="RTSP服务器端口")
    parser.add_argument("--stream", default="stream", help="流名称")
    
    args = parser.parse_args()
    
    server = RTSPServer(args.video_path, args.port, args.stream)
    try:
        url = server.start()
        print(f"RTSP服务器已启动，流地址: {url}")
        print("按Ctrl+C停止服务器...")
        while True:
            pass
    except KeyboardInterrupt:
        server.stop()
        print("RTSP服务器已停止")
    except Exception as e:
        print(f"错误: {str(e)}")
        server.stop()