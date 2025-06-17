#!/bin/bash

# 最终版启动脚本 - 简单可靠
echo "开始启动所有服务..."

# 清理已运行的服务
echo "清理已运行的服务..."
pkill -f "main_serving" 2>/dev/null || true
pkill -f "server_ui.py" 2>/dev/null || true  
pkill -f "camera_service.py" 2>/dev/null || true
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "start_system.py" 2>/dev/null || true
sleep 2

# 1. 启动 HKCamera main_serving
echo "1. 启动 HKCamera main_serving..."
cd ~/ISVLM/HKCamera/build
if [ -f "./main_serving" ]; then
    nohup ./main_serving > /tmp/main_serving.log 2>&1 &
    echo "   HKCamera main_serving 已启动 (PID: $!)"
else
    echo "   错误: main_serving 文件不存在"
fi
sleep 2

# 2. 启动 ASR 相关服务
echo "2. 启动 ASR 相关服务..."

# 检查虚拟环境是否存在
if [ -d "/home/lxt/ssn/whisper_streaming/venv" ]; then
    # 启动 server_ui.py
    echo "   启动 server_ui.py..."
    nohup bash -c "cd /home/lxt/ssn/mcp-server-camera && source /home/lxt/ssn/whisper_streaming/venv/bin/activate && python server_ui.py" > /tmp/server_ui.log 2>&1 &
    echo "   server_ui.py 已启动 (PID: $!)"
    
    # 启动 camera_service.py  
    echo "   启动 camera_service.py..."
    nohup bash -c "cd /home/lxt/ssn/mcp-server-camera && source /home/lxt/ssn/whisper_streaming/venv/bin/activate && python camera_service.py" > /tmp/camera_service.log 2>&1 &
    echo "   camera_service.py 已启动 (PID: $!)"
else
    echo "   错误: venv 目录不存在 (/home/lxt/ssn/whisper_streaming/venv)"
fi
sleep 2

# 3. 启动 Hikvision API 服务
echo "3. 启动 Hikvision API 服务..."
cd /home/lxt/ISVLM/hikvision

if [ -d "/home/lxt/ISVLM/hikvision" ]; then
    echo "   启动 uvicorn 服务..."
    nohup bash -c "cd /home/lxt/ISVLM/hikvision && eval \"\$(conda shell.bash hook)\" && conda activate py310 && uvicorn main:app --host 0.0.0.0 --port 8888" > /tmp/hikvision_api.log 2>&1 &
    echo "   Hikvision API 服务已启动 (PID: $!)"
else
    echo "   错误: hikvision 目录不存在"
fi
sleep 2

# 4. 启动 VLM Monitor 系统
echo "4. 启动 VLM Monitor 系统..."
cd /home/lxt/fze/code/beta/vlm_monitor

if [ -d "/home/lxt/fze/code/beta/vlm_monitor" ]; then
    echo "   启动 VLM Monitor..."
    nohup bash -c "cd /home/lxt/fze/code/beta/vlm_monitor && eval \"\$(conda shell.bash hook)\" && conda activate py310 && python start_system.py --mcp-inference --asr --tts" > /tmp/vlm_monitor_startup.log 2>&1 &
    echo "   VLM Monitor 系统已启动 (PID: $!)"
else
    echo "   错误: vlm_monitor 目录不存在"
fi

echo ""
echo "========================================="
echo "所有服务启动完成！"
echo "服务状态:"
echo "1. HKCamera main_serving: 已启动"
echo "2. ASR 服务 (server_ui + camera_service): 已启动"  
echo "3. Hikvision API: 已启动 (端口: 8888)"
echo "4. VLM Monitor: 已启动"
echo "========================================="
echo ""

# 等待服务完全启动
echo "等待服务完全启动..."
sleep 5

# 5. 显示日志
echo "开始显示 VLM Monitor 日志..."
if [ -f "logs/vlm_monitor.log" ]; then
    tail -f logs/vlm_monitor.log
else
    echo "主日志文件不存在，显示启动日志..."
    if [ -f "/tmp/vlm_monitor_startup.log" ]; then
        tail -f /tmp/vlm_monitor_startup.log
    else
        echo "启动日志也不存在，请检查服务状态"
        echo "可以查看以下日志文件:"
        echo "- /tmp/main_serving.log"
        echo "- /tmp/server_ui.log"
        echo "- /tmp/camera_service.log"
        echo "- /tmp/hikvision_api.log"
        echo "- /tmp/vlm_monitor_startup.log"
    fi
fi 