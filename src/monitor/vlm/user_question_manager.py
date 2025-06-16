#!/usr/bin/env python3
"""
用户问题管理器
负责从ASR服务器获取用户问题，并将问题传递给VLM推理系统
"""

import requests
import logging
import threading
import time
import uuid
from typing import Optional, Dict, Any, Tuple
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
        
        # 问题分配状态管理
        self.question_assigned = False  # 问题是否已被分配
        self.assigned_task_id = None    # 分配给哪个任务
        self.assignment_time = None     # 分配时间
        
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
                                # 🔧 修复竞争条件：预先分配问题，避免多个帧同时被认为有用户问题
                                # 生成预分配的任务ID，但标记为未真正分配
                                self.question_assigned = True  # 立即标记为已分配，防止竞争
                                self.assigned_task_id = "pending"  # 使用特殊标记表示预分配状态
                                self.assignment_time = time.time()
                                logger.info(f"获取到新的用户问题: {new_question}")
                        else:
                            # 没有问题或问题已超时
                            if self.current_question is not None:
                                logger.info("用户问题已清除或超时")
                                self.current_question = None
                                self.question_timestamp = None
                                self.question_assigned = False
                                self.assigned_task_id = None
                                self.assignment_time = None
                else:
                    logger.warning(f"ASR服务器API响应失败: {api_response.get('error', 'Unknown error')}")
            else:
                logger.warning(f"获取用户问题失败: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            # 网络错误，可能ASR服务器未启动，不记录错误避免日志污染
            pass
        except Exception as e:
            logger.error(f"获取用户问题时出错: {str(e)}")
    
    def acquire_question(self) -> Tuple[Optional[str], Optional[str]]:
        """
        原子性获取当前用户问题（仅分配给一个任务）
        
        Returns:
            Tuple[question, task_id]: 问题字符串和任务ID，如果没有可用问题则返回(None, None)
        """
        with self.question_lock:
            # 如果没有问题，返回None
            if self.current_question is None:
                return None, None
            
            # 🔧 修复竞争条件：检查是否是预分配状态
            if self.question_assigned and self.assigned_task_id == "pending":
                # 这是预分配状态，现在真正分配给当前任务
                task_id = str(uuid.uuid4())[:8]  # 生成真实任务ID
                self.assigned_task_id = task_id
                self.assignment_time = time.time()  # 更新分配时间
                
                logger.info(f"问题已分配给任务 {task_id}: {self.current_question}")
                return self.current_question, task_id
            elif self.question_assigned and self.assigned_task_id != "pending":
                # 问题已被其他任务分配，返回None
                return None, None
            else:
                # 这种情况不应该发生（question_assigned=False但有问题），为了兼容性处理
                logger.warning("检测到异常状态：有问题但未预分配，进行紧急分配")
                task_id = str(uuid.uuid4())[:8]
                self.question_assigned = True
                self.assigned_task_id = task_id
                self.assignment_time = time.time()
                
                logger.info(f"紧急分配问题给任务 {task_id}: {self.current_question}")
                return self.current_question, task_id
    
    def get_current_question(self) -> Optional[str]:
        """
        获取当前用户问题（兼容性方法，已废弃）
        
        Returns:
            当前问题字符串，如果没有问题则返回None
            
        Warning:
            此方法已废弃，请使用 acquire_question() 方法
        """
        logger.warning("get_current_question() 方法已废弃，请使用 acquire_question() 方法")
        with self.question_lock:
            return self.current_question
    
    def release_question(self, task_id: str, success: bool = True):
        """
        释放问题（推理完成后调用）
        
        Args:
            task_id: 任务ID
            success: 推理是否成功
        """
        with self.question_lock:
            # 检查任务ID是否匹配
            if self.assigned_task_id != task_id:
                logger.warning(f"任务ID不匹配: 期望 {self.assigned_task_id}, 实际 {task_id}")
                return
            
            old_question = self.current_question
            
            # 如果推理成功，清除问题并通知ASR服务器
            if success and old_question:
                try:
                    # 通知ASR服务器清除问题
                    response = requests.post(
                        f"{self.asr_server_url}/question/clear",
                        timeout=self.timeout
                    )
                    
                    if response.status_code == 200:
                        api_response = response.json()
                        
                        if api_response.get('success', False):
                            self.current_question = None
                            self.question_timestamp = None
                            logger.info(f"任务 {task_id} 推理成功，已清除用户问题: {old_question}")
                        else:
                            logger.warning(f"ASR服务器清除问题失败: {api_response.get('error', 'Unknown error')}")
                    else:
                        logger.warning(f"清除用户问题失败: HTTP {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    logger.warning(f"清除用户问题时网络错误: {str(e)}")
                except Exception as e:
                    logger.error(f"清除用户问题时出错: {str(e)}")
            else:
                logger.info(f"任务 {task_id} 推理失败或无问题，保留问题状态")
            
            # 重置分配状态
            self.question_assigned = False
            self.assigned_task_id = None
            self.assignment_time = None
    
    def clear_current_question(self):
        """清除当前问题（兼容性方法，已废弃）"""
        logger.warning("clear_current_question() 方法已废弃，请使用 release_question() 方法")
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
                        self.question_assigned = False
                        self.assigned_task_id = None
                        self.assignment_time = None
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
    
    def has_available_question(self) -> bool:
        """检查是否有可用的（未分配的）问题"""
        with self.question_lock:
            # 🔧 修复竞争条件：预分配状态也算作不可用
            return (self.current_question is not None and 
                    not self.question_assigned)
    
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
                'question_assigned': self.question_assigned,
                'assigned_task_id': self.assigned_task_id,
                'assignment_time': self.assignment_time,
                'assignment_duration': time.time() - self.assignment_time if self.assignment_time else None,
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