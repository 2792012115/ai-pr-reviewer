"""
AI PR Review 助手 - 配置模块
============================
集中管理所有配置项，支持环境变量覆盖。
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppConfig:
    """应用全局配置"""

    # ---- GitHub ----
    github_token: str = field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN", "")
    )
    github_api_base: str = "https://api.github.com"

    # ---- AI / LLM ----
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o")
    )
    openai_base_url: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL", None)
    )
    # 温度参数：评审场景需要稳定可复现，使用较低温度
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    llm_timeout: int = 120  # 秒

    # ---- 评审策略 ----
    max_diff_lines: int = 2000          # 单次评审最大 diff 行数
    max_files_per_review: int = 20      # 单次评审最多文件数
    include_file_context: bool = True    # 是否附带完整文件上下文

    # ---- 服务 ----
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ---- 缓存 ----
    cache_ttl: int = 300  # PR 数据缓存 5 分钟


# 全局单例
config = AppConfig()
