# TCP视频流服务使用指南

本指南介绍如何使用独立的TCP视频流服务，实现摄像头模拟和VLM监控的分离架构。

## 🏗️ 架构概述

```
TCP视频服务器 (后台服务)  ←→  VLM监控主程序 (客户端)
     ↓                           ↓
持续循环播放视频流              接收帧 → 异步处理 → VLM推理
```

## 🚀 快速开始

### 1. 启动TCP视频服务器 (终端1)

```bash
# 使用默认配置启动
python tcp_video_service.py

# 或指定参数
python tcp_video_service.py --video data/test.avi --port 9999 --fps 25
```

### 2. 运行VLM监控主程序 (终端2)

```bash
# 连接到TCP服务器进行监控
python src/monitor/main.py --stream-type tcp
```

## 📋 详细使用方法

### TCP视频服务器

#### 基本命令
```bash
python tcp_video_service.py [选项]
```

#### 命令行参数
- `--config, -c`: 配置文件路径 (默认: config.json)
- `--video, -v`: 视频文件路径 (覆盖配置文件)
- `--port, -p`: TCP端口 (覆盖配置文件)
- `--fps, -f`: 发送帧率 (覆盖配置文件)
- `--daemon, -d`: 后台运行模式

#### 示例
```bash
# 使用自定义视频文件
python tcp_video_service.py --video /path/to/your/video.mp4

# 使用不同端口
python tcp_video_service.py --port 8888

# 调整帧率
python tcp_video_service.py --fps 30

# 后台运行
python tcp_video_service.py --daemon
```

### VLM监控主程序

#### 基本命令
```bash
python src/monitor/main.py --stream-type tcp
```

#### 输出目录
所有输出文件将保存到 `tmp/` 目录下：
```
tmp/session_YYYYMMDD_HHMMSS/
├── experiment_log.json          # 实验日志
├── sampled_video_XXX_details/   # 视频片段详情
│   ├── frame_XX_orig_XXXX.jpg   # 抽取的帧
│   ├── sampled_video_XXX.mp4    # 生成的视频
│   └── video_details.json       # 视频元数据
└── result_XXXX.json             # VLM推理结果
```

## 🔧 配置文件

### config.json 关键配置
```json
{
  "stream": {
    "type": "tcp",
    "tcp": {
      "host": "localhost",
      "port": 9999,
      "video_file": "data/test_fixed.mp4",
      "fps": 25.0
    }
  },
  "monitoring": {
    "output_dir": "tmp"
  }
}
```

## 📹 视频文件说明

项目使用 `data/test_fixed.mp4` 作为测试视频：
- **格式**: H.264编码的MP4文件
- **分辨率**: 640x360
- **帧率**: 25fps  
- **时长**: 约2分钟（3130帧）
- **内容**: 监控场景，适合VLM分析测试

> 💡 **说明**: 原始的 `test.avi` 文件元数据损坏，已使用ffmpeg修复并转换为MP4格式。

## 📊 运行示例

### 终端1: 启动TCP服务器
```bash
$ python tcp_video_service.py

2025-05-29 17:00:00,123 - __main__ - INFO - TCP视频服务初始化:
2025-05-29 17:00:00,123 - __main__ - INFO -   - 视频文件: data/test.avi
2025-05-29 17:00:00,123 - __main__ - INFO -   - 端口: 9999
2025-05-29 17:00:00,123 - __main__ - INFO -   - 帧率: 25.0fps
2025-05-29 17:00:00,125 - __main__ - INFO - 🚀 启动TCP视频流服务...
2025-05-29 17:00:00,130 - __main__ - INFO - ✅ TCP视频流服务已启动: tcp://localhost:9999
2025-05-29 17:00:00,130 - __main__ - INFO - 📺 视频将持续循环播放，等待客户端连接...
```

### 终端2: 运行VLM监控
```bash
$ python src/monitor/main.py --stream-type tcp

2025-05-29 17:00:10,456 - __main__ - INFO - 🚀 启动VLM视频监控...
2025-05-29 17:00:10,500 - __main__ - INFO - ✅ VLM客户端已初始化，模型: qwen-vl-max-latest
2025-05-29 17:00:10,502 - __main__ - INFO - ✅ 异步视频处理器已初始化，原始帧率: 25.0fps
2025-05-29 17:00:10,503 - __main__ - INFO - 连接到外部TCP视频服务器: localhost:9999
2025-05-29 17:00:10,505 - __main__ - INFO - ✅ TCP客户端已创建
2025-05-29 17:00:10,607 - __main__ - INFO - ✅ 开始接收 TCP 视频流...
```

## 🔄 工作流程

1. **TCP服务器启动**
   - 加载视频文件
   - 创建TCP socket监听
   - 开始循环播放视频流

2. **客户端连接**
   - VLM监控程序连接到TCP服务器
   - 开始接收视频帧
   - 启动异步视频处理

3. **持续运行**
   - TCP服务器持续发送帧
   - VLM监控程序持续处理和推理
   - 结果保存到tmp目录

## 🛠️ 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 检查端口使用情况
   netstat -tlnp | grep 9999
   
   # 使用不同端口
   python tcp_video_service.py --port 8888
   ```

2. **视频文件不存在**
   ```bash
   # 检查视频文件路径
   ls -la data/test.avi
   
   # 使用绝对路径
   python tcp_video_service.py --video /absolute/path/to/video.avi
   ```

3. **连接失败**
   ```bash
   # 确保TCP服务器已启动
   # 检查防火墙设置
   # 验证host和port配置
   ```

### 调试模式
```bash
# 启用详细日志
python tcp_video_service.py 2>&1 | tee tcp_service.log
python src/monitor/main.py --stream-type tcp 2>&1 | tee vlm_monitor.log
```

## 🎯 优势

1. **服务分离**: TCP服务器和VLM监控独立运行
2. **持续流媒体**: 模拟真实摄像头的持续数据流
3. **灵活配置**: 支持多种参数覆盖
4. **简洁输出**: 所有文件统一保存到tmp目录
5. **易于调试**: 独立的日志和错误处理

## 📈 性能优化

- 调整TCP服务器的fps参数控制发送频率
- 修改VLM监控的并发推理数量
- 根据网络情况调整缓冲区大小
- 使用SSD存储提高I/O性能

---

**开发状态**: ✅ 稳定版本  
**支持平台**: Linux, macOS, Windows  
**推荐用法**: 生产环境中的摄像头流媒体模拟 