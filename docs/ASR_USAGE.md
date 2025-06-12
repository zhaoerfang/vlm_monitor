# ASR语音识别问题接收功能

## 🎤 功能概述

ASR（Automatic Speech Recognition）功能允许外部语音识别客户端向VLM监控系统发送用户问题，系统会在下一次推理时将用户问题包含在提示词中，并在返回的JSON结果中增加`response`字段来回答用户的问题。

## 🏗️ 架构设计

```
ASR客户端 → ASR服务器 → 用户问题管理器 → VLM推理 → 带response字段的JSON结果
```

### 核心组件

1. **ASR服务器** (`tools/asr_server.py`)
   - FastAPI架构的HTTP服务器
   - 接收和管理用户问题
   - 提供RESTful API接口

2. **用户问题管理器** (`src/monitor/vlm/user_question_manager.py`)
   - 从ASR服务器获取用户问题
   - 管理问题的生命周期
   - 与推理系统集成

3. **VLM客户端增强** (`src/monitor/vlm/vlm_client.py`)
   - 支持用户问题参数
   - 自动将问题添加到提示词中

4. **配置增强** (`config.json`)
   - 新增ASR配置节
   - 更新system_prompt支持response字段

## 🚀 启动方式

### 1. 启用ASR服务

```bash
# 启动完整系统（包含ASR服务）
python start_system.py --asr

# 或者组合启动（ASR + TTS）
python start_system.py --asr --tts

# 测试模式 + ASR
python start_system.py --test --asr
```

### 2. 单独启动ASR服务器

```bash
# 使用默认配置
python tools/asr_server.py

# 指定配置文件
python tools/asr_server.py --config config.json

# 自定义主机和端口
python tools/asr_server.py --host 0.0.0.0 --port 8081
```

## 📡 API接口

ASR服务器提供以下RESTful API接口：

### 1. 发送用户问题

```http
POST /asr
Content-Type: application/json

{
  "question": "现在画面中有几个人？"
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "status": "success",
    "message": "问题已接收",
    "question": "现在画面中有几个人？",
    "timestamp": "2024-01-01T12:00:00.000000"
  },
  "timestamp": 1704096000.0
}
```

### 2. 获取当前问题

```http
GET /question/current
```

**响应:**
```json
{
  "success": true,
  "data": {
    "has_question": true,
    "question": "现在画面中有几个人？",
    "timestamp": "2024-01-01T12:00:00.000000"
  },
  "timestamp": 1704096000.0
}
```

### 3. 清除当前问题

```http
POST /question/clear
```

### 4. 健康检查

```http
GET /health
```

### 5. 获取统计信息

```http
GET /stats
```

### 6. API文档

访问 `http://localhost:8081/docs` 查看完整的API文档。

## 🧪 测试工具

### ASR客户端测试工具

```bash
# 交互模式
python tools/test_asr_client.py

# 直接发送问题
python tools/test_asr_client.py --question "现在画面中有几个人？"

# 获取当前问题
python tools/test_asr_client.py --get

# 清除问题
python tools/test_asr_client.py --clear

# 检查健康状态
python tools/test_asr_client.py --health

# 指定服务器地址
python tools/test_asr_client.py --server http://192.168.1.100:8081
```

### 交互模式命令

```
>>> send 现在画面中有几个人？     # 发送问题
>>> get                        # 获取当前问题
>>> clear                      # 清除问题
>>> health                     # 健康检查
>>> stats                      # 统计信息
>>> quit                       # 退出
```

## ⚙️ 配置说明

### ASR配置节 (`config.json`)

```json
{
  "asr": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8081,
    "endpoint": "/asr",
    "max_question_length": 500,
    "question_timeout": 300,
    "comment": "ASR服务配置，用于接收语音识别客户端发送的用户问题"
  }
}
```

**配置项说明:**
- `enabled`: 是否启用ASR服务
- `host`: 监听主机地址
- `port`: 监听端口
- `endpoint`: 接收问题的端点路径
- `max_question_length`: 最大问题长度（字符）
- `question_timeout`: 问题超时时间（秒）

### VLM配置更新

system_prompt已更新，新增`response`字段：

```json
{
  "vlm": {
    "default_prompt": {
      "system": "你是一个多模态摄像头控制助手...返回JSON包含response字段用于回复用户问题"
    }
  }
}
```

## 🔄 工作流程

1. **问题接收**: ASR客户端发送用户问题到ASR服务器
2. **问题存储**: ASR服务器存储当前问题，设置时间戳
3. **问题获取**: 用户问题管理器定期从ASR服务器获取问题
4. **推理集成**: VLM推理时自动包含用户问题
5. **结果生成**: 模型返回包含response字段的JSON结果
6. **问题清除**: 推理完成后自动清除问题

## 📝 JSON响应格式

### 无用户问题时

```json
{
  "timestamp": "2024-01-01T12:00:00.000000",
  "people_count": 2,
  "vehicle_count": 1,
  "people": [...],
  "vehicles": [...],
  "summary": "画面中有2个人和1辆车",
  "response": ""
}
```

### 有用户问题时

```json
{
  "timestamp": "2024-01-01T12:00:00.000000",
  "people_count": 2,
  "vehicle_count": 1,
  "people": [...],
  "vehicles": [...],
  "summary": "画面中有2个人和1辆车",
  "response": "画面中目前有2个人，他们正在人行道上行走。"
}
```

## 🔧 故障排除

### 常见问题

1. **ASR服务器无法启动**
   - 检查端口是否被占用
   - 确认配置文件格式正确
   - 查看日志文件 `logs/asr_server.log`

2. **问题无法发送**
   - 检查ASR服务器是否运行
   - 确认网络连接正常
   - 验证问题长度是否超限

3. **推理结果无response字段**
   - 确认ASR服务已启用
   - 检查用户问题管理器是否正常运行
   - 验证问题是否已超时

### 日志文件

- ASR服务器日志: `logs/asr_server.log`
- 系统启动日志: `logs/system_startup.log`
- VLM监控日志: `logs/vlm_monitor.log`

## 🚀 使用示例

### 完整测试流程

```bash
# 1. 启动系统（包含ASR）
python start_system.py --test --asr

# 2. 在另一个终端发送问题
python tools/test_asr_client.py --question "现在画面中有几个人在做什么？"

# 3. 观察推理结果中的response字段
# 结果会在前端界面和日志中显示

# 4. 清除问题（可选，推理完成后会自动清除）
python tools/test_asr_client.py --clear
```

### 集成到外部ASR系统

```python
import requests

# 发送识别到的用户问题
def send_user_question(question: str):
    response = requests.post(
        "http://localhost:8081/asr",
        json={"question": question},
        timeout=10
    )
    return response.json()

# 使用示例
result = send_user_question("现在画面中有什么？")
if result.get('success'):
    print("问题已发送成功")
else:
    print(f"发送失败: {result.get('error')}")
```

## 📈 性能考虑

- 问题超时机制防止过期问题影响推理
- 线程安全的问题管理
- 轻量级HTTP服务器，低延迟响应
- 自动问题清除，避免重复回答

## 🔮 未来扩展

- 支持多轮对话历史
- 问题优先级管理
- 语音合成结果回传
- 多语言支持
- 问题分类和路由 