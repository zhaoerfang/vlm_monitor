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
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CameraClient:
    """摄像头控制客户端"""
    
    def __init__(self, config_path: str = "config.json"):
        """
        初始化客户端
        
        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.openai_client = self._init_openai_client()
        self.mcp_session: Optional[ClientSession] = None
        self.stdio_context = None
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            # 如果是相对路径，从项目根目录开始查找
            if not os.path.isabs(config_path):
                # 获取项目根目录（假设此文件在 mcp/ 目录下）
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
                args=[server_path],
                env=None
            )
            
            # 连接到 server
            self.stdio_context = stdio_client(server_params)
            read, write = await self.stdio_context.__aenter__()
            
            # 创建会话
            self.mcp_session = ClientSession(read, write)
            await self.mcp_session.__aenter__()
            
            # 初始化连接
            await self.mcp_session.initialize()
            
            logger.info("成功连接到 MCP server")
            return True
            
        except Exception as e:
            logger.error(f"连接 MCP server 失败: {e}")
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
            logger.info("已断开与 MCP server 的连接")
        except Exception as e:
            logger.error(f"断开连接时出错: {e}")
    
    async def list_available_tools(self) -> list:
        """列出可用的工具"""
        if not self.mcp_session:
            raise RuntimeError("未连接到 MCP server")
        
        tools = await self.mcp_session.list_tools()
        return tools.tools if hasattr(tools, 'tools') else []
    
    async def call_camera_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """调用摄像头控制工具"""
        if not self.mcp_session:
            raise RuntimeError("未连接到 MCP server")
        
        try:
            result = await self.mcp_session.call_tool(tool_name, arguments)
            if hasattr(result, 'content') and result.content:
                # 提取文本内容
                if isinstance(result.content, list) and len(result.content) > 0:
                    return result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                else:
                    return str(result.content)
            else:
                return str(result)
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 失败: {e}")
            return f"调用工具失败: {str(e)}"
    
    async def get_camera_status(self) -> str:
        """获取摄像头状态"""
        if not self.mcp_session:
            raise RuntimeError("未连接到 MCP server")
        
        try:
            result = await self.mcp_session.read_resource("camera://status")
            return result[0] if isinstance(result, tuple) else str(result)
        except Exception as e:
            logger.error(f"获取摄像头状态失败: {e}")
            return f"获取状态失败: {str(e)}"
    
    async def ai_control_camera(self, user_instruction: str) -> str:
        """
        使用 AI 智能控制摄像头
        
        Args:
            user_instruction: 用户指令，如 "向左转动3秒"、"拍一张照片"等
        
        Returns:
            执行结果
        """
        try:
            # 获取可用工具列表
            tools = await self.list_available_tools()
            tool_descriptions = []
            for tool in tools:
                tool_descriptions.append(f"- {tool.name}: {tool.description}")
            
            # 构建 AI 提示词
            system_prompt = f"""你是一个摄像头控制助手。用户会给你指令，你需要分析指令并调用相应的摄像头控制工具。

可用的摄像头控制工具：
{chr(10).join(tool_descriptions)}

工具参数说明：
- pan_tilt_move: pan_speed(水平速度，-100到100，正数右转，负数左转), tilt_speed(垂直速度，-100到100，正数上升，负数下降), duration(持续时间，秒)
- capture_image: img_name(图片名称，可选)
- goto_preset: point(预设点位编号)
- zoom_control: zoom_level(变焦级别，正数放大，负数缩小), duration(持续时间，秒)
- adjust_image_settings: brightness(亮度0-100), contrast(对比度0-100), saturation(饱和度0-100)
- setup_camera: ip(摄像头IP), admin(用户名), password(密码)

请根据用户指令，返回一个JSON格式的工具调用，格式如下：
{{
    "tool_name": "工具名称",
    "arguments": {{
        "参数名": "参数值"
    }}
}}

如果指令不清楚或无法执行，请返回错误信息。"""

            # 调用 AI 模型
            mcp_config = self.config.get('mcp_model', {})
            response = await self.openai_client.chat.completions.create(
                model=mcp_config.get('model', 'gpt-4'),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_instruction}
                ],
                temperature=mcp_config.get('temperature', 0.1),
                max_tokens=mcp_config.get('max_tokens', 1000)
            )
            
            ai_response = response.choices[0].message.content
            if ai_response:
                ai_response = ai_response.strip()
            else:
                ai_response = ""
            logger.info(f"AI 响应: {ai_response}")
            
            # 尝试解析 JSON 响应
            try:
                tool_call = json.loads(ai_response)
                tool_name = tool_call.get('tool_name')
                arguments = tool_call.get('arguments', {})
                
                if tool_name:
                    # 调用相应的工具
                    result = await self.call_camera_tool(tool_name, arguments)
                    return f"AI 执行结果: {result}"
                else:
                    return f"AI 响应格式错误: {ai_response}"
                    
            except json.JSONDecodeError:
                # 如果不是 JSON 格式，可能是错误信息或说明
                return f"AI 响应: {ai_response}"
                
        except Exception as e:
            logger.error(f"AI 控制摄像头失败: {e}")
            return f"AI 控制失败: {str(e)}"
    
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
                    print(f"🤖 {result}")
                    
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
  例如: call pan_tilt_move {"pan_speed": -50, "tilt_speed": 0, "duration": 3}

AI 智能控制（直接输入自然语言）：
  "向左转动3秒"
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