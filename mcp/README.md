# Camera MCP - 摄像头控制系统

基于 Model Context Protocol (MCP) 的智能摄像头控制系统，支持通过 AI 自然语言指令控制摄像头。

## 功能特性

### MCP Server
- 🎥 摄像头水平/垂直转动控制
- 📸 摄像头拍照功能
- 🔍 摄像头变焦控制
- 📍 预设点位移动
- ⚙️ 图像参数调整（亮度、对比度、饱和度）
- 🔧 摄像头连接配置

### MCP Client
- 🤖 AI 智能控制（支持自然语言指令）
- 🔧 直接工具调用
- 📊 摄像头状态查询
- 💬 交互式命令行界面
- 🔗 独立模型配置

## 项目结构

```
camera-mcp/
├── src/
│   └── camera_mcp/
│       ├── __init__.py          # 包初始化
│       ├── camera_server.py     # MCP Server 实现
│       ├── camera_client.py     # MCP Client 实现
│       ├── cli.py               # 命令行接口
│       └── utils/
│           ├── __init__.py
│           ├── Camera.py        # 摄像头控制类
│           └── test.py          # 原始测试脚本
├── tests/
│   ├── __init__.py
│   └── test_mcp_system.py       # 系统测试
├── docs/                        # 文档目录
├── config.json                  # 配置文件
├── pyproject.toml               # 项目配置
├── README.md                    # 项目文档
└── start_camera_system.py       # 兼容性启动脚本
```

## 安装

### 使用 uv (推荐)

```bash
# 克隆项目
git clone <repository-url>
cd camera-mcp

# 安装依赖
uv sync

# 开发模式安装
uv sync --dev
```

### 使用 pip

```bash
# 安装发布版本
pip install camera-mcp

# 或从源码安装
pip install -e .

# 安装开发依赖
pip install -e .[dev]
```

## 配置

系统使用项目根目录的 `config.json` 文件进行配置：

```json
{
  "mcp_model": {
    "api_key": "your-openai-api-key",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4",
    "temperature": 0.1,
    "max_tokens": 1000
  },
  "camera": {
    "default_ip": "192.168.1.64",
    "default_admin": "admin",
    "default_password": "pw4hkcamera"
  }
}
```

注意：`mcp_model` 配置独立于 VLM 监控系统的 `vlm` 配置，两者使用不同的模型和参数。

## 使用方法

### 命令行接口 (推荐)

```bash
# 启动 MCP Server
camera-mcp server

# 启动 MCP Client (在另一个终端)
camera-mcp client

# 运行系统测试
camera-mcp test

# 查看帮助
camera-mcp --help
```

### 兼容性脚本

```bash
# 使用旧的启动脚本 (已弃用)
python start_camera_system.py server
python start_camera_system.py client
python start_camera_system.py test
```

### 编程接口

```python
from camera_mcp import CameraClient, run_server, run_client

# 创建客户端
client = CameraClient()

# 或直接运行服务器/客户端
await run_server()
await run_client()
```

## 客户端使用

客户端启动后，你可以使用以下方式控制摄像头：

### AI 智能控制（推荐）
直接输入自然语言指令：
```
向左转动3秒
拍一张照片
放大镜头
移动到预设点位1
调整亮度到80
```

### 直接工具调用
```
call pan_tilt_move {"pan_speed": -50, "tilt_speed": 0, "duration": 3}
call capture_image {"img_name": "test.jpg"}
call zoom_control {"zoom_level": 10, "duration": 2}
```

### 基本命令
```
help     - 显示帮助信息
status   - 查看摄像头状态
tools    - 列出可用工具
quit     - 退出程序
```

## 可用工具

### `setup_camera`
设置摄像头连接参数
- `ip`: 摄像头IP地址
- `admin`: 用户名
- `password`: 密码

### `pan_tilt_move`
控制摄像头水平和垂直转动
- `pan_speed`: 水平速度 (-100 到 100，正数右转，负数左转)
- `tilt_speed`: 垂直速度 (-100 到 100，正数上升，负数下降)
- `duration`: 持续时间（秒）

### `capture_image`
摄像头拍照
- `img_name`: 图片名称（可选，为空则自动生成）

### `goto_preset`
移动到预设点位
- `point`: 预设点位编号

### `zoom_control`
控制摄像头变焦
- `zoom_level`: 变焦级别（正数放大，负数缩小）
- `duration`: 持续时间（秒）

### `adjust_image_settings`
调整图像设置
- `brightness`: 亮度 (0-100)
- `contrast`: 对比度 (0-100)
- `saturation`: 饱和度 (0-100)

## 开发

### 运行测试

```bash
# 使用 pytest
pytest tests/

# 或使用内置测试
camera-mcp test
```

### 代码格式化

```bash
# 使用 black
black src/ tests/

# 使用 isort
isort src/ tests/

# 使用 ruff
ruff check src/ tests/
```

### 类型检查

```bash
mypy src/
```

## 技术架构

```
┌─────────────────┐    MCP Protocol    ┌─────────────────┐
│   MCP Client    │◄──────────────────►│   MCP Server    │
│                 │                    │                 │
│ - AI 控制       │                    │ - 摄像头控制    │
│ - OpenAI 集成   │                    │ - 工具实现      │
│ - 交互界面      │                    │ - 资源管理      │
└─────────────────┘                    └─────────────────┘
         │                                       │
         │                                       │
         ▼                                       ▼
┌─────────────────┐                    ┌─────────────────┐
│   OpenAI API    │                    │   Camera API    │
│                 │                    │                 │
│ - 指令解析      │                    │ - HTTP 控制     │
│ - JSON 生成     │                    │ - RTSP 流       │
└─────────────────┘                    └─────────────────┘
```

## 故障排除

### 常见问题

1. **连接失败**
   - 检查摄像头IP地址和网络连接
   - 确认用户名和密码正确
   - 检查防火墙设置

2. **AI 控制失败**
   - 检查 OpenAI API 密钥配置
   - 确认网络连接正常
   - 查看日志输出获取详细错误信息

3. **MCP 连接问题**
   - 确保 MCP Server 正在运行
   - 检查 Python 环境和依赖安装
   - 查看控制台错误输出

### 日志查看

系统会在控制台输出详细的日志信息，包括：
- 连接状态
- 工具调用结果
- 错误信息
- AI 响应内容

## 许可证

本项目基于 MIT 许可证开源。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v0.1.0
- 初始版本
- 基本的 MCP Server 和 Client 功能
- AI 智能控制支持
- 完整的摄像头控制工具集 