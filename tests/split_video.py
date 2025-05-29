#!/usr/bin/env python3
"""
视频切分工具
将大视频切分成多个3秒的小视频用于测试
"""

import os
import cv2
import sys
from pathlib import Path

def split_video(input_path: str, output_dir: str, segment_duration: int = 3, max_segments: int = 5):
    """
    切分视频为多个小段
    
    Args:
        input_path: 输入视频路径
        output_dir: 输出目录
        segment_duration: 每段时长（秒）
        max_segments: 最大段数
    """
    
    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 打开视频
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"❌ 无法打开视频文件: {input_path}")
        return False
    
    # 获取视频信息
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    total_duration = total_frames / fps
    
    print(f"📹 视频信息:")
    print(f"  - 帧率: {fps:.2f} fps")
    print(f"  - 总帧数: {total_frames}")
    print(f"  - 总时长: {total_duration:.2f}s")
    print(f"  - 切分段数: {max_segments}")
    print(f"  - 每段时长: {segment_duration}s")
    
    # 计算每段的帧数
    frames_per_segment = int(fps * segment_duration)
    
    # 获取视频编码信息
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter.fourcc(*'mp4v')
    
    segments_created = 0
    
    for segment_idx in range(max_segments):
        # 计算起始帧
        start_frame = segment_idx * frames_per_segment
        if start_frame >= total_frames:
            break
            
        # 设置视频位置
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        # 创建输出文件
        output_file = output_path / f"segment_{segment_idx+1:02d}.mp4"
        writer = cv2.VideoWriter(str(output_file), fourcc, fps, (width, height))
        
        print(f"🎬 创建段 {segment_idx+1}: {output_file.name}")
        
        # 写入帧
        frames_written = 0
        while frames_written < frames_per_segment:
            ret, frame = cap.read()
            if not ret:
                break
                
            writer.write(frame)
            frames_written += 1
        
        writer.release()
        
        # 检查文件大小
        file_size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"  ✅ 完成: {frames_written} 帧, {file_size_mb:.2f}MB")
        
        segments_created += 1
    
    cap.release()
    
    print(f"\n🎉 视频切分完成！共创建 {segments_created} 个视频段")
    return True

if __name__ == "__main__":
    # 默认参数
    input_video = "data/test.avi"
    output_dir = "data/segments"
    
    if len(sys.argv) > 1:
        input_video = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]
    
    print(f"🔧 视频切分工具")
    print(f"输入视频: {input_video}")
    print(f"输出目录: {output_dir}")
    
    if not os.path.exists(input_video):
        print(f"❌ 输入视频不存在: {input_video}")
        sys.exit(1)
    
    success = split_video(input_video, output_dir)
    if success:
        print("✅ 切分成功！")
        sys.exit(0)
    else:
        print("❌ 切分失败！")
        sys.exit(1) 