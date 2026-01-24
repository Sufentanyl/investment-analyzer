"""
ValueCell Bridge Module
轻量级适配器，将 ValueCell 多智能体功能集成到 investment-analyzer

主要组件:
- config: 模型和 Agent 配置管理
- research_adapter: 深度研究代理适配器
- news_adapter: 智能新闻代理适配器
- utils: 工具函数（重试、多数据源、LLM 降级）
"""

from .config import ValueCellConfig, get_model_config
from .research_adapter import ResearchAdapter
from .news_adapter import NewsAdapter
from .utils import async_retry, AShareDataSource, LLMFallback

__all__ = [
    'ValueCellConfig',
    'get_model_config',
    'ResearchAdapter',
    'NewsAdapter',
    'async_retry',
    'AShareDataSource',
    'LLMFallback',
]
