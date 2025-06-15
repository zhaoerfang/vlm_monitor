# 摄像头服务器优化说明

## 优化概述

本次优化主要解决了原始 `camera_server.py` 中存在的架构问题，创建了更清晰、更可维护的代码结构，并实现了服务器启动时的自动初始化。

## 主要问题

### 原始代码的问题：

1. **camera_instance 管理混乱**
   - 全局变量 `camera_instance` 和 `get_camera()` 函数混合使用
   - 每个工具都通过 `get_camera()` 获取实例，但初始化逻辑在函数内部
   - 初始化时机不合适，可能在每次工具调用时重复执行

2. **初始化逻辑分散**
   - `goto_preset_point(point_id=1)` 在 `get_camera()` 函数中执行
   - 用户调用工具时可能触发意外的摄像头移动
   - 缺乏统一的初始化管理

3. **状态管理不一致**
   - 摄像头实例和位置状态分散在不同地方
   - 全局变量和函数逻辑耦合严重
   - 错误处理不统一

## 优化方案

### 1. 创建 CameraManager 类

```python
class CameraManager:
    """摄像头管理器 - 统一管理摄像头实例和状态"""
    
    def __init__(self):
        self.camera_instance: Optional[Camera] = None
        self.current_pan_position: float = 0.0
        self.PAN_MIN_LIMIT = -180.0
        self.PAN_MAX_LIMIT = 180.0
        self.is_initialized = False
        
        # 摄像头配置 - 从环境变量读取，否则使用默认值
        self.camera_config = {
            'ip': os.getenv('CAMERA_IP', '192.168.1.64'),
            'admin': os.getenv('CAMERA_ADMIN', 'admin'),
            'password': os.getenv('CAMERA_PASSWORD', 'pw4hkcamera')
        }
```

**优势：**
- 封装所有摄像头相关的状态和逻辑
- 提供清晰的接口和方法
- 统一的错误处理和状态管理
- 支持环境变量配置

### 2. 自动初始化流程

```python
def initialize_camera(self) -> bool:
    """初始化摄像头实例并移动到中心位置"""
    if self.is_initialized:
        return True
    
    # 创建摄像头实例
    self.camera_instance = Camera(
        ip=self.camera_config['ip'],
        admin=self.camera_config['admin'], 
        password=self.camera_config['password']
    )
    
    # 初始化到中心位置
    self.camera_instance.goto_preset_point(point_id=1)
    self.current_pan_position = 0.0
    self.is_initialized = True
```

**优势：**
- 服务器启动时自动执行，无需手动调用
- 明确的初始化状态跟踪
- 避免重复初始化和意外的摄像头移动
- 支持环境变量配置摄像头参数

### 3. 统一的实例获取

```python
def get_camera(self) -> Camera:
    """获取摄像头实例"""
    if not self.is_initialized or self.camera_instance is None:
        raise RuntimeError("摄像头未初始化，服务器启动时初始化失败")
    return self.camera_instance
```

**优势：**
- 明确的前置条件检查
- 统一的错误处理
- 避免空指针异常

### 4. 服务器启动时自动初始化

```python
def main():
    """启动 MCP server"""
    # 自动初始化摄像头
    logger.info("🚀 [SERVER] 正在自动初始化摄像头...")
    if camera_manager.initialize_camera():
        logger.info("🚀 [SERVER] ✅ 摄像头自动初始化成功，服务器就绪")
    else:
        logger.error("🚀 [SERVER] ❌ 摄像头自动初始化失败，服务器将无法正常工作")
    
    # 运行服务器
    mcp.run(transport="stdio")
```

**优势：**
- 服务器启动时就完成初始化
- 工具调用时摄像头已经就绪
- 避免首次调用时的延迟
- 清晰的启动日志和错误提示

## 优化后的架构

### 核心组件

1. **CameraManager 类**
   - `initialize_camera()`: 自动初始化摄像头
   - `get_camera()`: 获取摄像头实例
   - `update_position()`: 更新位置状态
   - `get_position_info()`: 获取位置信息
   - `check_position_limits()`: 检查位置限制
   - `reset_to_center()`: 重置到中心位置

2. **全局管理器实例**
   ```python
   camera_manager = CameraManager()
   ```

3. **统一的工具接口**
   - 所有工具都通过 `camera_manager.get_camera()` 获取实例
   - 统一的错误处理：`RuntimeError` 表示未初始化
   - 一致的返回格式：`✅ 成功` 或 `❌ 失败`

