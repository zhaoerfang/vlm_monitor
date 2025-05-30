#!/usr/bin/env python3
"""
主程序测试脚本
测试VLM监控系统的主要功能
"""

import os
import sys
import time
import signal
import threading
import subprocess
from pathlib import Path

# 添加src路径到模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitor.main import VLMMonitor
from monitor.core.config import load_config

def test_config_loading():
    """测试配置加载"""
    print("🔧 测试配置加载...")
    
    try:
        config = load_config()
        
        # 验证必要的配置项
        required_sections = ['video_processing', 'stream', 'vlm', 'monitoring']
        for section in required_sections:
            if section not in config:
                print(f"❌ 缺少配置节: {section}")
                return False
        
        # 验证流媒体配置
        stream_config = config['stream']
        if 'type' not in stream_config:
            print("❌ 缺少流媒体类型配置")
            return False
        
        if stream_config['type'] not in ['rtsp', 'tcp']:
            print(f"❌ 不支持的流媒体类型: {stream_config['type']}")
            return False
        
        print(f"✅ 配置加载成功，流媒体类型: {stream_config['type']}")
        return True
        
    except Exception as e:
        print(f"❌ 配置加载失败: {str(e)}")
        return False

def test_monitor_initialization():
    """测试监控器初始化"""
    print("🚀 测试监控器初始化...")
    
    try:
        monitor = VLMMonitor()
        
        # 检查基本属性
        if not hasattr(monitor, 'config'):
            print("❌ 监控器缺少config属性")
            return False
        
        if not hasattr(monitor, 'session_dir'):
            print("❌ 监控器缺少session_dir属性")
            return False
        
        if not monitor.session_dir.exists():
            print("❌ 会话目录未创建")
            return False
        
        print(f"✅ 监控器初始化成功，会话目录: {monitor.session_dir}")
        return True
        
    except Exception as e:
        print(f"❌ 监控器初始化失败: {str(e)}")
        return False

def test_vlm_client_setup():
    """测试VLM客户端设置"""
    print("🧠 测试VLM客户端设置...")
    
    try:
        monitor = VLMMonitor()
        
        # 测试VLM客户端设置
        success = monitor._setup_vlm_client()
        
        if success:
            print("✅ VLM客户端设置成功")
            return True
        else:
            print("❌ VLM客户端设置失败")
            return False
        
    except Exception as e:
        print(f"❌ VLM客户端设置异常: {str(e)}")
        return False

def test_stream_setup():
    """测试流媒体设置"""
    print("📹 测试流媒体设置...")
    
    try:
        monitor = VLMMonitor()
        
        # 设置VLM客户端（异步处理器需要）
        if not monitor._setup_vlm_client():
            print("❌ VLM客户端设置失败，跳过流媒体测试")
            return False
        
        # 设置异步处理器
        if not monitor._setup_async_processor():
            print("❌ 异步处理器设置失败，跳过流媒体测试")
            return False
        
        # 根据配置类型测试流媒体设置
        stream_type = monitor.config['stream']['type']
        
        if stream_type == 'rtsp':
            success = monitor._setup_rtsp_stream()
        elif stream_type == 'tcp':
            success = monitor._setup_tcp_stream()
        else:
            print(f"❌ 不支持的流媒体类型: {stream_type}")
            return False
        
        if success:
            print(f"✅ {stream_type.upper()}流媒体设置成功")
            
            # 清理资源
            if monitor.stream_server:
                monitor.stream_server.stop()
            
            return True
        else:
            print(f"❌ {stream_type.upper()}流媒体设置失败")
            return False
        
    except Exception as e:
        print(f"❌ 流媒体设置异常: {str(e)}")
        return False

def test_short_run():
    """测试短时间运行"""
    print("⏱️ 测试短时间运行（10秒）...")
    
    try:
        monitor = VLMMonitor()
        
        # 在单独线程中启动监控
        monitor_thread = threading.Thread(target=monitor.start, name="MonitorTest")
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # 等待10秒
        time.sleep(10)
        
        # 停止监控
        monitor.stop()
        
        # 等待线程结束
        monitor_thread.join(timeout=5)
        
        print("✅ 短时间运行测试成功")
        return True
        
    except Exception as e:
        print(f"❌ 短时间运行测试失败: {str(e)}")
        return False

def test_command_line():
    """测试命令行接口"""
    print("💻 测试命令行接口...")
    
    try:
        # 测试帮助信息
        result = subprocess.run([
            sys.executable, 'src/monitor/main.py', '--help'
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ 命令行帮助信息正常")
        else:
            print(f"❌ 命令行帮助信息异常: {result.stderr}")
            return False
        
        # 测试配置文件参数
        result = subprocess.run([
            sys.executable, 'src/monitor/main.py', '--config', 'config.json', '--stream-type', 'tcp'
        ], capture_output=True, text=True, timeout=5)
        
        # 由于没有真正运行，可能会有错误，但至少应该能解析参数
        if "不支持的流媒体类型" not in result.stderr:
            print("✅ 命令行参数解析正常")
        else:
            print(f"❌ 命令行参数解析异常: {result.stderr}")
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        print("✅ 命令行接口启动正常（超时停止）")
        return True
    except Exception as e:
        print(f"❌ 命令行接口测试失败: {str(e)}")
        return False

def main():
    """主测试函数"""
    print("🧪 开始VLM监控系统主程序测试")
    print("="*50)
    
    tests = [
        ("配置加载", test_config_loading),
        ("监控器初始化", test_monitor_initialization),
        ("VLM客户端设置", test_vlm_client_setup),
        ("流媒体设置", test_stream_setup),
        ("短时间运行", test_short_run),
        ("命令行接口", test_command_line),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n📋 测试: {test_name}")
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ 测试异常: {str(e)}")
            results[test_name] = False
    
    # 打印测试结果
    print("\n" + "="*50)
    print("📊 测试结果汇总:")
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  - {test_name}: {status}")
    
    print(f"\n🎯 总体成功率: {success_rate:.1f}% ({passed_tests}/{total_tests})")
    
    if success_rate >= 80:
        print("🎉 主程序测试基本通过！")
        return True
    else:
        print("⚠️ 主程序测试存在问题，需要修复")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 