# VLM 客户端与摄像头控制集成功能

## 概述

本文档介绍了 VLM 监控系统与基于 MCP (Model Context Protocol) 的摄像头控制系统的集成功能。通过这个集成，系统可以：

1. 分析摄像头抽帧图像
2. 根据用户问题和图像内容智能控制摄像头
3. 提供统一的异步推理服务

## 架构设计

```
┌─────────────────┐    图像+问题    ┌─────────────────┐    MCP协议    ┌─────────────────┐
│   VLM Client    │──────────────►│ Camera Inference │──────────────►│  Camera Server  │
│                 │                │    Service      │                │                 │
│ - 图像分析      │                │ - 智能分析      │                │ - 摄像头控制    │
│ - 用户问题处理  │                │ - 控制决策      │                │ - 工具实现      │
│ - 集成控制      │                │ - 异步服务      │                │ - 硬件接口      │
└─────────────────┘                └─────────────────┘                └─────────────────┘
```

## 主要组件

### 1. 改进的提示词系统

**文件**: `mcp/src/camera_mcp/prompts/prompt.py`

```python
def get_mcp_system_prompt(tools_description: str) -> str:
    """
    生成MCP系统提示词
    
    Args:
        tools_description: 工具描述列表
        
    Returns:
        完整的系统提示词
    """
```

**特性**:
- 动态生成系统提示词
- 支持工具描述参数化
- 保持向后兼容性

### 2. 优化的摄像头客户端

**文件**: `mcp/src/camera_mcp/cores/camera_client.py`

**主要改进**:
- 工具列表缓存：连接后缓存工具列表，避免重复获取
- 系统提示词缓存：动态生成并缓存系统提示词
- 更好的错误处理和连接管理

```python
class CameraClient:
    def __init__(self, config_path: Optional[str] = None):
        # 缓存工具列表和系统提示词
        self.available_tools: List[Any] = []
        self.system_prompt: str = ""
        self._tools_loaded = False
```

### 3. 摄像头推理服务

**文件**: `mcp/src/camera_mcp/cores/camera_inference_service.py`

这是一个新的异步推理服务，提供以下功能：

```python
class CameraInferenceService:
    async def analyze_and_control(self, image_path: str, user_question: str) -> Dict[str, Any]:
        """分析图像并根据用户问题控制摄像头"""
        
    async def simple_control(self, user_instruction: str) -> str:
        """简单的摄像头控制（不涉及图像分析）"""
```

**特性**:
- 图像编码和分析
- AI 响应解析
- MCP 工具调用
- 错误处理和日志记录

### 4. VLM 客户端集成

**文件**: `src/monitor/vlm/vlm_client.py`

在 `analyze_image_async` 方法中添加了摄像头控制功能：

```python
async def analyze_image_async(self, image_path: str, prompt: Optional[str] = None, 
                             user_question: Optional[str] = None, 
                             enable_camera_control: bool = False) -> Optional[str]:
```

**新参数**:
- `enable_camera_control`: 是否启用摄像头控制功能

## 使用方法

### 1. 基本摄像头控制

```python
from camera_mcp.cores.camera_inference_service import CameraInferenceService

service = CameraInferenceService()
await service.start_service()

# 简单控制
result = await service.simple_control("向左转动30度")
print(result)

await service.stop_service()
```

### 2. 图像分析结合摄像头控制

```python
# 使用推理服务
result = await service.analyze_and_control(
    "path/to/image.jpg",
    "如果图像中有人物在右侧，请向右转动摄像头20度"
)

print(f"控制执行: {result['control_executed']}")
print(f"控制结果: {result['control_result']}")
```

### 3. VLM 客户端集成控制

```python
from monitor.vlm.vlm_client import DashScopeVLMClient

vlm_client = DashScopeVLMClient()

# 启用摄像头控制的图像分析
result = await vlm_client.analyze_image_async(
    "path/to/image.jpg",
    user_question="请分析图像并调整摄像头到最佳位置",
    enable_camera_control=True
)
```

### 4. 全局服务实例

```python
from camera_mcp.cores.camera_inference_service import get_camera_inference_service

# 获取全局服务实例（自动启动）
service = await get_camera_inference_service()

# 使用服务
result = await service.simple_control("拍一张照片")
```

## 配置说明

### MCP 模型配置

在 `mcp/config.json` 中配置：

```json
{
  "mcp_model": {
    "api_key": "your-api-key",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3-14b",
    "temperature": 0.1,
    "max_tokens": 6000
  }
}
```

### 摄像头配置

```json
{
  "camera": {
    "default_ip": "192.168.1.64",
    "default_admin": "admin",
    "default_password": "pw4hkcamera"
  }
}
```

## 工作流程

### 1. 图像分析 + 摄像头控制流程

```
1. 用户提供图像和问题
2. 编码图像为 base64
3. 构建包含图像和问题的提示词
4. 调用 AI 模型分析
5. 解析 AI 响应中的 MCP 工具调用
6. 执行摄像头控制操作
7. 返回分析结果和控制结果
```

### 2. MCP 工具调用格式

AI 模型返回的工具调用格式：

```xml
<use_mcp_tool>
  <server_name>camera_server</server_name>
  <tool_name>pan_tilt_move</tool_name>
  <arguments>{"pan_angle": -30}</arguments>
  <reason>向左转动以获得更好的视角</reason>
</use_mcp_tool>
```

## 可用的摄像头工具

1. **pan_tilt_move**: 水平转动摄像头
2. **capture_image**: 拍照
3. **get_camera_position**: 获取当前位置
4. **reset_camera_position**: 重置到中心位置
5. **goto_preset**: 移动到预设点位
6. **zoom_control**: 变焦控制
7. **adjust_image_settings**: 调整图像设置

## 示例和测试

### 运行示例

```bash
# 运行集成示例
python examples/camera_control_example.py

# 运行集成测试
python mcp/tests/test_integrated_system.py
```

### 测试场景

1. **基本摄像头控制**: 测试基础的转动、拍照等功能
2. **图像分析控制**: 基于图像内容的智能控制
3. **VLM 集成**: 测试 VLM 客户端的摄像头控制集成
4. **交互式控制**: 命令行交互式控制

## 错误处理

系统提供多层错误处理：

1. **连接错误**: MCP 服务器连接失败时的处理
2. **工具调用错误**: 摄像头控制失败时的处理
3. **图像编码错误**: 图像文件处理失败时的处理
4. **AI 响应错误**: 模型响应解析失败时的处理

## 性能优化

1. **工具缓存**: 连接后缓存工具列表，避免重复获取
2. **提示词缓存**: 缓存生成的系统提示词
3. **全局服务**: 支持全局服务实例，避免重复初始化
4. **异步处理**: 全异步设计，提高并发性能

## 扩展性

系统设计支持以下扩展：

1. **新工具添加**: 在 MCP 服务器中添加新的摄像头控制工具
2. **多摄像头支持**: 扩展支持多个摄像头的控制
3. **自定义提示词**: 支持自定义 AI 分析提示词
4. **插件系统**: 支持第三方插件扩展功能

## 注意事项

1. **API 密钥**: 确保配置正确的 API 密钥
2. **摄像头连接**: 确保摄像头网络连接正常
3. **图像格式**: 支持常见的图像格式（JPG、PNG 等）
4. **并发控制**: 避免同时进行多个摄像头控制操作
5. **资源清理**: 使用完毕后及时停止服务释放资源 