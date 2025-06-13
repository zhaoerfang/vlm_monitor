#!/usr/bin/env python3
"""
遍历tmp目录中指定session_*/里的每一个frame_*里的inference_result.json文件，
找到其中parsed_result里response字段不为空的文件。

使用方法:
    python find_inference_results_with_response.py [session_pattern]
    
参数:
    session_pattern: 可选，指定session的模式，如 "session_20250612_*" 
                    如果不指定，则遍历所有session_*目录
                    
示例:
    python find_inference_results_with_response.py
    python find_inference_results_with_response.py "session_20250612_*"
    python find_inference_results_with_response.py "session_20250612_144126"
"""

import os
import json
import glob
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_inference_result(file_path: str) -> Optional[Dict[str, Any]]:
    """
    加载inference_result.json文件
    
    Args:
        file_path: inference_result.json文件路径
        
    Returns:
        解析后的JSON数据，如果加载失败返回None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, IOError) as e:
        print(f"警告: 无法加载文件 {file_path}: {e}")
        return None


def has_non_empty_response(data: Dict[str, Any]) -> bool:
    """
    检查parsed_result中是否有非空的response字段
    
    Args:
        data: inference_result.json的数据
        
    Returns:
        如果response字段存在且不为空返回True，否则返回False
    """
    if not data:
        return False
        
    parsed_result = data.get('parsed_result', {})
    if not isinstance(parsed_result, dict):
        return False
        
    response = parsed_result.get('response', '')
    return bool(response and response.strip())


def find_inference_results_with_response(tmp_dir: str, session_pattern: str = "session_*") -> List[Dict[str, Any]]:
    """
    查找包含非空response字段的inference_result.json文件
    
    Args:
        tmp_dir: tmp目录路径
        session_pattern: session目录的匹配模式
        
    Returns:
        包含文件信息的列表
    """
    results = []
    
    # 构建session目录的搜索路径
    session_search_path = os.path.join(tmp_dir, session_pattern)
    session_dirs = glob.glob(session_search_path)
    
    if not session_dirs:
        print(f"未找到匹配的session目录: {session_search_path}")
        return results
    
    print(f"找到 {len(session_dirs)} 个session目录")
    
    for session_dir in sorted(session_dirs):
        session_name = os.path.basename(session_dir)
        print(f"\n处理session: {session_name}")
        
        # 查找frame目录
        frame_search_path = os.path.join(session_dir, "frame_*")
        frame_dirs = glob.glob(frame_search_path)
        
        if not frame_dirs:
            print(f"  未找到frame目录")
            continue
            
        print(f"  找到 {len(frame_dirs)} 个frame目录")
        
        session_results = []
        for frame_dir in sorted(frame_dirs):
            frame_name = os.path.basename(frame_dir)
            inference_file = os.path.join(frame_dir, "inference_result.json")
            
            if not os.path.exists(inference_file):
                continue
                
            # 加载并检查inference_result.json
            data = load_inference_result(inference_file)
            if has_non_empty_response(data):
                result_info = {
                    'session': session_name,
                    'frame': frame_name,
                    'file_path': inference_file,
                    'response': data['parsed_result']['response'],
                    'user_question': data.get('user_question', ''),
                    'summary': data['parsed_result'].get('summary', ''),
                    'people_count': data['parsed_result'].get('people_count', 0),
                    'vehicle_count': data['parsed_result'].get('vehicle_count', 0),
                    'timestamp': data['parsed_result'].get('timestamp', ''),
                    'inference_duration': data.get('inference_duration', 0)
                }
                session_results.append(result_info)
        
        if session_results:
            print(f"  找到 {len(session_results)} 个包含response的文件")
            results.extend(session_results)
        else:
            print(f"  未找到包含response的文件")
    
    return results


def print_results(results: List[Dict[str, Any]], show_details: bool = True):
    """
    打印搜索结果
    
    Args:
        results: 搜索结果列表
        show_details: 是否显示详细信息
    """
    if not results:
        print("\n未找到包含非空response字段的inference_result.json文件")
        return
    
    print(f"\n找到 {len(results)} 个包含非空response字段的文件:")
    print("=" * 80)
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['session']} / {result['frame']}")
        print(f"   文件路径: {result['file_path']}")
        
        if show_details:
            if result['user_question']:
                print(f"   用户问题: {result['user_question']}")
            print(f"   Response: {result['response']}")
            if result['summary']:
                print(f"   摘要: {result['summary']}")
            print(f"   人数: {result['people_count']}, 车辆数: {result['vehicle_count']}")
            print(f"   时间戳: {result['timestamp']}")
            print(f"   推理耗时: {result['inference_duration']:.2f}秒")


def save_results_to_json(results: List[Dict[str, Any]], output_file: str):
    """
    将结果保存到JSON文件
    
    Args:
        results: 搜索结果列表
        output_file: 输出文件路径
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {output_file}")
    except IOError as e:
        print(f"保存文件失败: {e}")


def main():
    """主函数"""
    # 获取脚本所在目录的父目录作为项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    tmp_dir = project_root / "tmp"
    
    if not tmp_dir.exists():
        print(f"错误: tmp目录不存在: {tmp_dir}")
        sys.exit(1)
    
    # 解析命令行参数
    session_pattern = "session_*"
    if len(sys.argv) > 1:
        session_pattern = sys.argv[1]
    
    print(f"搜索目录: {tmp_dir}")
    print(f"Session模式: {session_pattern}")
    
    # 查找结果
    results = find_inference_results_with_response(str(tmp_dir), session_pattern)
    
    # 打印结果
    print_results(results, show_details=True)
    
    # 保存结果到JSON文件
    if results:
        output_file = script_dir / f"inference_results_with_response_{session_pattern.replace('*', 'all').replace('/', '_')}.json"
        save_results_to_json(results, str(output_file))
    
    print(f"\n搜索完成，共找到 {len(results)} 个文件")


if __name__ == "__main__":
    main() 