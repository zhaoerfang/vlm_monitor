# Camera MCP 包使用指南

## 概述

Camera MCP 现在已经被打包为一个独立的 pip 包，支持通过命令行启动各种服务，包括新增的异步推理服务。

## 新功能

### 1. 异步推理服务 (HTTP API)

新增了 `camera-mcp-inference` 命令，可以启动一个 HTTP API 服务，用于接收图像分析和摄像头控制请求。

#### 特性
- **HTTP API 接口**: 提供 RESTful API 用于图像分析和摄像头控制
- **XML 解析**: 支持解析 AI 模型返回的 XML 格式指令
- **结构化返回**: 返回包含 `tool_name`, `arguments`, `reason`, `result` 的结构化数据
- **异步处理**: 支持并发请求处理

#### API 端点
- `GET /`: 服务状态
- `GET /health`: 健康检查
- `POST /analyze`: 分析图像并控制摄像头
- `POST /control`: 简单摄像头控制
- `GET /status`: 获取摄像头状态
- `GET /tools`: 列出可用工具

### 2. 命令行工具增强

新增了 `inference_service` 命令选项：

```bash
camera-mcp inference_service  # 启动异步推理服务
```

## 安装和配置

### 1. 安装包

```bash
# 开发模式安装
cd mcp
pip install -e .

# 或使用 uv
uv sync
```

### 2. 配置文件

**重要**: Camera MCP 现在使用主项目的统一配置文件 `beta/vlm_monitor/config.json`，不再使用独立的配置文件。

确保主项目的 `config.json` 中包含以下配置：

```json
{
  "mcp_model": {
    "api_key": "your-api-key",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-vl-max-2025-04-02",
    "temperature": 0.1,
    "max_tokens": 1000
  },
  "camera": {
    "default_ip": "192.168.1.64",
    "default_admin": "admin",
    "default_password": "your-password",
    "connection_timeout": 30,
    "retry_attempts": 3
  },
  "camera_inference_service": {
    "enabled": false,
    "host": "0.0.0.0",
    "port": 8082
  }
}
```

## 使用方法

### 1. 启动 MCP Server

```bash
# 从主项目根目录启动
cd beta/vlm_monitor
camera-mcp server
```

### 2. 启动异步推理服务

```bash
# 从主项目根目录启动
cd beta/vlm_monitor
camera-mcp inference_service
```

服务将在 `http://localhost:8082` 启动，提供以下 API：

#### 分析图像并控制摄像头
```bash
curl -X POST http://localhost:8082/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "image_path": "/path/to/image.jpg",
    "user_question": "向左转动30度"
  }'
```

#### 简单摄像头控制
```bash
curl -X POST http://localhost:8082/control \
  -H "Content-Type: application/json" \
  -d '{
    "user_instruction": "拍一张照片"
  }'
```

### 3. 在主系统中启用

```bash
python start_system.py --mcp-inference
```

这将自动启动 MCP 推理服务作为系统的一部分。

## XML 格式解析

### AI 模型输出格式

AI 模型应该返回以下 XML 格式：

```xml
<use_mcp_tool>
  <tool_name>pan_tilt_move</tool_name>
  <arguments>{"pan_angle": -30, "tilt_angle": 0}</arguments>
  <reason>用户要求向左转动30度</reason>
</use_mcp_tool>
```

### 解析结果

解析后返回的结构化数据：

```json
{
  "success": true,
  "tool_name": "pan_tilt_move",
  "arguments": {"pan_angle": -30, "tilt_angle": 0},
  "reason": "用户要求向左转动30度",
  "result": "工具执行结果",
  "ai_response": "完整的AI响应"
}
```

## 集成到 VLM 客户端

在 `vlm_client.py` 中，摄像头控制现在通过 HTTP 请求 MCP 推理服务：

```python
# 发送请求到推理服务
response = requests.post(
    "http://localhost:8082/analyze",
    json={
        "image_path": image_path,
        "user_question": user_question
    },
    timeout=30
)

if response.status_code == 200:
    result = response.json()
    # 处理结果...
```

## 测试

运行测试脚本验证功能：

```bash
# 从主项目根目录运行测试
cd beta/vlm_monitor
python mcp/test_mcp_package.py
```

测试包括：
- 包结构验证
- XML 解析功能
- 命令行工具
- HTTP 服务接口

## 配置示例

### 完整的 config.json 示例

```json
{
  "mcp_model": {
    "api_key": "your-api-key",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-vl-max-2025-04-02",
    "temperature": 0.1,
    "max_tokens": 6000
  },
  "camera": {
    "default_ip": "192.168.1.64",
    "default_admin": "admin",
    "default_password": "your-password",
    "connection_timeout": 30,
    "retry_attempts": 3
  },
  "camera_inference_service": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8082
  }
}
```

## 架构说明

```
┌─────────────────┐    HTTP     ┌──────────────────────┐    MCP     ┌─────────────┐
│   VLM Client    │ ──────────► │ Camera Inference     │ ─────────► │ MCP Server  │
│                 │             │ Service (HTTP API)   │            │             │
└─────────────────┘             └──────────────────────┘            └─────────────┘
                                          │                                │
                                          │ XML解析                        │
                                          ▼                                ▼
                                ┌──────────────────────┐            ┌─────────────┐
                                │ 结构化数据返回        │            │   Camera    │
                                │ {tool_name, args,    │            │  Hardware   │
                                │  reason, result}     │            │             │
                                └──────────────────────┘            └─────────────┘
```

## 故障排除

### 1. 推理服务启动失败
- 检查端口 8082 是否被占用
- 确认 MCP Server 正在运行
- 检查配置文件格式

### 2. XML 解析失败
- 确认 AI 模型返回正确的 XML 格式
- 检查 `<use_mcp_tool>` 标签是否完整
- 验证 JSON 参数格式

### 3. HTTP 请求失败
- 确认推理服务正在运行
- 检查网络连接
- 验证请求数据格式

## 开发说明

### 添加新的 API 端点

在 `camera_inference_service.py` 中添加新的 FastAPI 路由：

```python
@app.post("/new_endpoint")
async def new_endpoint(request: NewRequest):
    # 实现逻辑
    pass
```

### 扩展 XML 解析

修改 `_extract_xml_content` 方法支持新的 XML 标签：

```python
def _extract_xml_content(self, text: str, tag: str) -> Optional[str]:
    # 扩展解析逻辑
    pass
```

## 版本历史

- **v0.1.0**: 初始版本，支持基本的 MCP 功能
- **v0.1.1**: 新增异步推理服务和 HTTP API
- **v0.1.2**: 增强 XML 解析和错误处理 

print("\n📖 使用说明:")
print("1. 安装包: pip install -e .")
print("2. 启动 MCP Server: camera-mcp server")
print("3. 启动推理服务: camera-mcp inference_service")
print("4. 在主系统中启用: python start_system.py --mcp-inference")
print("5. 注意: 所有命令都应该从主项目根目录 (beta/vlm_monitor) 运行") 