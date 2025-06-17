#!/bin/bash

# 停止所有服务的脚本
echo "正在停止所有服务..."

# 停止所有相关服务
echo "停止 main_serving..."
pkill -f "main_serving" 2>/dev/null && echo "main_serving 已停止" || echo "main_serving 未运行"

echo "停止 server_ui.py..."
pkill -f "server_ui.py" 2>/dev/null && echo "server_ui.py 已停止" || echo "server_ui.py 未运行"

echo "停止 camera_service.py..."
pkill -f "camera_service.py" 2>/dev/null && echo "camera_service.py 已停止" || echo "camera_service.py 未运行"

echo "停止 uvicorn..."
pkill -f "uvicorn main:app" 2>/dev/null && echo "uvicorn 已停止" || echo "uvicorn 未运行"

echo "停止 start_system.py..."
pkill -f "start_system.py" 2>/dev/null && echo "start_system.py 已停止" || echo "start_system.py 未运行"

echo "所有服务已停止！" 