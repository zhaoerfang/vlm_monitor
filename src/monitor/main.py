#!/usr/bin/env python3
"""
VLM视频监控主程序
支持RTSP和TCP视频流，可选择直接TCP连接或通过后端服务获取视频流
"""

import os
import sys
import time
import signal
import logging
import threading
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from monitor.core.config import load_config
from monitor.rtsp.rtsp_server import RTSPServer
from monitor.rtsp.rtsp_client import RTSPClient
from monitor.rtsp.rtsp_utils import detect_rtsp_fps
from monitor.tcp.tcp_video_server import TCPVideoServer
from monitor.tcp.tcp_client import TCPVideoClient
from monitor.tcp.tcp_utils import create_tcp_client_config, detect_tcp_fps
from monitor.vlm.vlm_client import DashScopeVLMClient
from monitor.vlm.async_video_processor import AsyncVideoProcessor
from monitor.vlm.backend_video_client import BackendVideoClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/vlm_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

class VLMMonitor:
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化VLM监控系统
        
        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        self.config = load_config(Path(config_path) if config_path else None)
        
        # 创建会话目录
        self.session_dir = self._create_session_dir()
        
        # 初始化组件
        self.vlm_client = None
        self.processor = None
        self.stream_client = None
        self.stream_server = None
        
        # 运行状态
        self.running = False
        
        logger.info(f"VLM监控系统初始化完成")
        logger.info(f"会话目录: {self.session_dir}")
        logger.info(f"配置文件: {config_path or '默认配置'}")

    def _create_session_dir(self) -> Path:
        """创建会话目录"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = Path("tmp") / f"session_{timestamp}"
        session_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"创建会话目录: {session_dir}")
        return session_dir

    def _setup_vlm_client(self):
        """设置VLM客户端"""
        try:
            vlm_config = self.config['vlm']
            self.vlm_client = DashScopeVLMClient(
                api_key=vlm_config.get('api_key'),
                model=vlm_config.get('model', 'qwen-vl-max')
            )
            logger.info(f"✅ VLM客户端已创建: {vlm_config.get('model', 'qwen-vl-max')}")
            return True
        except Exception as e:
            logger.error(f"❌ VLM客户端创建失败: {str(e)}")
            return False

    def _setup_async_processor(self):
        """设置异步视频处理器"""
        try:
            video_config = self.config.get('video_processing', {})
            vlm_config = self.config.get('vlm', {})
            
            self.processor = AsyncVideoProcessor(
                vlm_client=self.vlm_client,
                temp_dir=str(self.session_dir),
                target_video_duration=video_config.get('target_video_duration'),
                frames_per_second=video_config.get('frames_per_second'),
                original_fps=video_config.get('default_fps'),
                max_concurrent_inferences=vlm_config.get('max_concurrent_inferences')
            )
            
            logger.info("✅ 异步视频处理器已创建")
            return True
        except Exception as e:
            logger.error(f"❌ 异步视频处理器创建失败: {str(e)}")
            return False

    def _setup_rtsp_stream(self):
        """设置RTSP流"""
        try:
            stream_config = self.config['stream']
            rtsp_config = stream_config['rtsp']
            
            # 创建RTSP客户端
            self.stream_client = RTSPClient(
                rtsp_url=rtsp_config['url'],
                frame_rate=rtsp_config.get('frame_rate', 5),
                buffer_size=rtsp_config.get('buffer_size', 10),
                timeout=rtsp_config.get('timeout', 30)
            )
            
            logger.info(f"✅ RTSP客户端已创建: {rtsp_config['url']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ RTSP流设置失败: {str(e)}")
            return False

    def _setup_tcp_stream(self):
        """设置TCP流"""
        try:
            stream_config = self.config['stream']
            tcp_config = stream_config['tcp']
            
            # 检查是否使用后端视频客户端
            use_backend_client = tcp_config.get('use_backend_client', False)
            
            if use_backend_client:
                # 使用后端视频客户端
                backend_url = tcp_config.get('backend_url', 'http://localhost:8080')
                frame_rate = tcp_config.get('frame_rate', 5)
                
                logger.info(f"使用后端视频客户端: {backend_url}")
                
                self.stream_client = BackendVideoClient(
                    backend_url=backend_url,
                    frame_rate=frame_rate,
                    timeout=tcp_config.get('connection_timeout', 10)
                )
                
                logger.info(f"✅ 后端视频客户端已创建，帧率: {frame_rate}fps")
            else:
                # 直接TCP连接
                logger.info(f"直接连接TCP视频服务器: {tcp_config['host']}:{tcp_config['port']}")
                
                # 创建TCP客户端配置（包含动态帧率检测）
                client_config = create_tcp_client_config(
                    host=tcp_config['host'],
                    port=tcp_config['port'],
                    config=self.config
                )
                
                # 创建TCP客户端
                self.stream_client = TCPVideoClient(
                    host=client_config['host'],
                    port=client_config['port'],
                    frame_rate=int(client_config['frame_rate']),  # 使用动态检测的帧率
                    timeout=client_config['timeout'],
                    buffer_size=client_config['buffer_size']
                )
                
                logger.info(f"✅ TCP客户端已创建，使用帧率: {client_config['frame_rate']:.2f}fps")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ TCP流设置失败: {str(e)}")
            return False

    def _frame_callback(self, frame):
        """帧处理回调函数"""
        if not self.running:
            return False
        
        try:
            # 确保处理器已初始化
            if self.processor is None:
                logger.error("异步处理器未初始化")
                return False
                
            # 将帧发送到异步处理器
            current_time = time.time()
            self.processor.add_frame(frame, current_time)
            return True
            
        except Exception as e:
            logger.error(f"帧处理失败: {str(e)}")
            return False

    def _result_handler(self):
        """结果处理线程"""
        result_count = 0
        
        while self.running:
            try:
                # 确保处理器已初始化
                if self.processor is None:
                    logger.error("异步处理器未初始化")
                    break
                    
                # 获取推理结果
                result = self.processor.get_result(timeout=1.0)
                if result:
                    result_count += 1
                    
                    # 保存结果
                    if self.config.get('monitoring', {}).get('save_results', True):
                        result_file = self.session_dir / f"result_{result_count:04d}.json"
                        import json
                        with open(result_file, 'w', encoding='utf-8') as f:
                            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
                    
                    # 打印结果摘要
                    video_info = result.get('video_info', {})
                    inference_duration = result.get('inference_duration', 0)
                    result_text = result.get('result', '')
                    
                    logger.info(f"🎯 推理结果 #{result_count}:")
                    logger.info(f"  - 视频: {os.path.basename(result.get('video_path', 'N/A'))}")
                    logger.info(f"  - 帧数: {video_info.get('frame_count', 'N/A')}")
                    logger.info(f"  - 推理耗时: {inference_duration:.2f}s")
                    logger.info(f"  - 结果长度: {len(result_text) if result_text else 0} 字符")
                    
                    if result_text:
                        # 尝试解析JSON结果
                        try:
                            import json
                            parsed_result = json.loads(result_text)
                            people_count = parsed_result.get('people_count', 0)
                            summary = parsed_result.get('summary', 'N/A')
                            logger.info(f"  - 检测到人数: {people_count}")
                            logger.info(f"  - 场景摘要: {summary}")
                        except:
                            logger.info(f"  - 结果预览: {result_text[:100]}...")
                
            except Exception as e:
                if self.running:
                    logger.error(f"结果处理失败: {str(e)}")
                time.sleep(0.1)

    def start(self):
        """启动监控"""
        logger.info("🚀 启动VLM视频监控...")
        
        # 1. 设置VLM客户端
        if not self._setup_vlm_client():
            return False
        
        # 2. 设置异步处理器
        if not self._setup_async_processor():
            return False
        
        # 3. 设置流媒体
        stream_type = self.config['stream']['type']
        if stream_type == 'rtsp':
            if not self._setup_rtsp_stream():
                return False
        elif stream_type == 'tcp':
            if not self._setup_tcp_stream():
                return False
        else:
            logger.error(f"❌ 不支持的流媒体类型: {stream_type}")
            return False
        
        # 4. 启动异步处理器
        if self.processor is None:
            logger.error("异步处理器未初始化")
            return False
        self.processor.start()
        
        # 5. 启动结果处理线程
        result_thread = threading.Thread(target=self._result_handler, name="ResultHandler")
        result_thread.daemon = True
        result_thread.start()
        
        # 6. 开始接收视频流
        self.running = True
        logger.info(f"✅ 开始接收 {stream_type.upper()} 视频流...")
        
        try:
            # 确保流客户端已初始化
            if self.stream_client is None:
                logger.error("流客户端未初始化")
                return False
                
            # 在单独线程中运行流客户端
            client_thread = threading.Thread(
                target=lambda: self.stream_client.run(callback=self._frame_callback),
                name="StreamClient"
            )
            client_thread.daemon = True
            client_thread.start()
            
            # 主线程等待
            while self.running:
                time.sleep(1)
                
                # 检查客户端线程状态
                if not client_thread.is_alive():
                    logger.warning("流客户端线程已停止")
                    break
            
            return True
            
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在停止...")
            return True
        except Exception as e:
            logger.error(f"❌ 监控运行失败: {str(e)}")
            return False

    def stop(self):
        """停止监控"""
        logger.info("🛑 停止VLM视频监控...")
        
        self.running = False
        
        # 停止异步处理器
        if self.processor:
            self.processor.stop()
        
        # 停止流服务器
        if self.stream_server:
            self.stream_server.stop()
        
        # 断开流客户端
        if self.stream_client:
            if hasattr(self.stream_client, 'stop_event'):
                # RTSP客户端
                self.stream_client.stop_event.set()
            elif hasattr(self.stream_client, 'disconnect'):
                # TCP客户端或后端视频客户端
                self.stream_client.disconnect()
            else:
                # 通用停止方法
                self.stream_client.running = False
        
        logger.info(f"✅ 监控已停止，会话数据保存在: {self.session_dir}")

def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到信号 {signum}，正在停止监控...")
    if hasattr(signal_handler, 'monitor'):
        signal_handler.monitor.stop()
    sys.exit(0)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='VLM视频监控系统')
    parser.add_argument('--config', '-c', type=str, help='配置文件路径')
    parser.add_argument('--stream-type', choices=['rtsp', 'tcp'], help='强制指定流媒体类型')
    parser.add_argument('--output-dir', '-o', type=str, help='输出目录')
    
    args = parser.parse_args()
    
    try:
        # 创建监控器
        monitor = VLMMonitor(config_path=args.config)
        
        # 覆盖配置
        if args.stream_type:
            monitor.config['stream']['type'] = args.stream_type
            logger.info(f"强制使用流媒体类型: {args.stream_type}")
        
        if args.output_dir:
            monitor.output_dir = Path(args.output_dir)
            monitor.output_dir.mkdir(exist_ok=True)
            logger.info(f"使用输出目录: {args.output_dir}")
        
        # 设置信号处理
        signal_handler.monitor = monitor
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 启动监控
        success = monitor.start()
        
        if success:
            logger.info("监控正常结束")
        else:
            logger.error("监控异常结束")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"程序异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'monitor' in locals():
            monitor.stop()

if __name__ == "__main__":
    main() 