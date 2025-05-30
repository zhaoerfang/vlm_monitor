#!/usr/bin/env python3
"""
VLM视频监控主程序
支持RTSP和TCP两种流媒体输入，基于配置文件运行
"""

import os
import sys
import time
import signal
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 添加当前目录到Python路径
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

from monitor.core.config import load_config
from monitor.rtsp.rtsp_server import RTSPServer
from monitor.rtsp.rtsp_client import RTSPClient
from monitor.rtsp.rtsp_utils import detect_rtsp_fps
from monitor.tcp.tcp_video_server import TCPVideoServer
from monitor.tcp.tcp_client import TCPVideoClient
from monitor.vlm.vlm_client import DashScopeVLMClient
from monitor.vlm.async_video_processor import AsyncVideoProcessor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('vlm_monitor.log')
    ]
)
logger = logging.getLogger(__name__)

class VLMMonitor:
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化VLM监控器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认搜索
        """
        # 加载配置
        self.config = load_config(Path(config_path) if config_path else None)
        
        # 设置日志级别
        log_level = self.config.get('monitoring', {}).get('log_level', 'INFO')
        logging.getLogger().setLevel(getattr(logging, log_level))
        
        # 初始化组件
        self.vlm_client = None
        self.processor = None
        self.stream_server = None
        self.stream_client = None
        self.running = False
        
        # 输出目录
        self.output_dir = Path(self.config.get('monitoring', {}).get('output_dir', 'output'))
        self.output_dir.mkdir(exist_ok=True)
        
        # 创建会话目录
        session_name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session_dir = self.output_dir / session_name
        self.session_dir.mkdir(exist_ok=True)
        
        logger.info(f"VLM监控器初始化完成，会话目录: {self.session_dir}")

    def _setup_vlm_client(self):
        """设置VLM客户端"""
        try:
            vlm_config = self.config['vlm']
            self.vlm_client = DashScopeVLMClient(
                model=vlm_config['model']
            )
            
            if not self.vlm_client.api_key:
                raise ValueError("VLM客户端无法获取API密钥")
            
            logger.info(f"✅ VLM客户端已初始化，模型: {vlm_config['model']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ VLM客户端初始化失败: {str(e)}")
            return False

    def _setup_async_processor(self):
        """设置异步视频处理器"""
        try:
            # 确保VLM客户端已初始化
            if self.vlm_client is None:
                logger.error("VLM客户端未初始化")
                return False
                
            video_config = self.config['video_processing']
            vlm_config = self.config['vlm']
            
            # 根据流媒体类型确定原始帧率
            stream_config = self.config['stream']
            if stream_config['type'] == 'rtsp':
                if stream_config['rtsp']['use_local_server']:
                    original_fps = self.config['rtsp']['default_fps']
                else:
                    # 检测RTSP流帧率
                    original_fps = detect_rtsp_fps(stream_config['rtsp']['url'], self.config)
            else:  # TCP
                original_fps = stream_config['tcp']['fps']
            
            self.processor = AsyncVideoProcessor(
                vlm_client=self.vlm_client,
                temp_dir=str(self.session_dir),
                target_video_duration=video_config['target_video_duration'],
                frames_per_second=video_config['frames_per_second'],
                original_fps=original_fps,
                max_concurrent_inferences=vlm_config['max_concurrent_inferences']
            )
            
            logger.info(f"✅ 异步视频处理器已初始化，原始帧率: {original_fps}fps")
            return True
            
        except Exception as e:
            logger.error(f"❌ 异步视频处理器初始化失败: {str(e)}")
            return False

    def _setup_rtsp_stream(self):
        """设置RTSP流"""
        try:
            stream_config = self.config['stream']
            rtsp_config = stream_config['rtsp']
            
            if rtsp_config['use_local_server']:
                # 启动本地RTSP服务器
                local_config = rtsp_config['local_server']
                self.stream_server = RTSPServer(
                    video_path=local_config['video_file'],
                    port=local_config['port'],
                    stream_name=local_config['stream_name']
                )
                rtsp_url = self.stream_server.start()
                logger.info(f"✅ 本地RTSP服务器已启动: {rtsp_url}")
                
                # 等待服务器启动
                time.sleep(2)
            else:
                rtsp_url = rtsp_config['url']
                logger.info(f"使用外部RTSP流: {rtsp_url}")
            
            # 创建RTSP客户端
            rtsp_client_config = self.config['rtsp']
            self.stream_client = RTSPClient(
                rtsp_url=rtsp_url,
                frame_rate=5,  # 客户端目标帧率
                timeout=rtsp_client_config['connection_timeout'],
                buffer_size=rtsp_client_config['client_buffer_size']
            )
            
            logger.info(f"✅ RTSP客户端已创建")
            return True
            
        except Exception as e:
            logger.error(f"❌ RTSP流设置失败: {str(e)}")
            return False

    def _setup_tcp_stream(self):
        """设置TCP流"""
        try:
            stream_config = self.config['stream']
            tcp_config = stream_config['tcp']
            
            # 不再启动内置TCP服务器，假设外部TCP服务器已经运行
            logger.info(f"连接到外部TCP视频服务器: {tcp_config['host']}:{tcp_config['port']}")
            
            # 创建TCP客户端
            self.stream_client = TCPVideoClient(
                host=tcp_config['host'],
                port=tcp_config['port'],
                frame_rate=5,  # 客户端目标帧率
                timeout=10,
                buffer_size=100
            )
            
            logger.info(f"✅ TCP客户端已创建")
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
                # TCP客户端
                self.stream_client.disconnect()
            else:
                # 通用停止方法
                if hasattr(self.stream_client, 'running'):
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