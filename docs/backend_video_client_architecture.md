# 后端视频客户端架构

## 问题背景

在原始架构中，存在以下问题：

1. **TCP连接冲突**：后端服务和推理服务都作为TCP客户端连接摄像头，但真实摄像头通常只支持一对一连接
2. **测试环境vs生产环境差异**：
   - 测试环境：`tcp_video_service.py` 支持多客户端连接，所以都能正常工作
   - 生产环境：真实摄像头只支持单连接，导致后连接的客户端失败

## 解决方案

### 新架构设计

```
摄像头TCP服务 → 后端服务(唯一TCP客户端) → 内部分发 → 推理服务
                     ↓
                 WebSocket → 前端显示
```

### 核心改进

1. **后端服务作为唯一TCP客户端**
   - 只有后端服务连接摄像头TCP流
   - 避免了多客户端连接冲突

2. **内部视频流分发器**
   - 后端服务内置 `InternalVideoDistributor` 类
   - 支持多个内部订阅者
   - 线程安全的帧分发机制

3. **后端视频客户端**
   - 推理服务使用 `BackendVideoClient` 类
   - 通过HTTP API从后端获取视频帧
   - 替代直接TCP连接

## 文件结构

```
backend/
├── app.py                          # 后端服务（新增内部分发器）
src/monitor/vlm/
├── backend_video_client.py         # 后端视频客户端（新增）
src/monitor/
├── main.py                         # 推理服务主程序（支持后端客户端）
├── start_with_backend_client.py    # 新架构启动脚本（新增）
config.json                         # 配置文件（新增后端客户端选项）
```

## 配置说明

在 `config.json` 中添加以下配置：

```json
{
  "stream": {
    "type": "tcp",
    "tcp": {
      "host": "localhost",
      "port": 8888,
      "use_backend_client": true,        // 启用后端视频客户端
      "backend_url": "http://localhost:8080",  // 后端服务URL
      "frame_rate": 5                    // 推理服务目标帧率
    }
  }
}
```

## 使用方法

### 1. 测试模式（使用本地TCP视频服务）

```bash
python start_with_backend_client.py --test
```

这将启动：
1. TCP视频服务（支持多客户端）
2. 后端服务（连接TCP，内部分发）
3. 推理服务（使用后端客户端）
4. 前端服务

### 2. 生产模式（连接真实摄像头）

```bash
# 确保摄像头TCP服务已启动
python start_with_backend_client.py
```

### 3. 手动配置

```bash
# 1. 更新配置文件
# 设置 use_backend_client: true

# 2. 启动后端服务
python backend/app.py

# 3. 启动推理服务
vlm-monitor --config config.json

# 4. 启动前端服务
cd frontend && npm run dev
```

## API接口

### 内部视频流API

后端服务提供以下内部API供推理服务使用：

1. **获取最新帧**
   ```
   GET /internal/video/latest-frame
   ```

2. **获取视频流状态**
   ```
   GET /internal/video/status
   ```

3. **订阅视频流**
   ```
   POST /internal/video/subscribe
   ```

## 架构优势

1. **解决连接冲突**：只有一个TCP客户端连接摄像头
2. **统一管理**：后端服务统一管理视频流
3. **灵活分发**：支持多个内部订阅者
4. **向后兼容**：保持原有直接TCP连接选项
5. **易于扩展**：可以轻松添加更多视频流消费者

## 监控和调试

### 日志文件

- `logs/backend_client_startup.log` - 启动日志
- `logs/backend_service.log` - 后端服务日志
- `logs/inference_service.log` - 推理服务日志

### 状态检查

```bash
# 检查后端视频流状态
curl http://localhost:8080/internal/video/status

# 检查系统状态
curl http://localhost:8080/api/status
```

## 故障排除

### 常见问题

1. **推理服务无法获取视频帧**
   - 检查后端服务是否正常运行
   - 确认配置文件中 `use_backend_client: true`
   - 检查 `backend_url` 是否正确

2. **后端服务无法连接TCP**
   - 确认摄像头TCP服务已启动
   - 检查TCP端口和地址配置
   - 查看后端服务日志

3. **前端无法显示视频**
   - 检查WebSocket连接状态
   - 确认后端服务正在接收视频帧
   - 查看浏览器控制台错误

### 调试命令

```bash
# 清理端口占用
python start_with_backend_client.py --stop

# 查看端口占用
netstat -tulpn | grep -E "(8080|8888|5173)"

# 测试后端API
curl http://localhost:8080/api/status
curl http://localhost:8080/internal/video/status
``` 