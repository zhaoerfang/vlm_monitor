#!/usr/bin/env python3
"""
配置管理模块
提供API密钥获取、配置文件加载等功能
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def get_api_key() -> Optional[str]:
    """
    获取API密钥，按优先级从多个来源获取：
    1. 配置文件
    2. 环境变量
    3. 命令行参数
    
    Returns:
        API密钥字符串，如果未找到返回None
    """
    # 首先尝试从配置文件获取
    try:
        config = load_config()
        api_key = config.get('vlm', {}).get('api_key')
        if api_key:
            logger.info("✅ 从配置文件获取API密钥")
            return api_key
    except Exception as e:
        logger.warning(f"⚠️ 从配置文件读取API密钥失败: {str(e)}")
    
    # 从环境变量获取
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    if api_key:
        logger.info("✅ 从环境变量获取API密钥")
        return api_key
    
    # 从命令行参数获取
    if len(sys.argv) > 1:
        logger.info("✅ 从命令行参数获取API密钥")
        return sys.argv[1]
    
    # 没有找到API密钥
    logger.warning("❌ 未找到API密钥")
    return None

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径，如果为None则按优先级查找
        
    Returns:
        配置字典
    """
    if config_path is None:
        # 按优先级查找配置文件
        search_paths = [
            # 1. 当前工作目录
            Path.cwd() / "config.json",
            # 2. 项目根目录（从当前文件推断）
            Path(__file__).parent.parent.parent.parent / "config.json",
            # 3. 用户配置目录
            Path.home() / ".vlm_monitor" / "config.json",
            # 4. 系统配置目录
            Path("/etc/vlm_monitor/config.json")
        ]
        
        for path in search_paths:
            if path.exists():
                config_path = path
                logger.info(f"🔍 找到配置文件: {config_path}")
                break
        else:
            logger.warning("⚠️ 未找到配置文件，使用默认配置")
            return get_default_config()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"✅ 已加载配置文件: {config_path}")
        return config
    except FileNotFoundError:
        logger.warning(f"⚠️ 配置文件不存在: {config_path}，使用默认配置")
        return get_default_config()
    except Exception as e:
        logger.error(f"❌ 配置文件加载失败: {str(e)}，使用默认配置")
        return get_default_config()

def get_default_config() -> Dict[str, Any]:
    """
    获取默认配置
    
    Returns:
        默认配置字典
    """
    return {
        "video_processing": {
            "target_video_duration": 3.0,
            "frames_per_second": 5,
            "target_frames_per_video": 15
        },
        "rtsp": {
            "default_fps": 25.0,
            "auto_detect_fps": True,
            "client_buffer_size": 100,
            "connection_timeout": 60
        },
        "vlm": {
            "max_concurrent_inferences": 3,
            "model": "qwen-vl-max-latest"
        },
        "testing": {
            "n_frames_default": 50,
            "result_timeout": 180,
            "collection_timeout": 120
        }
    }

def save_config(config: Dict[str, Any], config_path: Optional[Path] = None) -> bool:
    """
    保存配置文件
    
    Args:
        config: 要保存的配置字典
        config_path: 配置文件路径，如果为None则使用默认路径
        
    Returns:
        是否保存成功
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent.parent / "config.json"
    
    try:
        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 配置文件已保存: {config_path}")
        return True
    except Exception as e:
        logger.error(f"❌ 配置文件保存失败: {str(e)}")
        return False

def validate_config(config: Dict[str, Any]) -> bool:
    """
    验证配置文件的有效性
    
    Args:
        config: 要验证的配置字典
        
    Returns:
        配置是否有效
    """
    required_sections = ['video_processing', 'rtsp', 'vlm', 'testing']
    
    for section in required_sections:
        if section not in config:
            logger.error(f"❌ 配置缺少必需的节: {section}")
            return False
    
    # 验证数值范围
    try:
        video_config = config['video_processing']
        if video_config['target_video_duration'] <= 0:
            logger.error("❌ target_video_duration 必须大于0")
            return False
        if video_config['frames_per_second'] <= 0:
            logger.error("❌ frames_per_second 必须大于0")
            return False
            
        rtsp_config = config['rtsp']
        if rtsp_config['default_fps'] <= 0:
            logger.error("❌ default_fps 必须大于0")
            return False
            
        vlm_config = config['vlm']
        if vlm_config['max_concurrent_inferences'] <= 0:
            logger.error("❌ max_concurrent_inferences 必须大于0")
            return False
            
        logger.info("✅ 配置验证通过")
        return True
        
    except KeyError as e:
        logger.error(f"❌ 配置缺少必需的键: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 配置验证失败: {str(e)}")
        return False

def get_config_with_validation(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    加载并验证配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        验证后的配置字典
    """
    config = load_config(config_path)
    
    if not validate_config(config):
        logger.warning("⚠️ 配置验证失败，使用默认配置")
        config = get_default_config()
    
    return config 