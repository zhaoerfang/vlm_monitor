# VLM监控系统

基于阿里云DashScope的实时视频监控和分析系统，支持RTSP流接入和异步视频处理。

## 功能特性

- **实时RTSP流处理**: 支持从RTSP摄像头获取视频流
- **异步视频处理**: 将RTSP帧异步转换为MP4视频片段
- **VLM智能分析**: 使用阿里云DashScope的Qwen-VL模型进行视频内容分析
- **非阻塞架构**: RTSP接收、视频处理和AI推理完全异步，互不阻塞
- **自动文件管理**: 自动控制视频文件大小（<100MB）和清理临时文件
- **告警系统**: 支持关键词检测和自定义告警回调
- **🎥 MCP摄像头控制**: 基于Model Context Protocol的智能摄像头控制系统

## 系统架构

```
RTSP流 → 帧队列 → 视频写入线程 → MP4文件队列 → 推理线程 → 结果队列 → 回调处理
```

### 异步处理流程

1. **RTSP客户端**: 持续从RTSP流获取视频帧
2. **帧队列**: 缓存接收到的帧，避免阻塞
3. **视频写入线程**: 将帧组装成MP4视频片段（10秒/片段，<95MB）
4. **视频队列**: 缓存待处理的视频文件
5. **推理线程**: 调用DashScope API分析视频内容
6. **结果队列**: 缓存分析结果
7. **回调处理**: 处理分析结果（告警、记录等）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置

### 1. 获取DashScope API密钥

1. 访问[阿里云百炼平台](https://bailian.console.aliyun.com/)
2. 创建应用并获取API Key
3. 设置环境变量：

```bash
export DASHSCOPE_API_KEY="your_api_key_here"
```

### 2. 准备RTSP流

确保你有可访问的RTSP摄像头或测试流。

## MCP摄像头控制系统

本项目新增了基于Model Context Protocol (MCP)的摄像头控制系统，支持通过AI自然语言指令控制摄像头。

### 快速开始

```bash
# 进入MCP目录
cd mcp/

# 启动MCP Server（在一个终端中）
python start_camera_system.py server

# 启动MCP Client（在另一个终端中）
python start_camera_system.py client

# 或者运行系统测试
python start_camera_system.py test
```

### MCP功能特性

- **🤖 AI智能控制**: 支持自然语言指令，如"向左转动3秒"、"拍一张照片"
- **🔧 直接工具调用**: 支持JSON格式的精确控制
- **📊 状态监控**: 实时查看摄像头连接状态
- **🎮 交互界面**: 友好的命令行交互界面
- **🔗 独立模型配置**: MCP系统使用独立的 `mcp_model` 配置，与VLM监控系统分离

### 支持的摄像头操作

- 水平/垂直转动控制
- 摄像头拍照
- 变焦控制
- 预设点位移动
- 图像参数调整（亮度、对比度、饱和度）
- 摄像头连接配置

详细使用说明请参考：[mcp/README.md](mcp/README.md)

## 使用方法

### 基本使用

```bash
# 使用环境变量中的API密钥
python src/example_vlm_monitor.py rtsp://your_camera_ip:port/stream

# 或者直接指定API密钥
python src/example_vlm_monitor.py rtsp://your_camera_ip:port/stream --api-key your_api_key
```

### 编程接口

```python
from src.rtsp_client import RTSPClient
from src.dashscope_vlm_client import DashScopeVLMClient, RTSPVLMMonitor

# 创建RTSP客户端
rtsp_client = RTSPClient("rtsp://your_camera_ip:port/stream", frame_rate=5)

# 创建VLM客户端
vlm_client = DashScopeVLMClient()

# 定义结果处理回调
def handle_result(result):
    print(f"分析结果: {result['result']}")
    print(f"时间戳: {result['timestamp']}")

# 创建监控器
monitor = RTSPVLMMonitor(rtsp_client, vlm_client, handle_result)

# 开始监控
monitor.start_monitoring()
```

### 单独使用DashScope客户端

```python
from src.dashscope_vlm_client import DashScopeVLMClient

# 创建客户端
client = DashScopeVLMClient()

# 分析本地视频文件
result = client.analyze_video(
    video_path="/path/to/video.mp4",
    prompt="请描述这段视频中发生的事件，特别关注是否有异常情况。",
    fps=2
)

print(result)
```

## 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python tests/test_dashscope_vlm.py

# 运行集成测试
python tests/test_rtsp_integration.py
```

## 配置参数

### RTSP客户端参数

- `frame_rate`: 目标帧率（默认5帧/秒）
- `timeout`: 连接超时时间（默认30秒）
- `buffer_size`: 帧缓冲区大小（默认20帧）

### 视频处理参数

- `video_fps`: 输出视频帧率（默认10帧/秒）
- `video_duration`: 视频片段时长（默认10秒）
- `max_file_size_mb`: 最大文件大小（默认95MB）

### VLM分析参数

- `model`: 使用的模型（默认'qwen-vl-max-latest'）
- `fps`: 视频抽帧频率（默认2帧/秒）
- `prompt`: 分析提示词

## 性能优化建议

1. **调整帧率**: 根据监控需求调整RTSP帧率和视频输出帧率
2. **队列大小**: 根据系统性能调整各队列的大小
3. **视频参数**: 平衡视频质量和文件大小
4. **并发控制**: 根据API限制调整推理频率

## 故障排除

### 常见问题

1. **RTSP连接失败**
   - 检查RTSP URL是否正确
   - 确认网络连接和防火墙设置
   - 验证摄像头认证信息

2. **API调用失败**
   - 检查API密钥是否正确
   - 确认账户余额和配额
   - 检查网络连接

3. **视频文件过大**
   - 调整视频参数（帧率、分辨率、时长）
   - 检查视频编码设置

4. **内存使用过高**
   - 减少队列大小
   - 调整视频缓冲参数
   - 优化帧处理频率

### 日志调试

```bash
# 启用详细日志
python src/example_vlm_monitor.py rtsp://your_stream --log-level DEBUG
```

## 扩展开发

### 自定义告警系统

```python
def custom_alert_handler(result):
    analysis = result['result']
    
    # 自定义告警逻辑
    if '火灾' in analysis:
        send_emergency_alert(analysis)
    elif '入侵' in analysis:
        send_security_alert(analysis)
    
    # 记录到数据库
    save_to_database(result)

monitor = RTSPVLMMonitor(rtsp_client, vlm_client, custom_alert_handler)
```

### 集成其他VLM服务

可以通过实现相同的接口来集成其他VLM服务：

```python
class CustomVLMClient:
    def analyze_video(self, video_path, prompt, fps=2):
        # 实现自定义VLM调用逻辑
        pass
```

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。