#!/usr/bin/env python3
"""
整理现有实验目录的工具脚本：
1. 将现有的experiment_*目录重命名为test*格式
2. 对实验日志按原始帧范围排序
3. 将mp4文件移动到对应的details文件夹内
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
import re

def find_experiment_directories(base_dir="tmp"):
    """查找所有实验目录"""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    
    # 查找experiment_*格式的目录
    experiment_dirs = list(base_path.glob("experiment_*"))
    # 查找test*格式的目录
    test_dirs = list(base_path.glob("test*"))
    
    return experiment_dirs, test_dirs

def get_next_test_number(test_dirs):
    """获取下一个test编号"""
    if not test_dirs:
        return 1
    
    test_numbers = []
    for test_dir in test_dirs:
        match = re.search(r'test(\d+)', test_dir.name)
        if match:
            test_numbers.append(int(match.group(1)))
    
    return max(test_numbers) + 1 if test_numbers else 1

def sort_experiment_log(log_file):
    """对实验日志按original_frame_range排序"""
    if not log_file.exists():
        return False
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        inference_log = data.get('inference_log', [])
        if not inference_log:
            return False
        
        # 按original_frame_range排序
        sorted_log = sorted(
            inference_log,
            key=lambda x: x.get('video_info', {}).get('original_frame_range', [0, 0])[0]
        )
        
        # 检查是否需要排序
        original_order = [entry.get('video_info', {}).get('original_frame_range', [0, 0])[0] for entry in inference_log]
        sorted_order = [entry.get('video_info', {}).get('original_frame_range', [0, 0])[0] for entry in sorted_log]
        
        if original_order == sorted_order:
            print(f"    推理日志已经是正确排序")
            return False
        
        # 更新日志
        data['inference_log'] = sorted_log
        
        # 备份原文件
        backup_file = log_file.with_suffix('.json.backup')
        shutil.copy2(log_file, backup_file)
        
        # 保存排序后的日志
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"    ✅ 推理日志已重新排序")
        print(f"    📄 原文件备份为: {backup_file.name}")
        
        # 显示排序前后对比
        print(f"    🔄 排序前: {original_order}")
        print(f"    ✅ 排序后: {sorted_order}")
        
        return True
        
    except Exception as e:
        print(f"    ❌ 排序失败: {str(e)}")
        return False

def organize_video_files(experiment_dir):
    """整理视频文件结构"""
    moved_count = 0
    
    # 查找目录外的mp4文件
    video_files = list(experiment_dir.glob("*.mp4"))
    
    for video_file in video_files:
        # 查找对应的details目录
        video_name = video_file.stem
        details_dir = experiment_dir / f"{video_name}_details"
        
        if details_dir.exists() and details_dir.is_dir():
            # 移动视频文件到details目录
            target_path = details_dir / video_file.name
            if not target_path.exists():
                shutil.move(str(video_file), str(target_path))
                print(f"    📁 移动: {video_file.name} -> {details_dir.name}/")
                moved_count += 1
            else:
                print(f"    ⚠️ 目标文件已存在: {target_path}")
        else:
            print(f"    ⚠️ 未找到对应的details目录: {details_dir.name}")
    
    if moved_count == 0:
        print(f"    文件结构已经是正确的")
    else:
        print(f"    ✅ 移动了 {moved_count} 个视频文件")
    
    return moved_count

def rename_experiment_to_test(experiment_dir, test_number):
    """将experiment目录重命名为test格式"""
    parent_dir = experiment_dir.parent
    new_name = f"test{test_number}"
    new_path = parent_dir / new_name
    
    if new_path.exists():
        print(f"    ❌ 目标目录已存在: {new_name}")
        return None
    
    try:
        experiment_dir.rename(new_path)
        print(f"    ✅ 重命名: {experiment_dir.name} -> {new_name}")
        return new_path
    except Exception as e:
        print(f"    ❌ 重命名失败: {str(e)}")
        return None

def organize_single_directory(dir_path, is_rename=False, test_number=None):
    """整理单个实验目录"""
    print(f"\n📁 处理目录: {dir_path.name}")
    
    # 重命名（如果需要）
    if is_rename and test_number is not None:
        new_path = rename_experiment_to_test(dir_path, test_number)
        if new_path:
            dir_path = new_path
        else:
            return False
    
    # 整理实验日志
    log_file = dir_path / "experiment_log.json"
    sort_experiment_log(log_file)
    
    # 整理文件结构
    organize_video_files(dir_path)
    
    return True

def main():
    """主函数"""
    print("🔧 VLM监控系统实验目录整理工具")
    print("="*60)
    
    # 查找所有实验目录
    experiment_dirs, test_dirs = find_experiment_directories()
    
    print(f"📊 发现的目录:")
    print(f"  - experiment_* 格式: {len(experiment_dirs)}个")
    print(f"  - test* 格式: {len(test_dirs)}个")
    
    if not experiment_dirs and not test_dirs:
        print("❌ 未找到任何实验目录")
        return 1
    
    # 获取下一个test编号
    next_test_num = get_next_test_number(test_dirs)
    print(f"🔢 下一个test编号: {next_test_num}")
    
    # 处理experiment_*目录（重命名 + 整理）
    current_test_num = next_test_num
    for exp_dir in sorted(experiment_dirs):
        organize_single_directory(exp_dir, is_rename=True, test_number=current_test_num)
        current_test_num += 1
    
    # 处理已有的test*目录（只整理，不重命名）
    for test_dir in sorted(test_dirs):
        organize_single_directory(test_dir, is_rename=False)
    
    print(f"\n🎯 整理完成!")
    
    # 显示最终状态
    _, final_test_dirs = find_experiment_directories()
    print(f"📁 最终test目录数量: {len(final_test_dirs)}")
    
    if final_test_dirs:
        print("📋 test目录列表:")
        for test_dir in sorted(final_test_dirs):
            # 统计内容
            mp4_files = list(test_dir.glob("**/*.mp4"))
            details_dirs = list(test_dir.glob("*_details"))
            log_file = test_dir / "experiment_log.json"
            
            print(f"  📁 {test_dir.name}:")
            print(f"    - MP4文件: {len(mp4_files)}个")
            print(f"    - Details目录: {len(details_dirs)}个")
            print(f"    - 实验日志: {'✅' if log_file.exists() else '❌'}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 