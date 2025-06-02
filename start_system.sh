#!/bin/bash

# 视频监控系统启动脚本 (Shell版本)
# 用法: ./start_system.sh [start|stop|restart|status]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
TCP_PORT=8888
BACKEND_PORT=8080
FRONTEND_PORT=5173

# 日志目录
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# 函数：打印带颜色的消息
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 函数：检查端口是否被占用
check_port() {
    local port=$1
    local service_name=$2
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warning "端口 $port ($service_name) 已被占用"
        return 0
    else
        return 1
    fi
}

# 函数：杀死占用端口的进程
kill_port() {
    local port=$1
    local service_name=$2
    
    if check_port $port "$service_name"; then
        log_info "正在杀死占用端口 $port 的进程..."
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 1
        
        if check_port $port "$service_name"; then
            log_warning "端口 $port 仍被占用"
        else
            log_success "端口 $port 已清理"
        fi
    fi
}

# 函数：停止所有服务
stop_services() {
    log_info "🛑 停止所有服务..."
    
    # 杀死相关进程
    pkill -f "tcp_video_service.py" 2>/dev/null || true
    pkill -f "vlm-monitor" 2>/dev/null || true
    pkill -f "backend/app.py" 2>/dev/null || true
    pkill -f "npm run dev" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    
    # 清理端口
    kill_port $TCP_PORT "TCP视频服务"
    kill_port $BACKEND_PORT "后端API"
    kill_port $FRONTEND_PORT "前端开发服务"
    
    log_success "所有服务已停止"
}

# 函数：检查依赖
check_dependencies() {
    log_info "🔍 检查依赖项..."
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        return 1
    fi
    
    # 检查Node.js
    if ! command -v node &> /dev/null; then
        log_error "Node.js 未安装"
        return 1
    fi
    
    # 检查npm
    if ! command -v npm &> /dev/null; then
        log_error "npm 未安装"
        return 1
    fi
    
    # 检查配置文件
    if [ ! -f "config.json" ]; then
        log_error "配置文件 config.json 不存在"
        return 1
    fi
    
    # 检查前端依赖
    if [ ! -d "frontend/node_modules" ]; then
        log_info "📦 安装前端依赖..."
        cd frontend
        npm install
        cd ..
    fi
    
    log_success "依赖检查通过"
    return 0
}

# 函数：启动TCP视频服务
start_tcp_service() {
    log_info "🚀 启动TCP视频服务..."
    
    if check_port $TCP_PORT "TCP视频服务"; then
        kill_port $TCP_PORT "TCP视频服务"
    fi
    
    python3 tools/tcp_video_service.py --config config.json > "$LOG_DIR/tcp_video_service.log" 2>&1 &
    local pid=$!
    
    sleep 3
    
    if kill -0 $pid 2>/dev/null; then
        log_success "TCP视频服务启动成功 (PID: $pid)"
        echo $pid > "$LOG_DIR/tcp_video.pid"
        return 0
    else
        log_error "TCP视频服务启动失败"
        return 1
    fi
}

# 函数：启动推理服务
start_inference_service() {
    log_info "🤖 启动推理服务..."
    
    vlm-monitor --config config.json > "$LOG_DIR/inference_service.log" 2>&1 &
    local pid=$!
    
    sleep 5
    
    if kill -0 $pid 2>/dev/null; then
        log_success "推理服务启动成功 (PID: $pid)"
        echo $pid > "$LOG_DIR/inference.pid"
        return 0
    else
        log_error "推理服务启动失败"
        return 1
    fi
}

# 函数：启动后端服务
start_backend_service() {
    log_info "🔧 启动后端API服务..."
    
    if check_port $BACKEND_PORT "后端API"; then
        kill_port $BACKEND_PORT "后端API"
    fi
    
    python3 backend/app.py > "$LOG_DIR/backend_service.log" 2>&1 &
    local pid=$!
    
    sleep 3
    
    if kill -0 $pid 2>/dev/null; then
        log_success "后端API服务启动成功 (PID: $pid)"
        echo $pid > "$LOG_DIR/backend.pid"
        return 0
    else
        log_error "后端API服务启动失败"
        return 1
    fi
}

