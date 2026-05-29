"""
AI PR Review 助手 - 测试套件
============================
"""

import sys
import os

# 确保 backend 目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
import asyncio

from models import (
    PRMetadata, FileChange, PRData, ReviewRequest,
    ReviewIssue, RiskLevel, FileReview, ReviewResult, ReviewStatus, PRSummary,
)
from github_client import GitHubClient, PRReference
from config import AppConfig


# ============================================================
# 模型测试
# ============================================================

class TestModels:
    """数据模型单元测试"""

    def test_pr_reference_creation(self):
        ref = PRReference(owner="test", repo="demo", pr_number=42)
        assert ref.owner == "test"
        assert ref.repo == "demo"
        assert ref.pr_number == 42

    def test_file_change_defaults(self):
        fc = FileChange(filename="src/main.py", status="modified")
        assert fc.filename == "src/main.py"
        assert fc.status == "modified"
        assert fc.patch == ""

    def test_pr_data_aggregation(self):
        files = [
            FileChange("a.py", "modified", additions=10, deletions=3),
            FileChange("b.py", "added", additions=25, deletions=0),
        ]
        pr = PRData(
            metadata=PRMetadata(owner="x", repo="y", pr_number=1, title="Test"),
            files=files,
            total_additions=35,
            total_deletions=3,
            total_files=2,
        )
        assert pr.total_files == 2
        assert pr.total_additions == 35

    def test_review_result_serialization(self):
        result = ReviewResult(
            status=ReviewStatus.COMPLETED,
            pr_summary=PRSummary(
                title="Test PR",
                one_line_summary="测试 PR",
                detailed_summary="这是一个测试",
            ),
            overall_risk_score=3.5,
            overall_assessment="代码质量良好",
            model_used="gpt-4o",
            analysis_time_ms=1500,
        )
        assert result.status == ReviewStatus.COMPLETED
        assert result.overall_risk_score == 3.5


# ============================================================
# GitHub Client 测试
# ============================================================

class TestGitHubClient:
    """GitHub API 客户端测试"""

    def setup_method(self):
        self.config = AppConfig()
        self.client = GitHubClient(self.config)

    def test_parse_valid_pr_url(self):
        ref = self.client.parse_pr_url(
            "https://github.com/owner/repo/pull/123"
        )
        assert ref.owner == "owner"
        assert ref.repo == "repo"
        assert ref.pr_number == 123

    def test_parse_pr_url_with_trailing_slash(self):
        ref = self.client.parse_pr_url(
            "https://github.com/a/b/pull/99/"
        )
        assert ref.pr_number == 99

    def test_parse_pr_url_with_fragment(self):
        ref = self.client.parse_pr_url(
            "https://github.com/a/b/pull/99#issue-123"
        )
        assert ref.pr_number == 99

    def test_parse_invalid_url(self):
        with pytest.raises(ValueError):
            self.client.parse_pr_url("https://gitlab.com/x/y/merge_requests/1")

    def test_parse_non_github_url(self):
        with pytest.raises(ValueError):
            self.client.parse_pr_url("not-a-url")


# ============================================================
# 评审引擎测试（无需真实 API）
# ============================================================

class TestAIReviewerHelpers:
    """AI 评审器辅助方法测试"""

    def test_extract_json_from_markdown(self):
        from ai_reviewer import _extract_json
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_plain(self):
        from ai_reviewer import _extract_json
        text = '{"issues": [], "summary": "ok"}'
        result = _extract_json(text)
        assert result == {"issues": [], "summary": "ok"}

    def test_extract_json_with_extra_text(self):
        from ai_reviewer import _extract_json
        text = 'Here is the result: {"score": 5} Thanks!'
        result = _extract_json(text)
        assert result == {"score": 5}

    def test_filter_binary_files(self):
        from ai_reviewer import AIReviewer
        config = AppConfig()
        reviewer = AIReviewer(config)
        files = [
            FileChange("main.py", "modified", patch="diff content"),
            FileChange("logo.png", "added"),
            FileChange("data.json", "modified", patch="json diff"),
            FileChange("deleted.py", "removed", patch="old code"),
        ]
        result = reviewer._filter_files(files)
        filenames = [f.filename for f in result]
        assert "main.py" in filenames
        assert "data.json" in filenames
        assert "logo.png" not in filenames
        assert "deleted.py" not in filenames


# ============================================================
# 报告生成器测试
# ============================================================

class TestReportGenerator:
    """报告生成器测试"""

    def setup_method(self):
        from report_generator import ReportGenerator
        self.generator = ReportGenerator()

    def test_markdown_basic(self):
        result = ReviewResult(
            status=ReviewStatus.COMPLETED,
            pr_summary=PRSummary(
                title="Test",
                one_line_summary="修复空指针",
                detailed_summary="修复了用户模块的空指针异常。",
                key_changes=["修复 NullPointerException"],
            ),
            overall_risk_score=2.0,
            overall_assessment="代码质量良好，建议合并。",
            model_used="gpt-4o",
            analysis_time_ms=500,
        )
        md = self.generator.to_markdown(result)
        assert "AI PR Review" in md
        assert "修复空指针" in md
        assert "2.0" in md

    def test_markdown_with_issues(self):
        from report_generator import ReportGenerator
        gen = ReportGenerator()
        result = ReviewResult(
            status=ReviewStatus.COMPLETED,
            file_reviews=[
                FileReview(
                    filename="app.py",
                    summary="简单修改",
                    issues=[
                        ReviewIssue(
                            file="app.py",
                            line_range="L10-L12",
                            risk_level=RiskLevel.HIGH,
                            category="security",
                            title="硬编码密钥",
                            description="API 密钥不应硬编码。",
                            suggestion="使用环境变量。",
                        )
                    ],
                    risk_score=7.0,
                )
            ],
            overall_risk_score=7.0,
        )
        md = gen.to_markdown(result)
        assert "硬编码密钥" in md
        assert "app.py" in md


# ============================================================
# 集成测试（需要 mock）
# ============================================================

@pytest.mark.asyncio
async def test_health_endpoint():
    """测试健康检查端点"""
    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "AI PR Review" in data["service"]


@pytest.mark.asyncio
async def test_review_invalid_url():
    """测试无效 PR URL"""
    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.post("/api/review", json={"pr_url": "not-a-url"})
    assert resp.status_code == 400
