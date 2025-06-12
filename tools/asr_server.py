#!/usr/bin/env python3
"""
ASR FastAPI服务器
接收ASR客户端发送的用户问题，并将问题传递给VLM推理系统
"""

import os
import sys
import time
import signal
import logging
import argparse
import threading
import uvicorn
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root / 'src'))

from monitor.core.config import load_config

# 配置日志
Path('logs').mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/asr_server.log')
    ]
)
logger = logging.getLogger(__name__)

# Pydantic模型
class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: float

class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")

class QuestionResponse(BaseModel):
    has_question: bool
    question: Optional[str] = None
    timestamp: Optional[str] = None
    message: Optional[str] = None

class ServerStats(BaseModel):
    server_status: str
    current_question_exists: bool
    question_timestamp: Optional[str] = None
    question_timeout_seconds: int
    max_question_length: int
    uptime_seconds: float

class ASRServerState:
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化ASR服务器状态
        
        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        self.config = load_config(Path(config_path) if config_path else None)
        self.asr_config = self.config.get('asr', {})
        
        # 服务器配置
        self.host = self.asr_config.get('host', '0.0.0.0')
        self.port = self.asr_config.get('port', 8081)
        self.max_question_length = self.asr_config.get('max_question_length', 500)
        self.question_timeout = self.asr_config.get('question_timeout', 300)  # 5分钟
        
        # 当前用户问题状态
        self.current_question = None
        self.question_timestamp = None
        self.question_lock = threading.Lock()
        
        # 运行状态
        self.running = False
        self.start_time = None
        
        logger.info(f"ASR服务器状态初始化完成:")
        logger.info(f"  - 监听地址: {self.host}:{self.port}")
        logger.info(f"  - 最大问题长度: {self.max_question_length}字符")
        logger.info(f"  - 问题超时时间: {self.question_timeout}秒")
    
    def _is_question_expired(self) -> bool:
        """检查当前问题是否已超时"""
        if self.question_timestamp is None:
            return True
        
        elapsed = datetime.now() - self.question_timestamp
        return elapsed.total_seconds() > self.question_timeout
    
    def set_question(self, question: str) -> Dict[str, Any]:
        """
        设置当前用户问题
        
        Args:
            question: 用户问题
            
        Returns:
            操作结果
        """
        with self.question_lock:
            self.current_question = question
            self.question_timestamp = datetime.now()
        
        logger.info(f"收到用户问题: {question}")
        
        return {
            'status': 'success',
            'message': '问题已接收',
            'question': question,
            'timestamp': self.question_timestamp.isoformat()
        }
    
    def get_current_question(self) -> Dict[str, Any]:
        """
        获取当前问题
        
        Returns:
            当前问题信息
        """
        with self.question_lock:
            if self.current_question is None:
                return {
                    'has_question': False,
                    'question': None,
                    'timestamp': None
                }
            
            # 检查问题是否超时
            if self._is_question_expired():
                self.current_question = None
                self.question_timestamp = None
                return {
                    'has_question': False,
                    'question': None,
                    'timestamp': None,
                    'message': '问题已超时'
                }
            
            return {
                'has_question': True,
                'question': self.current_question,
                'timestamp': self.question_timestamp.isoformat()
            }
    
    def clear_question(self) -> Dict[str, Any]:
        """
        清除当前问题
        
        Returns:
            操作结果
        """
        with self.question_lock:
            old_question = self.current_question
            self.current_question = None
            self.question_timestamp = None
        
        logger.info(f"已清除问题: {old_question}")
        return {
            'status': 'success',
            'message': '问题已清除',
            'cleared_question': old_question
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取服务器统计信息
        
        Returns:
            统计信息
        """
        with self.question_lock:
            return {
                'server_status': 'running' if self.running else 'stopped',
                'current_question_exists': self.current_question is not None,
                'question_timestamp': self.question_timestamp.isoformat() if self.question_timestamp else None,
                'question_timeout_seconds': self.question_timeout,
                'max_question_length': self.max_question_length,
                'uptime_seconds': time.time() - self.start_time if self.start_time else 0
            }

# 全局状态
state = None

# 创建FastAPI应用
app = FastAPI(
    title="ASR服务器API",
    description="语音识别问题接收服务器",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=ApiResponse)
async def health_check():
    """健康检查端点"""
    return ApiResponse(
        success=True,
        data={
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'current_question': state.current_question is not None if state else False
        },
        timestamp=time.time()
    )

@app.post("/asr", response_model=ApiResponse)
async def receive_question(request: QuestionRequest):
    """接收用户问题端点"""
    try:
        question = request.question.strip()
        
        # 验证问题长度
        if len(question) > state.max_question_length:
            raise HTTPException(
                status_code=400,
                detail=f'问题长度超过限制（{len(question)} > {state.max_question_length}）'
            )
        
        # 设置问题
        result = state.set_question(question)
        
        return ApiResponse(
            success=True,
            data=result,
            timestamp=time.time()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理用户问题时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f'服务器内部错误: {str(e)}')

@app.get("/question/current", response_model=ApiResponse)
async def get_current_question():
    """获取当前问题端点（供推理系统调用）"""
    try:
        result = state.get_current_question()
        
        return ApiResponse(
            success=True,
            data=result,
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.error(f"获取当前问题时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f'服务器内部错误: {str(e)}')

@app.post("/question/clear", response_model=ApiResponse)
async def clear_question():
    """清除当前问题端点（供推理系统调用）"""
    try:
        result = state.clear_question()
        
        return ApiResponse(
            success=True,
            data=result,
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.error(f"清除问题时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f'服务器内部错误: {str(e)}')

@app.get("/stats", response_model=ApiResponse)
async def get_stats():
    """获取服务器统计信息"""
    try:
        result = state.get_stats()
        
        return ApiResponse(
            success=True,
            data=result,
            timestamp=time.time()
        )
        
    except Exception as e:
        logger.error(f"获取统计信息时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f'服务器内部错误: {str(e)}')

# 全局ASR服务器实例（供其他模块导入使用）
_asr_server_instance = None

def get_asr_server() -> Optional[ASRServerState]:
    """获取全局ASR服务器实例"""
    return _asr_server_instance

def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到信号 {signum}，正在停止ASR服务器...")
    if hasattr(signal_handler, 'server_state'):
        signal_handler.server_state.running = False
    sys.exit(0)

def main():
    """主函数"""
    global state, _asr_server_instance
    
    parser = argparse.ArgumentParser(description='ASR FastAPI服务器')
    parser.add_argument('--config', '-c', type=str, help='配置文件路径')
    parser.add_argument('--host', type=str, help='监听主机地址')
    parser.add_argument('--port', '-p', type=int, help='监听端口')
    
    args = parser.parse_args()
    
    try:
        # 创建ASR服务器状态
        state = ASRServerState(config_path=args.config)
        _asr_server_instance = state
        
        # 覆盖配置
        if args.host:
            state.host = args.host
            logger.info(f"使用命令行指定的主机地址: {args.host}")
        
        if args.port:
            state.port = args.port
            logger.info(f"使用命令行指定的端口: {args.port}")
        
        # 设置信号处理
        signal_handler.server_state = state
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 启动服务器
        state.running = True
        state.start_time = time.time()
        
        logger.info(f"ASR服务器将在 http://{state.host}:{state.port} 启动")
        logger.info(f"接收问题端点: POST /asr")
        logger.info(f"健康检查端点: GET /health")
        logger.info(f"获取当前问题端点: GET /question/current")
        logger.info(f"清除问题端点: POST /question/clear")
        logger.info(f"统计信息端点: GET /stats")
        logger.info(f"API文档: http://{state.host}:{state.port}/docs")
        
        # 启动FastAPI应用
        uvicorn.run(
            app,
            host=state.host,
            port=state.port,
            log_level="info",
            access_log=True
        )
        
    except Exception as e:
        logger.error(f"程序异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if state:
            state.running = False

if __name__ == "__main__":
    main() 