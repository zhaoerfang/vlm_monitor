#!/usr/bin/env python3
"""
测试MCP服务的对话历史功能
"""

import os
import sys
import json
import time
import asyncio
import logging
import requests
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.test_tts_service import create_test_inference_result

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MCPConversationTester:
    """MCP对话历史测试器"""
    
    def __init__(self, mcp_host='localhost', mcp_port=8082):
        self.mcp_host = mcp_host
        self.mcp_port = mcp_port
        self.base_url = f"http://{mcp_host}:{mcp_port}"
        
    def check_mcp_service(self) -> bool:
        """检查MCP服务是否运行"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_conversation_history(self) -> dict:
        """获取对话历史"""
        try:
            response = requests.get(f"{self.base_url}/conversation/history", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"获取对话历史失败: {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            logger.error(f"获取对话历史异常: {e}")
            return {}
    
    def clear_conversation_history(self) -> bool:
        """清空对话历史"""
        try:
            response = requests.delete(f"{self.base_url}/conversation/history", timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"清空对话历史异常: {e}")
            return False
    
    def get_conversation_summary(self) -> dict:
        """获取对话摘要"""
        try:
            response = requests.get(f"{self.base_url}/conversation/summary", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"获取对话摘要失败: {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            logger.error(f"获取对话摘要异常: {e}")
            return {}
    
    def analyze_image(self, image_path: str) -> dict:
        """分析图像（触发MCP调用）"""
        try:
            data = {"image_path": image_path}
            response = requests.post(f"{self.base_url}/analyze", json=data, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"图像分析失败: {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            logger.error(f"图像分析异常: {e}")
            return {}

def test_conversation_history_functionality():
    """测试对话历史功能"""
    logger.info("🧪 开始测试MCP对话历史功能")
    
    tester = MCPConversationTester()
    
    # 检查MCP服务
    if not tester.check_mcp_service():
        logger.error("❌ MCP服务未运行，请先启动MCP服务")
        logger.info("💡 启动命令: cd mcp && python -m src.camera_mcp.cores.camera_inference_service")
        return False
    
    logger.info("✅ MCP服务运行正常")
    
    try:
        # 1. 清空对话历史
        logger.info("\n📝 步骤1: 清空对话历史")
        if tester.clear_conversation_history():
            logger.info("✅ 对话历史已清空")
        else:
            logger.error("❌ 清空对话历史失败")
            return False
        
        # 2. 检查初始状态
        logger.info("\n📊 步骤2: 检查初始对话状态")
        summary = tester.get_conversation_summary()
        if summary.get('success'):
            data = summary.get('data', {})
            logger.info(f"  - 对话轮数: {data.get('conversation_rounds', 0)}")
            logger.info(f"  - 消息总数: {data.get('total_messages', 0)}")
            logger.info(f"  - 最大轮数: {data.get('max_rounds', 0)}")
        
        # 3. 创建测试图像并进行多次分析
        logger.info("\n🖼️ 步骤3: 创建测试图像并进行多次分析")
        
        test_results = []
        for i in range(6):  # 测试6次，超过最大4轮限制
            # 创建测试图像
            frame_dir = create_test_inference_result("tmp")
            test_image_path = frame_dir / f"conversation_test_{i}.jpg"
            
            from PIL import Image
            colors = ['red', 'blue', 'green', 'yellow', 'purple', 'orange']
            test_img = Image.new('RGB', (200, 200), color=colors[i])
            test_img.save(test_image_path)
            
            logger.info(f"  📸 分析第 {i+1} 张图像: {colors[i]} 色块")
            
            # 分析图像
            result = tester.analyze_image(str(test_image_path))
            test_results.append(result)
            
            if result.get('success'):
                data = result.get('data', {})
                logger.info(f"    - 控制执行: {data.get('control_executed', False)}")
                if data.get('conversation_summary'):
                    conv_summary = data['conversation_summary']
                    logger.info(f"    - 当前对话轮数: {conv_summary.get('conversation_rounds', 0)}")
                    logger.info(f"    - 当前消息数: {conv_summary.get('total_messages', 0)}")
            
            # 稍微延迟，避免请求过快
            time.sleep(1)
        
        # 4. 检查最终对话历史
        logger.info("\n📋 步骤4: 检查最终对话历史")
        history = tester.get_conversation_history()
        if history.get('success'):
            data = history.get('data', {})
            conv_summary = data.get('conversation_summary', {})
            full_history = data.get('full_history', [])
            
            logger.info(f"  📊 对话统计:")
            logger.info(f"    - 总轮数: {conv_summary.get('conversation_rounds', 0)}")
            logger.info(f"    - 总消息数: {conv_summary.get('total_messages', 0)}")
            logger.info(f"    - 最大轮数限制: {conv_summary.get('max_rounds', 0)}")
            
            logger.info(f"  📝 对话历史详情:")
            for i, msg in enumerate(full_history):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:100]  # 只显示前100个字符
                logger.info(f"    {i+1}. [{role}] {content}...")
            
            # 验证历史记录是否符合预期
            expected_max_messages = conv_summary.get('max_rounds', 4) * 2
            actual_messages = len(full_history)
            
            if actual_messages <= expected_max_messages:
                logger.info(f"✅ 对话历史长度控制正常: {actual_messages} <= {expected_max_messages}")
            else:
                logger.error(f"❌ 对话历史长度超出限制: {actual_messages} > {expected_max_messages}")
                return False
        
        # 5. 测试清空功能
        logger.info("\n🗑️ 步骤5: 测试清空对话历史")
        if tester.clear_conversation_history():
            logger.info("✅ 对话历史清空成功")
            
            # 验证清空效果
            summary = tester.get_conversation_summary()
            if summary.get('success'):
                data = summary.get('data', {})
                if data.get('total_messages', 0) == 0:
                    logger.info("✅ 对话历史确实已清空")
                else:
                    logger.error(f"❌ 对话历史未完全清空，还有 {data.get('total_messages', 0)} 条消息")
                    return False
        
        logger.info("\n🎉 对话历史功能测试完成！")
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试过程中出现异常: {e}")
        return False

def main():
    """主函数"""
    logger.info("🚀 开始MCP对话历史功能测试")
    
    success = test_conversation_history_functionality()
    
    logger.info("\n" + "="*60)
    logger.info("测试总结")
    logger.info("="*60)
    
    if success:
        logger.info("🎉 所有测试通过！MCP对话历史功能正常工作")
        logger.info("💡 功能说明:")
        logger.info("   - 维护最近4轮对话历史")
        logger.info("   - AI分析作为assistant消息")
        logger.info("   - 控制结果作为user消息")
        logger.info("   - 自动清理超出限制的历史记录")
        logger.info("   - 支持手动清空对话历史")
    else:
        logger.error("❌ 部分测试失败，请检查日志")

if __name__ == "__main__":
    main() 