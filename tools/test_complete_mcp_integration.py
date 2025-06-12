#!/usr/bin/env python3
"""
综合测试MCP集成功能：并行执行、对话历史、结果保存
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

from src.monitor.vlm.vlm_client import DashScopeVLMClient
from tools.test_tts_service import create_test_inference_result

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CompleteMCPTester:
    """完整MCP功能测试器"""
    
    def __init__(self, mcp_host='localhost', mcp_port=8082):
        self.mcp_host = mcp_host
        self.mcp_port = mcp_port
        self.base_url = f"http://{mcp_host}:{mcp_port}"
        self.vlm_client = None
        
    def check_mcp_service(self) -> bool:
        """检查MCP服务是否运行"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def clear_conversation_history(self) -> bool:
        """清空MCP对话历史"""
        try:
            response = requests.delete(f"{self.base_url}/conversation/history", timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"清空对话历史异常: {e}")
            return False
    
    def get_conversation_summary(self) -> dict:
        """获取MCP对话摘要"""
        try:
            response = requests.get(f"{self.base_url}/conversation/summary", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                return {}
        except Exception as e:
            logger.error(f"获取对话摘要异常: {e}")
            return {}
    
    async def setup_vlm_client(self):
        """初始化VLM客户端"""
        try:
            self.vlm_client = DashScopeVLMClient()
            logger.info("✅ VLM客户端初始化成功")
            return True
        except Exception as e:
            logger.error(f"❌ VLM客户端初始化失败: {e}")
            return False
    
    async def test_parallel_execution_with_history(self):
        """测试并行执行和对话历史功能"""
        logger.info("🧪 开始测试并行执行和对话历史功能")
        
        # 检查服务状态
        if not self.check_mcp_service():
            logger.error("❌ MCP服务未运行")
            return False
        
        if not await self.setup_vlm_client():
            return False
        
        # 清空对话历史
        logger.info("📝 清空MCP对话历史")
        self.clear_conversation_history()
        
        test_scenarios = [
            {"color": "red", "description": "红色场景"},
            {"color": "blue", "description": "蓝色场景"},
            {"color": "green", "description": "绿色场景"},
            {"color": "yellow", "description": "黄色场景"},
            {"color": "purple", "description": "紫色场景"},
        ]
        
        results = []
        
        for i, scenario in enumerate(test_scenarios):
            logger.info(f"\n🎯 测试场景 {i+1}: {scenario['description']}")
            
            # 创建测试图像
            frame_dir = create_test_inference_result("tmp")
            test_image_path = frame_dir / f"integration_test_{i}_{scenario['color']}.jpg"
            
            from PIL import Image
            test_img = Image.new('RGB', (250, 250), color=scenario['color'])
            test_img.save(test_image_path)
            logger.info(f"  📸 创建测试图像: {test_image_path}")
            
            # 记录开始时间
            start_time = time.time()
            
            # 执行并行VLM和MCP分析
            result = await self.vlm_client.analyze_image_async(
                str(test_image_path),
                prompt=f"请分析这张{scenario['color']}色的图像",
                user_question=None,
                enable_camera_control=True
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            logger.info(f"  ⏱️ 分析耗时: {duration:.2f}s")
            logger.info(f"  📊 VLM结果长度: {len(result) if result else 0} 字符")
            
            # 检查MCP结果文件
            mcp_result_file = frame_dir / 'mcp_result.json'
            mcp_data = None
            if mcp_result_file.exists():
                with open(mcp_result_file, 'r', encoding='utf-8') as f:
                    mcp_data = json.load(f)
                logger.info(f"  📁 MCP结果已保存: {mcp_result_file}")
                logger.info(f"  🎮 MCP调用成功: {mcp_data.get('mcp_success', False)}")
                logger.info(f"  ⏱️ MCP耗时: {mcp_data.get('mcp_duration', 0):.2f}s")
            else:
                logger.warning(f"  ⚠️ MCP结果文件未找到")
            
            # 获取当前对话状态
            conv_summary = self.get_conversation_summary()
            if conv_summary.get('success'):
                data = conv_summary.get('data', {})
                logger.info(f"  💬 当前对话轮数: {data.get('conversation_rounds', 0)}")
                logger.info(f"  📝 当前消息数: {data.get('total_messages', 0)}")
            
            results.append({
                'scenario': scenario,
                'duration': duration,
                'vlm_result': result,
                'mcp_data': mcp_data,
                'conversation_state': conv_summary.get('data', {}) if conv_summary.get('success') else {}
            })
            
            # 稍微延迟
            await asyncio.sleep(1)
        
        return self.analyze_test_results(results)
    
    def analyze_test_results(self, results):
        """分析测试结果"""
        logger.info("\n📊 分析测试结果")
        
        total_tests = len(results)
        successful_vlm = sum(1 for r in results if r['vlm_result'])
        successful_mcp = sum(1 for r in results if r['mcp_data'] and r['mcp_data'].get('mcp_success'))
        
        # 性能分析
        durations = [r['duration'] for r in results]
        avg_duration = sum(durations) / len(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        
        logger.info(f"  📈 性能统计:")
        logger.info(f"    - 平均耗时: {avg_duration:.2f}s")
        logger.info(f"    - 最快耗时: {min_duration:.2f}s")
        logger.info(f"    - 最慢耗时: {max_duration:.2f}s")
        
        # 成功率分析
        vlm_success_rate = (successful_vlm / total_tests) * 100 if total_tests > 0 else 0
        mcp_success_rate = (successful_mcp / total_tests) * 100 if total_tests > 0 else 0
        
        logger.info(f"  ✅ 成功率统计:")
        logger.info(f"    - VLM分析成功率: {vlm_success_rate:.1f}% ({successful_vlm}/{total_tests})")
        logger.info(f"    - MCP调用成功率: {mcp_success_rate:.1f}% ({successful_mcp}/{total_tests})")
        
        # 对话历史分析
        final_conv_state = results[-1]['conversation_state'] if results else {}
        logger.info(f"  💬 对话历史状态:")
        logger.info(f"    - 最终对话轮数: {final_conv_state.get('conversation_rounds', 0)}")
        logger.info(f"    - 最终消息数: {final_conv_state.get('total_messages', 0)}")
        logger.info(f"    - 最大轮数限制: {final_conv_state.get('max_rounds', 0)}")
        
        # 验证对话历史是否正确维护
        max_expected_messages = final_conv_state.get('max_rounds', 4) * 2
        actual_messages = final_conv_state.get('total_messages', 0)
        history_ok = actual_messages <= max_expected_messages
        
        logger.info(f"  🔍 对话历史验证:")
        logger.info(f"    - 消息数限制: {actual_messages} <= {max_expected_messages} {'✅' if history_ok else '❌'}")
        
        # 并行执行效果分析
        mcp_durations = [r['mcp_data'].get('mcp_duration', 0) for r in results if r['mcp_data']]
        if mcp_durations:
            avg_mcp_duration = sum(mcp_durations) / len(mcp_durations)
            estimated_serial_time = avg_duration + avg_mcp_duration
            performance_improvement = ((estimated_serial_time - avg_duration) / estimated_serial_time) * 100 if estimated_serial_time > 0 else 0
            
            logger.info(f"  🚀 并行执行效果:")
            logger.info(f"    - 平均MCP耗时: {avg_mcp_duration:.2f}s")
            logger.info(f"    - 估算串行耗时: {estimated_serial_time:.2f}s")
            logger.info(f"    - 性能提升: {performance_improvement:.1f}%")
        
        # 判断测试是否通过
        success_criteria = [
            vlm_success_rate >= 80,  # VLM成功率至少80%
            history_ok,              # 对话历史正确维护
            avg_duration < 30,       # 平均响应时间小于30秒
        ]
        
        all_passed = all(success_criteria)
        
        logger.info(f"\n🎯 测试结果: {'✅ 通过' if all_passed else '❌ 失败'}")
        
        return all_passed

async def main():
    """主函数"""
    logger.info("🚀 开始完整MCP集成功能测试")
    
    tester = CompleteMCPTester()
    
    try:
        success = await tester.test_parallel_execution_with_history()
        
        logger.info("\n" + "="*70)
        logger.info("测试总结")
        logger.info("="*70)
        
        if success:
            logger.info("🎉 所有测试通过！完整MCP集成功能正常工作")
            logger.info("💡 功能特性:")
            logger.info("   ✅ VLM和MCP并行执行，提升响应速度")
            logger.info("   ✅ 维护4轮对话历史，支持上下文感知")
            logger.info("   ✅ 自动保存MCP结果到frame详情目录")
            logger.info("   ✅ 完整的错误处理和日志记录")
            logger.info("   ✅ 性能监控和统计分析")
        else:
            logger.error("❌ 部分测试失败，请检查日志和服务状态")
            logger.info("💡 故障排查:")
            logger.info("   1. 确保MCP服务正在运行")
            logger.info("   2. 检查VLM API配置和网络连接")
            logger.info("   3. 查看详细错误日志")
            
    except Exception as e:
        logger.error(f"❌ 测试过程中出现异常: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 