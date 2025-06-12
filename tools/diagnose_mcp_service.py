#!/usr/bin/env python3
"""
MCP推理服务诊断工具
检查服务状态、连接性和响应时间
"""

import os
import sys
import json
import time
import requests
import logging
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MCPServiceDiagnostic:
    """MCP服务诊断器"""
    
    def __init__(self, config_path=None):
        """初始化诊断器"""
        self.config_path = config_path or "config.json"
        self.config = self.load_config()
        
        # 从配置文件获取服务地址
        inference_config = self.config.get('camera_inference_service', {})
        self.host = inference_config.get('host', '0.0.0.0')
        self.port = inference_config.get('port', 8082)
        
        # 构建不同的URL进行测试
        self.test_urls = {
            'localhost': f"http://localhost:{self.port}",
            'config_host': f"http://{self.host}:{self.port}",
            '127.0.0.1': f"http://127.0.0.1:{self.port}"
        }
        
        logger.info(f"📋 配置信息:")
        logger.info(f"  - 配置文件: {self.config_path}")
        logger.info(f"  - 配置中的host: {self.host}")
        logger.info(f"  - 配置中的port: {self.port}")
        
    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ 无法加载配置文件 {self.config_path}: {e}")
            return {}
    
    def test_basic_connectivity(self):
        """测试基本连接性"""
        logger.info("\n🔍 测试基本连接性...")
        
        results = {}
        
        for name, base_url in self.test_urls.items():
            logger.info(f"\n📡 测试 {name}: {base_url}")
            
            # 测试根路径
            try:
                start_time = time.time()
                response = requests.get(f"{base_url}/", timeout=5)
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    logger.info(f"  ✅ 根路径可访问 - 状态码: {response.status_code}, 耗时: {duration:.2f}s")
                    results[name] = {'root': True, 'root_time': duration}
                else:
                    logger.warning(f"  ⚠️ 根路径响应异常 - 状态码: {response.status_code}")
                    results[name] = {'root': False, 'root_error': f"HTTP {response.status_code}"}
                    
            except requests.exceptions.ConnectRefused:
                logger.error(f"  ❌ 连接被拒绝 - 服务可能未启动")
                results[name] = {'root': False, 'root_error': 'Connection refused'}
            except requests.exceptions.Timeout:
                logger.error(f"  ❌ 连接超时")
                results[name] = {'root': False, 'root_error': 'Timeout'}
            except Exception as e:
                logger.error(f"  ❌ 连接异常: {e}")
                results[name] = {'root': False, 'root_error': str(e)}
        
        return results
    
    def test_health_endpoint(self):
        """测试健康检查端点"""
        logger.info("\n🏥 测试健康检查端点...")
        
        results = {}
        
        for name, base_url in self.test_urls.items():
            logger.info(f"\n📊 测试 {name} 健康检查: {base_url}/health")
            
            try:
                start_time = time.time()
                response = requests.get(f"{base_url}/health", timeout=10)
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"  ✅ 健康检查通过 - 耗时: {duration:.2f}s")
                    logger.info(f"  📋 响应数据: {data}")
                    results[name] = {'health': True, 'health_time': duration, 'health_data': data}
                else:
                    logger.warning(f"  ⚠️ 健康检查失败 - 状态码: {response.status_code}")
                    logger.warning(f"  📄 响应内容: {response.text}")
                    results[name] = {'health': False, 'health_error': f"HTTP {response.status_code}"}
                    
            except Exception as e:
                logger.error(f"  ❌ 健康检查异常: {e}")
                results[name] = {'health': False, 'health_error': str(e)}
        
        return results
    
    def test_analyze_endpoint(self):
        """测试分析端点（使用虚拟图像路径）"""
        logger.info("\n🖼️ 测试分析端点...")
        
        # 创建一个测试图像
        test_image_path = self.create_test_image()
        if not test_image_path:
            logger.error("❌ 无法创建测试图像")
            return {}
        
        results = {}
        
        for name, base_url in self.test_urls.items():
            logger.info(f"\n🔬 测试 {name} 分析端点: {base_url}/analyze")
            
            try:
                start_time = time.time()
                
                # 构建请求数据
                request_data = {"image_path": str(test_image_path)}
                
                # 发送请求，使用较长的超时时间
                response = requests.post(
                    f"{base_url}/analyze", 
                    json=request_data, 
                    timeout=60  # 增加超时时间到60秒
                )
                
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"  ✅ 分析请求成功 - 耗时: {duration:.2f}s")
                    logger.info(f"  📊 响应状态: {data.get('success', False)}")
                    
                    if data.get('data'):
                        analysis_data = data['data']
                        logger.info(f"  🎮 控制执行: {analysis_data.get('control_executed', False)}")
                        if analysis_data.get('conversation_summary'):
                            conv = analysis_data['conversation_summary']
                            logger.info(f"  💬 对话状态: {conv.get('conversation_rounds', 0)} 轮")
                    
                    results[name] = {
                        'analyze': True, 
                        'analyze_time': duration, 
                        'analyze_data': data
                    }
                else:
                    logger.warning(f"  ⚠️ 分析请求失败 - 状态码: {response.status_code}")
                    logger.warning(f"  📄 响应内容: {response.text[:500]}...")
                    results[name] = {
                        'analyze': False, 
                        'analyze_error': f"HTTP {response.status_code}",
                        'analyze_time': duration
                    }
                    
            except requests.exceptions.Timeout:
                duration = time.time() - start_time
                logger.error(f"  ❌ 分析请求超时 - 耗时: {duration:.2f}s")
                results[name] = {
                    'analyze': False, 
                    'analyze_error': 'Timeout',
                    'analyze_time': duration
                }
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"  ❌ 分析请求异常: {e}")
                results[name] = {
                    'analyze': False, 
                    'analyze_error': str(e),
                    'analyze_time': duration
                }
        
        # 清理测试图像
        try:
            os.remove(test_image_path)
        except:
            pass
        
        return results
    
    def create_test_image(self):
        """创建测试图像"""
        try:
            from PIL import Image
            
            # 创建一个简单的测试图像
            test_img = Image.new('RGB', (100, 100), color='blue')
            test_image_path = Path("tmp") / "mcp_diagnostic_test.jpg"
            
            # 确保目录存在
            test_image_path.parent.mkdir(exist_ok=True)
            
            test_img.save(test_image_path)
            logger.info(f"📸 创建测试图像: {test_image_path}")
            return test_image_path
            
        except Exception as e:
            logger.error(f"❌ 创建测试图像失败: {e}")
            return None
    
    def check_service_process(self):
        """检查MCP服务进程"""
        logger.info("\n🔍 检查MCP服务进程...")
        
        try:
            import subprocess
            
            # 查找MCP相关进程
            result = subprocess.run(
                ['ps', 'aux'], 
                capture_output=True, 
                text=True
            )
            
            mcp_processes = []
            for line in result.stdout.split('\n'):
                if 'camera_inference_service' in line or 'mcp' in line.lower():
                    mcp_processes.append(line.strip())
            
            if mcp_processes:
                logger.info(f"  ✅ 找到 {len(mcp_processes)} 个相关进程:")
                for i, process in enumerate(mcp_processes, 1):
                    logger.info(f"    {i}. {process}")
            else:
                logger.warning("  ⚠️ 未找到MCP相关进程")
                
            return mcp_processes
            
        except Exception as e:
            logger.error(f"  ❌ 检查进程失败: {e}")
            return []
    
    def run_full_diagnostic(self):
        """运行完整诊断"""
        logger.info("🚀 开始MCP服务完整诊断")
        logger.info("=" * 60)
        
        # 1. 检查进程
        processes = self.check_service_process()
        
        # 2. 测试基本连接
        connectivity_results = self.test_basic_connectivity()
        
        # 3. 测试健康检查
        health_results = self.test_health_endpoint()
        
        # 4. 测试分析端点
        analyze_results = self.test_analyze_endpoint()
        
        # 5. 生成诊断报告
        self.generate_diagnostic_report(
            processes, 
            connectivity_results, 
            health_results, 
            analyze_results
        )
    
    def generate_diagnostic_report(self, processes, connectivity, health, analyze):
        """生成诊断报告"""
        logger.info("\n📋 诊断报告")
        logger.info("=" * 60)
        
        # 进程状态
        logger.info(f"🔍 进程状态: {'✅ 运行中' if processes else '❌ 未找到'}")
        
        # 连接性测试结果
        logger.info("\n📡 连接性测试结果:")
        for name, result in connectivity.items():
            status = "✅ 成功" if result.get('root') else "❌ 失败"
            error = f" ({result.get('root_error', '')})" if not result.get('root') else ""
            time_info = f" - {result.get('root_time', 0):.2f}s" if result.get('root_time') else ""
            logger.info(f"  {name}: {status}{error}{time_info}")
        
        # 健康检查结果
        logger.info("\n🏥 健康检查结果:")
        for name, result in health.items():
            status = "✅ 健康" if result.get('health') else "❌ 异常"
            error = f" ({result.get('health_error', '')})" if not result.get('health') else ""
            time_info = f" - {result.get('health_time', 0):.2f}s" if result.get('health_time') else ""
            logger.info(f"  {name}: {status}{error}{time_info}")
        
        # 分析端点结果
        logger.info("\n🔬 分析端点结果:")
        for name, result in analyze.items():
            status = "✅ 正常" if result.get('analyze') else "❌ 异常"
            error = f" ({result.get('analyze_error', '')})" if not result.get('analyze') else ""
            time_info = f" - {result.get('analyze_time', 0):.2f}s" if result.get('analyze_time') else ""
            logger.info(f"  {name}: {status}{error}{time_info}")
        
        # 推荐方案
        logger.info("\n💡 推荐方案:")
        
        # 找到最佳可用的URL
        best_url = None
        for name in ['localhost', '127.0.0.1', 'config_host']:
            if (connectivity.get(name, {}).get('root') and 
                health.get(name, {}).get('health')):
                best_url = name
                break
        
        if best_url:
            logger.info(f"  ✅ 推荐使用: {best_url} ({self.test_urls[best_url]})")
        else:
            logger.error("  ❌ 所有URL都不可用，请检查服务状态")
        
        # 性能建议
        analyze_times = [r.get('analyze_time', 0) for r in analyze.values() if r.get('analyze')]
        if analyze_times:
            avg_time = sum(analyze_times) / len(analyze_times)
            if avg_time > 30:
                logger.warning(f"  ⚠️ 分析响应较慢 (平均 {avg_time:.2f}s)，建议增加超时时间")
            else:
                logger.info(f"  ✅ 分析响应正常 (平均 {avg_time:.2f}s)")

def main():
    """主函数"""
    diagnostic = MCPServiceDiagnostic()
    diagnostic.run_full_diagnostic()

if __name__ == "__main__":
    main() 