"""
AI PR Review 助手 - GitHub API 客户端
=====================================
负责与 GitHub REST API 交互，获取 PR 元数据、文件变更和 diff。
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from config import AppConfig
from models import PRMetadata, FileChange, PRData

logger = logging.getLogger(__name__)


# ============================================================
# PR 引用（解析后的 URL 信息）
# ============================================================

@dataclass
class PRReference:
    """从 PR URL 解析出的仓库与 PR 编号"""
    owner: str
    repo: str
    pr_number: int


# ============================================================
# GitHub Client
# ============================================================

class GitHubClient:
    """
    GitHub REST API 客户端。
    
    功能：
    - 解析 PR URL → owner/repo/number
    - 获取 PR 元信息（标题、描述、作者等）
    - 获取 PR 文件变更列表（含 unified diff）
    
    使用方式：
        client = GitHubClient(config)
        pr_ref = client.parse_pr_url("https://github.com/owner/repo/pull/123")
        pr_data = await client.fetch_pr_data(pr_ref)
    """

    # GitHub PR URL 正则：支持 https://github.com/{owner}/{repo}/pull/{number}
    PR_URL_PATTERN = re.compile(
        r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?.*$"
    )

    def __init__(self, config: AppConfig):
        self.config = config
        self.base_url = config.github_api_base
        self.token = config.github_token

    # ---- URL 解析 ----

    def parse_pr_url(self, pr_url: str) -> PRReference:
        """
        解析 GitHub PR URL，提取 owner/repo/number。
        
        示例：
            "https://github.com/owner/repo/pull/123" 
            → PRReference(owner="owner", repo="repo", pr_number=123)
        
        Raises:
            ValueError: URL 格式不合法
        """
        pr_url = pr_url.strip().rstrip("/")
        match = self.PR_URL_PATTERN.match(pr_url)
        if not match:
            raise ValueError(
                f"无效的 GitHub PR URL: {pr_url}\n"
                f"期望格式: https://github.com/{{owner}}/{{repo}}/pull/{{number}}"
            )
        return PRReference(
            owner=match.group(1),
            repo=match.group(2),
            pr_number=int(match.group(3)),
        )

    # ---- 数据获取 ----

    async def fetch_pr_data(self, pr_ref: PRReference) -> PRData:
        """
        获取完整 PR 数据：元信息 + 文件变更列表。
        
        分两步：
        1. GET /repos/{owner}/{repo}/pulls/{number}  → 元信息
        2. GET /repos/{owner}/{repo}/pulls/{number}/files → 文件列表
        
        第二步使用 media type 参数获取 diff。
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = self._build_headers()

            # 1. 获取 PR 元信息
            pr_url = (
                f"{self.base_url}/repos/{pr_ref.owner}/{pr_ref.repo}"
                f"/pulls/{pr_ref.pr_number}"
            )
            resp = await client.get(pr_url, headers=headers)
            resp.raise_for_status()
            pr_json = resp.json()

            metadata = PRMetadata(
                owner=pr_ref.owner,
                repo=pr_ref.repo,
                pr_number=pr_ref.pr_number,
                title=pr_json.get("title", ""),
                description=pr_json.get("body", "") or "",
                author=pr_json.get("user", {}).get("login", ""),
                base_branch=pr_json.get("base", {}).get("ref", ""),
                head_branch=pr_json.get("head", {}).get("ref", ""),
                html_url=pr_json.get("html_url", ""),
                created_at=pr_json.get("created_at", ""),
                updated_at=pr_json.get("updated_at", ""),
            )

            # 2. 获取文件变更列表
            files_url = f"{pr_url}/files"
            files_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            resp = await client.get(files_url, headers=files_headers, params={"per_page": 100})
            resp.raise_for_status()
            files_json = resp.json()

            files = []
            total_add = total_del = 0
            for f in files_json:
                fc = FileChange(
                    filename=f.get("filename", ""),
                    status=f.get("status", "modified"),
                    patch=f.get("patch", ""),
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    previous_filename=f.get("previous_filename"),
                )
                files.append(fc)
                total_add += fc.additions
                total_del += fc.deletions

            return PRData(
                metadata=metadata,
                files=files,
                total_additions=total_add,
                total_deletions=total_del,
                total_files=len(files),
            )

    # ---- 辅助方法 ----

    def _build_headers(self) -> dict:
        """构建 HTTP 请求头"""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-PR-Reviewer/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    # ---- PR Comment 发布 ----

    async def post_review_comment(
        self, pr_ref: PRReference, markdown_body: str
    ) -> dict:
        """
        将评审报告作为 PR Comment 发布到 GitHub。
        
        使用 GitHub Issues API: POST /repos/{owner}/{repo}/issues/{number}/comments
        
        Returns:
            dict: 创建的 comment 信息，含 html_url
        Raises:
            ValueError: 未配置 GitHub Token
            httpx.HTTPStatusError: API 调用失败
        """
        if not self.token:
            raise ValueError(
                "发布 PR Comment 需要 GitHub Token。"
                "请在 .env 中设置 GITHUB_TOKEN。"
            )

        comment_url = (
            f"{self.base_url}/repos/{pr_ref.owner}/{pr_ref.repo}"
            f"/issues/{pr_ref.pr_number}/comments"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                comment_url,
                headers=self._build_headers(),
                json={"body": markdown_body},
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(
                f"已发布 PR Comment: {pr_ref.owner}/{pr_ref.repo}"
                f"#{pr_ref.pr_number} → {result.get('html_url', 'N/A')}"
            )
            return result

    async def post_review_comment_with_retry(
        self, pr_ref: PRReference, markdown_body: str, max_retries: int = 3
    ) -> dict:
        """
        带重试的 PR Comment 发布。
        
        遇到网络错误或 5xx 响应时自动重试，采用指数退避策略。
        """
        import asyncio

        last_error = None
        for attempt in range(max_retries):
            try:
                return await self.post_review_comment(pr_ref, markdown_body)
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    # 服务端错误，可重试
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        f"GitHub API 5xx 错误 (尝试 {attempt + 1}/{max_retries})，"
                        f"{wait}s 后重试..."
                    )
                    await asyncio.sleep(wait)
                else:
                    raise  # 4xx 不重试
            except httpx.RequestError as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    f"网络错误 (尝试 {attempt + 1}/{max_retries})，"
                    f"{wait}s 后重试: {e}"
                )
                await asyncio.sleep(wait)

        raise last_error or RuntimeError("PR Comment 发布失败")
