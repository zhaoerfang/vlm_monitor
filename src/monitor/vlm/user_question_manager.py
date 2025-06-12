#!/usr/bin/env python3
"""
用户问题管理器
负责从ASR服务器获取用户问题，并将问题传递给VLM推理系统
"""

import requests
import logging
import threading
import time
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class UserQuestionManager:
    def __init__(self, asr_server_url: str = "http://localhost:8081", 
                 check_interval: float = 1.0, timeout: float = 5.0):
        """
        初始化用户问题管理器
        
        Args:
            asr_server_url: ASR服务器URL
            check_interval: 检查问题的间隔时间（秒）
            timeout: HTTP请求超时时间（秒）
        """
        self.asr_server_url = asr_server_url.rstrip('/')
        self.check_interval = check_interval
        self.timeout = timeout
        
        # 当前问题状态
        self.current_question = None
        self.question_timestamp = None
        self.question_lock = threading.Lock()
        
        # 运行状态
        self.running = False
        self.check_thread = None
        
        logger.info(f"用户问题管理器初始化:")
        logger.info(f"  - ASR服务器: {self.asr_server_url}")
        logger.info(f"  - 检查间隔: {self.check_interval}秒")
        logger.info(f"  - 请求超时: {self.timeout}秒")
    
    def start(self):
        """启动问题检查线程"""
        if self.running:
            logger.warning("用户问题管理器已在运行")
            return
        
        self.running = True
        self.check_thread = threading.Thread(
            target=self._check_questions_loop,
            name="QuestionChecker",
            daemon=True
        )
        self.check_thread.start()
        logger.info("用户问题管理器已启动")
    
    def stop(self):
        """停止问题检查线程"""
        self.running = False
        if self.check_thread:
            self.check_thread.join(timeout=5)
        logger.info("用户问题管理器已停止")
    
    def _check_questions_loop(self):
        """问题检查循环"""
        while self.running:
            try:
                self._fetch_current_question()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"检查用户问题时出错: {str(e)}")
                time.sleep(self.check_interval)
    
    def _fetch_current_question(self):
        """从ASR服务器获取当前问题"""
        try:
            response = requests.get(
                f"{self.asr_server_url}/question/current",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                api_response = response.json()
                
                # 检查API响应格式
                if api_response.get('success', False):
                    data = api_response.get('data', {})
                    
                    with self.question_lock:
                        if data.get('has_question', False):
                            new_question = data.get('question')
                            new_timestamp = data.get('timestamp')
                            
                            # 只有当问题发生变化时才更新
                            if (new_question != self.current_question or 
                                new_timestamp != self.question_timestamp):
                                self.current_question = new_question
                                self.question_timestamp = new_timestamp
                                logger.info(f"获取到新的用户问题: {new_question}")
                        else:
                            # 没有问题或问题已超时
                            if self.current_question is not None:
                                logger.info("用户问题已清除或超时")
                                self.current_question = None
                                self.question_timestamp = None
                else:
                    logger.warning(f"ASR服务器API响应失败: {api_response.get('error', 'Unknown error')}")
            else:
                logger.warning(f"获取用户问题失败: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            # 网络错误，可能ASR服务器未启动，不记录错误避免日志污染
            pass
        except Exception as e:
            logger.error(f"获取用户问题时出错: {str(e)}")
    
    def get_current_question(self) -> Optional[str]:
        """
        获取当前用户问题
        
        Returns:
            当前问题字符串，如果没有问题则返回None
        """
        with self.question_lock:
            return self.current_question
    
    def clear_current_question(self):
        """清除当前问题（推理完成后调用）"""
        try:
            # 通知ASR服务器清除问题
            response = requests.post(
                f"{self.asr_server_url}/question/clear",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                api_response = response.json()
                
                if api_response.get('success', False):
                    with self.question_lock:
                        old_question = self.current_question
                        self.current_question = None
                        self.question_timestamp = None
                        if old_question:
                            logger.info(f"已清除用户问题: {old_question}")
                else:
                    logger.warning(f"ASR服务器清除问题失败: {api_response.get('error', 'Unknown error')}")
            else:
                logger.warning(f"清除用户问题失败: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"清除用户问题时网络错误: {str(e)}")
        except Exception as e:
            logger.error(f"清除用户问题时出错: {str(e)}")
    
    def has_question(self) -> bool:
        """检查是否有当前问题"""
        with self.question_lock:
            return self.current_question is not None
    
    def get_question_info(self) -> Dict[str, Any]:
        """
        获取问题详细信息
        
        Returns:
            包含问题信息的字典
        """
        with self.question_lock:
            return {
                'has_question': self.current_question is not None,
                'question': self.current_question,
                'timestamp': self.question_timestamp,
                'manager_running': self.running
            }
    
    def check_asr_server_health(self) -> bool:
        """检查ASR服务器健康状态"""
        try:
            response = requests.get(
                f"{self.asr_server_url}/health",
                timeout=self.timeout
            )
            if response.status_code == 200:
                api_response = response.json()
                return api_response.get('success', False)
            return False
        except:
            return False

# 全局用户问题管理器实例
_question_manager_instance = None

def get_question_manager() -> Optional[UserQuestionManager]:
    """获取全局用户问题管理器实例"""
    return _question_manager_instance

def init_question_manager(asr_server_url: str = "http://localhost:8081", 
                         check_interval: float = 1.0, timeout: float = 5.0) -> UserQuestionManager:
    """
    初始化全局用户问题管理器
    
    Args:
        asr_server_url: ASR服务器URL
        check_interval: 检查问题的间隔时间（秒）
        timeout: HTTP请求超时时间（秒）
        
    Returns:
        用户问题管理器实例
    """
    global _question_manager_instance
    
    if _question_manager_instance is None:
        _question_manager_instance = UserQuestionManager(
            asr_server_url=asr_server_url,
            check_interval=check_interval,
            timeout=timeout
        )
    
    return _question_manager_instance 