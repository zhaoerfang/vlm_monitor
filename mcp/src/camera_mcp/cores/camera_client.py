#!/usr/bin/env python3
"""
摄像头控制 MCP Client
与摄像头 MCP Server 通信，并集成 OpenAI 接口进行智能控制
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import AnyUrl

# 导入提示词生成函数
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
    log_file = os.path.join(logs_dir, 'mcp_camera_client.log')
    
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


class CameraClient:
    """摄像头控制客户端"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化客户端
        
        Args:
            config_path: 配置文件路径，默认使用主项目根目录的 config.json
        """
        if config_path is None:
            # 默认使用主项目根目录的 config.json
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), 'config.json')
        
        self.config = self._load_config(config_path)
        self.openai_client = self._init_openai_client()
        self.mcp_session: Optional[ClientSession] = None
        self.stdio_context = None
        
        # 缓存工具列表和系统提示词
        self.available_tools: List[Any] = []
        self.system_prompt: str = ""
        self._tools_loaded = False
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            # 如果是相对路径，从主项目根目录开始查找
            if not os.path.isabs(config_path):
                # 获取主项目根目录（从 mcp/src/camera_mcp/cores/ 向上4级）
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
                config_path = os.path.join(project_root, config_path)
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # 检查是否有 mcp_model 配置，如果没有则使用默认配置
            if 'mcp_model' not in config:
                logger.warning("配置文件中未找到 mcp_model 配置，使用默认配置")
                config['mcp_model'] = {
                    "api_key": "your-api-key",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4",
                    "temperature": 0.1,
                    "max_tokens": 1000
                }
                
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            # 返回默认配置
            return {
                'mcp_model': {
                    "api_key": "your-api-key",
                    "base_url": "https://api.openai.com/v1", 
                    "model": "gpt-4",
                    "temperature": 0.1,
                    "max_tokens": 1000
                }
            }
    
    def _init_openai_client(self) -> AsyncOpenAI:
        """初始化 OpenAI 客户端"""
        mcp_config = self.config.get('mcp_model', {})
        return AsyncOpenAI(
            api_key=mcp_config.get('api_key'),
            base_url=mcp_config.get('base_url'),
        )
    
    async def connect_to_mcp_server(self, server_script: str = "camera_server.py"):
        """连接到 MCP server"""
        try:
            # 获取 server 脚本的完整路径
            server_path = os.path.join(os.path.dirname(__file__), server_script)
            
            # 创建 server 参数
            server_params = StdioServerParameters(
                command="python",
                # args=[server_path],
                args=["-m","camera_mcp.cores.camera_server"],
                env=None,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            )
            
            # 连接到 server
            self.stdio_context = stdio_client(server_params)
            read, write = await self.stdio_context.__aenter__()
            
            # 创建会话
            self.mcp_session = ClientSession(read, write)
            await self.mcp_session.__aenter__()
            
            # 初始化连接
            await self.mcp_session.initialize()
            
            # 加载工具列表和生成系统提示词
            await self._load_tools_and_prompt()
            
            logger.info("成功连接到 MCP server")
            return True
            
        except Exception as e:
            logger.info(f"连接 MCP server 失败: {e}")
            return False
    
    async def disconnect_from_mcp_server(self):
        """断开与 MCP server 的连接"""
        try:
            if self.mcp_session:
                await self.mcp_session.__aexit__(None, None, None)
                self.mcp_session = None
            if self.stdio_context:
                await self.stdio_context.__aexit__(None, None, None)
                self.stdio_context = None
            
            # 清空缓存
            self.available_tools = []
            self.system_prompt = ""
            self._tools_loaded = False
            
            logger.info("已断开与 MCP server 的连接")
        except Exception as e:
            logger.error(f"断开连接时出错: {e}")
    
    async def _load_tools_and_prompt(self):
        """加载工具列表并生成系统提示词"""
        if not self.mcp_session:
            raise RuntimeError("未连接到 MCP server")
        
        try:
            # 获取工具列表
            tools = await self.mcp_session.list_tools()
            self.available_tools = tools.tools if hasattr(tools, 'tools') else []
            
            # 生成工具描述
            tool_descriptions = []
            for tool in self.available_tools:
                tool_descriptions.append(f"  - {tool.name}: {tool.description}")
            
            # 生成系统提示词
            tools_description_text = "\n".join(tool_descriptions)
            self.system_prompt = get_mcp_system_prompt(tools_description_text)
            
            self._tools_loaded = True
            logger.info(f"已加载 {len(self.available_tools)} 个工具并生成系统提示词")
            
        except Exception as e:
            logger.error(f"加载工具列表失败: {e}")
            self.available_tools = []
            self.system_prompt = get_mcp_system_prompt("")
            self._tools_loaded = False
    
    async def list_available_tools(self) -> list:
        """列出可用的工具"""
        if not self._tools_loaded:
            await self._load_tools_and_prompt()
        return self.available_tools
    
    async def call_camera_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """调用摄像头控制工具"""
        if not self.mcp_session:
            raise RuntimeError("未连接到 MCP server")
        
        try:
            logger.info(f"🔧 调用摄像头工具: {tool_name}, 参数: {arguments}")
            
            result = await self.mcp_session.call_tool(tool_name, arguments)
            if hasattr(result, 'content') and result.content:
                # 提取文本内容
                if isinstance(result.content, list) and len(result.content) > 0:
                    content_item = result.content[0]
                    if hasattr(content_item, 'text'):
                        result_text = content_item.text
                    else:
                        result_text = str(content_item)
                else:
                    result_text = str(result.content)
                
                logger.info(f"✅ 工具调用成功: {tool_name} -> {result_text}")
                return result_text
            else:
                logger.warning(f"⚠️ 工具调用返回空结果: {tool_name}")
                return "工具调用成功，但无返回内容"
                
        except Exception as e:
            error_msg = f"工具调用失败: {str(e)}"
            logger.error(f"❌ {tool_name} 调用失败: {error_msg}")
            raise RuntimeError(error_msg)
    
    async def get_camera_status(self) -> str:
        """获取摄像头状态"""
        if not self.mcp_session:
            raise RuntimeError("未连接到 MCP server")
        
        try:
            result = await self.mcp_session.read_resource(AnyUrl("camera://status"))
            return result[0] if isinstance(result, tuple) else str(result)
        except Exception as e:
            logger.error(f"获取摄像头状态失败: {e}")
            return f"获取状态失败: {str(e)}"
    
    async def ai_control_camera(self, user_instruction: str) -> Dict[str, Any]:
        """
        使用 AI 智能控制摄像头
        
        Args:
            user_instruction: 用户指令
            
        Returns:
            包含控制结果的字典，格式：
            {
                "success": bool,
                "tool_name": str,
                "arguments": dict,
                "reason": str,
                "result": str,
                "ai_response": str
            }
        """
        if not self.mcp_session:
            error_msg = "未连接到 MCP server"
            logger.error(f"摄像头控制失败: {error_msg}")
            return {
                "success": False,
                "tool_name": "",
                "arguments": {},
                "reason": "",
                "result": error_msg,
                "ai_response": ""
            }
        
        try:
            # 记录用户指令
            logger.info(f"🎯 收到摄像头控制指令: {user_instruction}")
            
            # 构建消息
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_instruction}
            ]
            
            # 调用 AI 模型
            mcp_config = self.config.get('mcp_model', {})
            completion = await self.openai_client.chat.completions.create(
                model=mcp_config.get('model', 'gpt-4'),
                messages=messages,
                temperature=mcp_config.get('temperature', 0.1),
                max_tokens=mcp_config.get('max_tokens', 1000)
            )
            
            ai_response = completion.choices[0].message.content
            logger.info(f"🤖 AI 响应: {ai_response}")
            
            # 解析 XML 响应并执行工具调用
            result = await self._parse_xml_response(ai_response)
            
            # 记录控制结果
            if result["success"]:
                logger.info(f"✅ 摄像头控制成功 - 工具: {result['tool_name']}, 参数: {result['arguments']}, 原因: {result['reason']}")
                logger.info(f"📋 执行结果: {result['result']}")
            else:
                logger.warning(f"⚠️ 摄像头控制失败 - 工具: {result['tool_name']}, 原因: {result['reason']}, 错误: {result['result']}")
            
            return result
            
        except Exception as e:
            error_msg = f"AI 控制摄像头时出错: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "tool_name": "",
                "arguments": {},
                "reason": "",
                "result": error_msg,
                "ai_response": ""
            }
    
    async def _parse_xml_response(self, ai_response: str) -> Dict[str, Any]:
        """
        解析 XML 格式的 AI 响应
        
        Args:
            ai_response: AI 的响应内容
            
        Returns:
            解析结果字典
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
                            result = await self.call_camera_tool(tool_name, arguments)
                            
                            logger.info(f"执行摄像头控制: {tool_name}, 参数: {arguments}, 原因: {reason}")
                            logger.info(f"控制结果: {result}")
                            
                            return {
                                "success": True,
                                "tool_name": tool_name,
                                "arguments": arguments,
                                "reason": reason or "未提供原因",
                                "result": result,
                                "ai_response": ai_response
                            }
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"解析工具参数失败: {e}")
                            return {
                                "success": False,
                                "tool_name": tool_name,
                                "arguments": {},
                                "reason": reason or "参数解析失败",
                                "result": f"参数解析失败: {arguments_str}",
                                "ai_response": ai_response
                            }
                        except Exception as e:
                            logger.error(f"执行工具调用失败: {e}")
                            return {
                                "success": False,
                                "tool_name": tool_name,
                                "arguments": arguments,
                                "reason": reason or "工具调用失败",
                                "result": f"工具调用失败: {str(e)}",
                                "ai_response": ai_response
                            }
                    else:
                        return {
                            "success": False,
                            "tool_name": tool_name,
                            "arguments": {},
                            "reason": "XML解析不完整",
                            "result": f"工具名称或参数缺失: tool_name={tool_name}, arguments={arguments_str}",
                            "ai_response": ai_response
                        }
            
            # 检查是否包含单独的 reason 标签（观察完成状态）
            elif "<reason>" in ai_response and "</reason>" in ai_response:
                # 提取 reason 内容
                reason = self._extract_xml_content(ai_response, "reason")
                
                logger.info(f"观察完成，无需工具调用: {reason}")
                
                return {
                    "success": True,
                    "tool_name": None,  # 无工具调用
                    "arguments": {},
                    "reason": reason or "观察已完成",
                    "result": "观察任务已完成，无需进一步调整摄像头",
                    "ai_response": ai_response
                }
            
            # 没有找到工具调用，可能是纯文本响应
            return {
                "success": True,
                "tool_name": None,
                "arguments": {},
                "reason": "无需工具调用",
                "result": ai_response,
                "ai_response": ai_response
            }
            
        except Exception as e:
            logger.error(f"解析 XML 响应失败: {e}")
            return {
                "success": False,
                "tool_name": None,
                "arguments": {},
                "reason": "XML解析失败",
                "result": f"解析失败: {str(e)}",
                "ai_response": ai_response
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
    
    async def interactive_mode(self):
        """交互模式"""
        print("🎥 摄像头控制客户端")
        print("输入 'help' 查看帮助，输入 'quit' 退出")
        print("=" * 50)
        
        while True:
            try:
                user_input = input("\n请输入指令: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("👋 再见！")
                    break
                elif user_input.lower() == 'help':
                    await self._show_help()
                elif user_input.lower() == 'status':
                    status = await self.get_camera_status()
                    print(f"📊 摄像头状态: {status}")
                elif user_input.lower() == 'tools':
                    tools = await self.list_available_tools()
                    print("🔧 可用工具:")
                    for tool in tools:
                        print(f"  - {tool.name}: {tool.description}")
                elif user_input.startswith('call '):
                    # 直接调用工具: call tool_name {"arg1": "value1"}
                    await self._handle_direct_call(user_input[5:])
                elif user_input:
                    # AI 智能控制
                    result = await self.ai_control_camera(user_input)
                    if result["success"]:
                        if result["tool_name"]:
                            print(f"🤖 执行工具: {result['tool_name']}")
                            print(f"   参数: {result['arguments']}")
                            print(f"   原因: {result['reason']}")
                            print(f"   结果: {result['result']}")
                        else:
                            print(f"🤖 {result['result']}")
                    else:
                        print(f"❌ 执行失败: {result['result']}")
                    
            except KeyboardInterrupt:
                print("\n👋 再见！")
                break
            except Exception as e:
                print(f"❌ 错误: {e}")
    
    async def _show_help(self):
        """显示帮助信息"""
        help_text = """
🎥 摄像头控制客户端帮助

基本命令：
  help     - 显示此帮助信息
  status   - 查看摄像头状态
  tools    - 列出可用工具
  quit     - 退出程序

直接工具调用：
  call <tool_name> <json_args>
  例如: call pan_tilt_move {"pan_angle": -30, "tilt_speed": 0, "duration": 0}

AI 智能控制（直接输入自然语言）：
  "向左转动30度"
  "向右转45度"
  "拍一张照片"
  "放大镜头"
  "移动到预设点位1"
  "调整亮度到80"
  
支持的摄像头操作：
  - 水平/垂直转动
  - 拍照
  - 变焦
  - 预设点位
  - 图像设置调整
  - 摄像头连接设置
"""
        print(help_text)
    
    async def _handle_direct_call(self, call_str: str):
        """处理直接工具调用"""
        try:
            parts = call_str.split(' ', 1)
            tool_name = parts[0]
            
            if len(parts) > 1:
                arguments = json.loads(parts[1])
            else:
                arguments = {}
            
            result = await self.call_camera_tool(tool_name, arguments)
            print(f"🔧 工具调用结果: {result}")
            
        except Exception as e:
            print(f"❌ 工具调用失败: {e}")


async def main():
    """主函数"""
    client = CameraClient()
    
    # 连接到 MCP server
    if await client.connect_to_mcp_server():
        try:
            # 进入交互模式
            await client.interactive_mode()
        finally:
            # 断开连接
            await client.disconnect_from_mcp_server()
    else:
        print("❌ 无法连接到 MCP server")


if __name__ == "__main__":
    asyncio.run(main()) 