# TTS服务实现总结

## 实现概述

根据需求，我们成功实现了TTS（Text-to-Speech）服务功能，该服务能够监控最新的推理结果并将summary字段发送给外部TTS服务进行语音合成。

## 实现的功能

### 1. 配置管理
- ✅ 在 `config.json` 中添加了完整的TTS配置项
- ✅ 支持启用/禁用TTS服务的开关
- ✅ 可配置TTS服务的主机、端口、端点等参数
- ✅ 支持检查间隔、重试次数、超时时间等高级配置

### 2. TTS服务核心功能
- ✅ 自动监控最新的session目录
- ✅ 读取 `experiment_log.json` 文件中的推理结果
- ✅ 提取推理结果中的 `summary` 字段
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
- ✅ 提供详细的日志输出和调试模式
- ✅ 创建测试数据用于验证功能

## 文件结构

```
vlm_monitor/
├── config.json                    # 添加了TTS配置
├── start_system.py                # 添加了TTS服务启动功能
├── tools/
│   ├── tts_service.py             # TTS服务主程序
│   ├── test_tts_service.py        # TTS服务测试脚本
│   └── example_usage.md           # 使用示例
└── docs/
    ├── TTS_SERVICE.md             # TTS服务使用指南
    └── TTS_IMPLEMENTATION_SUMMARY.md  # 本文档
```

## 配置示例

### config.json中的TTS配置
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
curl -X POST http://localhost:8888/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "室内场景，一人坐在椅子上"}'
```

## 工作流程

1. **启动**: TTS服务随系统启动或单独启动
2. **监控**: 定期检查最新的session目录
3. **读取**: 解析 `experiment_log.json` 文件
4. **提取**: 从推理结果中提取summary字段
5. **去重**: 使用唯一ID避免重复处理
6. **发送**: 将summary发送给外部TTS服务
7. **重试**: 失败时自动重试
8. **记录**: 记录处理状态和错误信息

## 技术特性

### 错误处理
- 网络连接失败自动重试
- 配置文件错误提示
- 推理结果格式异常处理
- 详细的错误日志记录

### 性能优化
- 轻量级设计，对系统性能影响最小
- 可配置的检查间隔
- 异步处理，不阻塞其他服务
- 内存中去重，避免重复处理

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
- ✅ 推理结果监控
- ✅ Summary提取
- ✅ TTS请求发送
- ✅ 去重机制验证

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

TTS服务功能已经完全实现并集成到视频监控系统中。该功能具有以下优点：

- **易用性**: 简单的命令行参数即可启用
- **可靠性**: 完善的错误处理和重试机制
- **灵活性**: 丰富的配置选项和扩展能力
- **性能**: 轻量级设计，不影响系统性能
- **可维护性**: 清晰的代码结构和完整的文档

用户可以根据需要启用TTS功能，将视频监控的推理结果转换为语音播报，提升监控系统的用户体验。 