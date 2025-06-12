#!/usr/bin/env python3
"""
摄像头控制异步推理服务
基于 MCP 的摄像头控制服务，接收图像和用户问题，进行智能分析并控制摄像头
"""

import asyncio
import json
import logging
import os
import base64
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, Tuple
from openai import AsyncOpenAI
from pathlib import Path

from .camera_client import CameraClient
from ..prompts.prompt import get_mcp_system_prompt

# 配置日志 - 输出到主项目的 logs 目录
def setup_logger():
    """设置日志配置"""
    # 获取主项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    logs_dir = os.path.join(project_root, 'logs')
    
    # 确保 logs 目录存在
    os.makedirs(logs_dir, exist_ok=True)
    
    # 配置日志
    log_file = os.path.join(logs_dir, 'mcp_camera_inference.log')
    
    # 创建 logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # 避免重复添加 handler
    if not logger.handlers:
        # 文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger

logger = setup_logger()


class CameraInferenceService:
    """摄像头控制异步推理服务"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化推理服务
        
        Args:
            config_path: 配置文件路径，默认使用项目根目录的 config.json
        """
        self.camera_client = CameraClient(config_path)
        self.is_connected = False
        
        # 对话历史管理
        self.conversation_history = []  # 存储对话历史
        self.max_history_rounds = 4     # 最大保留4轮对话
        
    def _add_to_conversation_history(self, ai_analysis: str, control_result: Optional[Dict[str, Any]]):
        """
        添加对话到历史记录
        
        Args:
            ai_analysis: AI分析结果（作为assistant角色）
            control_result: 控制执行结果（作为user角色的反馈）
        """
        try:
            # 添加AI分析作为assistant消息
            if ai_analysis:
                self.conversation_history.append({
                    "role": "assistant",
                    "content": ai_analysis
                })
            
            # 添加控制结果作为user消息
            if control_result and control_result.get('result'):
                control_feedback = f"控制执行结果: {control_result['result']}"
                if control_result.get('tool_name'):
                    control_feedback = f"执行了{control_result['tool_name']}操作，{control_feedback}"
                
                self.conversation_history.append({
                    "role": "user", 
                    "content": control_feedback
                })
            
            # 保持历史记录在指定轮数内
            # 每轮对话包含一个assistant消息和一个user消息，所以最大消息数是 max_history_rounds * 2
            max_messages = self.max_history_rounds * 2
            if len(self.conversation_history) > max_messages:
                # 移除最旧的消息，保持偶数个消息（成对的assistant-user）
                messages_to_remove = len(self.conversation_history) - max_messages
                # 确保移除偶数个消息，保持对话的完整性
                if messages_to_remove % 2 != 0:
                    messages_to_remove += 1
                self.conversation_history = self.conversation_history[messages_to_remove:]
            
            logger.info(f"对话历史已更新，当前包含 {len(self.conversation_history)} 条消息")
            
        except Exception as e:
            logger.error(f"更新对话历史失败: {e}")
    
    def _build_messages_with_history(self, base64_image: str, mime_type: str) -> list:
        """
        构建包含历史对话的消息列表
        
        Args:
            base64_image: base64编码的图像
            mime_type: 图像MIME类型
            
        Returns:
            包含历史对话的消息列表
        """
        messages = [
            {
                "role": "system",
                "content": self.camera_client.system_prompt
            }
        ]
        
        # 添加历史对话
        if self.conversation_history:
            logger.info(f"添加 {len(self.conversation_history)} 条历史对话到上下文")
            messages.extend(self.conversation_history)
        
        # 添加当前图像分析请求
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                },
                {"type": "text", "text": ""},
            ],
        })
        
        return messages
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        获取对话历史摘要
        
        Returns:
            对话历史摘要信息
        """
        return {
            "total_messages": len(self.conversation_history),
            "conversation_rounds": len(self.conversation_history) // 2,
            "max_rounds": self.max_history_rounds,
            "recent_messages": self.conversation_history[-4:] if len(self.conversation_history) >= 4 else self.conversation_history
        }
    
    def clear_conversation_history(self):
        """清空对话历史"""
        self.conversation_history.clear()
        logger.info("对话历史已清空")
        
    async def start_service(self) -> bool:
        """启动服务，连接到 MCP server"""
        try:
            if await self.camera_client.connect_to_mcp_server():
                self.is_connected = True
                logger.info("摄像头推理服务启动成功")
                return True
            else:
                logger.error("摄像头推理服务启动失败：无法连接到 MCP server")
                return False
        except Exception as e:
            logger.error(f"摄像头推理服务启动失败: {e}")
            return False
    
    async def stop_service(self):
        """停止服务，断开连接"""
        try:
            await self.camera_client.disconnect_from_mcp_server()
            self.is_connected = False
            logger.info("摄像头推理服务已停止")
        except Exception as e:
            logger.error(f"停止摄像头推理服务时出错: {e}")
    
    def _encode_image_to_base64(self, image_path: str) -> Tuple[str, str]:
        """
        将图像编码为base64格式
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            Tuple[base64_data, mime_type]: base64编码的图像数据和MIME类型
        """
        try:
            # 获取图像文件扩展名，用于确定MIME类型
            ext = Path(image_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.bmp': 'image/bmp',
                '.gif': 'image/gif', '.tiff': 'image/tiff',
                '.webp': 'image/webp'
            }.get(ext, 'image/jpeg')
            
            with open(image_path, "rb") as image_file:
                image_data = image_file.read()
                base64_data = base64.b64encode(image_data).decode("utf-8")
                
            return base64_data, mime_type
        except Exception as e:
            logger.error(f"图像编码失败: {e}")
            raise
    
    async def analyze_and_control(self, image_path: str) -> Dict[str, Any]:
        """
        分析图像并根据用户问题控制摄像头
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            包含分析结果和控制结果的字典
        """
        if not self.is_connected:
            raise RuntimeError("服务未启动或未连接到 MCP server")
        
        try:
            # 编码图像
            base64_image, mime_type = self._encode_image_to_base64(image_path) 
            
            # 构建包含历史对话的消息
            messages = self._build_messages_with_history(base64_image, mime_type)
            
            # 调用 AI 模型
            mcp_config = self.camera_client.config.get('mcp_model', {})
            response = await self.camera_client.openai_client.chat.completions.create(
                model=mcp_config.get('model', 'gpt-4'),
                messages=messages,
                temperature=mcp_config.get('temperature', 0.1),
                max_tokens=mcp_config.get('max_tokens', 2000)
            )
            
            ai_response = response.choices[0].message.content
            if not ai_response:
                ai_response = ""
            
            logger.info(f"AI 分析响应: {ai_response}")
            
            # 解析响应并执行摄像头控制
            control_result = await self._parse_and_execute_control(ai_response)
            
            # 更新对话历史
            self._add_to_conversation_history(ai_response, control_result)
            
            return {
                "image_path": image_path,
                "ai_analysis": ai_response,
                "control_executed": control_result is not None,
                "control_result": control_result,
                "conversation_summary": self.get_conversation_summary(),
                "timestamp": asyncio.get_event_loop().time()
            }
            
        except Exception as e:
            logger.error(f"分析和控制失败: {e}")
            return {
                "image_path": image_path,
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time()
            }
    
    async def _parse_and_execute_control(self, ai_response: str) -> Optional[Dict[str, Any]]:
        """
        解析AI响应并执行摄像头控制
        
        Args:
            ai_response: AI的响应内容
            
        Returns:
            控制执行结果字典，包含 tool_name, arguments, reason 和 result，如果没有控制操作则返回None
        """
        try:
            # 检查是否包含 MCP 工具调用标签
            if "<use_mcp_tool>" in ai_response and "</use_mcp_tool>" in ai_response:
                # 提取工具调用内容
                start_tag = "<use_mcp_tool>"
                end_tag = "</use_mcp_tool>"
                start_idx = ai_response.find(start_tag) + len(start_tag)
                end_idx = ai_response.find(end_tag)
                
                if start_idx > len(start_tag) - 1 and end_idx > start_idx:
                    tool_content = ai_response[start_idx:end_idx].strip()
                    
                    # 解析工具名称和参数
                    tool_name = self._extract_xml_content(tool_content, "tool_name")
                    arguments_str = self._extract_xml_content(tool_content, "arguments")
                    reason = self._extract_xml_content(tool_content, "reason")
                    
                    if tool_name and arguments_str:
                        try:
                            # 解析参数
                            arguments = json.loads(arguments_str)
                            
                            # 执行工具调用
                            result = await self.camera_client.call_camera_tool(tool_name, arguments)
                            
                            logger.info(f"执行摄像头控制: {tool_name}, 参数: {arguments}, 原因: {reason}")
                            logger.info(f"控制结果: {result}")
                            
                            return {
                                "tool_name": tool_name,
                                "arguments": arguments,
                                "reason": reason,
                                "result": result,
                                "success": True
                            }
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"解析工具参数失败: {e}")
                            return {
                                "tool_name": tool_name,
                                "arguments": arguments_str,
                                "reason": reason,
                                "result": f"参数解析失败: {arguments_str}"
                            }
                        except Exception as e:
                            logger.error(f"执行工具调用失败: {e}")
                            return {
                                "tool_name": tool_name,
                                "arguments": arguments,
                                "reason": reason,
                                "result": f"工具调用失败: {str(e)}"
                            }
            
            # 没有找到工具调用
            return None
            
        except Exception as e:
            logger.error(f"解析和执行控制失败: {e}")
            return {
                "tool_name": "unknown",
                "arguments": {},
                "reason": "解析失败",
                "result": f"解析失败: {str(e)}"
            }
    
    def _extract_xml_content(self, text: str, tag: str) -> Optional[str]:
        """
        从文本中提取XML标签的内容
        
        Args:
            text: 包含XML标签的文本
            tag: 要提取的标签名
            
        Returns:
            标签内容，如果未找到则返回None
        """
        try:
            start_tag = f"<{tag}>"
            end_tag = f"</{tag}>"
            start_idx = text.find(start_tag)
            end_idx = text.find(end_tag)
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                return text[start_idx + len(start_tag):end_idx].strip()
            
            return None
        except Exception:
            return None
    
    async def simple_control(self, user_instruction: str) -> str:
        """
        简单的摄像头控制（不涉及图像分析）
        
        Args:
            user_instruction: 用户指令
            
        Returns:
            控制结果
        """
        if not self.is_connected:
            raise RuntimeError("服务未启动或未连接到 MCP server")
        
        return await self.camera_client.ai_control_camera(user_instruction)
    
    async def get_camera_status(self) -> str:
        """获取摄像头状态"""
        if not self.is_connected:
            raise RuntimeError("服务未启动或未连接到 MCP server")
        
        return await self.camera_client.get_camera_status()
    
    async def list_available_tools(self) -> list:
        """列出可用工具"""
        if not self.is_connected:
            raise RuntimeError("服务未启动或未连接到 MCP server")
        
        return await self.camera_client.list_available_tools()


# 全局服务实例
_camera_inference_service: Optional[CameraInferenceService] = None


async def get_camera_inference_service(config_path: Optional[str] = None) -> CameraInferenceService:
    """
    获取全局摄像头推理服务实例
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        摄像头推理服务实例
    """
    global _camera_inference_service
    
    if _camera_inference_service is None:
        _camera_inference_service = CameraInferenceService(config_path)
        await _camera_inference_service.start_service()
    
    return _camera_inference_service


async def stop_camera_inference_service():
    """停止全局摄像头推理服务"""
    global _camera_inference_service
    
    if _camera_inference_service is not None:
        await _camera_inference_service.stop_service()
        _camera_inference_service = None


# HTTP 服务部分
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn


class AnalyzeRequest(BaseModel):
    """分析请求模型"""
    image_path: str = Field(..., description="图像文件路径")


class ControlRequest(BaseModel):
    """控制请求模型"""
    user_instruction: str = Field(..., description="用户指令")


class ApiResponse(BaseModel):
    """API响应模型"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: float


