# VLM视频监控系统 - 主程序

基于配置文件驱动的VLM视频监控系统，支持RTSP和TCP两种流媒体输入，具备完整的异步视频处理和VLM推理能力。

## 🚀 功能特性

### 核心功能
- **双流媒体支持**: 支持RTSP和TCP两种视频流输入
- **配置文件驱动**: 通过`config.json`统一管理所有配置
- **自动VLM初始化**: 自动从配置文件加载VLM客户端设置
- **异步视频处理**: 实时帧收集、视频生成和并发推理
- **会话管理**: 自动创建会话目录，完整记录实验数据
- **命令行支持**: 灵活的命令行参数覆盖配置

### 技术架构
```
配置文件 → VLM监控器 → 流媒体服务器/客户端 → 异步视频处理器 → VLM推理 → 结果保存
```

## 📋 系统要求

- Python 3.8+
- OpenCV
- FFmpeg (用于RTSP服务器)
- 阿里云DashScope API密钥

## 🔧 安装

### 使用uv安装 (推荐)
```bash
# 安装到开发模式
uv pip install -e .

# 验证安装
python src/monitor/main.py --help
```

### 传统pip安装
```bash
pip install -e .
```

## ⚙️ 配置

### 配置文件结构 (`config.json`)

```json
{
  "stream": {
    "type": "tcp",  // 或 "rtsp"
    "tcp": {
      "host": "localhost",
      "port": 9999,
      "video_file": "data/test.avi",
      "fps": 25.0
    },
    "rtsp": {
      "url": "rtsp://camera_ip:port/stream",
      "use_local_server": true,
      "local_server": {
        "video_file": "data/test.avi",
        "port": 8554,
        "stream_name": "stream"
      }
    }
  },
  "vlm": {
    "api_key": "your_api_key",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-vl-max-latest",
    "max_concurrent_inferences": 3
  },
  "video_processing": {
    "target_video_duration": 3.0,
    "frames_per_second": 5,
    "target_frames_per_video": 15
  },
  "monitoring": {
    "output_dir": "output",
    "save_frames": true,
    "save_videos": true,
    "save_results": true,
    "log_level": "INFO"
  }
}
```

## 🎯 使用方法

### 基本使用

```bash
# 使用默认配置运行
python src/monitor/main.py

# 指定流媒体类型
python src/monitor/main.py --stream-type tcp
python src/monitor/main.py --stream-type rtsp

# 自定义配置文件和输出目录
python src/monitor/main.py --config my_config.json --output-dir my_output
```

### 命令行参数

```bash
python src/monitor/main.py [选项]

选项:
  -h, --help                    显示帮助信息
  --config CONFIG, -c CONFIG    配置文件路径
  --stream-type {rtsp,tcp}      强制指定流媒体类型
  --output-dir OUTPUT_DIR, -o   输出目录
```

## 📊 运行示例

### TCP模式示例
```bash
$ python src/monitor/main.py --stream-type tcp

2025-05-29 16:45:16,622 - __main__ - INFO - 🚀 启动VLM视频监控...
2025-05-29 16:45:16,665 - __main__ - INFO - ✅ VLM客户端已初始化，模型: qwen-vl-max-latest
2025-05-29 16:45:16,667 - __main__ - INFO - ✅ 异步视频处理器已初始化，原始帧率: 25.0fps
2025-05-29 16:45:16,670 - __main__ - INFO - ✅ TCP视频服务器已启动: tcp://localhost:9999
2025-05-29 16:45:18,673 - __main__ - INFO - ✅ TCP客户端已创建
2025-05-29 16:45:18,775 - __main__ - INFO - ✅ 开始接收 TCP 视频流...
```

### RTSP模式示例
```bash
$ python src/monitor/main.py --stream-type rtsp

2025-05-29 16:46:44,125 - __main__ - INFO - 🚀 启动VLM视频监控...
2025-05-29 16:46:44,164 - __main__ - INFO - ✅ VLM客户端已初始化，模型: qwen-vl-max-latest
2025-05-29 16:46:44,166 - __main__ - INFO - ✅ 异步视频处理器已初始化，原始帧率: 25.0fps
2025-05-29 16:46:44,170 - __main__ - INFO - ✅ 本地RTSP服务器已启动: rtsp://localhost:8554/stream
2025-05-29 16:46:46,171 - __main__ - INFO - ✅ RTSP客户端已创建
2025-05-29 16:46:46,273 - __main__ - INFO - ✅ 开始接收 RTSP 视频流...
```

## 📁 输出结构

每次运行会创建一个会话目录，包含：

```
output/session_YYYYMMDD_HHMMSS/
├── experiment_log.json          # 实验日志
├── sampled_video_XXX_details/   # 视频片段详情
│   ├── frame_XX_orig_XXXX.jpg   # 抽取的帧
│   ├── sampled_video_XXX.mp4    # 生成的视频
│   └── video_details.json       # 视频元数据
└── result_XXXX.json             # VLM推理结果
```

## 🧪 测试

### 运行功能测试
```bash
python test_main_functionality.py
```

### 测试覆盖
- ✅ 配置验证
- ✅ TCP模式运行
- ✅ RTSP模式运行
- ✅ 输出结构验证

## 🔄 工作流程

1. **初始化阶段**
   - 加载配置文件
   - 初始化VLM客户端
   - 创建异步视频处理器
   - 设置流媒体服务器和客户端

2. **运行阶段**
   - 启动流媒体服务器（如果需要）
   - 连接流媒体客户端
   - 开始帧收集和处理
   - 异步生成视频片段
   - 并发执行VLM推理
   - 保存推理结果

3. **停止阶段**
   - 优雅停止所有组件
   - 保存实验日志
   - 清理资源

## 🛠️ 技术细节

### 异步处理
- 帧收集与视频处理分离
- 多个视频片段并发推理
- 非阻塞结果处理

### 配置管理
- 统一的配置文件格式
- 自动配置文件搜索
- 命令行参数覆盖

### 错误处理
- 连接断开自动重试
- 优雅的信号处理
- 完整的错误日志

## 🚨 故障排除

### 常见问题

1. **TCP连接失败**
   ```
   检查端口是否被占用
   确认视频文件路径正确
   ```

2. **RTSP连接失败**
   ```
   确认FFmpeg已安装
   检查视频文件格式
   验证端口可用性
   ```

3. **VLM推理失败**
   ```
   检查API密钥配置
   确认网络连接
   验证模型名称
   ```

### 调试模式
```bash
# 启用详细日志
python src/monitor/main.py --config config.json 2>&1 | tee debug.log
```

## 📈 性能优化

- 调整`max_concurrent_inferences`控制并发数
- 修改`frames_per_second`平衡质量和性能
- 设置合适的`target_video_duration`
- 根据硬件调整缓冲区大小

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 📄 许可证

MIT License

---

**开发状态**: ✅ 稳定版本  
**测试覆盖**: 75%+ 功能测试通过  
**支持平台**: Linux, macOS, Windows 