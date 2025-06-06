#!/usr/bin/env python3
"""
TTS服务脚本
监控最新的推理结果，提取summary字段并发送给外部TTS服务
"""

import os
import sys
import json
import time
import logging
import argparse
import requests
import re
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TTSService:
    def __init__(self, config_path: str = 'config.json'):
        """初始化TTS服务"""
        self.config_path = config_path
        self.config = self._load_config()
        self.tts_config = self.config.get('tts', {})
        self.monitoring_config = self.config.get('monitoring', {})
        
        # TTS服务配置
        self.enabled = self.tts_config.get('enabled', False)
        self.host = self.tts_config.get('host', 'localhost')
        self.port = self.tts_config.get('port', 8888)
        self.endpoint = self.tts_config.get('endpoint', '/speak')
        self.check_interval = self.tts_config.get('check_interval', 5.0)
        self.max_retries = self.tts_config.get('max_retries', 3)
        self.timeout = self.tts_config.get('timeout', 10)
        
        # 监控配置
        self.output_dir = self.monitoring_config.get('output_dir', 'tmp')
        
        # TTS服务URL
        self.tts_url = f"http://{self.host}:{self.port}{self.endpoint}"
        
        # 记录已处理的推理结果
        self.processed_results = set()
        
        logger.info(f"TTS服务初始化完成")
        logger.info(f"TTS服务URL: {self.tts_url}")
        logger.info(f"检查间隔: {self.check_interval}秒")
        logger.info(f"监控目录: {self.output_dir}")
        
    def _load_config(self) -> Dict[Any, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"配置文件加载成功: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def _get_latest_session_dir(self) -> Optional[Path]:
        """获取最新的session目录"""
        try:
            output_path = Path(self.output_dir)
            if not output_path.exists():
                logger.warning(f"输出目录不存在: {output_path}")
                return None
            
            # 查找所有session目录
            session_dirs = [d for d in output_path.iterdir() 
                          if d.is_dir() and d.name.startswith('session_')]
            
            if not session_dirs:
                logger.warning("未找到session目录")
                return None
            
            # 按名称排序，获取最新的
            latest_session = sorted(session_dirs, key=lambda x: x.name)[-1]
            logger.debug(f"最新session目录: {latest_session}")
            return latest_session
            
        except Exception as e:
            logger.error(f"获取最新session目录失败: {e}")
            return None
    
    def _load_experiment_log(self, session_dir: Path) -> Optional[Dict[Any, Any]]:
        """加载experiment_log.json文件"""
        try:
            log_file = session_dir / 'experiment_log.json'
            if not log_file.exists():
                logger.warning(f"experiment_log.json不存在: {log_file}")
                return None
            
            with open(log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
            
        except Exception as e:
            logger.error(f"加载experiment_log.json失败: {e}")
            return None
    
    def _extract_summary_from_result(self, result_text: str) -> Optional[str]:
        """从推理结果中提取summary字段"""
        try:
            # 推理结果通常包含在```json和```之间
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result_text, re.DOTALL)
            if not json_match:
                # 尝试直接解析JSON
                json_match = re.search(r'(\{.*\})', result_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
                result_data = json.loads(json_str)
                summary = result_data.get('summary', '')
                if summary:
                    logger.debug(f"提取到summary: {summary}")
                    return summary
            
            logger.warning(f"无法从结果中提取summary: {result_text[:100]}...")
            return None
            
        except Exception as e:
            logger.error(f"提取summary失败: {e}")
            return None
    
    def _send_to_tts(self, text: str) -> bool:
        """发送文本到TTS服务"""
        try:
            payload = {"text": text}
            
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"发送TTS请求 (尝试 {attempt + 1}/{self.max_retries}): {text}")
                    
                    response = requests.post(
                        self.tts_url,
                        json=payload,
                        headers={'Content-Type': 'application/json'},
                        timeout=self.timeout
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"TTS请求成功: {text}")
                        return True
                    else:
                        logger.warning(f"TTS请求失败 (状态码: {response.status_code}): {response.text}")
                        
                except requests.exceptions.RequestException as e:
                    logger.warning(f"TTS请求异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(1)  # 重试前等待1秒
            
            logger.error(f"TTS请求最终失败: {text}")
            return False
            
        except Exception as e:
            logger.error(f"发送TTS请求异常: {e}")
            return False
    
    def _get_inference_result_id(self, inference_result: Dict[Any, Any]) -> str:
        """生成推理结果的唯一ID"""
        try:
            # 使用media_path和inference_start_time作为唯一标识
            media_path = inference_result.get('media_path', '')
            start_time = inference_result.get('inference_start_time', 0)
            return f"{media_path}_{start_time}"
        except Exception as e:
            logger.error(f"生成推理结果ID失败: {e}")
            return str(time.time())
    
    def _process_new_results(self):
        """处理新的推理结果"""
        try:
            # 获取最新session目录
            session_dir = self._get_latest_session_dir()
            if not session_dir:
                return
            
            # 加载experiment_log.json
            experiment_data = self._load_experiment_log(session_dir)
            if not experiment_data:
                return
            
            # 获取推理日志
            inference_log = experiment_data.get('inference_log', [])
            if not inference_log:
                logger.debug("没有推理结果")
                return
            
            # 处理新的推理结果
            new_results_count = 0
            for inference_result in inference_log:
                result_id = self._get_inference_result_id(inference_result)
                
                # 跳过已处理的结果
                if result_id in self.processed_results:
                    continue
                
                # 提取summary
                result_text = inference_result.get('result', '')
                summary = self._extract_summary_from_result(result_text)
                
                if summary:
                    # 发送到TTS服务
                    if self._send_to_tts(summary):
                        self.processed_results.add(result_id)
                        new_results_count += 1
                    else:
                        logger.warning(f"TTS发送失败，结果ID: {result_id}")
                else:
                    # 即使没有summary也标记为已处理，避免重复处理
                    self.processed_results.add(result_id)
            
            if new_results_count > 0:
                logger.info(f"处理了 {new_results_count} 个新的推理结果")
            
        except Exception as e:
            logger.error(f"处理推理结果失败: {e}")
    
    def run(self):
        """运行TTS服务"""
        if not self.enabled:
            logger.warning("TTS服务未启用，请在配置文件中设置 tts.enabled = true")
            return
        
        logger.info("🎵 TTS服务启动")
        logger.info(f"监控推理结果，每 {self.check_interval} 秒检查一次")
        
        try:
            while True:
                self._process_new_results()
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("收到停止信号，TTS服务退出")
        except Exception as e:
            logger.error(f"TTS服务运行异常: {e}")
            raise

def main():
    parser = argparse.ArgumentParser(description='TTS服务 - 监控推理结果并发送语音合成请求')
    parser.add_argument('--config', '-c', default='config.json', 
                       help='配置文件路径 (默认: config.json)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='启用详细日志')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 创建并运行TTS服务
    tts_service = TTSService(config_path=args.config)
    tts_service.run()

if __name__ == "__main__":
    main() 