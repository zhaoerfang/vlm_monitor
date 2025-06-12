#!/usr/bin/env python3
"""
MCP 日志查看工具
用于查看所有 MCP 相关的日志文件
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

def get_logs_dir():
    """获取日志目录路径"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    return project_root / 'logs'

def list_mcp_logs():
    """列出所有 MCP 相关的日志文件"""
    logs_dir = get_logs_dir()
    if not logs_dir.exists():
        print(f"❌ 日志目录不存在: {logs_dir}")
        return []
    
    # MCP 相关的日志文件模式
    mcp_patterns = [
        'mcp_camera_client.log',
        'mcp_camera_server.log', 
        'mcp_camera_inference.log',
        'mcp_inference_service.log'
    ]
    
    mcp_logs = []
    for pattern in mcp_patterns:
        log_file = logs_dir / pattern
        if log_file.exists():
            stat = log_file.stat()
            mcp_logs.append({
                'file': log_file,
                'name': pattern,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime)
            })
    
    return mcp_logs

def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def show_log_list():
    """显示 MCP 日志文件列表"""
    logs = list_mcp_logs()
    
    if not logs:
        print("📝 未找到 MCP 相关的日志文件")
        return
    
    print("📋 MCP 相关日志文件:")
    print("-" * 80)
    print(f"{'序号':<4} {'文件名':<30} {'大小':<10} {'最后修改时间':<20}")
    print("-" * 80)
    
    for i, log in enumerate(logs, 1):
        print(f"{i:<4} {log['name']:<30} {format_size(log['size']):<10} {log['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("-" * 80)

def tail_log(log_file, lines=50):
    """显示日志文件的最后几行"""
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            
        if len(all_lines) <= lines:
            print(f"📄 显示 {log_file.name} 的全部内容 ({len(all_lines)} 行):")
        else:
            print(f"📄 显示 {log_file.name} 的最后 {lines} 行:")
        
        print("=" * 80)
        
        start_index = max(0, len(all_lines) - lines)
        for line in all_lines[start_index:]:
            print(line.rstrip())
            
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 读取日志文件失败: {e}")

def follow_log(log_file):
    """实时跟踪日志文件"""
    try:
        print(f"🔍 实时跟踪 {log_file.name} (按 Ctrl+C 停止)")
        print("=" * 80)
        
        with open(log_file, 'r', encoding='utf-8') as f:
            # 移动到文件末尾
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    print(line.rstrip())
                else:
                    import time
                    time.sleep(0.1)
                    
    except KeyboardInterrupt:
        print("\n⏹️ 停止跟踪日志")
    except Exception as e:
        print(f"❌ 跟踪日志失败: {e}")

def search_logs(keyword, case_sensitive=False):
    """在所有 MCP 日志中搜索关键词"""
    logs = list_mcp_logs()
    
    if not logs:
        print("📝 未找到 MCP 相关的日志文件")
        return
    
    print(f"🔍 在 MCP 日志中搜索关键词: '{keyword}'")
    if not case_sensitive:
        print("(不区分大小写)")
    print("=" * 80)
    
    total_matches = 0
    
    for log in logs:
        try:
            with open(log['file'], 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            matches = []
            for i, line in enumerate(lines, 1):
                search_line = line if case_sensitive else line.lower()
                search_keyword = keyword if case_sensitive else keyword.lower()
                
                if search_keyword in search_line:
                    matches.append((i, line.rstrip()))
            
            if matches:
                print(f"\n📄 {log['name']} ({len(matches)} 个匹配):")
                print("-" * 60)
                for line_num, line_content in matches:
                    print(f"{line_num:>6}: {line_content}")
                total_matches += len(matches)
                
        except Exception as e:
            print(f"❌ 搜索 {log['name']} 失败: {e}")
    
    print("=" * 80)
    print(f"🎯 总共找到 {total_matches} 个匹配")

def main():
    parser = argparse.ArgumentParser(description='MCP 日志查看工具')
    parser.add_argument('--list', '-l', action='store_true', help='列出所有 MCP 日志文件')
    parser.add_argument('--tail', '-t', type=str, help='显示指定日志文件的最后几行')
    parser.add_argument('--lines', '-n', type=int, default=50, help='显示的行数 (默认: 50)')
    parser.add_argument('--follow', '-f', type=str, help='实时跟踪指定日志文件')
    parser.add_argument('--search', '-s', type=str, help='在所有 MCP 日志中搜索关键词')
    parser.add_argument('--case-sensitive', '-c', action='store_true', help='区分大小写搜索')
    parser.add_argument('--all', '-a', action='store_true', help='显示所有 MCP 日志的最后几行')
    
    args = parser.parse_args()
    
    if args.list:
        show_log_list()
    elif args.tail:
        logs = list_mcp_logs()
        log_file = None
        for log in logs:
            if args.tail in log['name']:
                log_file = log['file']
                break
        
        if log_file:
            tail_log(log_file, args.lines)
        else:
            print(f"❌ 未找到匹配的日志文件: {args.tail}")
            print("可用的日志文件:")
            show_log_list()
    elif args.follow:
        logs = list_mcp_logs()
        log_file = None
        for log in logs:
            if args.follow in log['name']:
                log_file = log['file']
                break
        
        if log_file:
            follow_log(log_file)
        else:
            print(f"❌ 未找到匹配的日志文件: {args.follow}")
            print("可用的日志文件:")
            show_log_list()
    elif args.search:
        search_logs(args.search, args.case_sensitive)
    elif args.all:
        logs = list_mcp_logs()
        for log in logs:
            print(f"\n📄 {log['name']}:")
            tail_log(log['file'], args.lines)
    else:
        show_log_list()
        print("\n💡 使用示例:")
        print("  python tools/view_mcp_logs.py --list                    # 列出所有日志文件")
        print("  python tools/view_mcp_logs.py --tail client             # 查看客户端日志")
        print("  python tools/view_mcp_logs.py --follow server           # 实时跟踪服务端日志")
        print("  python tools/view_mcp_logs.py --search '摄像头控制'      # 搜索关键词")
        print("  python tools/view_mcp_logs.py --all                     # 显示所有日志的最后几行")

if __name__ == "__main__":
    main() 