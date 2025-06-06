# TTS服务使用指南

## 概述

TTS（Text-to-Speech）服务是视频监控系统的一个可选组件，用于将推理结果中的场景描述（summary字段）转换为语音播报。

## 功能特性

- 🎵 自动监控最新的推理结果
- 📝 提取推理结果中的summary字段
- 🔊 发送给外部TTS服务进行语音合成
- 🔄 支持重试机制和错误处理
- ⚙️ 可配置的检查间隔和服务参数

## 配置说明

### config.json配置

在 `config.json` 文件中添加TTS配置：

```json
{
  "tts": {
    "enabled": false,
    "host": "localhost",
    "port": 8888,
    "endpoint": "/speak",
    "check_interval": 5.0,
    "max_retries": 3,
    "timeout": 10,
    "comment": "TTS服务配置，enabled控制是否启用TTS服务，check_interval为检查新推理结果的间隔（秒）"
  }
}
```

### 配置参数说明

- `enabled`: 是否启用TTS服务（默认：false）
- `host`: TTS服务主机地址（默认：localhost）
- `port`: TTS服务端口（默认：8888）
- `endpoint`: TTS服务端点（默认：/speak）
- `check_interval`: 检查新推理结果的间隔，单位秒（默认：5.0）
- `max_retries`: 最大重试次数（默认：3）
- `timeout`: 请求超时时间，单位秒（默认：10）

## 使用方法

### 1. 启动系统时启用TTS服务

```bash
# 启动系统并启用TTS服务
python start_system.py --tts

# 或者结合其他参数
python start_system.py --test --backend-client --tts
```

### 2. 单独运行TTS服务

```bash
# 使用默认配置运行
python tools/tts_service.py

# 使用自定义配置文件
python tools/tts_service.py --config /path/to/config.json

# 启用详细日志
python tools/tts_service.py --verbose
```

### 3. 测试TTS服务

```bash
# 测试TTS端点连接
python tools/test_tts_service.py --endpoint-only

# 完整集成测试
python tools/test_tts_service.py

# 创建测试数据
python tools/test_tts_service.py --create-test-data --count 3

# 测试指定的TTS服务
python tools/test_tts_service.py --host 192.168.1.100 --port 9999
```

## 外部TTS服务要求

TTS服务需要一个外部的语音合成服务，该服务应该：

1. 提供HTTP POST接口
2. 接受JSON格式的请求：`{"text": "要合成的文本"}`
3. 返回HTTP 200状态码表示成功

### 示例请求

```bash
curl -X POST http://localhost:8888/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "室内场景，一人坐在椅子上"}'
```

## 工作原理

TTS服务的工作流程如下：

1. **监控session目录**: 定期检查 `tmp/` 目录中最新的session目录
2. **扫描frame目录**: 查找session中所有以 `_details` 结尾的frame目录
3. **读取推理结果**: 从每个frame目录中的 `inference_result.json` 文件读取推理结果
4. **提取summary**: 从 `parsed_result.summary` 字段提取场景描述
5. **去重处理**: 使用frame目录名和推理时间戳作为唯一ID避免重复处理
6. **发送请求**: 将summary文本发送给外部TTS服务
7. **错误处理**: 支持重试机制和超时处理

### 数据结构

TTS服务监控的文件结构：
```
tmp/
└── session_20250606_121752/
    ├── frame_000050_121813_702_details/
    │   └── inference_result.json
    ├── frame_000075_121816_020_details/
    │   └── inference_result.json
    └── ...
```

`inference_result.json` 文件格式：
```json
{
  "video_path": "path/to/frame.jpg",
  "inference_start_time": 1749183493.7101,
  "inference_end_time": 1749183497.7412698,
  "raw_result": "```json\n{...}\n```",
  "parsed_result": {
    "timestamp": "1970-01-09T03:55:02Z",
    "people_count": 2,
    "vehicle_count": 0,
    "people": [...],
    "vehicles": [...],
    "summary": "两个人在室内环境中，一人使用手机，另一人站立"
  }
}
```

## 日志和调试

### 日志文件

- 系统启动时：`logs/tts_service.log`
- 单独运行时：控制台输出

### 调试模式

```bash
# 启用详细日志
python tools/tts_service.py --verbose
```

### 日志示例

```
2025-06-06 12:25:19,732 - INFO - TTS服务初始化完成
2025-06-06 12:25:19,732 - INFO - TTS服务URL: http://172.20.10.4:8888/speak
2025-06-06 12:25:19,733 - INFO - 🎵 TTS服务启动
2025-06-06 12:25:19,734 - DEBUG - 提取到summary: 室内场景，一人坐在椅子上使用电脑
2025-06-06 12:25:19,734 - INFO - 发送TTS请求 (尝试 1/3): 室内场景，一人坐在椅子上使用电脑
2025-06-06 12:25:22,385 - INFO - TTS请求成功: 室内场景，一人坐在椅子上使用电脑
2025-06-06 12:25:22,385 - INFO - 成功处理推理结果: frame_000000_1749183877_test_details
2025-06-06 12:25:25,397 - INFO - 处理了 2 个新的推理结果
```

### 常见问题

1. **TTS服务连接失败**
   - 检查外部TTS服务是否正在运行
   - 验证host和port配置是否正确
   - 检查网络连接

2. **没有检测到推理结果**
   - 确保推理服务正在运行并产生结果
   - 检查 `tmp` 目录中是否有session文件夹
   - 验证frame目录中是否有 `inference_result.json` 文件

3. **重复播报**
   - TTS服务会自动去重，不会重复处理相同的推理结果
   - 如果需要重置，可以重启TTS服务

4. **找不到summary字段**
   - 检查 `inference_result.json` 中是否有 `parsed_result.summary` 字段
   - 如果没有，TTS服务会尝试从 `raw_result` 中解析

## 性能考虑

- TTS服务是轻量级的，对系统性能影响很小
- 检查间隔可以根据需要调整（建议5-10秒）
- 支持异步处理，不会阻塞推理服务
- 自动跳过没有summary的推理结果

## 扩展功能

可以根据需要扩展TTS服务：

1. **过滤规则**: 只播报特定类型的场景
2. **语音定制**: 根据场景内容选择不同的语音风格
3. **多语言支持**: 支持多种语言的语音合成
4. **音频后处理**: 添加音效或背景音乐

## 故障排除

如果遇到问题，请检查：

1. 配置文件格式是否正确
2. 外部TTS服务是否可访问
3. 推理服务是否正常产生结果
4. frame目录中是否有 `inference_result.json` 文件
5. 日志文件中的错误信息 