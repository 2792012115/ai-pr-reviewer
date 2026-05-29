"""
AI PR Review 助手 - 数据模型
============================
定义所有 API 请求/响应与内部数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举类型
# ============================================================

class RiskLevel(str, Enum):
    """风险等级"""
    CRITICAL = "critical"   # 严重：可能导致崩溃/安全漏洞
    HIGH = "high"           # 高：逻辑错误/性能问题
    MEDIUM = "medium"       # 中：代码规范/可维护性
    LOW = "low"             # 低：建议性改进
    INFO = "info"           # 信息：备注/提示


class ReviewStatus(str, Enum):
    """评审状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================
# 请求模型 (Pydantic, FastAPI 原生支持)
# ============================================================

class ReviewRequest(BaseModel):
    """评审请求"""
    pr_url: str = Field(..., description="GitHub PR URL")
    include_file_context: bool = Field(True, description="是否附带文件上下文")
    focus_areas: list[str] = Field(default_factory=list, description="关注领域")
    post_comment: bool = Field(False, description="是否将评审报告发布为 PR Comment")


# ============================================================
# GitHub 数据模型
# ============================================================

@dataclass
class PRMetadata:
    """PR 元信息"""
    owner: str
    repo: str
    pr_number: int
    title: str
    description: str = ""
    author: str = ""
    base_branch: str = ""
    head_branch: str = ""
    html_url: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class FileChange:
    """单个文件的变更"""
    filename: str
    status: str              # added / modified / removed / renamed
    patch: str = ""          # unified diff 内容
    additions: int = 0
    deletions: int = 0
    previous_filename: Optional[str] = None  # 重命名场景


@dataclass
class PRData:
    """完整的 PR 数据"""
    metadata: PRMetadata
    files: list[FileChange] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    total_files: int = 0


# ============================================================
# 评审结果模型
# ============================================================

@dataclass
class ReviewIssue:
    """单个评审问题/建议"""
    file: str
    line_range: str          # 例如 "L42-L48"
    risk_level: RiskLevel
    category: str            # security / performance / bug / style / logic
    title: str               # 简短标题
    description: str         # 详细描述
    suggestion: str = ""     # 修改建议
    code_snippet: str = ""   # 相关代码片段


@dataclass
class FileReview:
    """单文件评审结果"""
    filename: str
    summary: str
    issues: list[ReviewIssue] = field(default_factory=list)
    risk_score: float = 0.0  # 0-10 风险评分


@dataclass
class PRSummary:
    """PR 整体摘要"""
    title: str
    one_line_summary: str     # 一句话总结
    detailed_summary: str     # 详细摘要
    changed_files: list[str] = field(default_factory=list)
    key_changes: list[str] = field(default_factory=list)


@dataclass
class ReviewResult:
    """完整评审结果"""
    status: ReviewStatus
    pr_summary: Optional[PRSummary] = None
    file_reviews: list[FileReview] = field(default_factory=list)
    overall_risk_score: float = 0.0
    overall_assessment: str = ""          # 整体评价
    recommendations: list[str] = field(default_factory=list)  # 全局建议
    model_used: str = ""
    analysis_time_ms: int = 0
    error_message: str = ""