# 函数：启动前端服务
start_frontend_service() {
    log_info "🎨 启动前端开发服务..."
    
    if check_port $FRONTEND_PORT "前端开发服务"; then
        kill_port $FRONTEND_PORT "前端开发服务"
    fi
    
    cd frontend
    npm run dev > "../$LOG_DIR/frontend_service.log" 2>&1 &
    local pid=$!
    cd ..
    
    sleep 5
    
    if kill -0 $pid 2>/dev/null; then
        log_success "前端开发服务启动成功 (PID: $pid)"
        echo $pid > "$LOG_DIR/frontend.pid"
        return 0
    else
        log_error "前端开发服务启动失败"
        return 1
    fi
}

# 函数：启动所有服务
start_services() {
    log_info "🚀 启动视频监控系统..."
    
    # 检查依赖
    if ! check_dependencies; then
        log_error "依赖检查失败"
        return 1
    fi
    
    # 停止现有服务
    stop_services
    
    # 按顺序启动服务
    if ! start_tcp_service; then
        log_error "TCP视频服务启动失败"
        return 1
    fi
    
    sleep 2
    
    if ! start_inference_service; then
        log_error "推理服务启动失败"
        stop_services
        return 1
    fi
    
    sleep 2
    
    if ! start_backend_service; then
        log_error "后端API服务启动失败"
        stop_services
        return 1
    fi
    
    sleep 2
    
    if ! start_frontend_service; then
        log_error "前端开发服务启动失败"
        stop_services
        return 1
    fi
    
    log_success "🎉 所有服务启动完成！"
    echo ""
    log_info "📱 前端界面: http://localhost:$FRONTEND_PORT"
    log_info "🔧 后端API: http://localhost:$BACKEND_PORT"
    log_info "📹 TCP视频流: tcp://localhost:$TCP_PORT"
    echo ""
    log_info "使用 './start_system.sh stop' 停止所有服务"
    log_info "使用 './start_system.sh status' 查看服务状态"
    
    return 0
}

# 函数：显示服务状态
show_status() {
    log_info "📊 服务状态检查..."
    
    # 检查TCP视频服务
    if check_port $TCP_PORT "TCP视频服务"; then
        log_success "TCP视频服务 (端口 $TCP_PORT): 运行中"
    else
        log_warning "TCP视频服务 (端口 $TCP_PORT): 未运行"
    fi
    
    # 检查后端API
    if check_port $BACKEND_PORT "后端API"; then
        log_success "后端API (端口 $BACKEND_PORT): 运行中"
    else
        log_warning "后端API (端口 $BACKEND_PORT): 未运行"
    fi
    
    # 检查前端服务
    if check_port $FRONTEND_PORT "前端开发服务"; then
        log_success "前端开发服务 (端口 $FRONTEND_PORT): 运行中"
    else
        log_warning "前端开发服务 (端口 $FRONTEND_PORT): 未运行"
    fi
    
    # 检查进程
    echo ""
    log_info "相关进程:"
    pgrep -f "tcp_video_service.py" > /dev/null && log_success "TCP视频服务进程: 运行中" || log_warning "TCP视频服务进程: 未运行"
    pgrep -f "vlm-monitor" > /dev/null && log_success "推理服务进程: 运行中" || log_warning "推理服务进程: 未运行"
    pgrep -f "backend/app.py" > /dev/null && log_success "后端API进程: 运行中" || log_warning "后端API进程: 未运行"
    pgrep -f "vite" > /dev/null && log_success "前端开发进程: 运行中" || log_warning "前端开发进程: 未运行"
}

# 主函数
main() {
    case "${1:-start}" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            stop_services
            sleep 2
            start_services
            ;;
        status)
            show_status
            ;;
        *)
            echo "用法: $0 {start|stop|restart|status}"
            echo ""
            echo "  start   - 启动所有服务 (默认)"
            echo "  stop    - 停止所有服务"
            echo "  restart - 重启所有服务"
            echo "  status  - 显示服务状态"
            exit 1
            ;;
    esac
}

# 检查是否有lsof命令
if ! command -v lsof &> /dev/null; then
    log_error "lsof 命令未找到，请安装 lsof"
    log_info "Ubuntu/Debian: sudo apt-get install lsof"
    log_info "macOS: brew install lsof (通常已预装)"
    log_info "CentOS/RHEL: sudo yum install lsof"
    exit 1
fi

# 执行主函数
main "$@" 