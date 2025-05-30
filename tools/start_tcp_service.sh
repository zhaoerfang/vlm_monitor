#!/bin/bash
# TCP视频流服务启动脚本

set -e

echo "🚀 启动TCP视频流服务"
echo "===================="

# 切换到项目根目录
cd "$(dirname "$0")/.."

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查配置文件
if [ ! -f "config.json" ]; then
    echo "❌ 配置文件 config.json 不存在"
    exit 1
fi

# 检查视频文件
VIDEO_FILE=$(python3 -c "import json; print(json.load(open('config.json'))['stream']['tcp']['video_file'])")
if [ ! -f "$VIDEO_FILE" ]; then
    echo "❌ 视频文件不存在: $VIDEO_FILE"
    exit 1
fi

# 创建tmp目录
mkdir -p tmp

echo "✅ 环境检查通过"
echo ""

# 启动TCP视频服务器
echo "🎬 启动TCP视频服务器..."
echo "按 Ctrl+C 停止服务"
echo ""

python3 tools/tcp_video_service.py --config config.json 