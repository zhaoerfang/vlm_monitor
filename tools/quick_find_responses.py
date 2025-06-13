#!/usr/bin/env python3
"""
快速查找tmp目录中包含非空response字段的inference_result.json文件

使用方法:
    python quick_find_responses.py [session_pattern] [--count-only]
    
参数:
    session_pattern: 可选，指定session的模式，默认为所有session
    --count-only: 只显示统计信息，不显示详细内容
                    
示例:
    python quick_find_responses.py
    python quick_find_responses.py "session_20250612_*"
    python quick_find_responses.py --count-only
"""

import os
import json
import glob
import sys
from pathlib import Path
from collections import defaultdict


def quick_scan_for_responses(tmp_dir: str, session_pattern: str = "session_*"):
    """
    快速扫描包含response字段的文件
    
    Args:
        tmp_dir: tmp目录路径
        session_pattern: session目录的匹配模式
        
    Returns:
        统计信息字典
    """
    stats = {
        'total_sessions': 0,
        'sessions_with_responses': 0,
        'total_files_with_responses': 0,
        'session_details': defaultdict(int),
        'response_files': []
    }
    
    session_search_path = os.path.join(tmp_dir, session_pattern)
    session_dirs = glob.glob(session_search_path)
    
    if not session_dirs:
        return stats
    
    stats['total_sessions'] = len(session_dirs)
    
    for session_dir in sorted(session_dirs):
        session_name = os.path.basename(session_dir)
        session_response_count = 0
        
        # 查找所有inference_result.json文件
        inference_files = glob.glob(os.path.join(session_dir, "frame_*/inference_result.json"))
        
        for inference_file in inference_files:
            try:
                with open(inference_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 检查是否有非空response
                parsed_result = data.get('parsed_result', {})
                if isinstance(parsed_result, dict):
                    response = parsed_result.get('response', '')
                    if response and response.strip():
                        session_response_count += 1
                        frame_name = os.path.basename(os.path.dirname(inference_file))
                        stats['response_files'].append({
                            'session': session_name,
                            'frame': frame_name,
                            'file_path': inference_file,
                            'response_length': len(response),
                            'has_user_question': bool(data.get('user_question', '').strip())
                        })
                        
            except (json.JSONDecodeError, FileNotFoundError, IOError):
                continue
        
        if session_response_count > 0:
            stats['sessions_with_responses'] += 1
            stats['session_details'][session_name] = session_response_count
            stats['total_files_with_responses'] += session_response_count
    
    return stats


def print_statistics(stats, show_details=True):
    """打印统计信息"""
    print(f"扫描统计:")
    print(f"  总session数: {stats['total_sessions']}")
    print(f"  包含response的session数: {stats['sessions_with_responses']}")
    print(f"  包含response的文件总数: {stats['total_files_with_responses']}")
    
    if show_details and stats['session_details']:
        print(f"\n各session详情:")
        for session, count in sorted(stats['session_details'].items()):
            print(f"  {session}: {count} 个文件")
    
    if show_details and stats['response_files']:
        print(f"\n文件列表:")
        for i, file_info in enumerate(stats['response_files'], 1):
            user_q_indicator = " [有用户问题]" if file_info['has_user_question'] else ""
            print(f"  {i:2d}. {file_info['session']} / {file_info['frame']}")
            print(f"      Response长度: {file_info['response_length']} 字符{user_q_indicator}")


def main():
    """主函数"""
    # 解析命令行参数
    args = sys.argv[1:]
    session_pattern = "session_*"
    count_only = False
    
    for arg in args:
        if arg == "--count-only":
            count_only = True
        elif not arg.startswith("--"):
            session_pattern = arg
    
    # 获取项目路径
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    tmp_dir = project_root / "tmp"
    
    if not tmp_dir.exists():
        print(f"错误: tmp目录不存在: {tmp_dir}")
        sys.exit(1)
    
    print(f"快速扫描目录: {tmp_dir}")
    print(f"Session模式: {session_pattern}")
    if count_only:
        print("模式: 仅统计")
    print("-" * 50)
    
    # 执行扫描
    stats = quick_scan_for_responses(str(tmp_dir), session_pattern)
    
    # 打印结果
    print_statistics(stats, show_details=not count_only)
    
    print(f"\n扫描完成!")


if __name__ == "__main__":
    main() 