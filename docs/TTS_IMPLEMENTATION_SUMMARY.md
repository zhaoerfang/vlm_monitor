# TTS服务实现总结

## 实现概述

根据需求，我们成功实现了TTS（Text-to-Speech）服务功能，该服务能够监控最新的推理结果并将summary字段发送给外部TTS服务进行语音合成。

**重要修正**: 经过用户反馈，TTS服务现在正确监控每个frame的details目录中的 `inference_result.json` 文件，而不是session级别的 `experiment_log.json` 文件。

## 实现的功能

### 1. 配置管理
- ✅ 在 `config.json` 中添加了完整的TTS配置项
- ✅ 支持启用/禁用TTS服务的开关
- ✅ 可配置TTS服务的主机、端口、端点等参数
- ✅ 支持检查间隔、重试次数、超时时间等高级配置

### 2. TTS服务核心功能
- ✅ 自动监控最新的session目录
- ✅ 扫描session中所有frame的details目录
- ✅ 读取每个frame目录中的 `inference_result.json` 文件
- ✅ 从 `parsed_result.summary` 字段提取场景描述
- ✅ 发送HTTP POST请求到外部TTS服务
- ✅ 支持重试机制和错误处理
- ✅ 自动去重，避免重复处理相同的推理结果

### 3. 系统集成
- ✅ 在 `start_system.py` 中添加了 `--tts` 命令行参数
- ✅ 支持自动启动TTS服务作为系统的一部分
- ✅ 自动更新配置文件启用TTS功能
- ✅ 完整的日志记录和状态监控

### 4. 测试和调试工具
- ✅ 创建了TTS服务测试脚本 `tools/test_tts_service.py`
- ✅ 支持端点连接测试和完整集成测试
- ✅ 支持创建正确格式的测试数据
- ✅ 提供详细的日志输出和调试模式

## 文件结构

```
vlm_monitor/
├── config.json                    # 添加了TTS配置
├── start_system.py                # 添加了TTS服务启动功能
├── tools/
│   ├── tts_service.py             # TTS服务主程序（已修正）
│   ├── test_tts_service.py        # TTS服务测试脚本（已修正）
│   └── example_usage.md           # 使用示例
└── docs/
    ├── TTS_SERVICE.md             # TTS服务使用指南（已更新）
    └── TTS_IMPLEMENTATION_SUMMARY.md  # 本文档
```

## 数据结构和工作原理

### 监控的文件结构
```
tmp/
└── session_20250606_121752/
    ├── frame_000050_121813_702_details/
    │   └── inference_result.json
    ├── frame_000075_121816_020_details/
    │   └── inference_result.json
    └── ...
```

### inference_result.json 格式
```json
{
  "video_path": "path/to/frame.jpg",
  "inference_start_time": 1749183493.7101,
  "inference_end_time": 1749183497.7412698,
  "inference_start_timestamp": "2025-06-06T12:18:13.710101",
  "inference_end_timestamp": "2025-06-06T12:18:17.741272",
  "inference_duration": 4.031169891357422,
  "result_received_at": 1749183497.7414584,
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

### 工作流程

1. **监控session目录**: 定期检查 `tmp/` 目录中最新的session目录
2. **扫描frame目录**: 查找session中所有以 `_details` 结尾的frame目录
3. **读取推理结果**: 从每个frame目录中的 `inference_result.json` 文件读取推理结果
4. **提取summary**: 优先从 `parsed_result.summary` 字段提取，如果没有则从 `raw_result` 解析
5. **去重处理**: 使用frame目录名和推理时间戳作为唯一ID避免重复处理
6. **发送请求**: 将summary文本发送给外部TTS服务
7. **错误处理**: 支持重试机制和超时处理

## 配置示例

### config.json中的TTS配置
```json
{
  "tts": {
    "enabled": true,
    "host": "172.20.10.4",
    "port": 8888,
    "endpoint": "/speak",
    "check_interval": 5.0,
    "max_retries": 3,
    "timeout": 10,
    "comment": "TTS服务配置，enabled控制是否启用TTS服务，check_interval为检查新推理结果的间隔（秒）"
  }
}
```

## 使用方法

### 1. 启动系统时启用TTS
```bash
# 启动系统并启用TTS服务
python start_system.py --tts

# 结合其他参数使用
python start_system.py --test --backend-client --tts
```

### 2. 单独运行TTS服务
```bash
# 基本运行
python tools/tts_service.py

# 详细日志模式
python tools/tts_service.py --verbose
```

### 3. 测试TTS功能
```bash
# 测试TTS端点
python tools/test_tts_service.py --endpoint-only

# 创建测试数据
python tools/test_tts_service.py --create-test-data --count 3

