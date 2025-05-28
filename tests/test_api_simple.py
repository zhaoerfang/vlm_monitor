#!/usr/bin/env python3
"""
简单的DashScope API测试脚本
使用data目录下的真实视频文件进行测试
"""

import os
import sys
import tempfile
import cv2
import numpy as np

from monitor.dashscope_vlm_client import DashScopeVLMClient

def convert_video_to_mp4(input_path, output_path, max_size_mb=95, duration_seconds=10):
    """
    将视频转换为MP4格式并控制大小
    
    Args:
        input_path: 输入视频路径
        output_path: 输出MP4路径
        max_size_mb: 最大文件大小（MB）
        duration_seconds: 最大时长（秒）
    """
    cap = cv2.VideoCapture(input_path)
    
    # 获取原视频信息
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"原视频信息: {width}x{height}, {fps}fps, {total_frames}帧")
    
    # 计算目标参数
    target_fps = min(fps, 10)  # 限制帧率
    max_frames = duration_seconds * target_fps
    
    # 如果分辨率太高，进行缩放
    if width > 1280 or height > 720:
        scale_factor = min(1280/width, 720/height)
        target_width = int(width * scale_factor)
        target_height = int(height * scale_factor)
    else:
        target_width = width
        target_height = height
    
    print(f"目标参数: {target_width}x{target_height}, {target_fps}fps, 最多{max_frames}帧")
    
    # 创建视频写入器
    fourcc = cv2.VideoWriter.fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, target_fps, (target_width, target_height))
    
    frame_count = 0
    written_frames = 0
    
    while True:
        ret, frame = cap.read()
        if not ret or written_frames >= max_frames:
            break
            
        # 每隔几帧取一帧（降低帧率）
        if frame_count % (fps // target_fps) == 0:
            # 缩放帧
            if target_width != width or target_height != height:
                frame = cv2.resize(frame, (target_width, target_height))
            
            writer.write(frame)
            written_frames += 1
            
            # 检查文件大小
            if written_frames % 30 == 0:  # 每30帧检查一次
                current_size = os.path.getsize(output_path) / (1024 * 1024)
                if current_size > max_size_mb:
                    print(f"达到大小限制 {current_size:.2f}MB，停止写入")
                    break
        
        frame_count += 1
    
    cap.release()
    writer.release()
    
    final_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"转换完成: {written_frames}帧, {final_size:.2f}MB")
    
    return final_size <= 100  # 返回是否符合大小要求

def test_dashscope_api(api_key, video_path=None):
    """测试DashScope API"""
    print("DashScope API 测试")
    print("="*50)
    
    # 确定视频文件路径
    if video_path is None:
        # 使用data目录下的视频
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        video_files = [f for f in os.listdir(data_dir) if f.endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        
        if not video_files:
            print("❌ 在data目录下没有找到视频文件")
            return False
            
        video_path = os.path.join(data_dir, video_files[0])
    
    if not os.path.exists(video_path):
        print(f"❌ 视频文件不存在: {video_path}")
        return False
    
    print(f"使用视频文件: {video_path}")
    
    # 检查原始文件大小
    original_size = os.path.getsize(video_path) / (1024 * 1024)
    print(f"原始文件大小: {original_size:.2f} MB")
    
    # 如果文件太大或不是MP4格式，需要转换
    temp_video_path = None
    if original_size > 100 or not video_path.lower().endswith('.mp4'):
        print("文件过大或格式不是MP4，正在转换...")
        
        temp_video_path = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        
        if not convert_video_to_mp4(video_path, temp_video_path):
            print("❌ 视频转换失败或转换后仍然过大")
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return False
            
        test_video_path = temp_video_path
    else:
        test_video_path = video_path
    
    try:
        # 创建VLM客户端
        print("正在初始化DashScope VLM客户端...")
        client = DashScopeVLMClient(api_key=api_key)
        
        # 测试视频分析
        print("正在调用DashScope API分析视频...")
        result = client.analyze_video(
            video_path=test_video_path,
            prompt="请详细描述这段视频中的内容，包括场景、人物、动作、物体等。",
            fps=2
        )
        
        if result:
            print("\n" + "="*60)
            print("✅ API调用成功！")
            print("分析结果:")
            print("-" * 60)
            print(result)
            print("="*60)
            return True
        else:
            print("\n❌ API调用失败，返回结果为空")
            return False
            
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 清理临时文件
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
            print(f"已清理临时文件: {temp_video_path}")

def main():
    """主函数"""
    print("DashScope API 测试工具")
    print("="*40)
    
    # 从命令行参数或环境变量获取API密钥
    api_key = None
    video_path = None
    
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    if len(sys.argv) > 2:
        video_path = sys.argv[2]
    
    if not api_key:
        api_key = os.getenv('DASHSCOPE_API_KEY')
    
    if not api_key:
        print("❌ 错误: 请提供API密钥")
        print("使用方法:")
        print("  python test_api_simple.py your_api_key [video_path]")
        print("  或设置环境变量: export DASHSCOPE_API_KEY=your_api_key")
        sys.exit(1)
    
    print(f"使用API密钥: {api_key[:10]}...")
    if video_path:
        print(f"指定视频文件: {video_path}")
    else:
        print("将使用data目录下的视频文件")
    
    # 运行测试
    success = test_dashscope_api(api_key, video_path)
    
    if success:
        print("\n✅ API测试通过！DashScope服务正常工作。")
        print("现在可以使用完整的VLM监控系统了。")
    else:
        print("\n❌ API测试失败，请检查:")
        print("  1. API密钥是否正确")
        print("  2. 网络连接是否正常")
        print("  3. 账户余额是否充足")
        print("  4. 是否有API调用权限")
        print("  5. 视频文件是否有效")

if __name__ == "__main__":
    main() 