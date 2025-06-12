#!/usr/bin/env python3
"""
ASR客户端测试脚本
用于测试ASR服务器的功能
"""

import requests
import json
import time
import argparse
from typing import Dict, Any

def send_question(server_url: str, question: str) -> Dict[str, Any]:
    """
    发送问题到ASR服务器
    
    Args:
        server_url: ASR服务器URL
        question: 用户问题
        
    Returns:
        服务器响应
    """
    try:
        response = requests.post(
            f"{server_url}/asr",
            json={"question": question},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"请求失败: {str(e)}"
        }

def get_current_question(server_url: str) -> Dict[str, Any]:
    """
    获取当前问题
    
    Args:
        server_url: ASR服务器URL
        
    Returns:
        当前问题信息
    """
    try:
        response = requests.get(
            f"{server_url}/question/current",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"请求失败: {str(e)}"
        }

def clear_question(server_url: str) -> Dict[str, Any]:
    """
    清除当前问题
    
    Args:
        server_url: ASR服务器URL
        
    Returns:
        操作结果
    """
    try:
        response = requests.post(
            f"{server_url}/question/clear",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"请求失败: {str(e)}"
        }

def check_health(server_url: str) -> Dict[str, Any]:
    """
    检查服务器健康状态
    
    Args:
        server_url: ASR服务器URL
        
    Returns:
        健康状态信息
    """
    try:
        response = requests.get(
            f"{server_url}/health",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"请求失败: {str(e)}"
        }

def get_stats(server_url: str) -> Dict[str, Any]:
    """
    获取服务器统计信息
    
    Args:
        server_url: ASR服务器URL
        
    Returns:
        统计信息
    """
    try:
        response = requests.get(
            f"{server_url}/stats",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"请求失败: {str(e)}"
        }

def interactive_mode(server_url: str):
    """交互模式"""
    print(f"🎤 ASR客户端测试工具")
    print(f"服务器: {server_url}")
    print("命令:")
    print("  send <问题>  - 发送问题")
    print("  get         - 获取当前问题")
    print("  clear       - 清除当前问题")
    print("  health      - 检查健康状态")
    print("  stats       - 获取统计信息")
    print("  quit        - 退出")
    print()
    
    while True:
        try:
            command = input(">>> ").strip()
            
            if not command:
                continue
                
            if command.lower() in ['quit', 'exit', 'q']:
                print("👋 再见!")
                break
                
            parts = command.split(' ', 1)
            cmd = parts[0].lower()
            
            if cmd == 'send':
                if len(parts) < 2:
                    print("❌ 请提供问题内容: send <问题>")
                    continue
                    
                question = parts[1]
                print(f"📤 发送问题: {question}")
                result = send_question(server_url, question)
                
                if result.get('success'):
                    print(f"✅ 问题已发送")
                    data = result.get('data', {})
                    print(f"   时间戳: {data.get('timestamp', 'N/A')}")
                else:
                    print(f"❌ 发送失败: {result.get('error', 'Unknown error')}")
                    
            elif cmd == 'get':
                print("📥 获取当前问题...")
                result = get_current_question(server_url)
                
                if result.get('success'):
                    data = result.get('data', {})
                    if data.get('has_question'):
                        print(f"✅ 当前问题: {data.get('question')}")
                        print(f"   时间戳: {data.get('timestamp', 'N/A')}")
                    else:
                        print("ℹ️ 当前没有问题")
                        if data.get('message'):
                            print(f"   说明: {data.get('message')}")
                else:
                    print(f"❌ 获取失败: {result.get('error', 'Unknown error')}")
                    
            elif cmd == 'clear':
                print("🗑️ 清除当前问题...")
                result = clear_question(server_url)
                
                if result.get('success'):
                    data = result.get('data', {})
                    cleared_question = data.get('cleared_question')
                    if cleared_question:
                        print(f"✅ 已清除问题: {cleared_question}")
                    else:
                        print("✅ 问题已清除（原本没有问题）")
                else:
                    print(f"❌ 清除失败: {result.get('error', 'Unknown error')}")
                    
            elif cmd == 'health':
                print("🏥 检查健康状态...")
                result = check_health(server_url)
                
                if result.get('success'):
                    data = result.get('data', {})
                    print(f"✅ 服务器健康")
                    print(f"   状态: {data.get('status', 'N/A')}")
                    print(f"   时间戳: {data.get('timestamp', 'N/A')}")
                    print(f"   有问题: {data.get('current_question', False)}")
                else:
                    print(f"❌ 健康检查失败: {result.get('error', 'Unknown error')}")
                    
            elif cmd == 'stats':
                print("📊 获取统计信息...")
                result = get_stats(server_url)
                
                if result.get('success'):
                    data = result.get('data', {})
                    print(f"✅ 统计信息:")
                    print(f"   服务器状态: {data.get('server_status', 'N/A')}")
                    print(f"   当前有问题: {data.get('current_question_exists', False)}")
                    print(f"   问题时间戳: {data.get('question_timestamp', 'N/A')}")
                    print(f"   问题超时时间: {data.get('question_timeout_seconds', 'N/A')}秒")
                    print(f"   最大问题长度: {data.get('max_question_length', 'N/A')}字符")
                    print(f"   运行时间: {data.get('uptime_seconds', 0):.1f}秒")
                else:
                    print(f"❌ 获取统计信息失败: {result.get('error', 'Unknown error')}")
                    
            else:
                print(f"❌ 未知命令: {cmd}")
                print("输入 'quit' 退出")
                
        except KeyboardInterrupt:
            print("\n👋 再见!")
            break
        except Exception as e:
            print(f"❌ 错误: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='ASR客户端测试工具')
    parser.add_argument('--server', '-s', type=str, default='http://localhost:8081',
                       help='ASR服务器URL (默认: http://localhost:8081)')
    parser.add_argument('--question', '-q', type=str, help='直接发送问题')
    parser.add_argument('--get', action='store_true', help='获取当前问题')
    parser.add_argument('--clear', action='store_true', help='清除当前问题')
    parser.add_argument('--health', action='store_true', help='检查健康状态')
    parser.add_argument('--stats', action='store_true', help='获取统计信息')
    
    args = parser.parse_args()
    
    server_url = args.server.rstrip('/')
    
    # 检查服务器连接
    print(f"🔗 连接到ASR服务器: {server_url}")
    health_result = check_health(server_url)
    if not health_result.get('success'):
        print(f"❌ 无法连接到ASR服务器: {health_result.get('error')}")
        print("请确保ASR服务器正在运行")
        return
    
    print("✅ 服务器连接正常")
    
    # 执行命令
    if args.question:
        print(f"📤 发送问题: {args.question}")
        result = send_question(server_url, args.question)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.get:
        print("📥 获取当前问题...")
        result = get_current_question(server_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.clear:
        print("🗑️ 清除当前问题...")
        result = clear_question(server_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.health:
        print("🏥 检查健康状态...")
        result = check_health(server_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    elif args.stats:
        print("📊 获取统计信息...")
        result = get_stats(server_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    else:
        # 进入交互模式
        interactive_mode(server_url)

if __name__ == "__main__":
    main() 