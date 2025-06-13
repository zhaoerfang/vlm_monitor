#!/usr/bin/env python3
"""
测试用户问题分配机制
验证多个并发任务只有一个能获取到用户问题
"""

import sys
import os
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitor.vlm.user_question_manager import UserQuestionManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def simulate_inference_task(task_name: str, question_manager: UserQuestionManager, delay: float = 0):
    """模拟推理任务"""
    try:
        # 模拟任务启动延迟
        if delay > 0:
            time.sleep(delay)
        
        logger.info(f"任务 {task_name} 开始尝试获取问题")
        
        # 尝试获取问题
        question, task_id = question_manager.acquire_question()
        
        if question and task_id:
            logger.info(f"✅ 任务 {task_name} 成功获取问题: {question} (任务ID: {task_id})")
            
            # 模拟推理过程
            inference_time = 2.0 + (hash(task_name) % 3)  # 2-5秒的推理时间
            logger.info(f"任务 {task_name} 开始推理，预计耗时 {inference_time:.1f}s")
            time.sleep(inference_time)
            
            # 模拟推理成功
            success = True
            question_manager.release_question(task_id, success)
            logger.info(f"✅ 任务 {task_name} 推理完成，已释放问题")
            
            return True
        else:
            logger.info(f"❌ 任务 {task_name} 未获取到问题")
            return False
            
    except Exception as e:
        logger.error(f"任务 {task_name} 执行失败: {str(e)}")
        return False

def test_question_assignment():
    """测试问题分配机制"""
    logger.info("=" * 60)
    logger.info("开始测试用户问题分配机制")
    logger.info("=" * 60)
    
    # 创建问题管理器（不连接真实ASR服务器）
    question_manager = UserQuestionManager(
        asr_server_url="http://localhost:8081",
        check_interval=1.0,
        timeout=5.0
    )
    
    # 手动设置一个测试问题
    with question_manager.question_lock:
        question_manager.current_question = "帮我找一个穿黑色衣服的人"
        question_manager.question_timestamp = time.time()
        question_manager.question_assigned = False
        question_manager.assigned_task_id = None
        question_manager.assignment_time = None
    
    logger.info(f"设置测试问题: {question_manager.current_question}")
    
    # 测试1: 单个任务获取问题
    logger.info("\n--- 测试1: 单个任务获取问题 ---")
    result = simulate_inference_task("单任务测试", question_manager)
    logger.info(f"单任务测试结果: {'成功' if result else '失败'}")
    
    # 重新设置问题用于下一个测试
    with question_manager.question_lock:
        question_manager.current_question = "帮我找一个穿红色衣服的人"
        question_manager.question_timestamp = time.time()
        question_manager.question_assigned = False
        question_manager.assigned_task_id = None
        question_manager.assignment_time = None
    
    # 测试2: 多个并发任务竞争问题
    logger.info("\n--- 测试2: 多个并发任务竞争问题 ---")
    logger.info(f"设置新测试问题: {question_manager.current_question}")
    
    task_names = [f"并发任务{i+1}" for i in range(5)]
    results = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # 提交所有任务，模拟真实的并发场景
        futures = []
        for i, task_name in enumerate(task_names):
            delay = i * 0.1  # 每个任务间隔0.1秒启动
            future = executor.submit(simulate_inference_task, task_name, question_manager, delay)
            futures.append(future)
        
        # 等待所有任务完成
        for future in futures:
            result = future.result()
            results.append(result)
    
    # 统计结果
    successful_tasks = sum(results)
    logger.info(f"\n并发测试结果:")
    logger.info(f"  - 总任务数: {len(results)}")
    logger.info(f"  - 成功获取问题的任务数: {successful_tasks}")
    logger.info(f"  - 未获取到问题的任务数: {len(results) - successful_tasks}")
    
    # 验证结果
    if successful_tasks == 1:
        logger.info("✅ 测试通过: 只有一个任务成功获取到问题")
    else:
        logger.error(f"❌ 测试失败: 应该只有1个任务获取到问题，实际有{successful_tasks}个")
    
    # 测试3: 问题状态检查
    logger.info("\n--- 测试3: 问题状态检查 ---")
    question_info = question_manager.get_question_info()
    logger.info(f"最终问题状态: {question_info}")
    
    if not question_info['has_question']:
        logger.info("✅ 问题已被正确清除")
    else:
        logger.warning("⚠️ 问题仍然存在，可能未被正确清除")
    
    logger.info("\n" + "=" * 60)
    logger.info("测试完成")
    logger.info("=" * 60)

if __name__ == "__main__":
    test_question_assignment() 