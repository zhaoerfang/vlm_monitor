#!/usr/bin/env python3
"""
简化的RTSP和VLM集成测试
"""

import os
import sys
import time
import threading
import cv2
import json
from datetime import datetime
from pathlib import Path


from monitor.rtsp_server import RTSPServer
from monitor.rtsp_client import RTSPClient
from monitor.dashscope_vlm_client import DashScopeVLMClient, AsyncVideoProcessor

def create_experiment_dir():
    """创建实验目录"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_dir = Path(__file__).parent.parent / "tmp" / f"experiment_{timestamp}"
    experiment_dir.mkdir(parents=True, exist_ok=True)
    return experiment_dir

def find_test_video():
    """查找测试视频文件"""
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    video_files = [f for f in os.listdir(data_dir) if f.endswith(('.mp4', '.avi', '.mov', '.mkv'))]
    
    if not video_files:
        raise FileNotFoundError("在data目录下没有找到视频文件")
        
    return os.path.join(data_dir, video_files[0])

def test_rtsp_server(video_path, port=8554):
    """测试RTSP服务器"""
    print("\n" + "="*50)
    print("测试1: RTSP服务器测试")
    print("="*50)
    
    rtsp_url = f"rtsp://localhost:{port}/stream"
    
    try:
        # 启动RTSP服务器
        print(f"启动RTSP服务器，端口: {port}")
        print(f"使用视频文件: {video_path}")
        
        # 先检查原始视频信息
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            original_fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / original_fps if original_fps > 0 else 0
            
            print(f"原始视频信息: {width}x{height}, {original_fps:.2f}fps, "
                  f"{total_frames}帧, 时长{duration:.2f}秒")
            cap.release()
        
        rtsp_server = RTSPServer(video_path, port=port, stream_name="stream")
        
        # 在单独线程中启动服务器
        server_thread = threading.Thread(target=rtsp_server.start)
        server_thread.daemon = True
        server_thread.start()
        
        # 等待服务器启动
        time.sleep(5)
        
        # 测试连接
        print(f"测试连接: {rtsp_url}")
        test_cap = cv2.VideoCapture(rtsp_url)
        
        if test_cap.isOpened():
            ret, frame = test_cap.read()
            if ret and frame is not None:
                print("✅ RTSP服务器工作正常")
                test_cap.release()
                return True, rtsp_server
            else:
                print("❌ 无法从RTSP流读取帧")
        else:
            print("❌ 无法连接到RTSP流")
            
        test_cap.release()
        return False, None
        
    except Exception as e:
        print(f"❌ RTSP服务器测试失败: {str(e)}")
        return False, None

def test_rtsp_client(rtsp_url, experiment_dir):
    """测试RTSP客户端"""
    print("\n" + "="*50)
    print("测试2: RTSP客户端测试")
    print("="*50)
    
    try:
        # 创建RTSP客户端
        rtsp_client = RTSPClient(
            rtsp_url=rtsp_url,
            frame_rate=5,
            timeout=10,
            buffer_size=10
        )
        
        # 收集帧
        collected_frames = []
        max_frames = 20
        
        def frame_callback(frame):
            collected_frames.append(frame)
            print(f"收到帧 {len(collected_frames)}/{max_frames}")
            return len(collected_frames) < max_frames
        
        print(f"开始收集 {max_frames} 帧...")
        
        # 在单独线程中运行客户端
        client_thread = threading.Thread(
            target=lambda: rtsp_client.run(callback=frame_callback)
        )
        client_thread.daemon = True
        client_thread.start()
        
        # 等待收集帧
        timeout = 15
        start_time = time.time()
        while len(collected_frames) < max_frames and time.time() - start_time < timeout:
            time.sleep(0.5)
        
        if len(collected_frames) >= max_frames:
            print(f"✅ 成功收集到 {len(collected_frames)} 帧")
            
            # 显示RTSP流信息
            stream_info = rtsp_client.get_stream_info()
            print(f"RTSP流信息: 原始帧率={stream_info['original_fps']:.2f}fps, "
                  f"目标帧率={stream_info['target_fps']}fps, "
                  f"分辨率={stream_info['width']}x{stream_info['height']}")
            
            # 保存一些帧
            for i, frame in enumerate(collected_frames[:5]):
                frame_path = experiment_dir / f"rtsp_frame_{i:03d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                
            print(f"已保存前5帧到: {experiment_dir}")
            return True, collected_frames
        else:
            print(f"❌ 只收集到 {len(collected_frames)} 帧")
            return False, []
            
    except Exception as e:
        print(f"❌ RTSP客户端测试失败: {str(e)}")
        return False, []

def create_video_from_frames(frames, output_path, fps=10):
    """从帧创建视频文件"""
    if not frames:
        return False
        
    try:
        height, width = frames[0].shape[:2]
        fourcc = cv2.VideoWriter.fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
        
        for frame in frames:
            writer.write(frame)
            
        writer.release()
        return True
        
    except Exception as e:
        print(f"创建视频失败: {str(e)}")
        return False

def test_vlm_analysis(api_key, frames, experiment_dir):
    """测试VLM分析"""
    print("\n" + "="*50)
    print("测试3: VLM分析测试")
    print("="*50)
    
    try:
        # 创建VLM客户端
        vlm_client = DashScopeVLMClient(api_key=api_key)
        
        # 创建视频文件
        video_path = experiment_dir / "test_video.mp4"
        
        print("正在创建测试视频...")
        if not create_video_from_frames(frames, video_path):
            print("❌ 创建视频失败")
            return False
            
        print(f"视频已创建: {video_path}")
        
        # 分析视频
        print("正在调用VLM分析...")
        result = vlm_client.analyze_video(
            video_path=str(video_path),
            prompt="请描述这段视频中的内容，包括场景、人物、动作等。",
            fps=2
        )
        
        if result:
            print("✅ VLM分析成功")
            print(f"结果长度: {len(result)} 字符")
            print(f"结果预览: {result[:200]}...")
            
            # 保存结果
            result_file = experiment_dir / "vlm_result.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'result': result,
                    'timestamp': time.time(),
                    'video_path': str(video_path)
                }, f, ensure_ascii=False, indent=2)
                
            print(f"结果已保存到: {result_file}")
            return True
        else:
            print("❌ VLM分析失败，返回结果为空")
            return False
            
    except Exception as e:
        print(f"❌ VLM分析测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_n_frames_async(api_key, rtsp_url, experiment_dir, n_frames=20):
    """测试N帧异步处理"""
    print("\n" + "="*50)
    print(f"测试4: {n_frames}帧异步处理测试")
    print("="*50)
    
    try:
        # 创建VLM客户端
        vlm_client = DashScopeVLMClient(api_key=api_key)
        
        # 获取RTSP流的原始帧率信息
        test_cap = cv2.VideoCapture(rtsp_url)
        original_fps = 25.0  # 默认值
        if test_cap.isOpened():
            original_fps = test_cap.get(cv2.CAP_PROP_FPS) or 25.0
            test_cap.release()
        
        # 创建异步视频处理器，使用新的抽帧策略
        processor = AsyncVideoProcessor(
            vlm_client=vlm_client,
            temp_dir=str(experiment_dir),
            target_video_duration=3.0,  # 3秒视频
            frames_per_second=2,        # 每秒抽2帧
            original_fps=original_fps   # 原始帧率
        )
        
        # 创建N帧目录
        n_frames_dir = experiment_dir / f"n_frames_{n_frames}"
        n_frames_dir.mkdir(exist_ok=True)
        
        # 启动处理器
        processor.start()
        
        # 创建RTSP客户端
        rtsp_client = RTSPClient(
            rtsp_url=rtsp_url,
            frame_rate=10,
            timeout=30,
            buffer_size=50
        )
        
        # 收集帧并发送到处理器
        frames_sent = 0
        max_frames = 150  # 收集150帧，足够生成2个3秒视频（每个需要75帧）
        
        def frame_callback(frame):
            nonlocal frames_sent
            # 获取当前时间戳
            current_time = time.time()
            processor.add_frame(frame, current_time)
            frames_sent += 1
            
            if frames_sent % 25 == 0:
                print(f"已发送 {frames_sent}/{max_frames} 帧到处理器")
            return frames_sent < max_frames
        
        print(f"开始收集 {max_frames} 帧进行异步处理...")
        print(f"抽帧策略: 每3秒收集{int(3*original_fps)}帧，每秒抽取2帧，制作3秒视频（共6帧）")
        
        # 收集帧
        client_thread = threading.Thread(
            target=lambda: rtsp_client.run(callback=frame_callback)
        )
        client_thread.daemon = True
        client_thread.start()
        
        # 等待收集完成
        timeout = 40
        start_time = time.time()
        while frames_sent < max_frames and time.time() - start_time < timeout:
            time.sleep(0.5)
        
        print(f"帧收集完成，共发送 {frames_sent} 帧")
        
        # 等待处理器处理完成
        print("等待视频处理和VLM推理完成...")
        results = []
        result_timeout = 90  # 90秒超时
        result_start_time = time.time()
        
        while len(results) < 2 and time.time() - result_start_time < result_timeout:
            result = processor.get_result(timeout=2.0)
            if result:
                results.append(result)
                print(f"收到第 {len(results)} 个推理结果")
                
                # 保存结果到N帧目录
                result_file = n_frames_dir / f"batch_{len(results):03d}_result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
                
                # 打印详细信息
                video_info = result.get('video_info', {})
                print(f"  视频路径: {os.path.basename(result.get('video_path', 'N/A'))}")
                print(f"  帧数: {video_info.get('frame_count', 'N/A')}")
                print(f"  原始帧范围: {video_info.get('original_frame_range', 'N/A')}")
                print(f"  源视频时间范围: {video_info.get('start_relative_timestamp', 0):.2f}s - {video_info.get('end_relative_timestamp', 0):.2f}s")
                print(f"  推理开始时间: {result.get('inference_start_timestamp', 'N/A')}")
                print(f"  推理结束时间: {result.get('inference_end_timestamp', 'N/A')}")
                print(f"  推理耗时: {result.get('inference_duration', 0):.2f}s")
                print(f"  结果长度: {len(result.get('result', '')) if result.get('result') else 0} 字符")
                if result.get('result'):
                    # 处理结果可能是列表格式
                    result_text = result['result']
                    if isinstance(result_text, list) and len(result_text) > 0:
                        result_text = result_text[0].get('text', str(result_text))
                    print(f"  结果预览: {str(result_text)[:100]}...")
                print()
        
        # 停止处理器
        processor.stop()
        
        if len(results) >= 2:
            print(f"✅ N帧异步处理成功，完成 {len(results)} 个批次")
            
            # 保存总结果
            summary_file = n_frames_dir / "summary.json"
            summary_data = {
                'n_frames': n_frames,
                'frames_sent': frames_sent,
                'total_batches': len(results),
                'sampling_strategy': 'time_based',
                'frames_per_second': 2,
                'target_video_duration': 3.0,
                'original_fps': original_fps,
                'frames_to_collect_per_video': int(3 * original_fps),
                'results': results
            }
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"结果总结已保存到: {summary_file}")
            return True
        else:
            print(f"❌ N帧异步处理结果不足: {len(results)}")
            return False
            
    except Exception as e:
        print(f"❌ N帧异步测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="RTSP和VLM集成测试")
    parser.add_argument("api_key", help="DashScope API密钥")
    parser.add_argument("--video", help="测试视频路径（可选）")
    parser.add_argument("--n-frames", type=int, default=30, help="N帧异步测试的帧数")
    parser.add_argument("--port", type=int, default=8554, help="RTSP服务器端口")
    
    args = parser.parse_args()
    
    # 创建实验目录
    experiment_dir = create_experiment_dir()
    print(f"实验目录: {experiment_dir}")
    
    # 查找测试视频
    video_path = args.video or find_test_video()
    print(f"测试视频: {video_path}")
    
    rtsp_url = f"rtsp://localhost:{args.port}/stream"
    
    # 测试结果
    results = {
        'rtsp_server_test': False,
        'rtsp_client_test': False,
        'vlm_analysis_test': False,
        'n_frames_async_test': False
    }
    
    try:
        # 测试1: RTSP服务器
        server_ok, rtsp_server = test_rtsp_server(video_path, args.port)
        results['rtsp_server_test'] = server_ok
        
        if server_ok:
            # 测试2: RTSP客户端
            client_ok, frames = test_rtsp_client(rtsp_url, experiment_dir)
            results['rtsp_client_test'] = client_ok
            
            if client_ok and frames:
                # 测试3: VLM分析
                vlm_ok = test_vlm_analysis(args.api_key, frames, experiment_dir)
                results['vlm_analysis_test'] = vlm_ok
                
                # 测试4: N帧异步处理
                async_ok = test_n_frames_async(args.api_key, rtsp_url, experiment_dir, args.n_frames)
                results['n_frames_async_test'] = async_ok
        
    finally:
        # 清理
        if 'rtsp_server' in locals() and rtsp_server:
            try:
                rtsp_server.stop()
            except:
                pass
    
    # 保存测试结果
    results_file = experiment_dir / "test_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 打印总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed_tests = sum(1 for v in results.values() if v)
    total_tests = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n总体结果: {passed_tests}/{total_tests} 测试通过")
    print(f"实验数据保存在: {experiment_dir}")
    
    if passed_tests == total_tests:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 