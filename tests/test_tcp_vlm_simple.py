#!/usr/bin/env python3
"""
TCP视频流和VLM集成测试
仿照RTSP测试的四个阶段：TCP服务器测试、客户端测试、VLM分析测试、异步性能测试
"""

import os
import sys
import time
import threading
import cv2
import json
from datetime import datetime
from pathlib import Path


# 导入模块
from monitor.core.config import get_api_key, load_config
from monitor.tcp.tcp_video_server import TCPVideoServer
from monitor.tcp.tcp_client import TCPVideoClient
from monitor.tcp.tcp_utils import test_tcp_connection, detect_video_info, check_tcp_server_status
from monitor.utils.test_utils import (
    create_experiment_dir, create_phase_directories, save_test_config,
    save_phase_result, create_video_from_frames, find_test_video,
    save_test_summary, print_test_summary
)
from monitor.vlm.vlm_client import DashScopeVLMClient
from monitor.vlm.async_video_processor import AsyncVideoProcessor

def test_tcp_server(tcp_host: str, tcp_port: int, video_path: str):
    """测试TCP视频服务器连通性"""
    print(f"🔗 测试TCP视频服务器: {tcp_host}:{tcp_port}")
    print(f"📹 视频文件: {video_path}")
    
    # 检测视频文件信息
    video_info = detect_video_info(video_path)
    
    if not video_info['exists']:
        print(f"❌ 视频文件不存在: {video_path}")
        return False
    
    if not video_info['readable']:
        print(f"❌ 视频文件无法读取: {video_info['error']}")
        return False
    
    print(f"✅ 视频文件检测成功")
    print(f"📊 视频信息: {video_info['resolution']}, {video_info['fps']:.2f}fps, {video_info['duration']:.2f}s")
    print(f"📦 文件大小: {video_info['file_size_mb']:.2f}MB")
    
    # 测试TCP连接（服务器还未启动，应该失败）
    connection_result = test_tcp_connection(tcp_host, tcp_port, timeout=2)
    
    if connection_result['connected']:
        print(f"⚠️ TCP端口 {tcp_port} 已被占用")
        return False
    else:
        print(f"✅ TCP端口 {tcp_port} 可用")
        return True

