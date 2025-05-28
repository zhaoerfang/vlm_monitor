#!/usr/bin/env python3
"""
RTSP和VLM集成测试
测试RTSP伪服务、客户端和VLM推理的完整流程
"""

import os
import sys
import time
import threading
import subprocess
import tempfile
import cv2
import numpy as np
import queue
import json
from datetime import datetime
from pathlib import Path
import argparse
import logging
import concurrent.futures

from monitor.rtsp_server import RTSPServer
from monitor.rtsp_client import RTSPClient
from monitor.dashscope_vlm_client import DashScopeVLMClient, AsyncVideoProcessor

class RTSPVLMIntegrationTest:
    def __init__(self, api_key, video_path=None):
        """
        初始化集成测试
        
        Args:
            api_key: DashScope API密钥
            video_path: 测试视频路径，如果为None则使用data目录下的视频
        """
        self.api_key = api_key
        self.video_path = video_path or self._find_test_video()
        
        # 创建实验目录
        self.experiment_dir = self._create_experiment_dir()
        
        # RTSP配置
        self.rtsp_port = 8554
        self.rtsp_url = f"rtsp://localhost:{self.rtsp_port}/test"
        
        # 组件
        self.rtsp_server = None
        self.rtsp_client = None
        self.vlm_client = None
        
        # 测试结果
        self.test_results = {
            'rtsp_server_test': False,
            'rtsp_client_test': False,
            'vlm_integration_test': False,
            'n_frames_async_test': False,
            'experiment_dir': str(self.experiment_dir)
        }
        
    def _find_test_video(self):
        """查找测试视频文件"""
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        video_files = [f for f in os.listdir(data_dir) if f.endswith(('.mp4', '.avi', '.mov', '.mkv'))]
        
        if not video_files:
            raise FileNotFoundError("在data目录下没有找到视频文件")
            
        return os.path.join(data_dir, video_files[0])
    
    def _create_experiment_dir(self):
        """创建实验目录"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_dir = Path(__file__).parent.parent / "tmp" / f"experiment_{timestamp}"
        experiment_dir.mkdir(parents=True, exist_ok=True)
        return experiment_dir
    
    def test_1_rtsp_server(self):
        """测试1: RTSP伪服务是否工作"""
        print("\n" + "="*60)
        print("测试1: RTSP伪服务测试")
        print("="*60)
        
        try:
            # 启动RTSP服务器
            print(f"启动RTSP服务器，端口: {self.rtsp_port}")
            print(f"使用视频文件: {self.video_path}")
            
            self.rtsp_server = RTSPServer(self.video_path, port=self.rtsp_port)
            
            # 在单独线程中启动服务器
            server_thread = threading.Thread(target=self.rtsp_server.start)
            server_thread.daemon = True
            server_thread.start()
            
            # 等待服务器启动
            time.sleep(3)
            
            # 使用ffprobe检查RTSP流是否可用
            print(f"检查RTSP流: {self.rtsp_url}")
            
            # 简单的连接测试
            test_cap = cv2.VideoCapture(self.rtsp_url)
            if test_cap.isOpened():
                ret, frame = test_cap.read()
                if ret and frame is not None:
                    print("✅ RTSP服务器工作正常，可以获取视频帧")
                    self.test_results['rtsp_server_test'] = True
                    
                    # 保存第一帧作为验证
                    first_frame_path = self.experiment_dir / "rtsp_first_frame.jpg"
                    cv2.imwrite(str(first_frame_path), frame)
                    print(f"已保存第一帧: {first_frame_path}")
                else:
                    print("❌ 无法从RTSP流读取帧")
            else:
                print("❌ 无法连接到RTSP流")
                
            test_cap.release()
            
        except Exception as e:
            print(f"❌ RTSP服务器测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return self.test_results['rtsp_server_test']
    
    def test_2_rtsp_client(self):
        """测试2: RTSP客户端能否从伪服务获取数据"""
        print("\n" + "="*60)
        print("测试2: RTSP客户端测试")
        print("="*60)
        
        if not self.test_results['rtsp_server_test']:
            print("❌ RTSP服务器测试未通过，跳过客户端测试")
            return False
            
        try:
            # 创建RTSP客户端
            self.rtsp_client = RTSPClient(
                rtsp_url=self.rtsp_url,
                frame_rate=5,
                timeout=10,
                buffer_size=10
            )
            
            # 收集帧的列表
            collected_frames = []
            max_frames = 20
            
            def frame_callback(frame):
                collected_frames.append(frame)
                print(f"收到帧 {len(collected_frames)}/{max_frames}")
                return len(collected_frames) < max_frames
            
            print(f"开始从RTSP流收集 {max_frames} 帧...")
            
            # 在单独线程中运行客户端
            client_thread = threading.Thread(
                target=lambda: self.rtsp_client.run(callback=frame_callback)
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
                self.test_results['rtsp_client_test'] = True
                
                # 保存一些帧作为验证
                for i, frame in enumerate(collected_frames[:5]):
                    frame_path = self.experiment_dir / f"rtsp_client_frame_{i:03d}.jpg"
                    cv2.imwrite(str(frame_path), frame)
                    
                print(f"已保存前5帧到: {self.experiment_dir}")
                
            else:
                print(f"❌ 只收集到 {len(collected_frames)} 帧，少于预期的 {max_frames} 帧")
                
        except Exception as e:
            print(f"❌ RTSP客户端测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return self.test_results['rtsp_client_test']
    
    def test_3_vlm_integration(self):
        """测试3: RTSP客户端能否将数据给DashScope VLM客户端"""
        print("\n" + "="*60)
        print("测试3: VLM集成测试")
        print("="*60)
        
        if not self.test_results['rtsp_client_test']:
            print("❌ RTSP客户端测试未通过，跳过VLM集成测试")
            return False
            
        try:
            # 创建VLM客户端
            self.vlm_client = DashScopeVLMClient(api_key=self.api_key)
            
            # 创建异步视频处理器
            processor = AsyncVideoProcessor(
                vlm_client=self.vlm_client,
                temp_dir=str(self.experiment_dir)
            )
            
            # 修改处理器参数以便快速测试
            processor.video_duration = 5  # 5秒视频片段
            processor.video_fps = 5       # 5帧/秒
            
            # 收集结果
            vlm_results = []
            
            def collect_results():
                while len(vlm_results) < 2:  # 等待至少2个结果
                    result = processor.get_result(timeout=1.0)
                    if result:
                        vlm_results.append(result)
                        print(f"收到VLM分析结果 {len(vlm_results)}")
                        
                        # 保存结果
                        result_file = self.experiment_dir / f"vlm_result_{len(vlm_results)}.json"
                        with open(result_file, 'w', encoding='utf-8') as f:
                            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
            
            # 启动处理器
            processor.start()
            
            # 启动结果收集线程
            result_thread = threading.Thread(target=collect_results)
            result_thread.daemon = True
            result_thread.start()
            
            # 从RTSP流获取帧并发送给处理器
            frame_count = 0
            max_frames = 60  # 发送60帧（应该能生成2个视频片段）
            
            def frame_callback(frame):
                nonlocal frame_count
                processor.add_frame(frame)
                frame_count += 1
                if frame_count % 10 == 0:
                    print(f"已发送 {frame_count} 帧到VLM处理器")
                return frame_count < max_frames
            
            print(f"开始发送帧到VLM处理器...")
            
            # 重新创建RTSP客户端（因为之前的可能已经停止）
            rtsp_client = RTSPClient(
                rtsp_url=self.rtsp_url,
                frame_rate=10,
                timeout=15,
                buffer_size=20
            )
            
            # 在单独线程中运行
            client_thread = threading.Thread(
                target=lambda: rtsp_client.run(callback=frame_callback)
            )
            client_thread.daemon = True
            client_thread.start()
            
            # 等待处理完成
            timeout = 30
            start_time = time.time()
            while len(vlm_results) < 2 and time.time() - start_time < timeout:
                time.sleep(1)
                print(f"等待VLM结果... 当前: {len(vlm_results)}/2")
            
            # 停止处理器
            processor.stop()
            
            if len(vlm_results) >= 2:
                print(f"✅ 成功获得 {len(vlm_results)} 个VLM分析结果")
                self.test_results['vlm_integration_test'] = True
                
                # 打印结果摘要
                for i, result in enumerate(vlm_results):
                    print(f"\n结果 {i+1}:")
                    print(f"  时间戳: {result['timestamp']}")
                    print(f"  结果长度: {len(result['result'])} 字符")
                    print(f"  结果预览: {result['result'][:100]}...")
                    
            else:
                print(f"❌ 只获得 {len(vlm_results)} 个结果，少于预期的2个")
                
        except Exception as e:
            print(f"❌ VLM集成测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return self.test_results['vlm_integration_test']
    
    def test_4_n_frames_async(self, n_frames=30):
        """测试4: N帧异步推理测试"""
        print("\n" + "="*60)
        print(f"测试4: {n_frames}帧异步推理测试")
        print("="*60)
        
        if not self.test_results['rtsp_client_test']:
            print("❌ RTSP客户端测试未通过，跳过N帧异步测试")
            return False
            
        try:
            # 创建N帧处理器
            n_frames_processor = NFramesAsyncProcessor(
                vlm_client=DashScopeVLMClient(api_key=self.api_key),
                n_frames=n_frames,
                experiment_dir=self.experiment_dir
            )
            
            # 启动处理器
            n_frames_processor.start()
            
            # 从RTSP流获取帧
            frame_count = 0
            max_frames = n_frames * 3  # 发送3批帧
            
            def frame_callback(frame):
                nonlocal frame_count
                n_frames_processor.add_frame(frame)
                frame_count += 1
                if frame_count % 10 == 0:
                    print(f"已发送 {frame_count}/{max_frames} 帧")
                return frame_count < max_frames
            
            print(f"开始发送 {max_frames} 帧进行N帧异步处理...")
            
            # 创建新的RTSP客户端
            rtsp_client = RTSPClient(
                rtsp_url=self.rtsp_url,
                frame_rate=10,
                timeout=20,
                buffer_size=30
            )
            
            # 运行客户端
            client_thread = threading.Thread(
                target=lambda: rtsp_client.run(callback=frame_callback)
            )
            client_thread.daemon = True
            client_thread.start()
            
            # 等待处理完成
            timeout = 45
            start_time = time.time()
            while frame_count < max_frames and time.time() - start_time < timeout:
                time.sleep(0.5)
            
            # 等待处理器完成
            time.sleep(5)
            
            # 停止处理器
            results = n_frames_processor.stop()
            
            if len(results) >= 2:
                print(f"✅ 成功完成N帧异步处理，获得 {len(results)} 个结果")
                self.test_results['n_frames_async_test'] = True
                
                # 打印结果统计
                print(f"\nN帧异步处理结果统计:")
                for i, result in enumerate(results):
                    print(f"  批次 {i+1}: {result['frame_count']} 帧, "
                          f"处理时间: {result['processing_time']:.2f}秒")
                    
            else:
                print(f"❌ N帧异步处理结果不足，只获得 {len(results)} 个结果")
                
        except Exception as e:
            print(f"❌ N帧异步测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
            
        return self.test_results['n_frames_async_test']
    
    def run_all_tests(self):
        """运行所有测试"""
        print("开始RTSP和VLM集成测试")
        print(f"实验目录: {self.experiment_dir}")
        print(f"测试视频: {self.video_path}")
        
        try:
            # 运行所有测试
            self.test_1_rtsp_server()
            self.test_2_rtsp_client()
            self.test_3_vlm_integration()
            self.test_4_n_frames_async()
            
        finally:
            # 清理资源
            if self.rtsp_server:
                try:
                    self.rtsp_server.stop()
                except:
                    pass
                    
        # 保存测试结果
        results_file = self.experiment_dir / "test_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, ensure_ascii=False, indent=2)
            
        # 打印总结
        print("\n" + "="*60)
        print("测试总结")
        print("="*60)
        
        passed_tests = sum(self.test_results.values() if isinstance(v, bool) else [False] for v in self.test_results.values())
        total_tests = len([v for v in self.test_results.values() if isinstance(v, bool)])
        
        for test_name, result in self.test_results.items():
            if isinstance(result, bool):
                status = "✅ 通过" if result else "❌ 失败"
                print(f"  {test_name}: {status}")
                
        print(f"\n总体结果: {passed_tests}/{total_tests} 测试通过")
        print(f"实验数据保存在: {self.experiment_dir}")
        
        return passed_tests == total_tests

class NFramesAsyncProcessor:
    """N帧异步处理器"""
    
    def __init__(self, vlm_client, n_frames=30, experiment_dir=None):
        self.vlm_client = vlm_client
        self.n_frames = n_frames
        self.experiment_dir = Path(experiment_dir) if experiment_dir else Path("tmp")
        
        self.frame_buffer = []
        self.frame_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        
        self.batch_count = 0
        self.results = []
        
        # 创建N帧目录
        self.n_frames_dir = self.experiment_dir / f"n_frames_{n_frames}"
        self.n_frames_dir.mkdir(exist_ok=True)
        
    def start(self):
        """启动处理器"""
        self.stop_event.clear()
        
        # 启动帧收集线程
        self.collector_thread = threading.Thread(target=self._frame_collector)
        self.collector_thread.start()
        
        # 启动推理线程
        self.inference_thread = threading.Thread(target=self._inference_worker)
        self.inference_thread.start()
        
        print(f"N帧异步处理器已启动 (N={self.n_frames})")
        
    def add_frame(self, frame):
        """添加帧"""
        try:
            self.frame_queue.put(frame, timeout=1)
        except queue.Full:
            print("帧队列已满，丢弃帧")
            
    def stop(self):
        """停止处理器"""
        self.stop_event.set()
        
        if hasattr(self, 'collector_thread'):
            self.collector_thread.join()
        if hasattr(self, 'inference_thread'):
            self.inference_thread.join()
            
        return self.results
        
    def _frame_collector(self):
        """帧收集线程"""
        while not self.stop_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=1)
                self.frame_buffer.append(frame)
                
                # 当收集到N帧时，创建视频并发送推理
                if len(self.frame_buffer) >= self.n_frames:
                    frames_batch = self.frame_buffer[:self.n_frames]
                    self.frame_buffer = self.frame_buffer[self.n_frames:]
                    
                    self.batch_count += 1
                    self._process_frames_batch(frames_batch, self.batch_count)
                    
            except queue.Empty:
                continue
                
    def _process_frames_batch(self, frames, batch_id):
        """处理帧批次"""
        try:
            # 创建批次目录
            batch_dir = self.n_frames_dir / f"batch_{batch_id:03d}"
            batch_dir.mkdir(exist_ok=True)
            
            # 保存帧
            for i, frame in enumerate(frames):
                frame_path = batch_dir / f"frame_{i:03d}.jpg"
                cv2.imwrite(str(frame_path), frame)
                
            # 创建视频文件
            video_path = batch_dir / f"batch_{batch_id:03d}.mp4"
            self._create_video_from_frames(frames, str(video_path))
            
            # 发送到推理队列
            inference_data = {
                'batch_id': batch_id,
                'video_path': str(video_path),
                'frame_count': len(frames),
                'batch_dir': str(batch_dir),
                'timestamp': time.time()
            }
            
            self.result_queue.put(inference_data)
            print(f"批次 {batch_id} 已准备，包含 {len(frames)} 帧")
            
        except Exception as e:
            print(f"处理帧批次失败: {str(e)}")
            
    def _create_video_from_frames(self, frames, output_path):
        """从帧创建视频"""
        if not frames:
            return
            
        height, width = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(output_path, fourcc, 10, (width, height))
        
        for frame in frames:
            writer.write(frame)
            
        writer.release()
        
    def _inference_worker(self):
        """推理工作线程"""
        while not self.stop_event.is_set():
            try:
                inference_data = self.result_queue.get(timeout=1)
                
                start_time = time.time()
                
                # 执行VLM推理
                result = self.vlm_client.analyze_video(
                    video_path=inference_data['video_path'],
                    prompt=f"请描述这段包含{inference_data['frame_count']}帧的视频片段内容。",
                    fps=2
                )
                
                processing_time = time.time() - start_time
                
                # 保存结果
                result_data = {
                    'batch_id': inference_data['batch_id'],
                    'frame_count': inference_data['frame_count'],
                    'processing_time': processing_time,
                    'vlm_result': result,
                    'timestamp': inference_data['timestamp']
                }
                
                self.results.append(result_data)
                
                # 保存结果到文件
                result_file = Path(inference_data['batch_dir']) / "vlm_result.json"
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)
                    
                print(f"批次 {inference_data['batch_id']} 推理完成，耗时 {processing_time:.2f}秒")
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"推理失败: {str(e)}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="RTSP和VLM集成测试")
    parser.add_argument("api_key", help="DashScope API密钥")
    parser.add_argument("--video", help="测试视频路径（可选）")
    parser.add_argument("--n-frames", type=int, default=30, help="N帧异步测试的帧数")
    
    args = parser.parse_args()
    
    # 创建测试实例
    test = RTSPVLMIntegrationTest(args.api_key, args.video)
    
    # 运行测试
    success = test.run_all_tests()
    
    if success:
        print("\n🎉 所有测试通过！")
    else:
        print("\n❌ 部分测试失败，请查看详细日志")
        
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 