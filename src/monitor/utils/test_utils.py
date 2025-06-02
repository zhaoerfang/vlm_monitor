#!/usr/bin/env python3
"""
测试工具模块
提供测试相关的工具函数，如实验目录管理、视频文件处理等
"""

import os
import cv2
import json
import glob
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def create_experiment_dir(base_dir: str = "tmp", prefix: str = "test") -> Path:
    """
    创建实验目录
    
    Args:
        base_dir: 基础目录名
        prefix: 目录前缀
        
    Returns:
        创建的实验目录路径
    """
    # 找到下一个可用的测试编号
    existing_tests = glob.glob(f"{base_dir}/{prefix}*")
    if existing_tests:
        # 找到最大的test编号
        test_numbers = []
        for test_dir in existing_tests:
            try:
                test_num = int(test_dir.split(prefix)[-1])
                test_numbers.append(test_num)
            except ValueError:
                continue
        next_test_num = max(test_numbers) + 1 if test_numbers else 1
    else:
        next_test_num = 1
        
    experiment_dir = Path(f"{base_dir}/{prefix}{next_test_num}")
    experiment_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"📁 实验目录已创建: {experiment_dir}")
    return experiment_dir

def create_phase_directories(experiment_dir: Path, phase_names: List[str]) -> Dict[str, Path]:
    """
    创建测试阶段目录
    
    Args:
        experiment_dir: 实验主目录
        phase_names: 阶段名称列表
        
    Returns:
        阶段名称到目录路径的映射
    """
    phase_dirs = {}
    
    for phase_name in phase_names:
        phase_dir = experiment_dir / phase_name
        phase_dir.mkdir(exist_ok=True)
        phase_dirs[phase_name] = phase_dir
        logger.info(f"📂 创建测试阶段目录: {phase_name}")
    
    return phase_dirs

def save_test_config(experiment_dir: Path, config: Dict[str, Any], 
                     test_number: int, phase_names: List[str]) -> Path:
    """
    保存测试配置
    
    Args:
        experiment_dir: 实验目录
        config: 配置字典
        test_number: 测试编号
        phase_names: 阶段名称列表
        
    Returns:
        配置文件路径
    """
    config_file = experiment_dir / "test_config.json"
    
    test_config = {
        'test_number': test_number,
        'config': config,
        'timestamp': time.time(),
        'iso_timestamp': datetime.now().isoformat(),
        'test_phases': phase_names
    }
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(test_config, f, ensure_ascii=False, indent=2)
    
    logger.info(f"🔧 测试配置已保存: {config_file}")
    return config_file

