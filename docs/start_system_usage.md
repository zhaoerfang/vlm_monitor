# start_system.py 使用说明

## 概述

`start_system.py` 是视频监控系统的唯一启动入口，支持两种架构模式：

1. **传统模式**：后端服务和推理服务分别连接TCP视频流
2. **后端视频客户端模式**：后端服务作为唯一TCP客户端，推理服务通过后端获取视频流

## 使用方法

### 基本命令

```bash
# 传统模式启动
python start_system.py

# 后端视频客户端模式启动（解决TCP连接冲突）
python start_system.py --backend-client

# 测试模式（启动本地TCP视频服务）
python start_system.py --test

# 后端视频客户端模式 + 测试模式
python start_system.py --backend-client --test

# 仅清理端口占用
python start_system.py --stop
```

### 参数说明

- `--test, -t`: 测试模式，会启动本地TCP视频服务
- `--backend-client, -b`: 后端视频客户端模式，解决TCP连接冲突
- `--stop, -s`: 仅清理端口占用，不启动服务

## 架构模式对比

### 传统模式（默认）

```
摄像头TCP服务 ← 后端服务（TCP客户端）
              ← 推理服务（TCP客户端）
```

**特点**：
- 两个服务都直接连接TCP视频流
- 适用于支持多客户端连接的TCP服务
- 原有架构，兼容性好

**问题**：
- 真实摄像头可能只支持一对一连接
- 可能出现TCP连接冲突

### 后端视频客户端模式

```
摄像头TCP服务 → 后端服务（唯一TCP客户端） → 内部分发 → 推理服务
                     ↓
                 WebSocket → 前端显示
```

**特点**：
- 只有后端服务连接TCP视频流
- 推理服务通过HTTP API从后端获取视频帧
- 解决TCP连接冲突问题

**优势**：
- 兼容只支持单连接的摄像头
- 统一视频流管理
- 易于扩展更多视频流消费者

## 配置文件变化

启动脚本会自动管理配置文件中的 `use_backend_client` 设置：

- **传统模式**：`"use_backend_client": false`
- **后端视频客户端模式**：`"use_backend_client": true`

**重要**：配置文件中的其他设置（video_file路径、VLM配置、监控配置等）不会被修改。

## 启动顺序

### 传统模式启动顺序

1. 清理端口占用
2. 启动TCP视频服务（测试模式）
3. 启动推理服务
4. 启动后端服务
5. 启动前端服务

### 后端视频客户端模式启动顺序

1. 清理端口占用
2. 启动TCP视频服务（测试模式）
3. 启动后端服务
4. 等待后端服务完全启动（3秒）
5. 启动推理服务
6. 启动前端服务

## 使用场景

### 开发和测试

```bash
# 使用本地TCP视频服务进行测试
python start_system.py --test

# 测试新架构
python start_system.py --backend-client --test
```

### 生产环境

```bash
# 连接真实摄像头（传统模式）
python start_system.py

# 连接只支持单连接的摄像头（推荐）
python start_system.py --backend-client
```

### 故障排除

```bash
# 清理端口占用
python start_system.py --stop

# 查看日志
tail -f logs/system_startup.log
tail -f logs/backend_service.log
tail -f logs/inference_service.log
```

## 日志文件

- `logs/system_startup.log` - 启动脚本日志
- `logs/tcp_video_service.log` - TCP视频服务日志（测试模式）
- `logs/backend_service.log` - 后端服务日志
- `logs/inference_service.log` - 推理服务日志
- `logs/frontend_service.log` - 前端服务日志

## 端口使用

- **8888**: TCP视频服务端口（可配置）
- **8080**: 后端服务端口
- **5173**: 前端服务端口

## 常见问题

### Q: 什么时候使用后端视频客户端模式？

A: 当遇到以下情况时建议使用：
- 真实摄像头只支持一个TCP连接
- 前端无法显示视频流
- 出现TCP连接冲突错误

### Q: 两种模式的性能差异？

A: 后端视频客户端模式会增加一次HTTP请求的开销，但对于推理任务来说影响很小。

### Q: 如何确认使用了哪种模式？

A: 查看启动日志中的"架构模式"信息，或检查配置文件中的 `use_backend_client` 设置。 