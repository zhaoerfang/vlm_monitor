#!/usr/bin/env python3
"""
简化的视频监控系统启动脚本
支持传统模式和后端视频客户端模式
"""

import os
import sys
import time
import signal
import subprocess
import psutil
import argparse
import logging
import json
from pathlib import Path
from typing import Optional

# 配置日志
Path('logs').mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/system_startup.log')
    ]
)
logger = logging.getLogger(__name__)

class SimpleSystemManager:
    def __init__(self, test_mode: bool = False, backend_client_mode: bool = False):
        self.test_mode = test_mode
        self.backend_client_mode = backend_client_mode
        self.processes = {}
        
        # 从配置文件读取TCP端口
        self.tcp_port = self._load_tcp_port()
        self.ports = [self.tcp_port, 8080, 5173]  # TCP视频、后端、前端端口
        
    def _load_tcp_port(self) -> int:
        """从配置文件加载TCP端口"""
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            tcp_port = config['stream']['tcp']['port']
            logger.info(f"从配置文件读取TCP端口: {tcp_port}")
            return tcp_port
        except Exception as e:
            logger.warning(f"读取配置文件失败，使用默认TCP端口8888: {e}")
            return 8888
    
    def _update_config_for_backend_client(self):
        """更新配置文件以使用后端视频客户端模式"""
        if not self.backend_client_mode:
            return True
            
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 启用后端视频客户端模式
            config['stream']['tcp']['use_backend_client'] = True
            
            # 保存更新的配置，确保保持原有格式
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2, separators=(',', ': '))
            
            logger.info("✅ 配置文件已更新为后端视频客户端模式")
            return True
        except Exception as e:
            logger.error(f"更新配置文件失败: {e}")
            return False
    
    def _restore_config_for_traditional_mode(self):
        """恢复配置文件为传统模式"""
        if self.backend_client_mode:
            return True
            
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 禁用后端视频客户端模式
            config['stream']['tcp']['use_backend_client'] = False
            
            # 保存更新的配置，确保保持原有格式
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2, separators=(',', ': '))
            
            logger.info("✅ 配置文件已恢复为传统模式")
            return True
        except Exception as e:
            logger.error(f"恢复配置文件失败: {e}")
            return False
        
    def kill_port_processes(self, port: int):
        """杀死占用指定端口的进程"""
        killed = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port:
                        logger.info(f"杀死端口 {port} 进程: PID={proc.pid}, 名称={proc.name()}")
                        proc.terminate()
                        proc.wait(timeout=3)
                        killed.append(proc.pid)
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
        return killed
    
    def cleanup_ports(self):
        """清理所有相关端口"""
        logger.info(f"🧹 清理端口占用: {self.ports}...")
        for port in self.ports:
            self.kill_port_processes(port)
        time.sleep(1)
    
    def start_service(self, name: str, cmd: list, cwd: Optional[str] = None, wait_time: int = 3):
        """启动服务"""
        logger.info(f"🚀 启动{name}...")
        
        log_file = open(f'logs/{name.lower().replace(" ", "_")}.log', 'w')
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
        
        self.processes[name] = process
        time.sleep(wait_time)
        
        if process.poll() is None:
            logger.info(f"✅ {name}启动成功 (PID: {process.pid})")
            return True
        else:
            logger.error(f"❌ {name}启动失败")
            return False
    
    def start_all(self):
        """启动所有服务"""
        if self.backend_client_mode:
            logger.info("🚀 启动视频监控系统（后端视频客户端模式）...")
        else:
            logger.info("🚀 启动视频监控系统（传统模式）...")
        
        # 0. 更新配置文件
        if self.backend_client_mode:
            if not self._update_config_for_backend_client():
                return False
        else:
            if not self._restore_config_for_traditional_mode():
                return False
        
        # 1. 清理端口
        self.cleanup_ports()
        
        # 获取配置文件的绝对路径
        config_path = os.path.abspath('config.json')
        
        # 2. 启动TCP视频服务（测试模式）
        if self.test_mode:
            if not self.start_service(
                "TCP_video_service", 
                [sys.executable, 'tools/tcp_video_service.py', '--config', config_path]
            ):
                return False
            time.sleep(2)  # 等待TCP服务启动
        
        # 3. 根据模式选择启动顺序
        if self.backend_client_mode:
            # 后端视频客户端模式：先启动后端服务，再启动推理服务
            if not self.start_service(
                "Backend_service",
                [sys.executable, 'backend/app.py']
            ):
                return False
            
            time.sleep(3)  # 等待后端服务完全启动
            
            if not self.start_service(
                "Inference_service",
                ['vlm-monitor', '--config', config_path]
            ):
                return False
        else:
            # 传统模式：先启动推理服务，再启动后端服务
            if not self.start_service(
                "Inference_service",
                ['vlm-monitor', '--config', config_path]
            ):
                return False
            
            if not self.start_service(
                "Backend_service",
                [sys.executable, 'backend/app.py']
            ):
                return False
        
        # 4. 启动前端服务
        if not self.start_service(
            "Frontend_service",
            ['npm', 'run', 'dev'],
            cwd='frontend',
            wait_time=5
        ):
            return False
        
        logger.info("🎉 所有服务启动完成！")
        logger.info("📱 前端界面: http://localhost:5173")
        logger.info("🔧 后端API: http://localhost:8080")
        if self.test_mode:
            logger.info(f"📹 TCP视频流: tcp://localhost:{self.tcp_port}")
        
        if self.backend_client_mode:
            logger.info("🔄 架构模式: 后端作为唯一TCP客户端，推理服务通过后端获取视频流")
        else:
            logger.info("🔄 架构模式: 传统模式，后端和推理服务分别连接TCP")
        
        return True
    
    def stop_all(self):
        """停止所有服务"""
        logger.info("🛑 停止所有服务...")
        
        for name, process in self.processes.items():
            try:
                logger.info(f"  - 停止 {name}")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                logger.warning(f"停止 {name} 失败: {e}")
        
        logger.info("✅ 所有服务已停止")
    
    def monitor(self):
        """监控服务状态"""
        logger.info("📊 监控服务状态... (按 Ctrl+C 停止)")
        
        try:
            while True:
                time.sleep(10)
                # 检查服务状态
                for name, process in self.processes.items():
                    if process.poll() is not None:
                        logger.warning(f"⚠️ {name} 已停止")
        except KeyboardInterrupt:
            self.stop_all()

def signal_handler(signum, frame):
    """信号处理"""
    if hasattr(signal_handler, 'manager'):
        signal_handler.manager.stop_all()
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description='简化的视频监控系统启动脚本')
    parser.add_argument('--test', '-t', action='store_true', help='测试模式（启动TCP视频服务）')
    parser.add_argument('--stop', '-s', action='store_true', help='仅清理端口')
    parser.add_argument('--backend-client', '-b', action='store_true', 
                       help='后端视频客户端模式（解决TCP连接冲突）')
    
    args = parser.parse_args()
    
    manager = SimpleSystemManager(test_mode=args.test, backend_client_mode=args.backend_client)
    signal_handler.manager = manager
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if args.stop:
        manager.cleanup_ports()
        return
    
    if manager.start_all():
        manager.monitor()
    else:
        logger.error("❌ 系统启动失败")
        manager.stop_all()
        sys.exit(1)

if __name__ == "__main__":
    main() 