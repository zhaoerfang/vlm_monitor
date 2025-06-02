# VLM监控系统前端

基于Vue 3 + TypeScript + Element Plus构建的视频监控系统前端界面。

## 功能特性

### 🎥 实时视频播放
- 通过WebSocket接收TCP视频流
- 实时显示帧率、延迟等统计信息
- 支持全屏播放
- 自动重连机制

### 🤖 推理结果展示
- 显示VLM推理生成的视频片段
- 在视频上实时标注人员bbox
- 展示人数统计、活动描述等推理结果
- 推理历史记录浏览

### 📊 分屏布局
- 左侧：实时视频流（无延迟）
- 右侧：推理结果视频（包含bbox标注）
- 支持水平/垂直布局切换
- 响应式设计，适配不同屏幕尺寸

### 🔧 系统监控
- 实时连接状态显示
- 帧数、推理数量统计
- 系统运行时间监控
- 错误处理和提示

## 技术栈

- **框架**: Vue 3 + TypeScript
- **构建工具**: Vite
- **UI组件**: Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router
- **HTTP客户端**: Axios
- **WebSocket**: Socket.IO Client

## 项目结构

```
frontend/
├── src/
│   ├── components/          # Vue组件
│   │   ├── LiveVideoPlayer.vue    # 实时视频播放器
│   │   └── InferencePlayer.vue    # 推理结果播放器
│   ├── views/              # 页面组件
│   │   └── MonitorView.vue        # 主监控页面
│   ├── stores/             # Pinia状态管理
│   │   └── monitor.ts             # 监控状态
│   ├── services/           # 服务层
│   │   ├── api.ts                 # REST API服务
│   │   └── websocket.ts           # WebSocket服务
│   ├── types/              # TypeScript类型定义
│   │   └── index.ts               # 类型定义
│   ├── router/             # 路由配置
│   │   └── index.ts               # 路由定义
│   ├── App.vue             # 根组件
│   └── main.ts             # 应用入口
├── index.html              # HTML模板
├── package.json            # 依赖配置
├── vite.config.ts          # Vite配置
├── tsconfig.json           # TypeScript配置
└── README.md               # 项目说明
```

## 快速开始

### 安装依赖

```bash
cd frontend
npm install
```

### 开发模式

```bash
npm run dev
```

访问 http://localhost:5173

### 构建生产版本

```bash
npm run build
```

### 代码检查

```bash
npm run lint
```

## 配置说明

### Vite配置 (vite.config.ts)

- **开发服务器**: 端口5173
- **代理配置**: API请求代理到后端8080端口
- **自动导入**: Element Plus组件和Vue API
- **路径别名**: @指向src目录

### TypeScript配置 (tsconfig.json)

- **严格模式**: 启用所有严格类型检查
- **ES模块**: 支持ES6+语法
- **DOM类型**: 包含浏览器API类型定义

## API接口

### WebSocket事件

- `connect` - 连接建立
- `disconnect` - 连接断开
- `video_frame` - 接收视频帧
- `inference_result` - 接收推理结果
- `status_update` - 状态更新
- `start_stream` - 开始视频流
- `stop_stream` - 停止视频流

### REST API

- `GET /api/status` - 获取系统状态
- `GET /api/experiment-log` - 获取实验日志
- `GET /api/inference-history` - 获取推理历史
- `GET /api/latest-inference` - 获取最新推理结果
- `GET /api/videos/<filename>` - 获取视频文件
- `POST /api/stream/start` - 启动视频流
- `POST /api/stream/stop` - 停止视频流
- `DELETE /api/history` - 清空历史数据

## 开发指南

### 组件开发

1. **实时视频播放器** (`LiveVideoPlayer.vue`)
   - 使用Canvas绘制视频帧
   - WebSocket连接管理
   - 播放控制和状态显示

2. **推理结果播放器** (`InferencePlayer.vue`)
   - HTML5 Video播放推理视频
   - Bbox覆盖层绘制
   - 推理信息面板

### 状态管理

使用Pinia管理应用状态：
- 连接状态
- 视频帧数据
- 推理结果
- 统计信息

### 类型安全

完整的TypeScript类型定义：
- API响应类型
- 推理结果类型
- 视频数据类型
- 应用状态类型

## 部署说明

### 开发环境

确保后端服务器运行在8080端口，前端开发服务器会自动代理API请求。

### 生产环境

1. 构建前端：`npm run build`
2. 将`dist`目录部署到Web服务器
3. 配置反向代理将API请求转发到后端服务器

## 故障排除

### 常见问题

1. **WebSocket连接失败**
   - 检查后端服务器是否运行
   - 确认端口8080未被占用
   - 检查防火墙设置

2. **视频播放异常**
   - 确认TCP视频服务已启动
   - 检查视频文件是否存在
   - 查看浏览器控制台错误信息

3. **推理结果不显示**
   - 确认实验日志文件存在
   - 检查推理服务是否正常运行
   - 验证JSON数据格式

### 调试技巧

- 打开浏览器开发者工具查看网络请求
- 检查WebSocket连接状态
- 查看Vue DevTools的状态变化
- 使用console.log输出调试信息

## 贡献指南

1. Fork项目
2. 创建特性分支
3. 提交代码更改
4. 创建Pull Request

## 许可证

本项目采用MIT许可证。 