# 创建 FastAPI 应用
app = FastAPI(
    title="Camera MCP Inference Service",
    description="基于 MCP 的摄像头控制异步推理服务",
    version="0.1.0"
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局推理服务实例
inference_service: Optional[CameraInferenceService] = None


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    global inference_service
    try:
        inference_service = CameraInferenceService()
        if await inference_service.start_service():
            logger.info("🚀 摄像头推理服务 HTTP API 启动成功")
        else:
            logger.error("❌ 摄像头推理服务启动失败")
            raise RuntimeError("无法启动摄像头推理服务")
    except Exception as e:
        logger.error(f"❌ 启动事件失败: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    global inference_service
    if inference_service:
        await inference_service.stop_service()
        logger.info("🛑 摄像头推理服务已停止")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Camera MCP Inference Service",
        "version": "0.1.0",
        "status": "running" if inference_service and inference_service.is_connected else "disconnected"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    if not inference_service or not inference_service.is_connected:
        raise HTTPException(status_code=503, detail="推理服务未连接")
    
    return ApiResponse(
        success=True,
        data={"status": "healthy", "connected": True},
        timestamp=asyncio.get_event_loop().time()
    )


@app.post("/analyze")
async def analyze_image_and_control(request: AnalyzeRequest):
    """分析图像并控制摄像头"""
    try:
        logger.info(f"📸 收到图像分析请求 - 图像: {request.image_path}")
        
        if not inference_service or not inference_service.is_connected:
            logger.error("❌ 摄像头服务未初始化")
            raise HTTPException(status_code=500, detail="摄像头服务未初始化")
        
        # 检查图像文件是否存在
        if not os.path.exists(request.image_path):
            logger.error(f"❌ 图像文件不存在: {request.image_path}")
            raise HTTPException(status_code=404, detail=f"图像文件不存在: {request.image_path}")
        
        # 使用 AI 控制摄像头
        result = await inference_service.analyze_and_control(
            request.image_path,
        )
        
        # 记录处理结果
        if result["control_executed"]:
            logger.info(f"✅ 图像分析和摄像头控制完成 - 工具: {result['control_result']['tool_name']}")
        else:
            logger.warning(f"⚠️ 摄像头控制失败: {result['control_result']['result']}")
        
        return ApiResponse(
            success=True,
            data=result,
            timestamp=asyncio.get_event_loop().time()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"处理请求时出错: {str(e)}"
        logger.error(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.post("/control")
async def control_camera(request: ControlRequest):
    """简单摄像头控制"""
    try:
        logger.info(f"🎮 收到摄像头控制请求 - 指令: {request.user_instruction}")
        
        if not inference_service or not inference_service.is_connected:
            logger.error("❌ 摄像头服务未初始化")
            raise HTTPException(status_code=500, detail="摄像头服务未初始化")
        
        # 执行控制指令
        result = await inference_service.simple_control(request.user_instruction)
        
        # 记录控制结果
        if result["success"]:
            logger.info(f"✅ 摄像头控制成功 - 工具: {result['tool_name']}, 参数: {result['arguments']}")
        else:
            logger.warning(f"⚠️ 摄像头控制失败: {result['result']}")
        
        return ApiResponse(
            success=True,
            data=result,
            timestamp=asyncio.get_event_loop().time()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"控制请求处理失败: {str(e)}"
        logger.error(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/status")
async def get_status():
    """获取摄像头状态"""
    if not inference_service or not inference_service.is_connected:
        raise HTTPException(status_code=503, detail="推理服务未连接")
    
    try:
        status = await inference_service.get_camera_status()
        
        return ApiResponse(
            success=True,
            data={"status": status},
            timestamp=asyncio.get_event_loop().time()
        )
        
    except Exception as e:
        logger.error(f"状态查询失败: {e}")
        return ApiResponse(
            success=False,
            error=str(e),
            timestamp=asyncio.get_event_loop().time()
        )


@app.get("/tools")
async def list_tools():
    """列出可用工具"""
    if not inference_service or not inference_service.is_connected:
        raise HTTPException(status_code=503, detail="推理服务未连接")
    
    try:
        tools = await inference_service.list_available_tools()
        
        return ApiResponse(
            success=True,
            data={"tools": [{"name": tool.name, "description": tool.description} for tool in tools]},
            timestamp=asyncio.get_event_loop().time()
        )
        
    except Exception as e:
        logger.error(f"工具列表查询失败: {e}")
        return ApiResponse(
            success=False,
            error=str(e),
            timestamp=asyncio.get_event_loop().time()
        )


@app.get("/conversation/history")
async def get_conversation_history():
    """获取对话历史"""
    if not inference_service or not inference_service.is_connected:
        raise HTTPException(status_code=503, detail="推理服务未连接")
    
    try:
        summary = inference_service.get_conversation_summary()
        
        return ApiResponse(
            success=True,
            data={
                "conversation_summary": summary,
                "full_history": inference_service.conversation_history
            },
            timestamp=asyncio.get_event_loop().time()
        )
        
    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        return ApiResponse(
            success=False,
            error=str(e),
            timestamp=asyncio.get_event_loop().time()
        )


@app.delete("/conversation/history")
async def clear_conversation_history():
    """清空对话历史"""
    if not inference_service or not inference_service.is_connected:
        raise HTTPException(status_code=503, detail="推理服务未连接")
    
    try:
        inference_service.clear_conversation_history()
        
        return ApiResponse(
            success=True,
            data={"message": "对话历史已清空"},
            timestamp=asyncio.get_event_loop().time()
        )
        
    except Exception as e:
        logger.error(f"清空对话历史失败: {e}")
        return ApiResponse(
            success=False,
            error=str(e),
            timestamp=asyncio.get_event_loop().time()
        )


@app.get("/conversation/summary")
async def get_conversation_summary():
    """获取对话历史摘要"""
    if not inference_service or not inference_service.is_connected:
        raise HTTPException(status_code=503, detail="推理服务未连接")
    
    try:
        summary = inference_service.get_conversation_summary()
        
        return ApiResponse(
            success=True,
            data=summary,
            timestamp=asyncio.get_event_loop().time()
        )
        
    except Exception as e:
        logger.error(f"获取对话摘要失败: {e}")
        return ApiResponse(
            success=False,
            error=str(e),
            timestamp=asyncio.get_event_loop().time()
        )


async def main():
    """主函数 - 启动 HTTP 服务"""
    logger.info("🚀 启动摄像头推理服务 HTTP API...")
    
    # 从主项目配置文件读取端口
    try:
        # 获取主项目根目录的配置文件路径
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 获取推理服务配置
        inference_config = config.get('camera_inference_service', {})
        host = inference_config.get('host', '0.0.0.0')
        port = inference_config.get('port', 8082)
        
    except Exception as e:
        logger.warning(f"无法读取配置文件，使用默认端口: {e}")
        host = '0.0.0.0'
        port = 8082
    
    # 启动 HTTP 服务
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    server = uvicorn.Server(config)
    
    logger.info(f"🌐 HTTP API 服务地址: http://{host}:{port}")
    logger.info("📖 API 文档: http://localhost:8082/docs")
    
    await server.serve()


# 测试函数
async def test_camera_inference_service():
    """测试摄像头推理服务"""
    service = CameraInferenceService()
    
    try:
        # 启动服务
        if await service.start_service():
            print("✅ 服务启动成功")
            
            # 测试简单控制
            result = await service.simple_control("获取摄像头当前位置")
            print(f"简单控制结果: {result}")
            
            # 测试工具列表
            tools = await service.list_available_tools()
            print(f"可用工具数量: {len(tools)}")
            
        else:
            print("❌ 服务启动失败")
            
    finally:
        await service.stop_service()


if __name__ == "__main__":
    asyncio.run(main()) 