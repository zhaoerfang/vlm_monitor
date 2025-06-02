#!/usr/bin/env python3
"""
视频监控系统启动脚本
自动启动TCP视频服务、推理服务、后端API和前端界面
"""

import os
import sys
import time
import signal
import subprocess
import psutil
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/system_startup.log')
    ]
)
logger = logging.getLogger(__name__)

class SystemManager:
    """系统管理器"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.processes: Dict[str, subprocess.Popen] = {}
        self.ports = {
            'tcp_video': 8888,
            'backend': 8080,
            'frontend': 5173,
            'websocket': 8080  # WebSocket使用同一端口
        }
        
        # 确保日志目录存在
        Path('logs').mkdir(exist_ok=True)
        
    def check_port_occupied(self, port: int) -> List[psutil.Process]:
        """检查端口是否被占用"""
        occupied_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port:
                        occupied_processes.append(proc)
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return occupied_processes
    
    def kill_processes_on_port(self, port: int, service_name: str):
        """杀死占用指定端口的进程"""
        processes = self.check_port_occupied(port)
        if processes:
            logger.info(f"🔍 发现 {len(processes)} 个进程占用端口 {port} ({service_name})")
            for proc in processes:
                try:
                    logger.info(f"  - 杀死进程: PID={proc.pid}, 名称={proc.name()}, 命令={' '.join(proc.cmdline()[:3])}")
                    proc.terminate()
                    proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                    try:
                        proc.kill()
                    except psutil.NoSuchProcess:
                        pass
                except Exception as e:
                    logger.warning(f"  - 无法杀死进程 {proc.pid}: {e}")
            
            # 再次检查
            time.sleep(1)
            remaining = self.check_port_occupied(port)
            if remaining:
                logger.warning(f"⚠️ 端口 {port} 仍有 {len(remaining)} 个进程占用")
            else:
                logger.info(f"✅ 端口 {port} 已清理完成")
    
    def kill_related_processes(self):
        """杀死所有相关进程"""
        logger.info("🧹 清理现有进程...")
        
        # 按服务名称查找并杀死进程
        service_patterns = [
            'tcp_video_service.py',
            'vlm-monitor',
            'backend/app.py',
            'vite',
            'npm run dev'
        ]
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.cmdline())
                for pattern in service_patterns:
                    if pattern in cmdline:
                        logger.info(f"  - 杀死相关进程: PID={proc.pid}, 命令={cmdline[:100]}")
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        # 清理端口
        for service, port in self.ports.items():
            self.kill_processes_on_port(port, service)
    
    def check_dependencies(self) -> bool:
        """检查依赖项"""
        logger.info("🔍 检查依赖项...")
        
        # 检查Python包
        try:
            import cv2
            import numpy as np
            import fastapi
            import websockets
            logger.info("✅ Python依赖项检查通过")
        except ImportError as e:
            logger.error(f"❌ Python依赖项缺失: {e}")
            return False
        
        # 检查Node.js和npm
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"✅ Node.js版本: {result.stdout.strip()}")
            else:
                logger.error("❌ Node.js未安装")
                return False
                
            result = subprocess.run(['npm', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"✅ npm版本: {result.stdout.strip()}")
            else:
                logger.error("❌ npm未安装")
                return False
        except FileNotFoundError:
            logger.error("❌ Node.js或npm未安装")
            return False
        
        # 检查前端依赖
        if not Path('frontend/node_modules').exists():
            logger.info("📦 安装前端依赖...")
            try:
                result = subprocess.run(
                    ['npm', 'install'],
                    cwd='frontend',
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    logger.info("✅ 前端依赖安装完成")
                else:
                    logger.error(f"❌ 前端依赖安装失败: {result.stderr}")
                    return False
            except Exception as e:
                logger.error(f"❌ 前端依赖安装异常: {e}")
                return False
        
        # 检查配置文件
        if not Path('config.json').exists():
            logger.error("❌ 配置文件 config.json 不存在")
            return False
        
        logger.info("✅ 所有依赖项检查通过")
        return True
    
    def start_tcp_video_service(self) -> bool:
        """启动TCP视频服务"""
        logger.info("🚀 启动TCP视频服务...")
        
        try:
            cmd = [
                sys.executable, 'tools/tcp_video_service.py',
                '--config', 'config.json'
            ]
            
            if self.debug:
                # 调试模式下显示输出
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
            else:
                # 正常模式下重定向到日志文件
                log_file = open('logs/tcp_video_service.log', 'w')
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )
            
            self.processes['tcp_video'] = process
            
            # 等待服务启动
            time.sleep(3)
            
            if process.poll() is None:
                logger.info(f"✅ TCP视频服务启动成功 (PID: {process.pid})")
                return True
            else:
                logger.error("❌ TCP视频服务启动失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动TCP视频服务异常: {e}")
            return False
    
    def start_inference_service(self) -> bool:
        """启动推理服务"""
        logger.info("🤖 启动推理服务...")
        
        try:
            cmd = ['vlm-monitor', '--config', 'config.json']
            
            if self.debug:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
            else:
                log_file = open('logs/inference_service.log', 'w')
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )
            
            self.processes['inference'] = process
            
            # 等待服务启动
            time.sleep(5)
            
            if process.poll() is None:
                logger.info(f"✅ 推理服务启动成功 (PID: {process.pid})")
                return True
            else:
                logger.error("❌ 推理服务启动失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动推理服务异常: {e}")
            return False
    
    def start_backend_service(self) -> bool:
        """启动后端API服务"""
        logger.info("🔧 启动后端API服务...")
        
        try:
            cmd = [sys.executable, 'backend/app.py']
            
            if self.debug:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
            else:
                log_file = open('logs/backend_service.log', 'w')
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )
            
            self.processes['backend'] = process
            
            # 等待服务启动
            time.sleep(3)
            
            if process.poll() is None:
                logger.info(f"✅ 后端API服务启动成功 (PID: {process.pid})")
                return True
            else:
                logger.error("❌ 后端API服务启动失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动后端API服务异常: {e}")
            return False
    
    def start_frontend_service(self) -> bool:
        """启动前端开发服务"""
        logger.info("🎨 启动前端开发服务...")
        
        try:
            cmd = ['npm', 'run', 'dev']
            
            if self.debug:
                process = subprocess.Popen(
                    cmd,
                    cwd='frontend',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1
                )
            else:
                log_file = open('logs/frontend_service.log', 'w')
                process = subprocess.Popen(
                    cmd,
                    cwd='frontend',
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )
            
            self.processes['frontend'] = process
            
            # 等待服务启动
            time.sleep(5)
            
            if process.poll() is None:
                logger.info(f"✅ 前端开发服务启动成功 (PID: {process.pid})")
                return True
            else:
                logger.error("❌ 前端开发服务启动失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动前端开发服务异常: {e}")
            return False
    
    def monitor_services(self):
        """监控服务状态"""
        logger.info("📊 开始监控服务状态...")
        logger.info("按 Ctrl+C 停止所有服务")
        
        try:
            while True:
                time.sleep(10)
                
                # 检查各服务状态
                for service_name, process in self.processes.items():
                    if process.poll() is not None:
                        logger.warning(f"⚠️ 服务 {service_name} 已停止 (退出码: {process.returncode})")
                
                # 显示端口状态
                if self.debug:
                    for service, port in self.ports.items():
                        processes = self.check_port_occupied(port)
                        if processes:
                            logger.info(f"📊 {service} (端口 {port}): {len(processes)} 个进程")
                        else:
                            logger.warning(f"📊 {service} (端口 {port}): 无进程")
                
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在停止所有服务...")
            self.stop_all_services()
    
    def stop_all_services(self):
        """停止所有服务"""
        logger.info("🛑 停止所有服务...")
        
        for service_name, process in self.processes.items():
            try:
                logger.info(f"  - 停止 {service_name} (PID: {process.pid})")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"  - 强制杀死 {service_name}")
                process.kill()
            except Exception as e:
                logger.warning(f"  - 停止 {service_name} 失败: {e}")
        
        logger.info("✅ 所有服务已停止")
    
    def start_all_services(self) -> bool:
        """启动所有服务"""
        logger.info("🚀 启动视频监控系统...")
        
        # 检查依赖项
        if not self.check_dependencies():
            return False
        
        # 清理现有进程
        self.kill_related_processes()
        
        # 按顺序启动服务
        services = [
            ('TCP视频服务', self.start_tcp_video_service),
            ('推理服务', self.start_inference_service),
            ('后端API服务', self.start_backend_service),
            ('前端开发服务', self.start_frontend_service)
        ]
        
        for service_name, start_func in services:
            if not start_func():
                logger.error(f"❌ {service_name}启动失败，停止启动流程")
                self.stop_all_services()
                return False
            
            # 服务间启动间隔
            time.sleep(2)
        
        logger.info("🎉 所有服务启动完成！")
        logger.info("📱 前端界面: http://localhost:5173")
        logger.info("🔧 后端API: http://localhost:8080")
        logger.info("📹 TCP视频流: tcp://localhost:8888")
        
        return True

def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到信号 {signum}，正在停止系统...")
    if hasattr(signal_handler, 'manager'):
        signal_handler.manager.stop_all_services()
    sys.exit(0)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='视频监控系统启动脚本')
    parser.add_argument('--debug', '-d', action='store_true', help='调试模式（显示详细输出）')
    parser.add_argument('--stop', '-s', action='store_true', help='仅停止现有服务')
    parser.add_argument('--check', '-c', action='store_true', help='仅检查端口占用情况')
    
    args = parser.parse_args()
    
    try:
        manager = SystemManager(debug=args.debug)
        
        # 设置信号处理
        signal_handler.manager = manager
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        if args.check:
            # 仅检查端口状态
            logger.info("🔍 检查端口占用情况...")
            for service, port in manager.ports.items():
                processes = manager.check_port_occupied(port)
                if processes:
                    logger.info(f"📊 {service} (端口 {port}): {len(processes)} 个进程占用")
                    for proc in processes:
                        logger.info(f"  - PID: {proc.pid}, 名称: {proc.name()}")
                else:
                    logger.info(f"📊 {service} (端口 {port}): 空闲")
            return
        
        if args.stop:
            # 仅停止服务
            manager.kill_related_processes()
            return
        
        # 启动所有服务
        success = manager.start_all_services()
        
        if success:
            # 监控服务状态
            manager.monitor_services()
        else:
            logger.error("❌ 系统启动失败")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"程序异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 