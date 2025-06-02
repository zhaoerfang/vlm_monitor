# 视频监控系统启动指南

## 系统架构

本视频监控系统由以下四个主要组件组成：

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   TCP视频服务   │───▶│    推理服务     │───▶│   后端API服务   │───▶│   前端界面      │
│   (端口8888)    │    │  (vlm-monitor)  │    │   (端口8080)    │    │   (端口5173)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │                       │                       │
        ▼                       ▼                       ▼                       ▼
   模拟摄像头流              AI视频分析              WebSocket API           Vue.js界面
   循环播放视频              人员检测识别             推理结果管理             实时显示结果
```

### 组件说明

1. **TCP视频服务** (`tools/tcp_video_service.py`)
   - 模拟摄像头TCP流，循环播放视频文件
   - 端口：8888
   - 功能：提供持续的视频帧数据

2. **推理服务** (`vlm-monitor`)
   - 连接TCP视频流，进行AI视频分析
   - 使用大语言模型进行人员检测和活动识别
   - 生成推理结果和视频片段

3. **后端API服务** (`backend/app.py`)
   - FastAPI服务器，提供REST API和WebSocket
   - 端口：8080
   - 功能：管理推理结果，提供前端数据接口

4. **前端界面** (`frontend/`)
   - Vue.js + TypeScript开发的Web界面
   - 端口：5173
   - 功能：实时显示视频流和推理结果

## 快速启动

### 方法一：使用Python启动脚本（推荐）

```bash
# 启动所有服务
python3 start_system.py

# 调试模式（显示详细输出）
python3 start_system.py --debug

# 仅停止现有服务
python3 start_system.py --stop

# 检查端口占用情况
python3 start_system.py --check
```

### 方法二：使用Shell脚本

```bash
# 启动所有服务
./start_system.sh

# 停止所有服务
./start_system.sh stop

# 重启所有服务
./start_system.sh restart

# 查看服务状态
./start_system.sh status
```

## 手动启动（调试用）

如果需要单独启动各个服务进行调试：

### 1. 启动TCP视频服务
```bash
python3 tools/tcp_video_service.py --config config.json
```

### 2. 启动推理服务
```bash
vlm-monitor --config config.json
```

### 3. 启动后端API服务
```bash
python3 backend/app.py
```

### 4. 启动前端开发服务
```bash
cd frontend
npm run dev
```

## 系统要求

### Python依赖
- Python 3.8+
- opencv-python>=4.8.0
- numpy>=1.21.0
- dashscope>=1.14.0
- requests>=2.28.0
- openai>=1.0.0
- psutil>=5.9.0
- fastapi>=0.100.0
- websockets>=11.0.0
- uvicorn>=0.23.0

### Node.js依赖
- Node.js 16+
- npm 8+

### 系统工具
- lsof（用于端口检查）

## 安装依赖

### Python依赖
```bash
pip install -r requirements.txt
```

### 前端依赖
```bash
cd frontend
npm install
```

### 系统工具
```bash
# Ubuntu/Debian
sudo apt-get install lsof

# macOS (通常已预装)
brew install lsof

# CentOS/RHEL
sudo yum install lsof
```

## 配置文件

确保项目根目录有 `config.json` 配置文件，包含以下配置：

```json
{
  "stream": {
    "tcp": {
      "host": "localhost",
      "port": 8888,
      "video_file": "data/test_video.mp4",
      "fps": 30
    }
  },
  "inference": {
    "interval": 10,
    "duration": 3,
    "model": "qwen-vl-max"
  },
  "api": {
    "host": "localhost",
    "port": 8080
  }
}
```

## 访问地址

启动成功后，可以通过以下地址访问：

- **前端界面**: http://localhost:5173
- **后端API**: http://localhost:8080
- **API文档**: http://localhost:8080/docs
- **TCP视频流**: tcp://localhost:8888

## 日志文件

所有服务的日志文件保存在 `logs/` 目录下：

- `logs/system_startup.log` - 系统启动日志
- `logs/tcp_video_service.log` - TCP视频服务日志
- `logs/inference_service.log` - 推理服务日志
- `logs/backend_service.log` - 后端API服务日志
- `logs/frontend_service.log` - 前端开发服务日志

## 故障排除

### 端口占用问题
```bash
# 检查端口占用
python3 start_system.py --check

# 或使用系统命令
lsof -i :8888  # TCP视频服务
lsof -i :8080  # 后端API
lsof -i :5173  # 前端服务
```

### 服务启动失败
1. 检查依赖是否安装完整
2. 查看对应的日志文件
3. 确认配置文件存在且格式正确
4. 检查端口是否被其他程序占用

### 前端无法连接后端
1. 确认后端服务正常运行（端口8080）
2. 检查防火墙设置
3. 查看浏览器控制台错误信息

### 推理服务无法连接TCP流
1. 确认TCP视频服务正常运行（端口8888）
2. 检查视频文件是否存在
3. 查看推理服务日志

## 开发模式

### 前端热重载
前端使用Vite开发服务器，支持热重载。修改前端代码后会自动刷新页面。

### 后端调试
后端使用FastAPI的自动重载功能。修改后端代码后需要重启服务。

### 添加新功能
1. 后端API：修改 `backend/app.py` 和相关模块
2. 前端界面：修改 `frontend/src/` 下的Vue组件
3. 推理逻辑：修改 `src/monitor/` 下的推理模块

## 生产部署

生产环境部署时需要：

1. 使用生产级WSGI服务器（如Gunicorn）
2. 构建前端静态文件：`npm run build`
3. 配置反向代理（如Nginx）
4. 设置系统服务（systemd）
5. 配置日志轮转
6. 设置监控和告警

## 许可证

本项目采用MIT许可证。详见LICENSE文件。 