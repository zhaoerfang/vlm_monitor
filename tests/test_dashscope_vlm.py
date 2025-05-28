import unittest
import os
import sys
import tempfile
import time
import cv2
import numpy as np
from unittest.mock import patch, MagicMock

from monitor.dashscope_vlm_client import DashScopeVLMClient, AsyncVideoProcessor, RTSPVLMMonitor
from monitor.rtsp_client import RTSPClient

class TestDashScopeVLMClient(unittest.TestCase):
    def setUp(self):
        """测试前的设置"""
        # 使用模拟的API密钥
        self.test_api_key = "test_api_key_12345"
        
    def test_client_initialization(self):
        """测试客户端初始化"""
        # 测试使用传入的API密钥
        client = DashScopeVLMClient(api_key=self.test_api_key)
        self.assertEqual(client.api_key, self.test_api_key)
        self.assertEqual(client.model, 'qwen-vl-max-latest')
        
        # 测试自定义模型
        client = DashScopeVLMClient(api_key=self.test_api_key, model='custom-model')
        self.assertEqual(client.model, 'custom-model')
        
    def test_client_initialization_with_env_var(self):
        """测试使用环境变量初始化客户端"""
        with patch.dict(os.environ, {'DASHSCOPE_API_KEY': self.test_api_key}):
            client = DashScopeVLMClient()
            self.assertEqual(client.api_key, self.test_api_key)
            
    def test_client_initialization_without_api_key(self):
        """测试没有API密钥时的初始化"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                DashScopeVLMClient()
                
    def create_test_video(self, duration_seconds=5, fps=10, width=640, height=480):
        """创建测试视频文件"""
        temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        temp_file.close()
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(temp_file.name, fourcc, fps, (width, height))
        
        total_frames = duration_seconds * fps
        for i in range(total_frames):
            # 创建一个简单的测试帧
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            
            # 添加一些变化的内容
            color = (i * 10 % 255, (i * 20) % 255, (i * 30) % 255)
            cv2.rectangle(frame, (50, 50), (width-50, height-50), color, -1)
            
            # 添加文本
            text = f"Frame {i}"
            cv2.putText(frame, text, (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            writer.write(frame)
            
        writer.release()
        return temp_file.name
        
    @patch('dashscope_vlm_client.MultiModalConversation.call')
    def test_analyze_video_success(self, mock_call):
        """测试视频分析成功的情况"""
        # 模拟API响应
        mock_response = {
            "output": {
                "choices": [{
                    "message": {
                        "content": [{
                            "text": "这是一个测试视频，显示了一个变化的矩形和帧计数器。"
                        }]
                    }
                }]
            }
        }
        mock_call.return_value = mock_response
        
        # 创建测试视频
        video_path = self.create_test_video(duration_seconds=2)
        
        try:
            client = DashScopeVLMClient(api_key=self.test_api_key)
            result = client.analyze_video(video_path, "描述这个视频", fps=2)
            
            self.assertIsNotNone(result)
            self.assertEqual(result, "这是一个测试视频，显示了一个变化的矩形和帧计数器。")
            
            # 验证API调用参数
            mock_call.assert_called_once()
            call_args = mock_call.call_args
            self.assertEqual(call_args[1]['api_key'], self.test_api_key)
            self.assertEqual(call_args[1]['model'], 'qwen-vl-max-latest')
            
        finally:
            # 清理测试文件
            if os.path.exists(video_path):
                os.remove(video_path)
                
    def test_analyze_video_file_not_exists(self):
        """测试分析不存在的视频文件"""
        client = DashScopeVLMClient(api_key=self.test_api_key)
        result = client.analyze_video("nonexistent_video.mp4")
        self.assertIsNone(result)
        
    def test_analyze_video_file_too_large(self):
        """测试分析过大的视频文件"""
        # 创建一个模拟的大文件
        temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        
        try:
            # 写入超过100MB的数据
            large_data = b'0' * (101 * 1024 * 1024)  # 101MB
            temp_file.write(large_data)
            temp_file.close()
            
            client = DashScopeVLMClient(api_key=self.test_api_key)
            result = client.analyze_video(temp_file.name)
            self.assertIsNone(result)
            
        finally:
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
                
    @patch('dashscope_vlm_client.MultiModalConversation.call')
    def test_analyze_video_api_error(self, mock_call):
        """测试API调用错误的情况"""
        # 模拟API错误
        mock_call.side_effect = Exception("API调用失败")
        
        video_path = self.create_test_video(duration_seconds=1)
        
        try:
            client = DashScopeVLMClient(api_key=self.test_api_key)
            result = client.analyze_video(video_path)
            self.assertIsNone(result)
            
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

class TestAsyncVideoProcessor(unittest.TestCase):
    def setUp(self):
        """测试前的设置"""
        self.test_api_key = "test_api_key_12345"
        self.vlm_client = DashScopeVLMClient(api_key=self.test_api_key)
        
    def test_processor_initialization(self):
        """测试处理器初始化"""
        processor = AsyncVideoProcessor(self.vlm_client)
        self.assertEqual(processor.vlm_client, self.vlm_client)
        self.assertIsNotNone(processor.temp_dir)
        self.assertEqual(processor.video_fps, 10)
        self.assertEqual(processor.video_duration, 10)
        
    def test_processor_start_stop(self):
        """测试处理器启动和停止"""
        processor = AsyncVideoProcessor(self.vlm_client)
        
        # 启动处理器
        processor.start()
        self.assertIsNotNone(processor.video_writer_thread)
        self.assertIsNotNone(processor.inference_thread)
        self.assertTrue(processor.video_writer_thread.is_alive())
        self.assertTrue(processor.inference_thread.is_alive())
        
        # 停止处理器
        processor.stop()
        self.assertFalse(processor.video_writer_thread.is_alive())
        self.assertFalse(processor.inference_thread.is_alive())
        
    def test_add_frame(self):
        """测试添加帧"""
        processor = AsyncVideoProcessor(self.vlm_client)
        
        # 创建测试帧
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 添加帧（不启动处理器，只测试队列操作）
        processor.add_frame(frame)
        
        # 验证帧已添加到队列
        self.assertFalse(processor.frame_queue.empty())

class TestRTSPVLMMonitor(unittest.TestCase):
    def setUp(self):
        """测试前的设置"""
        self.test_api_key = "test_api_key_12345"
        self.vlm_client = DashScopeVLMClient(api_key=self.test_api_key)
        
    def test_monitor_initialization(self):
        """测试监控器初始化"""
        # 创建模拟的RTSP客户端
        mock_rtsp_client = MagicMock()
        
        # 创建结果回调函数
        def result_callback(result):
            print(f"收到结果: {result}")
            
        monitor = RTSPVLMMonitor(mock_rtsp_client, self.vlm_client, result_callback)
        
        self.assertEqual(monitor.rtsp_client, mock_rtsp_client)
        self.assertEqual(monitor.vlm_client, self.vlm_client)
        self.assertEqual(monitor.result_callback, result_callback)
        self.assertIsNotNone(monitor.video_processor)

class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        """测试前的设置"""
        self.test_api_key = "test_api_key_12345"
        
    @patch('dashscope_vlm_client.MultiModalConversation.call')
    def test_end_to_end_video_processing(self, mock_call):
        """端到端视频处理测试"""
        # 模拟API响应
        mock_response = {
            "output": {
                "choices": [{
                    "message": {
                        "content": [{
                            "text": "检测到正常的监控画面，没有异常情况。"
                        }]
                    }
                }]
            }
        }
        mock_call.return_value = mock_response
        
        # 创建VLM客户端
        vlm_client = DashScopeVLMClient(api_key=self.test_api_key)
        
        # 创建异步视频处理器
        processor = AsyncVideoProcessor(vlm_client)
        
        # 收集结果的列表
        results = []
        
        def collect_results():
            """收集处理结果"""
            while True:
                result = processor.get_result(timeout=0.1)
                if result:
                    results.append(result)
                else:
                    break
                    
        try:
            # 启动处理器
            processor.start()
            
            # 添加一些测试帧
            for i in range(50):  # 添加50帧，应该能生成一个视频片段
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, f"Frame {i}", (50, 50), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                processor.add_frame(frame)
                time.sleep(0.01)  # 模拟帧间隔
                
            # 等待处理完成
            time.sleep(2)
            
            # 收集结果
            collect_results()
            
            # 验证是否有结果
            self.assertGreater(len(results), 0, "应该至少有一个处理结果")
            
            # 验证结果格式
            for result in results:
                self.assertIn('video_path', result)
                self.assertIn('result', result)
                self.assertIn('timestamp', result)
                
        finally:
            # 停止处理器
            processor.stop()

if __name__ == '__main__':
    # 设置测试环境
    os.environ['DASHSCOPE_API_KEY'] = 'test_api_key_for_testing'
    
    # 运行测试
    unittest.main(verbosity=2) 