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
from typing import Optional, Dict, Any, List
from datetime import datetime
import hashlib

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
            
            # 按修改时间排序，获取最新的
            latest_session = sorted(session_dirs, key=lambda x: x.stat().st_mtime)[-1]
            logger.debug(f"最新session目录: {latest_session}")
            return latest_session
            
        except Exception as e:
            logger.error(f"获取最新session目录失败: {e}")
            return None
    
    def _get_frame_details_dirs(self, session_dir: Path) -> List[Path]:
        """获取session目录下所有frame的details目录"""
        try:
            frame_dirs = []
            for item in session_dir.iterdir():
                if item.is_dir() and item.name.endswith('_details'):
                    frame_dirs.append(item)
            
            # 按名称排序，确保按时间顺序处理
            frame_dirs.sort(key=lambda x: x.name)
            return frame_dirs
            
        except Exception as e:
            logger.error(f"获取frame details目录失败: {e}")
            return []
    
    def _load_inference_result(self, frame_dir: Path) -> Optional[Dict[Any, Any]]:
        """加载frame目录中的inference_result.json文件"""
        try:
            result_file = frame_dir / 'inference_result.json'
            if not result_file.exists():
                logger.debug(f"inference_result.json不存在: {result_file}")
                return None
            
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
            
        except Exception as e:
            logger.error(f"加载inference_result.json失败: {e}")
            return None
    
    def _load_user_question_result(self, frame_dir: Path) -> Optional[Dict[Any, Any]]:
        """加载frame目录中的user_question.json文件"""
        try:
            user_question_file = frame_dir / 'user_question.json'
            if not user_question_file.exists():
                logger.debug(f"user_question.json不存在: {user_question_file}")
                return None
            
            with open(user_question_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
            
        except Exception as e:
            logger.error(f"加载user_question.json失败: {e}")
            return None
    
    def _extract_summary_from_inference_result(self, inference_data: Dict[Any, Any]) -> Optional[str]:
        """从推理结果中提取summary字段"""
        try:
            # 从parsed_result中直接获取summary
            parsed_result = inference_data.get('parsed_result', {})
            response = parsed_result.get('response', '')
            
            if response:
                logger.debug(f"提取到summary: {response}")
                return response
            
            # 如果parsed_result中没有，尝试从raw_result中解析
            raw_result = inference_data.get('raw_result', '')
            if raw_result:
                return self._extract_summary_from_raw_result(raw_result)
            
            logger.warning(f"无法从推理结果中提取summary")
            return None
            
        except Exception as e:
            logger.error(f"提取summary失败: {e}")
            return None
    
    def _extract_summary_from_raw_result(self, raw_result: str) -> Optional[str]:
        """从原始结果字符串中提取summary字段"""
        try:
            # 推理结果通常包含在```json和```之间
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_result, re.DOTALL)
            if not json_match:
                # 尝试直接解析JSON
                json_match = re.search(r'(\{.*\})', raw_result, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
                result_data = json.loads(json_str)
                summary = result_data.get('response', '')
                if summary:
                    logger.debug(f"从raw_result提取到summary: {summary}")
                    return summary
            
            logger.warning(f"无法从raw_result中提取summary: {raw_result[:100]}...")
            return None
            
        except Exception as e:
            logger.error(f"从raw_result提取summary失败: {e}")
            return None
    
    def _extract_response_from_user_question_result(self, user_question_data: Dict[Any, Any]) -> Optional[str]:
        """从用户问题结果中提取response字段"""
        try:
            response = user_question_data.get('response', '')
            
            if response:
                logger.debug(f"提取到用户问题回答: {response}")
                return response
            
            logger.warning(f"用户问题结果中没有response字段")
            return None
            
        except Exception as e:
            logger.error(f"提取用户问题回答失败: {e}")
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
    
    def _get_inference_result_id(self, frame_dir: Path, inference_data: Dict[Any, Any]) -> str:
        """生成推理结果的唯一ID"""
        try:
            # 使用frame目录名和推理开始时间作为唯一标识
            frame_name = frame_dir.name
            start_time = inference_data.get('inference_start_time', 0)
            return f"{frame_name}_{start_time}"
        except Exception as e:
            logger.error(f"生成推理结果ID失败: {e}")
            return f"{frame_dir.name}_{time.time()}"
    
    def _get_user_question_result_id(self, frame_dir: Path, user_question_data: Dict[Any, Any]) -> str:
        """生成用户问题结果的唯一ID"""
        try:
            # 🔧 修复：使用frame目录名和用户问题内容的hash作为唯一标识，而不是时间戳
            # 这样即使文件被重新写入，只要内容相同，ID就不会变化
            frame_name = frame_dir.name
            user_question = user_question_data.get('user_question', '')
            response = user_question_data.get('response', '')
            
            # 使用问题和回答的组合生成稳定的hash
            content_hash = hashlib.md5(f"{user_question}_{response}".encode('utf-8')).hexdigest()[:8]
            
            return f"{frame_name}_user_question_{content_hash}"
        except Exception as e:
            logger.error(f"生成用户问题结果ID失败: {e}")
            return f"{frame_dir.name}_user_question_{time.time()}"
    
    def _process_new_results(self):
        """处理新的推理结果"""
        try:
            # 获取最新session目录
            session_dir = self._get_latest_session_dir()
            if not session_dir:
                return
            
            # 获取所有frame details目录
            frame_dirs = self._get_frame_details_dirs(session_dir)
            if not frame_dirs:
                logger.debug("没有找到frame details目录")
                return
            
            # 处理新的推理结果
            new_results_count = 0
            for frame_dir in frame_dirs:
                # 🆕 优先检查用户问题结果
                user_question_data = self._load_user_question_result(frame_dir)
                if user_question_data:
                    # 生成用户问题结果的唯一ID
                    user_question_id = self._get_user_question_result_id(frame_dir, user_question_data)
                    
                    # 跳过已处理的用户问题结果
                    if user_question_id in self.processed_results:
                        continue
                    
                    # 提取用户问题回答
                    response = self._extract_response_from_user_question_result(user_question_data)
                    
                    if response:
                        # 发送到TTS服务
                        if self._send_to_tts(response):
                            self.processed_results.add(user_question_id)
                            new_results_count += 1
                            logger.info(f"成功处理用户问题结果: {frame_dir.name}")
                        else:
                            # 🔧 修复：即使TTS发送失败也标记为已处理，避免无限重试
                            self.processed_results.add(user_question_id)
                            logger.warning(f"TTS发送失败，用户问题结果ID: {user_question_id}，已标记为已处理避免重试")
                    else:
                        # 即使没有response也标记为已处理，避免重复处理
                        self.processed_results.add(user_question_id)
                        logger.debug(f"用户问题结果无response，跳过: {frame_dir.name}")
                    
                    # 如果处理了用户问题，跳过常规推理结果处理
                    continue
                
                # 🔄 如果没有用户问题结果，处理常规推理结果
                # 加载推理结果
                inference_data = self._load_inference_result(frame_dir)
                if not inference_data:
                    continue
                
                result_id = self._get_inference_result_id(frame_dir, inference_data)
                
                # 跳过已处理的结果
                if result_id in self.processed_results:
                    continue
                
                # 提取summary
                summary = self._extract_summary_from_inference_result(inference_data)
                
                if summary:
                    # 发送到TTS服务
                    if self._send_to_tts(summary):
                        self.processed_results.add(result_id)
                        new_results_count += 1
                        logger.info(f"成功处理推理结果: {frame_dir.name}")
                    else:
                        # 🔧 修复：即使TTS发送失败也标记为已处理，避免无限重试
                        self.processed_results.add(result_id)
                        logger.warning(f"TTS发送失败，结果ID: {result_id}，已标记为已处理避免重试")
                else:
                    # 即使没有summary也标记为已处理，避免重复处理
                    self.processed_results.add(result_id)
                    logger.debug(f"推理结果无summary，跳过: {frame_dir.name}")
            
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