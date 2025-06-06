#!/usr/bin/env python3
"""
TTS服务测试脚本
用于测试TTS服务的基本功能
"""

import json
import time
import requests
import argparse
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_tts_endpoint(host: str = "localhost", port: int = 8888, endpoint: str = "/speak"):
    """测试TTS服务端点"""
    url = f"http://{host}:{port}{endpoint}"
    test_text = "这是一个TTS服务测试"
    
    logger.info(f"测试TTS服务: {url}")
    logger.info(f"测试文本: {test_text}")
    
    try:
        payload = {"text": test_text}
        response = requests.post(
            url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ TTS服务测试成功")
            logger.info(f"响应: {response.text}")
            return True
        else:
            logger.error(f"❌ TTS服务测试失败 (状态码: {response.status_code})")
            logger.error(f"响应: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ TTS服务连接失败: {e}")
        return False

def create_test_inference_result(output_dir: str = "tmp"):
    """创建测试用的推理结果"""
    output_path = Path(output_dir)
    
    # 创建测试session目录
    session_name = f"session_test_{int(time.time())}"
    session_dir = output_path / session_name
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建测试推理结果
    test_result = {
        "processor_config": {
            "target_video_duration": 1.0,
            "frames_per_second": 1,
            "original_fps": 25.0
        },
        "statistics": {
            "total_frames_received": 1,
            "total_inferences_completed": 1,
            "start_time": time.time(),
            "start_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        },
        "inference_log": [
            {
                "media_path": f"{session_dir}/test_frame.jpg",
                "media_type": "image",
                "result": """```json
{
  "timestamp": "2025-06-06T10:30:00+08:00",
  "people_count": 2,
  "vehicle_count": 1,
  "people": [
    {
      "id": 1,
      "bbox": [100, 100, 200, 300],
      "activity": "走路"
    },
    {
      "id": 2,
      "bbox": [300, 150, 400, 350],
      "activity": "站立"
    }
  ],
  "vehicles": [
    {
      "id": 1,
      "bbox": [500, 200, 600, 300],
      "type": "小轿车",
      "status": "行驶"
    }
  ],
  "summary": "街道场景，两人在路边，一辆小轿车正在行驶"
}
```""",
                "inference_start_time": time.time(),
                "inference_end_time": time.time() + 1,
                "inference_duration": 1.0
            }
        ]
    }
    
    # 保存测试结果
    log_file = session_dir / "experiment_log.json"
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(test_result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ 创建测试推理结果: {log_file}")
    return session_dir

def test_tts_service_integration(config_path: str = "config.json"):
    """测试TTS服务集成功能"""
    logger.info("🧪 开始TTS服务集成测试")
    
    # 1. 创建测试推理结果
    session_dir = create_test_inference_result()
    
    # 2. 读取配置
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        tts_config = config.get('tts', {})
    except Exception as e:
        logger.error(f"读取配置文件失败: {e}")
        return False
    
    # 3. 测试TTS端点
    host = tts_config.get('host', 'localhost')
    port = tts_config.get('port', 8888)
    endpoint = tts_config.get('endpoint', '/speak')
    
    if not test_tts_endpoint(host, port, endpoint):
        logger.warning("⚠️ TTS服务端点测试失败，请确保外部TTS服务正在运行")
        return False
    
    logger.info("✅ TTS服务集成测试完成")
    return True

def main():
    parser = argparse.ArgumentParser(description='TTS服务测试脚本')
    parser.add_argument('--config', '-c', default='config.json',
                       help='配置文件路径')
    parser.add_argument('--endpoint-only', action='store_true',
                       help='仅测试TTS端点')
    parser.add_argument('--host', default='localhost',
                       help='TTS服务主机地址')
    parser.add_argument('--port', type=int, default=8888,
                       help='TTS服务端口')
    
    args = parser.parse_args()
    
    if args.endpoint_only:
        # 仅测试TTS端点
        success = test_tts_endpoint(args.host, args.port)
    else:
        # 完整集成测试
        success = test_tts_service_integration(args.config)
    
    if success:
        logger.info("🎉 所有测试通过")
    else:
        logger.error("❌ 测试失败")
        exit(1)

if __name__ == "__main__":
    main() 