"""
ValueCell Configuration Manager
管理 LLM 模型配置，优先复用现有 API Key
"""

import os
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """模型配置"""
    provider: str
    model_id: str
    api_key: str
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class ValueCellConfig:
    """ValueCell 整体配置"""
    
    # 默认模型配置
    default_model: ModelConfig = field(default_factory=lambda: ModelConfig(
        provider="deepseek",
        model_id="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    ))
    
    # Agent 特定配置
    research_agent_model: Optional[ModelConfig] = None
    news_agent_model: Optional[ModelConfig] = None
    
    # SEC 邮箱 (用于 EDGAR API)
    sec_email: str = field(default_factory=lambda: os.getenv("SEC_EMAIL", ""))
    
    # 功能开关
    enable_research: bool = True
    enable_news: bool = True
    
    def __post_init__(self):
        """初始化后处理，设置默认 Agent 模型"""
        if self.research_agent_model is None:
            self.research_agent_model = self._get_best_model_for("research")
        if self.news_agent_model is None:
            self.news_agent_model = self._get_best_model_for("news")
    
    def _get_best_model_for(self, agent_type: str) -> ModelConfig:
        """根据可用 API Key 选择最佳模型 (DeepSeek > OpenAI/GPT > Gemini > Kimi > Qwen > OpenRouter)"""
        if os.getenv("DEEPSEEK_API_KEY"):
            return ModelConfig(
                provider="deepseek",
                model_id=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            )

        if os.getenv("OPENAI_API_KEY"):
            return ModelConfig(
                provider="openai",
                model_id=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                api_key=os.getenv("OPENAI_API_KEY", ""),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            )

        gemini_keys = os.getenv("GEMINI_API_KEY", "")
        if gemini_keys:
            first_key = gemini_keys.split(",")[0].strip()
            return ModelConfig(
                provider="gemini",
                model_id=os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip(),
                api_key=first_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )

        if os.getenv("KIMI_API_KEY"):
            return ModelConfig(
                provider="kimi",
                model_id=os.getenv("KIMI_MODEL", "moonshot-v1-8k"),
                api_key=os.getenv("KIMI_API_KEY", ""),
                base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
            )

        if os.getenv("QWEN_API_KEY"):
            return ModelConfig(
                provider="qwen",
                model_id=os.getenv("QWEN_MODEL", "qwen-plus"),
                api_key=os.getenv("QWEN_API_KEY", ""),
                base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            )

        if os.getenv("OPENROUTER_API_KEY"):
            return ModelConfig(
                provider="openrouter",
                model_id="anthropic/claude-haiku-4.5",
                api_key=os.getenv("OPENROUTER_API_KEY", ""),
                base_url="https://openrouter.ai/api/v1"
            )

        # 回退到默认配置
        logger.warning(f"⚠️ 未找到可用的 API Key，{agent_type} agent 将无法正常工作")
        return self.default_model


# 全局配置实例
_config: Optional[ValueCellConfig] = None


def get_config() -> ValueCellConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = ValueCellConfig()
    return _config


def get_model_config(agent_name: str) -> ModelConfig:
    """获取指定 Agent 的模型配置"""
    config = get_config()
    
    if agent_name == "research_agent":
        return config.research_agent_model
    elif agent_name == "news_agent":
        return config.news_agent_model
    else:
        return config.default_model


def create_openai_client(model_config: ModelConfig):
    """创建 OpenAI 兼容客户端"""
    try:
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=model_config.api_key,
            base_url=model_config.base_url
        )
    except ImportError:
        logger.error("openai 库未安装")
        return None