### 工具函数优化

```python
@mcp.tool()
def pan_tilt_move(pan_angle: float = 0) -> str:
    try:
        camera = camera_manager.get_camera()  # 统一获取
        # ... 业务逻辑
        camera_manager.update_position(target_position)  # 统一更新状态
        return f"✅ 摄像头转动成功"
    except RuntimeError as e:
        return f"❌ {str(e)}"  # 统一错误处理
```

## 配置方式

### 环境变量配置

现在支持通过环境变量配置摄像头参数：

```bash
# 设置摄像头IP地址
export CAMERA_IP=192.168.1.100

# 设置用户名
export CAMERA_ADMIN=admin

# 设置密码
export CAMERA_PASSWORD=newpassword

# 启动服务器
python mcp/src/camera_mcp/cores/camera_server.py
```

### 默认配置

如果未设置环境变量，将使用以下默认配置：
- IP: `192.168.1.64`
- 用户名: `admin`
- 密码: `pw4hkcamera`

## 新增功能

### 1. 增强的状态资源

```python
@mcp.resource("camera://status")
def get_camera_status() -> str:
    """获取详细的摄像头状态信息"""
```

提供更详细的状态信息，包括：
- 连接状态
- 初始化状态
- 当前位置
- 位置限制
- 剩余可移动范围

### 2. 改进的错误处理

- 统一的错误消息格式
- 明确的错误类型区分
- 详细的日志记录
- 启动时的配置信息显示

### 3. 环境变量支持

- 支持通过环境变量配置摄像头参数
- 灵活的部署配置
- 安全的密码管理

## 使用方式

### 1. 基本启动

```bash
python mcp/src/camera_mcp/cores/camera_server.py
```

服务器启动时会：
- 显示配置信息
- 自动初始化摄像头
- 移动到中心位置
- 准备接收工具调用

### 2. 自定义配置启动

```bash
# 设置环境变量
export CAMERA_IP=192.168.1.100
export CAMERA_ADMIN=admin
export CAMERA_PASSWORD=mypassword

# 启动服务器
python mcp/src/camera_mcp/cores/camera_server.py
```

### 3. 正常使用

```python
# 获取位置信息（摄像头已自动初始化）
position = await client.call_camera_tool("get_camera_position", {})

# 转动摄像头
result = await client.call_camera_tool("pan_tilt_move", {"pan_angle": 30})

# 拍照
photo = await client.call_camera_tool("capture_image", {"img_name": "test"})
```

## 测试

运行测试脚本验证优化效果：

```bash
python mcp/test_optimized_camera_server.py
```

测试包括：
- 环境变量配置测试
- CameraManager 类直接测试
- MCP 客户端集成测试
- 自动初始化流程验证
- 状态管理验证

## 启动日志示例

```
================================================================================
🚀 [SERVER] 摄像头控制 MCP Server 启动中...
🚀 [SERVER] 启动时间: 2024-01-15 10:30:00
🚀 [SERVER] Python 版本: 3.11.0
🚀 [SERVER] 工作目录: /home/user/vlm_monitor
🚀 [SERVER] 摄像头配置: IP=192.168.1.64, 用户=admin
================================================================================
🚀 [SERVER] 正在自动初始化摄像头...
正在初始化摄像头连接: IP=192.168.1.64
正在将摄像头移动到中心位置...
✅ 摄像头初始化完成，已移动到中心位置
🚀 [SERVER] ✅ 摄像头自动初始化成功，服务器就绪
🚀 [SERVER] 开始运行 FastMCP server (stdio transport)...
```

## 总结

通过这次优化，我们实现了：

1. **更清晰的架构**：CameraManager 类封装所有摄像头逻辑
2. **自动初始化**：服务器启动时自动初始化，无需手动设置
3. **环境变量支持**：灵活的配置方式，支持不同部署环境
4. **更统一的接口**：所有工具使用相同的获取和错误处理模式
5. **更好的可维护性**：代码结构清晰，职责分离明确
6. **更强的健壮性**：完善的错误处理和状态管理
7. **更好的用户体验**：启动即可用，无需额外配置步骤

这个优化彻底解决了原始代码中的主要问题，提供了更专业、更可靠、更易用的摄像头控制服务。摄像头在服务器启动时自动初始化到中心位置，用户可以立即开始使用各种控制功能。 