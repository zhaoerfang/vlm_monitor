#!/usr/bin/env python3
"""
TCP流分析运行脚本
简单的入口脚本，用于快速执行TCP流分析
"""

import sys
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from test_tcp_stream_info import main

if __name__ == "__main__":
    main() 