def save_phase_result(phase_dir: Path, phase_name: str, 
                      success: bool, **kwargs) -> Path:
    """
    保存阶段结果
    
    Args:
        phase_dir: 阶段目录
        phase_name: 阶段名称
        success: 是否成功
        **kwargs: 其他结果数据
        
    Returns:
        结果文件路径
    """
    result_file = phase_dir / "result.json"
    
    result_data = {
        'phase': phase_name,
        'success': success,
        'timestamp': datetime.now().isoformat(),
        **kwargs
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    return result_file

def create_video_from_frames(frames: List, output_path: Path, fps: int = 10) -> bool:
    """
    从帧创建视频文件
    
    Args:
        frames: 帧列表
        output_path: 输出视频路径
        fps: 视频帧率
        
    Returns:
        是否创建成功
    """
    if not frames:
        logger.error("没有帧数据，无法创建视频")
        return False
        
    try:
        height, width = frames[0].shape[:2]
        fourcc = cv2.VideoWriter.fourcc(*'avc1')
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
        
        for frame in frames:
            writer.write(frame)
            
        writer.release()
        logger.info(f"✅ 视频文件已创建: {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 创建视频失败: {str(e)}")
        return False

def find_test_video(data_dir: str = "data") -> str:
    """
    查找测试视频文件
    
    Args:
        data_dir: 数据目录
        
    Returns:
        找到的视频文件路径
        
    Raises:
        FileNotFoundError: 如果没有找到视频文件
    """
    if not os.path.exists(data_dir):
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")
    
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
    video_files = []
    
    for ext in video_extensions:
        video_files.extend(glob.glob(os.path.join(data_dir, f"*{ext}")))
        video_files.extend(glob.glob(os.path.join(data_dir, f"*{ext.upper()}")))
    
    if not video_files:
        raise FileNotFoundError(f"在{data_dir}目录下没有找到视频文件")
    
    video_path = video_files[0]
    logger.info(f"🎬 找到测试视频: {video_path}")
    return video_path

def save_test_summary(experiment_dir: Path, phase_results: Dict[str, bool], 
                      test_number: int, frames_collected: int = 0) -> Path:
    """
    保存测试结果总结
    
    Args:
        experiment_dir: 实验目录
        phase_results: 各阶段结果
        test_number: 测试编号
        frames_collected: 收集的帧数
        
    Returns:
        总结文件路径
    """
    summary_file = experiment_dir / "test_summary.json"
    
    total_phases = len(phase_results)
    successful_phases = sum(1 for result in phase_results.values() if result)
    success_rate = (successful_phases / total_phases) * 100 if total_phases > 0 else 0
    
    summary_data = {
        'test_number': test_number,
        'timestamp': time.time(),
        'iso_timestamp': datetime.now().isoformat(),
        'total_phases': total_phases,
        'successful_phases': successful_phases,
        'success_rate': success_rate,
        'frames_collected': frames_collected,
        'phase_results': phase_results,
        'conclusion': '所有测试阶段通过' if success_rate == 100 else f'部分测试阶段通过 ({success_rate:.1f}%)'
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"📊 测试总结已保存: {summary_file}")
    return summary_file

def print_test_summary(phase_results: Dict[str, bool], success_rate: float,
                       experiment_dir: Path, frames_collected: int = 0):
    """
    打印测试总结
    
    Args:
        phase_results: 阶段结果字典
        success_rate: 成功率
        experiment_dir: 实验目录
        frames_collected: 收集的帧数
    """
    successful_phases = sum(1 for result in phase_results.values() if result)
    total_phases = len(phase_results)
    
    print(f"\n🎉 所有测试阶段已完成！")
    print(f"📊 测试成功率: {success_rate:.1f}% ({successful_phases}/{total_phases})")
    print(f"📋 阶段结果:")
    
    for phase_name, result in phase_results.items():
        status = "✅ 成功" if result else "❌ 失败"
        print(f"  - {phase_name}: {status}")
    
    if frames_collected > 0:
        print(f"📦 总共收集帧数: {frames_collected}")
    
    print(f"📁 实验数据保存在: {experiment_dir}")

def validate_video_file(video_path: str) -> Dict[str, Any]:
    """
    验证视频文件
    
    Args:
        video_path: 视频文件路径
        
    Returns:
        验证结果字典
    """
    result = {
        'valid': False,
        'error': None,
        'info': {}
    }
    
    try:
        if not os.path.exists(video_path):
            result['error'] = f"视频文件不存在: {video_path}"
            return result
        
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            result['error'] = f"无法打开视频文件: {video_path}"
            return result
        
        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        
        cap.release()
        
        result['valid'] = True
        result['info'] = {
            'fps': fps,
            'width': width,
            'height': height,
            'frame_count': frame_count,
            'duration': duration,
            'file_size_mb': os.path.getsize(video_path) / (1024 * 1024)
        }
        
        logger.info(f"✅ 视频文件验证通过: {video_path}")
        logger.info(f"   信息: {width}x{height}, {fps:.2f}fps, {duration:.2f}s")
        
    except Exception as e:
        result['error'] = f"视频文件验证失败: {str(e)}"
        logger.error(result['error'])
    
    return result 