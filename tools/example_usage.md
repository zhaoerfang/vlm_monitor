# TTS服务使用示例

## 快速开始

### 1. 启用TTS配置

首先在 `config.json` 中启用TTS服务：

```bash
# 临时启用TTS（通过命令行参数）
python start_system.py --tts

# 或者手动修改config.json
# 将 "tts.enabled" 设置为 true
```

### 2. 启动外部TTS服务

在启动监控系统之前，确保外部TTS服务正在运行。例如：

```bash
# 假设你有一个TTS服务运行在localhost:8888
# 测试TTS服务是否可用
curl -X POST http://localhost:8888/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "测试语音合成服务"}'
```

### 3. 启动完整系统

```bash
# 启动系统并启用TTS服务
python start_system.py --test --tts

# 或者启用后端客户端模式
python start_system.py --test --backend-client --tts
```

### 4. 验证TTS功能

系统启动后，TTS服务会：

1. 监控 `tmp/` 目录中最新的session
2. 读取 `experiment_log.json` 中的推理结果
3. 提取每个推理结果的 `summary` 字段
4. 发送给外部TTS服务进行语音合成

## 测试示例

### 测试TTS端点连接

```bash
# 测试TTS服务是否可访问
python tools/test_tts_service.py --endpoint-only

# 测试指定的TTS服务
python tools/test_tts_service.py --endpoint-only --host 192.168.1.100 --port 9999
```

### 创建测试推理结果

```bash
# 运行完整的集成测试（会创建测试数据）
python tools/test_tts_service.py
```

### 单独运行TTS服务

```bash
# 启用TTS配置后单独运行
python tools/tts_service.py --verbose

# 使用自定义配置
python tools/tts_service.py --config custom_config.json
```

## 配置示例

### 基本配置

```json
{
  "tts": {
    "enabled": true,
    "host": "localhost",
    "port": 8888,
    "endpoint": "/speak",
    "check_interval": 5.0,
    "max_retries": 3,
    "timeout": 10
  }
}
```

### 高级配置

```json
{
  "tts": {
    "enabled": true,
    "host": "192.168.1.100",
    "port": 9999,
    "endpoint": "/api/v1/speak",
    "check_interval": 3.0,
    "max_retries": 5,
    "timeout": 15,
    "comment": "连接到远程TTS服务，更短的检查间隔和更长的超时"
  }
}
```

## 预期行为

当系统正常运行时，你应该看到类似的日志输出：

```
2025-06-06 10:45:19,183 - __main__ - INFO - TTS服务初始化完成
2025-06-06 10:45:19,183 - __main__ - INFO - TTS服务URL: http://localhost:8888/speak
2025-06-06 10:45:19,183 - __main__ - INFO - 🎵 TTS服务启动
2025-06-06 10:45:19,183 - __main__ - INFO - 监控推理结果，每 5.0 秒检查一次
2025-06-06 10:45:24,185 - __main__ - INFO - 发送TTS请求 (尝试 1/3): 室内场景，一人坐在椅子上
2025-06-06 10:45:24,200 - __main__ - INFO - TTS请求成功: 室内场景，一人坐在椅子上
2025-06-06 10:45:24,200 - __main__ - INFO - 处理了 1 个新的推理结果
```

## 故障排除

### 常见错误和解决方案

1. **连接被拒绝**
   ```
   TTS请求异常: Connection refused
   ```
   解决：确保外部TTS服务正在运行

2. **配置文件错误**
   ```
   加载配置文件失败: JSON decode error
   ```
   解决：检查config.json格式是否正确

3. **没有推理结果**
   ```
   没有推理结果
   ```
   解决：确保推理服务正在运行并产生结果

### 调试技巧

```bash
# 启用详细日志
python tools/tts_service.py --verbose

# 检查推理结果文件
ls -la tmp/session_*/experiment_log.json

# 手动测试TTS端点
curl -X POST http://localhost:8888/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "手动测试"}'
``` 