# 完整集成测试
python tools/test_tts_service.py
```

## 外部TTS服务要求

TTS服务需要一个外部的语音合成服务，该服务应该：

1. **HTTP POST接口**: 接受POST请求
2. **JSON格式**: 请求体格式为 `{"text": "要合成的文本"}`
3. **成功响应**: 返回HTTP 200状态码表示成功

### 示例请求
```bash
curl -X POST http://172.20.10.4:8888/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "两个人在室内环境中，一人使用手机，另一人站立"}'
```

## 实际运行日志

```
2025-06-06 12:25:19,732 - INFO - TTS服务初始化完成
2025-06-06 12:25:19,732 - INFO - TTS服务URL: http://172.20.10.4:8888/speak
2025-06-06 12:25:19,733 - INFO - 🎵 TTS服务启动
2025-06-06 12:25:19,733 - DEBUG - 最新session目录: tmp/session_test_1749183877
2025-06-06 12:25:19,734 - DEBUG - 提取到summary: 室内场景，一人坐在椅子上使用电脑
2025-06-06 12:25:19,734 - INFO - 发送TTS请求 (尝试 1/3): 室内场景，一人坐在椅子上使用电脑
2025-06-06 12:25:22,385 - INFO - TTS请求成功: 室内场景，一人坐在椅子上使用电脑
2025-06-06 12:25:22,385 - INFO - 成功处理推理结果: frame_000000_1749183877_test_details
2025-06-06 12:25:22,386 - DEBUG - 提取到summary: 街道场景，两人在路边，一辆小轿车正在行驶
2025-06-06 12:25:22,386 - INFO - 发送TTS请求 (尝试 1/3): 街道场景，两人在路边，一辆小轿车正在行驶
2025-06-06 12:25:25,397 - INFO - TTS请求成功: 街道场景，两人在路边，一辆小轿车正在行驶
2025-06-06 12:25:25,397 - INFO - 成功处理推理结果: frame_000001_1749183878_test_details
2025-06-06 12:25:25,397 - INFO - 处理了 2 个新的推理结果
```

## 技术特性

### 错误处理
- 网络连接失败自动重试
- 配置文件错误提示
- 推理结果格式异常处理
- 详细的错误日志记录
- 自动跳过没有summary的推理结果

### 性能优化
- 轻量级设计，对系统性能影响最小
- 可配置的检查间隔
- 异步处理，不阻塞其他服务
- 内存中去重，避免重复处理
- 按时间顺序处理frame目录

### 可扩展性
- 模块化设计，易于扩展
- 配置驱动，支持多种TTS服务
- 插件式架构，可添加过滤规则
- 支持多语言和自定义处理逻辑

## 测试验证

### 基本功能测试
- ✅ 配置文件格式验证
- ✅ 命令行参数解析
- ✅ 帮助信息显示
- ✅ 服务启动和停止

### 集成测试
- ✅ 与start_system.py的集成
- ✅ 配置文件自动更新
- ✅ 日志文件生成
- ✅ 错误处理机制

### 端到端测试
- ✅ 推理结果监控（修正后的路径）
- ✅ Summary提取（从正确的字段）
- ✅ TTS请求发送（实际测试成功）
- ✅ 去重机制验证

## 修正历史

### 初始实现问题
- ❌ 错误地监控session级别的 `experiment_log.json` 文件
- ❌ 从错误的数据结构中提取summary

### 修正后的实现
- ✅ 正确监控frame级别的 `inference_result.json` 文件
- ✅ 从 `parsed_result.summary` 字段提取数据
- ✅ 支持从 `raw_result` 作为备选方案
- ✅ 实际测试验证功能正常

## 部署建议

### 生产环境
1. 确保外部TTS服务稳定可用
2. 根据推理频率调整检查间隔
3. 监控TTS服务的日志输出
4. 定期清理旧的session数据

### 开发环境
1. 使用测试脚本验证功能
2. 启用详细日志进行调试
3. 使用模拟TTS服务进行测试
4. 验证配置文件的各种参数

## 后续扩展

可以考虑的功能扩展：

1. **智能过滤**: 只播报重要或异常场景
2. **语音定制**: 根据场景类型选择不同语音
3. **多语言支持**: 支持多种语言的TTS
4. **音频处理**: 添加音效或背景音乐
5. **实时通知**: 结合其他通知方式（邮件、短信等）
6. **历史回放**: 支持历史推理结果的语音回放

## 总结

TTS服务功能已经完全实现并集成到视频监控系统中，经过用户反馈修正后，现在能够正确监控推理结果并发送给外部TTS服务。该功能具有以下优点：

- **准确性**: 正确监控frame级别的推理结果
- **易用性**: 简单的命令行参数即可启用
- **可靠性**: 完善的错误处理和重试机制
- **灵活性**: 丰富的配置选项和扩展能力
- **性能**: 轻量级设计，不影响系统性能
- **可维护性**: 清晰的代码结构和完整的文档

用户可以根据需要启用TTS功能，将视频监控的推理结果转换为语音播报，提升监控系统的用户体验。 