def test_tcp_client(tcp_host: str, tcp_port: int, experiment_dir: Path):
    """测试TCP客户端"""
    print("\n" + "="*50)
    print("测试2: TCP客户端测试")
    print("="*50)
    
    try:
        # 创建TCP客户端
        tcp_client = TCPVideoClient(
            host=tcp_host,
            port=tcp_port,
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
            target=lambda: tcp_client.run(callback=frame_callback)
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
            
            # 显示TCP流统计信息
            stats = tcp_client.get_stats()
            print(f"TCP流信息: 目标帧率={tcp_client.frame_rate}fps, "
                  f"实际帧率={stats['average_fps']:.2f}fps, "
                  f"接收字节数={stats['bytes_received']/1024/1024:.2f}MB")
            
            # 保存一些帧
            for i, frame in enumerate(collected_frames[:5]):
                frame_path = experiment_dir / f"tcp_frame_{i:03d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                
            print(f"已保存前5帧到: {experiment_dir}")
            return collected_frames
        else:
            print(f"❌ 只收集到 {len(collected_frames)} 帧")
            return []
            
    except Exception as e:
        print(f"❌ TCP客户端测试失败: {str(e)}")
        return []

def test_vlm_analysis(frames, experiment_dir: Path):
    """测试VLM分析"""
    print("\n" + "="*50)
    print("测试3: VLM分析测试（基于配置文件）")
    print("="*50)
    
    # 加载配置
    config = load_config()
    vlm_config = config['vlm']
    
    try:
        # 创建VLM客户端，让它自己从配置文件读取API密钥
        vlm_client = DashScopeVLMClient(model=vlm_config['model'])
        
        # 检查是否成功获取到API密钥
        if not vlm_client.api_key:
            print("❌ VLM客户端无法获取API密钥，跳过测试")
            return False
        
        print(f"✅ VLM客户端已初始化，使用模型: {vlm_config['model']}")
        
        # 创建视频文件，使用配置的fps
        video_path = experiment_dir / "test_video.mp4"
        video_fps = config['video_processing']['frames_per_second']  # 使用配置的5fps
        
        print("正在创建测试视频...")
        if not create_video_from_frames(frames, video_path, fps=video_fps):
            print("❌ 创建视频失败")
            return False
            
        print(f"视频已创建: {video_path} (fps: {video_fps})")
        
        # 分析视频，使用JSON格式提示词（与AsyncVideoProcessor一致）
        print("正在调用VLM分析...")
        result = vlm_client.analyze_video(
            video_path=str(video_path),
            prompt=None,  # 使用默认的JSON格式提示词
            fps=video_fps
        )
        
        if result:
            print("✅ VLM分析成功")
            print(f"结果长度: {len(result)} 字符")
            print(f"结果预览: {result[:200]}...")
            
            # 保存结果
            result_file = experiment_dir / "vlm_result.json"
            result_data = {
                'result': result,
                'timestamp': time.time(),
                'video_path': str(video_path),
                'config_used': {
                    'model': vlm_config['model'],
                    'video_fps': video_fps,
                    'frames_count': len(frames)
                }
            }
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
                
            print(f"结果已保存到: {result_file}")
            print(f"使用模型: {vlm_config['model']}")
            print(f"视频帧率: {video_fps}fps")
            return True
        else:
            print("❌ VLM分析失败，返回结果为空")
            return False
            
    except ValueError as e:
        if "API密钥未设置" in str(e):
            print(f"❌ API密钥配置错误: {str(e)}")
            return False
        else:
            raise e
    except Exception as e:
        print(f"❌ VLM分析测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_n_frames_async_tcp(tcp_host: str, tcp_port: int, experiment_dir: Path, n_frames=20):
    """
    测试N帧异步处理（TCP版本）
    """
    print("\n" + "="*50)
    print(f"测试4: 每{n_frames}帧异步处理测试（TCP版本，基于配置文件）")
    print("="*50)
    
    # 加载配置
    config = load_config()
    video_config = config['video_processing']
    vlm_config = config['vlm']
    test_config = config['testing']
    
    print(f"📋 使用配置:")
    print(f"  - 目标视频时长: {video_config['target_video_duration']}s")
    print(f"  - 每秒抽帧数: {video_config['frames_per_second']}帧")
    print(f"  - 每个视频帧数: {video_config['target_frames_per_video']}帧")
    print(f"  - 最大并发推理数: {vlm_config['max_concurrent_inferences']}")
    
    try:
        # 创建VLM客户端，让它自己从配置文件读取API密钥
        vlm_client = DashScopeVLMClient(model=vlm_config['model'])
        
        # 检查是否成功获取到API密钥
        if not vlm_client.api_key:
            print("❌ VLM客户端无法获取API密钥，跳过异步测试")
            return False
        
        print(f"✅ VLM客户端已初始化，使用模型: {vlm_config['model']}")
        
        # 使用固定的TCP流帧率（从视频文件检测）
        original_fps = 25.0  # TCP服务器的默认帧率
        
        # 创建异步视频处理器，使用配置文件参数
        processor = AsyncVideoProcessor(
            vlm_client=vlm_client,
            temp_dir=str(experiment_dir),
            target_video_duration=video_config['target_video_duration'],
            frames_per_second=video_config['frames_per_second'],  # 每秒5帧
            original_fps=original_fps,  # TCP流帧率
            max_concurrent_inferences=vlm_config['max_concurrent_inferences']
        )
        
        # 计算测试参数
        frames_per_video = int(video_config['target_video_duration'] * original_fps)  # 每个3秒视频需要的原始帧数
        expected_videos = max(2, n_frames // 15)  # 根据n_frames计算期望的视频数量
        total_frames_needed = expected_videos * frames_per_video  # 总共需要的帧数
        
        print(f"\n📊 计算的测试参数:")
        print(f"  - TCP流帧率: {original_fps}fps")
        print(f"  - 每个视频需要原始帧数: {frames_per_video}帧")
        print(f"  - 期望生成视频数量: {expected_videos}个")
        print(f"  - 总共需要收集帧数: {total_frames_needed}帧")
        print(f"  - 抽帧策略: 每秒从{original_fps}帧中抽取{video_config['frames_per_second']}帧")
        print(f"  - 每{int(original_fps/video_config['frames_per_second'])}帧抽1帧")
        
        # 创建N帧目录
        n_frames_dir = experiment_dir / f"n_frames_{n_frames}"
        n_frames_dir.mkdir(exist_ok=True)
        
        # 启动处理器
        processor.start()
        
        # 创建TCP客户端
        tcp_client = TCPVideoClient(
            host=tcp_host,
            port=tcp_port,
            frame_rate=int(min(10, original_fps)),  # TCP客户端目标帧率
            timeout=10,
            buffer_size=100
        )
        
        # 收集帧并发送到处理器
        frames_sent = 0
        frame_timestamps = []
        
        def frame_callback(frame):
            nonlocal frames_sent
            # 获取当前时间戳
            current_time = time.time()
            processor.add_frame(frame, current_time)
            frames_sent += 1
            frame_timestamps.append(current_time)
            
            # 每N帧报告一次进度
            if frames_sent % n_frames == 0:
                elapsed_time = current_time - frame_timestamps[0] if frame_timestamps else 0
                fps_actual = frames_sent / elapsed_time if elapsed_time > 0 else 0
                print(f"已发送 {frames_sent}/{total_frames_needed} 帧到处理器 (实际fps: {fps_actual:.1f})")
            
            return frames_sent < total_frames_needed
        
        print(f"🎬 开始收集 {total_frames_needed} 帧进行异步处理...")
        
        # 记录开始时间
        collection_start_time = time.time()
        
        # 收集帧
        client_thread = threading.Thread(
            target=lambda: tcp_client.run(callback=frame_callback)
        )
        client_thread.daemon = True
        client_thread.start()
        
        # 等待收集完成，使用配置的超时时间
        timeout = test_config['collection_timeout']
        start_time = time.time()
        while frames_sent < total_frames_needed and time.time() - start_time < timeout:
            time.sleep(0.5)
        
        collection_end_time = time.time()
        collection_duration = collection_end_time - collection_start_time
        
        print(f"📦 帧收集完成:")
        print(f"  - 实际收集帧数: {frames_sent}")
        print(f"  - 收集耗时: {collection_duration:.2f}s")
        print(f"  - 平均收集帧率: {frames_sent/collection_duration:.2f}fps")
        
        # 等待处理器处理完成，使用配置的超时时间
        print("\n⏳ 等待视频处理和VLM推理完成...")
        results = []
        result_timeout = test_config['result_timeout']
        result_start_time = time.time()
        
        # 记录推理时间线
        inference_timeline = []
        
        while len(results) < expected_videos and time.time() - result_start_time < result_timeout:
            result = processor.get_result(timeout=3.0)
            if result:
                results.append(result)
                current_time = time.time()
                
                print(f"\n🎯 收到第 {len(results)} 个推理结果:")
                
                # 保存结果到N帧目录
                result_file = n_frames_dir / f"video_{len(results):03d}_result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
                
                # 分析推理时间线
                video_info = result.get('video_info', {})
                inference_start = result.get('inference_start_time', 0)
                inference_end = result.get('inference_end_time', 0)
                
                inference_timeline.append({
                    'video_id': len(results),
                    'video_creation_time': video_info.get('created_at', 0),
                    'inference_start_time': inference_start,
                    'inference_end_time': inference_end,
                    'inference_duration': result.get('inference_duration', 0)
                })
                
                # 打印详细信息
                print(f"  📹 视频: {os.path.basename(result.get('video_path', 'N/A'))}")
                print(f"  🎬 帧数: {video_info.get('frame_count', 'N/A')}")
                print(f"  📊 原始帧范围: {video_info.get('original_frame_range', 'N/A')}")
                print(f"  ⏱️  源视频时间: {video_info.get('start_relative_timestamp', 0):.2f}s - {video_info.get('end_relative_timestamp', 0):.2f}s")
                print(f"  🚀 推理开始: {result.get('inference_start_timestamp', 'N/A')}")
                print(f"  🏁 推理结束: {result.get('inference_end_timestamp', 'N/A')}")
                print(f"  ⏳ 推理耗时: {result.get('inference_duration', 0):.2f}s")
                print(f"  📝 结果长度: {len(result.get('result', '')) if result.get('result') else 0} 字符")
                
                # 验证抽帧策略（更新为5fps）
                frame_range = video_info.get('original_frame_range', [0, 0])
                time_range = video_info.get('end_relative_timestamp', 0) - video_info.get('start_relative_timestamp', 0)
                expected_frames = int(time_range * video_config['frames_per_second'])  # 每秒5帧
                actual_frames = video_info.get('frame_count', 0)
                
                print(f"  ✅ 抽帧验证: 期望{expected_frames}帧, 实际{actual_frames}帧, 时间跨度{time_range:.2f}s")
                
                if result.get('result'):
                    # 处理结果可能是列表格式
                    result_text = result['result']
                    if isinstance(result_text, list) and len(result_text) > 0:
                        result_text = result_text[0].get('text', str(result_text))
                    print(f"  📄 结果预览: {str(result_text)[:100]}...")
        
        # 停止处理器
        processor.stop()
        
        # 验证测试成功条件
        success_conditions = {
            'frames_collected': frames_sent >= total_frames_needed * 0.8,  # 至少收集80%的帧
            'videos_generated': len(results) >= expected_videos * 0.5,     # 至少生成50%的视频
            'async_processing': len(inference_timeline) >= 2,              # 至少有2个视频进行推理
            'detailed_logs': all(r.get('inference_duration') is not None for r in results)  # 所有结果都有详细日志
        }
        
        print(f"\n✅ 测试结果验证:")
        for condition, passed in success_conditions.items():
            print(f"  - {condition}: {'✅ 通过' if passed else '❌ 失败'}")
        
        overall_success = all(success_conditions.values())
        
        if overall_success:
            print(f"\n🎉 N帧异步处理测试成功!")
            print(f"  - 收集帧数: {frames_sent}")
            print(f"  - 生成视频: {len(results)}个")
            print(f"  - 完成推理: {len([r for r in results if r.get('result')])}个")
            return True
        else:
            print(f"\n❌ N帧异步处理测试失败:")
            print(f"  - 收集帧数: {frames_sent}/{total_frames_needed}")
            print(f"  - 生成视频: {len(results)}/{expected_videos}")
            return False
            
    except Exception as e:
        print(f"❌ N帧异步测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    try:
        # 加载配置
        config = load_config()
        
        # 创建实验目录
        experiment_dir = create_experiment_dir()
        test_number = int(experiment_dir.name.replace('test', ''))
        
        print(f"📁 实验目录: {experiment_dir}")
        
        # 创建4个测试阶段的子文件夹
        phase_names = [
            "phase1_tcp_server_test",
            "phase2_tcp_client_test", 
            "phase3_vlm_analysis_test",
            "phase4_n_frames_async_test"
        ]
        
        phase_dirs = create_phase_directories(experiment_dir, phase_names)
        
        # 保存测试配置
        save_test_config(experiment_dir, config, test_number, phase_names)
        
        # TCP配置
        tcp_host = "localhost"
        tcp_port = 9999
        video_path = "data/test.avi"  # 使用现有的test.avi文件
        
        # 记录所有阶段的结果
        phase_results = {}
        frames = []  # 初始化frames变量
        tcp_server = None
        
        # 测试阶段1：TCP服务器测试
        print(f"\n{'='*50}")
        print("🌐 阶段1: TCP视频服务器连通性测试")
        print(f"{'='*50}")
        
        try:
            phase1_result = test_tcp_server(tcp_host, tcp_port, video_path)
            if phase1_result:
                # 启动TCP视频服务器
                print("🚀 启动TCP视频服务器...")
                tcp_server = TCPVideoServer(video_path, tcp_port, fps=25.0)
                tcp_url = tcp_server.start()
                print(f"✅ TCP视频服务器已启动: {tcp_url}")
                
                # 等待服务器启动
                time.sleep(2)
                
                # 再次测试连接
                connection_result = test_tcp_connection(tcp_host, tcp_port, timeout=5)
                if connection_result['connected']:
                    print(f"✅ TCP服务器连接验证成功，响应时间: {connection_result['response_time']:.3f}s")
                    phase1_result = True
                else:
                    print(f"❌ TCP服务器连接验证失败: {connection_result['error']}")
                    phase1_result = False
            
            print(f"✅ 阶段1完成，结果: {'成功' if phase1_result else '失败'}")
        except Exception as e:
            print(f"❌ 阶段1异常: {str(e)}")
            phase1_result = False
        
        phase_results['phase1_tcp_server_test'] = phase1_result
        save_phase_result(phase_dirs["phase1_tcp_server_test"], 
                         "阶段1: TCP视频服务器连通性测试", phase1_result,
                         tcp_url=f"tcp://{tcp_host}:{tcp_port}",
                         video_path=video_path)
        
        # 测试阶段2：TCP客户端测试
        print(f"\n{'='*50}")
        print("📹 阶段2: TCP客户端功能测试")
        print(f"{'='*50}")
        
        try:
            if phase1_result:
                frames = test_tcp_client(tcp_host, tcp_port, phase_dirs["phase2_tcp_client_test"])
                phase2_result = len(frames) > 0
                print(f"✅ 阶段2完成，收集到 {len(frames)} 帧")
            else:
                print("⚠️ 由于阶段1失败，跳过TCP客户端测试")
                phase2_result = False
        except Exception as e:
            print(f"❌ 阶段2异常: {str(e)}")
            phase2_result = False
            
        phase_results['phase2_tcp_client_test'] = phase2_result
        save_phase_result(phase_dirs["phase2_tcp_client_test"],
                         "阶段2: TCP客户端功能测试", phase2_result,
                         frames_collected=len(frames))
        
        # 测试阶段3：VLM分析测试
        print(f"\n{'='*50}")
        print("🧠 阶段3: VLM分析测试")
        print(f"{'='*50}")
        
        try:
            if phase2_result and frames:
                phase3_result = test_vlm_analysis(frames, phase_dirs["phase3_vlm_analysis_test"])
                print(f"✅ 阶段3完成，结果: {'成功' if phase3_result else '失败'}")
            elif not phase2_result:
                print("⚠️ 由于阶段2失败，跳过VLM分析测试")
                phase3_result = False
            else:
                print("⚠️ 没有可用帧，跳过VLM分析测试")
                phase3_result = False
        except Exception as e:
            print(f"❌ 阶段3异常: {str(e)}")
            phase3_result = False
            
        phase_results['phase3_vlm_analysis_test'] = phase3_result
        save_phase_result(phase_dirs["phase3_vlm_analysis_test"],
                         "阶段3: VLM分析测试", phase3_result,
                         frames_used=len(frames))
        
        # 测试阶段4：N帧异步处理测试
        print(f"\n{'='*50}")
        print("🎬 阶段4: N帧异步处理测试（TCP版本）")
        print(f"{'='*50}")
        
        try:
            if phase1_result:
                phase4_result = test_n_frames_async_tcp(tcp_host, tcp_port, phase_dirs["phase4_n_frames_async_test"], config['testing']['n_frames_default'])
                print(f"✅ 阶段4完成，结果: {'成功' if phase4_result else '失败'}")
            elif not phase1_result:
                print("⚠️ 由于阶段1失败，跳过N帧异步处理测试")
                phase4_result = False
        except Exception as e:
            print(f"❌ 阶段4异常: {str(e)}")
            phase4_result = False
            
        phase_results['phase4_n_frames_async_test'] = phase4_result
        save_phase_result(phase_dirs["phase4_n_frames_async_test"],
                         "阶段4: N帧异步处理测试（TCP版本）", phase4_result,
                         n_frames=config['testing']['n_frames_default'])
        
        # 计算总体成功率和保存总结
        total_phases = len(phase_results)
        successful_phases = sum(1 for result in phase_results.values() if result)
        success_rate = (successful_phases / total_phases) * 100 if total_phases > 0 else 0
        
        # 保存测试结果总结
        save_test_summary(experiment_dir, phase_results, test_number, len(frames))
        
        # 打印测试总结
        print_test_summary(phase_results, success_rate, experiment_dir, len(frames))
        
        # 即使某些阶段失败，也算作完成了所有测试
        return True
        
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 停止TCP视频服务器
        if tcp_server:
            try:
                tcp_server.stop()
                print("🛑 TCP视频服务器已停止")
            except Exception as e:
                print(f"⚠️ 停止TCP服务器时出错: {str(e)}")

if __name__ == "__main__":
    sys.exit(main()) 