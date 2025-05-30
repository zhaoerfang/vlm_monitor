#!/usr/bin/env python3
"""
独立的TCP视频流服务器
持续循环播放视频文件，模拟摄像头TCP流
"""

import os
import sys
import time
import signal
import logging
import argparse
from pathlib import Path
from typing import Optional

from monitor.core.config import load_config
from monitor.tcp.tcp_video_server import TCPVideoServer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('log/tcp_video_service.log')
    ]
)
logger = logging.getLogger(__name__)

class TCPVideoService:
    def __init__(self, config_path: Optional[str] = None, video_file: Optional[str] = None, 
                 port: Optional[int] = None, fps: Optional[float] = None):
        """
        初始化TCP视频服务
        
        Args:
            config_path: 配置文件路径
            video_file: 视频文件路径（覆盖配置）
            port: TCP端口（覆盖配置）
            fps: 帧率（覆盖配置）
        """
        # 加载配置
        self.config = load_config(Path(config_path) if config_path else None)
        
        # 获取TCP配置
        tcp_config = self.config['stream']['tcp']
        
        # 使用参数覆盖配置
        self.video_file = video_file or tcp_config['video_file']
        self.port = port or tcp_config['port']
        self.fps = fps or tcp_config['fps']
        
        # 验证视频文件
        if not Path(self.video_file).exists():
            raise FileNotFoundError(f"视频文件不存在: {self.video_file}")
        
        self.server = None
        self.running = False
        
        logger.info(f"TCP视频服务初始化:")
        logger.info(f"  - 视频文件: {self.video_file}")
        logger.info(f"  - 端口: {self.port}")
        logger.info(f"  - 帧率: {self.fps}fps")

    def start(self):
        """启动TCP视频服务"""
        try:
            logger.info("🚀 启动TCP视频流服务...")
            
            # 创建TCP视频服务器
            self.server = TCPVideoServer(
                video_path=self.video_file,
                port=self.port,
                fps=self.fps
            )
            
            # 启动服务器
            tcp_url = self.server.start()
            self.running = True
            
            logger.info(f"✅ TCP视频流服务已启动: {tcp_url}")
            logger.info("📺 视频将持续循环播放，等待客户端连接...")
            
            # 主循环 - 监控服务状态
            try:
                while self.running:
                    time.sleep(5)  # 每5秒检查一次状态
                    
                    # 获取服务器状态
                    status = self.server.get_status()
                    if status['clients_count'] > 0:
                        logger.info(f"📊 服务状态: 连接客户端 {status['clients_count']} 个, "
                                  f"当前帧 {status['current_frame']}/{status['total_frames']}")
                    
            except KeyboardInterrupt:
                logger.info("收到中断信号，正在停止服务...")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 启动TCP视频服务失败: {str(e)}")
            return False

    def stop(self):
        """停止TCP视频服务"""
        logger.info("🛑 停止TCP视频流服务...")
        
        self.running = False
        
        if self.server:
            self.server.stop()
        
        logger.info("✅ TCP视频流服务已停止")

def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到信号 {signum}，正在停止服务...")
    if hasattr(signal_handler, 'service'):
        signal_handler.service.stop()
    sys.exit(0)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='TCP视频流服务器 - 持续循环播放视频')
    parser.add_argument('--config', '-c', type=str, help='配置文件路径')
    parser.add_argument('--video', '-v', type=str, help='视频文件路径')
    parser.add_argument('--port', '-p', type=int, help='TCP端口')
    parser.add_argument('--fps', '-f', type=float, help='发送帧率')
    parser.add_argument('--daemon', '-d', action='store_true', help='后台运行模式')
    
    args = parser.parse_args()
    
    try:
        # 创建服务
        service = TCPVideoService(
            config_path=args.config,
            video_file=args.video,
            port=args.port,
            fps=args.fps
        )
        
        # 设置信号处理
        signal_handler.service = service
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        if args.daemon:
            logger.info("🔄 后台运行模式")
        
        # 启动服务
        success = service.start()
        
        if success:
            logger.info("TCP视频流服务正常结束")
        else:
            logger.error("TCP视频流服务异常结束")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"程序异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'service' in locals():
            service.stop()

if __name__ == "__main__":
    main() 