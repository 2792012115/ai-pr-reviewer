"""
AI PR Review 助手 - AI 评审引擎
===============================
核心模块：将 PR diff 送入 LLM 进行智能分析，
生成变更摘要、风险识别和 Review 建议。

设计思路：
- 采用"分文件 + 聚合总结"两阶段策略
- 第一阶段：逐文件分析，识别具体问题
- 第二阶段：跨文件聚合，生成整体评估
- 支持多模型后端（OpenAI / 兼容接口），通过 config 切换
"""

from __future__ import annotations

import asyncio
import logging
import json
import re
from typing import Optional

from openai import AsyncOpenAI

from config import AppConfig
from models import (
    PRData,
    FileChange,
    FileReview,
    ReviewIssue,
    RiskLevel,
    ReviewResult,
    ReviewStatus,
    PRSummary,
)

logger = logging.getLogger(__name__)

# ============================================================
# Prompt 模板
# ============================================================

SYSTEM_PROMPT = """你是一位资深代码评审专家（Senior Code Reviewer），擅长发现代码中的：
- 安全漏洞（SQL注入、XSS、认证缺陷、密钥泄露等）
- 逻辑错误（边界条件、空指针、竞态条件等）
- 性能问题（N+1查询、不必要的循环、内存泄漏等）
- 代码规范问题（命名、注释、复杂度等）
- 可维护性问题（耦合度过高、重复代码、缺少错误处理等）

请以 JSON 格式输出评审结果。严格遵循以下 JSON Schema：

{
  "issues": [
    {
      "line_range": "L10-L15",
      "risk_level": "critical|high|medium|low|info",
      "category": "security|bug|performance|style|logic|maintainability",
      "title": "简短标题（≤20字）",
      "description": "详细问题描述",
      "suggestion": "具体的修改建议（含代码示例）",
      "code_snippet": "触发问题的代码片段（从diff中摘取）"
    }
  ],
  "summary": "对该文件变更的一句话总结",
  "risk_score": 3.5
}

注意：
- risk_score 为 0-10 分，0=无风险，10=极高风险
- 只报告真实存在的问题，不要虚构
- 如果代码质量很好，issues 可为空数组
- 优先关注安全漏洞和逻辑错误（critical/high）"""

FOCUS_PROMPTS = {
    "security": "请**重点关注安全漏洞**：SQL注入、XSS攻击、认证绕过、密钥泄露、敏感数据暴露、权限控制缺陷等。",
    "performance": "请**重点关注性能问题**：N+1查询、不必要的IO操作、内存泄漏、算法复杂度、缓存策略等。",
    "style": "请**重点关注代码规范**：命名约定、代码风格一致性、注释质量、代码复杂度（圈复杂度）等。",
    "logic": "请**重点关注逻辑正确性**：边界条件处理、空值检查、类型安全、异常处理、并发安全等。",
    "maintainability": "请**重点关注可维护性**：模块耦合度、代码重复、抽象层次、测试覆盖、错误处理等。",
}

SUMMARY_SYSTEM_PROMPT = """你是一位资深代码评审专家。请根据所有文件的评审结果，生成一个 PR 整体评估报告。

输出 JSON 格式：
{
  "one_line_summary": "一句话总结（≤50字）",
  "detailed_summary": "详细变更摘要（2-5句话）",
  "key_changes": ["变更点1", "变更点2", ...],
  "overall_assessment": "整体评价（2-3句话，包括优点和需要改进的地方）",
  "overall_risk_score": 5.5,
  "recommendations": ["全局建议1", "全局建议2", ...]
}
"""


# ============================================================
# 文件级评审 Prompt 构建
# ============================================================

def _build_file_review_prompt(
    filename: str,
    status: str,
    patch: str,
    include_context: bool = True,
) -> str:
    """构建单文件评审的 user prompt"""
    lines = []
    lines.append(f"请评审以下文件的代码变更：\n")
    lines.append(f"**文件**: `{filename}`")
    lines.append(f"**变更类型**: {status}")

    if patch:
        # 截断过长的 diff
        patch_lines = patch.split("\n")
        if len(patch_lines) > 800:
            patch_display = "\n".join(patch_lines[:800])
            lines.append(f"\n**Diff (前800行，共{len(patch_lines)}行)**:")
        else:
            patch_display = patch
            lines.append(f"\n**Diff ({len(patch_lines)}行)**:")
        lines.append(f"```diff\n{patch_display}\n```")
    else:
        lines.append("\n**Diff**: (空变更或二进制文件)")

    lines.append("\n请以 JSON 格式输出评审结果。")
    return "\n".join(lines)


def _build_summary_prompt(
    file_summaries: list[dict],
    pr_title: str,
    pr_description: str,
) -> str:
    """构建整体摘要的 user prompt"""
    lines = []
    lines.append(f"PR 标题: {pr_title}")
    if pr_description:
        # 截断过长描述
        desc = pr_description[:1000]
        lines.append(f"PR 描述: {desc}")
    lines.append(f"\n各文件评审摘要:")
    for fs in file_summaries:
        lines.append(f"- `{fs['filename']}`: {fs.get('summary', '无')} (风险: {fs.get('risk_score', 0)})")
    lines.append("\n请生成整体评估报告，JSON 格式输出。")
    return "\n".join(lines)


# ============================================================
# JSON 解析工具
# ============================================================

def _extract_json(text: str) -> dict:
    """从 LLM 返回文本中提取 JSON（处理 markdown code block 包裹）"""
    # 尝试匹配 ```json ... ``` 或 ``` ... ```
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if json_match:
        text = json_match.group(1)

    # 尝试找到第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]

    return json.loads(text)


# ============================================================
# AI 评审器
# ============================================================

class AIReviewer:
    """
    AI 评审引擎。
    
    模型选择设计：
    - 默认使用 OpenAI GPT-4o（平衡速度与质量）
    - 通过 OPENAI_BASE_URL 可切换兼容接口（Claude API、本地模型等）
    - 未来可扩展：添加 ModelRouter 根据 PR 复杂度自动选择模型
    
    上下文获取方式：
    - 当前：仅使用 PR diff（unified diff patch）
    - 可扩展：通过 GitHub Contents API 获取完整文件内容作为上下文
    """

    def _build_system_prompt(self, focus_areas: Optional[list[str]] = None) -> str:
        """
        根据用户指定的关注领域构建 System Prompt。
        
        如果未指定 focus_areas，返回通用评审 prompt；
        如果指定了，在通用 prompt 基础上追加领域特定的强调指令。
        """
        base = SYSTEM_PROMPT
        if focus_areas:
            additions = []
            for area in focus_areas:
                area_lower = area.lower().strip()
                if area_lower in FOCUS_PROMPTS:
                    additions.append(FOCUS_PROMPTS[area_lower])
            if additions:
                base += "\n\n## 重点关注领域\n" + "\n".join(additions)
                base += "\n\n尽管你仍应报告所有发现的问题，但请为上述领域的问题分配更高的风险评分。"
        return base

    def __init__(self, config: AppConfig):
        self.config = config
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        """懒加载 OpenAI 客户端（避免无 API Key 时导入即报错）"""
        if self._client is None:
            if not self.config.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY 未设置。请设置环境变量或创建 .env 文件。\n"
                    "复制 .env.example → .env 并填入你的 API Key。"
                )
            self._client = AsyncOpenAI(
                api_key=self.config.openai_api_key,
                base_url=self.config.openai_base_url,
                timeout=float(self.config.llm_timeout),
            )
        return self._client

    async def review(
        self,
        pr_data: PRData,
        include_context: bool = True,
        focus_areas: Optional[list[str]] = None,
    ) -> ReviewResult:
        """
        对 PR 进行完整评审。
        
        流程：
        1. 过滤掉无需评审的文件（二进制、删除、太大）
        2. 并发评审每个文件（支持 focus_areas 关注领域筛选）
        3. 聚合生成整体摘要
        """
        # 过滤文件
        reviewable_files = self._filter_files(pr_data.files)
        logger.info(
            f"可评审文件: {len(reviewable_files)}/{len(pr_data.files)}"
        )

        if not reviewable_files:
            return ReviewResult(
                status=ReviewStatus.COMPLETED,
                overall_assessment="无可评审的代码文件（可能全是二进制或删除操作）。",
            )

        # 1. 逐文件并发评审
        semaphore = asyncio.Semaphore(5)  # 限制并发数

        async def review_one(fc: FileChange) -> FileReview:
            async with semaphore:
                return await self._review_single_file(
                    fc, include_context, focus_areas
                )

        tasks = [review_one(fc) for fc in reviewable_files]
        file_reviews = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        clean_reviews: list[FileReview] = []
        for i, fr in enumerate(file_reviews):
            if isinstance(fr, Exception):
                logger.error(f"文件评审异常 {reviewable_files[i].filename}: {fr}")
                clean_reviews.append(
                    FileReview(
                        filename=reviewable_files[i].filename,
                        summary=f"评审失败: {fr}",
                    )
                )
            else:
                clean_reviews.append(fr)

        # 2. 聚合总结
        file_summaries = [
            {
                "filename": fr.filename,
                "summary": fr.summary,
                "risk_score": fr.risk_score,
            }
            for fr in clean_reviews
        ]

        try:
            overall = await self._generate_summary(
                file_summaries,
                pr_data.metadata.title,
                pr_data.metadata.description,
            )
        except Exception as e:
            logger.error(f"生成整体摘要失败: {e}")
            overall = {
                "one_line_summary": f"PR: {pr_data.metadata.title}",
                "detailed_summary": "无法生成详细摘要。",
                "key_changes": [fr.filename for fr in clean_reviews],
                "overall_assessment": "评审完成，但摘要生成失败。",
                "overall_risk_score": sum(fr.risk_score for fr in clean_reviews)
                / max(len(clean_reviews), 1),
                "recommendations": [],
            }

        # 构建结果
        pr_summary = PRSummary(
            title=pr_data.metadata.title,
            one_line_summary=overall.get("one_line_summary", ""),
            detailed_summary=overall.get("detailed_summary", ""),
            changed_files=[fr.filename for fr in clean_reviews],
            key_changes=overall.get("key_changes", []),
        )

        return ReviewResult(
            status=ReviewStatus.COMPLETED,
            pr_summary=pr_summary,
            file_reviews=clean_reviews,
            overall_risk_score=overall.get("overall_risk_score", 0.0),
            overall_assessment=overall.get("overall_assessment", ""),
            recommendations=overall.get("recommendations", []),
        )

    # ---- 内部方法 ----

    def _filter_files(self, files: list[FileChange]) -> list[FileChange]:
        """过滤掉无需评审的文件"""
        BINARY_EXTENSIONS = {
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
            ".pdf", ".zip", ".tar", ".gz", ".7z",
            ".exe", ".dll", ".so", ".dylib",
            ".woff", ".woff2", ".ttf", ".eot",
            ".mp4", ".mp3", ".wav", ".avi",
        }
        SKIP_EXTENSIONS = {
            ".lock", ".sum",  # lock files
        }

        reviewable = []
        for f in files:
            # 跳过删除的文件
            if f.status == "removed":
                continue
            # 跳过二进制
            lower = f.filename.lower()
            if any(lower.endswith(ext) for ext in BINARY_EXTENSIONS):
                continue
            if any(lower.endswith(ext) for ext in SKIP_EXTENSIONS):
                continue
            # 跳过无 patch 的非新增文件
            if not f.patch and f.status != "added":
                continue
            reviewable.append(f)

        return reviewable

    async def _review_single_file(
        self,
        fc: FileChange,
        include_context: bool,
        focus_areas: Optional[list[str]] = None,
    ) -> FileReview:
        """评审单个文件（支持关注领域筛选）"""
        user_prompt = _build_file_review_prompt(
            fc.filename, fc.status, fc.patch, include_context
        )
        system_prompt = self._build_system_prompt(focus_areas)

        try:
            response = await self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.llm_temperature,
                max_tokens=self.config.llm_max_tokens,
            )
            content = response.choices[0].message.content or "{}"
            data = _extract_json(content)

            issues = []
            for issue_data in data.get("issues", []):
                try:
                    risk = RiskLevel(issue_data.get("risk_level", "info"))
                except ValueError:
                    risk = RiskLevel.INFO
                issues.append(
                    ReviewIssue(
                        file=fc.filename,
                        line_range=issue_data.get("line_range", ""),
                        risk_level=risk,
                        category=issue_data.get("category", "style"),
                        title=issue_data.get("title", ""),
                        description=issue_data.get("description", ""),
                        suggestion=issue_data.get("suggestion", ""),
                        code_snippet=issue_data.get("code_snippet", ""),
                    )
                )

            return FileReview(
                filename=fc.filename,
                summary=data.get("summary", ""),
                issues=issues,
                risk_score=float(data.get("risk_score", 0)),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败 {fc.filename}: {e}")
            return FileReview(
                filename=fc.filename,
                summary="AI 评审输出解析失败，请重试。",
                risk_score=0,
            )

    async def _generate_summary(
        self,
        file_summaries: list[dict],
        pr_title: str,
        pr_description: str,
    ) -> dict:
        """聚合各文件评审，生成整体评估"""
        user_prompt = _build_summary_prompt(
            file_summaries, pr_title, pr_description
        )

        response = await self.client.chat.completions.create(
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
        )

        content = response.choices[0].message.content or "{}"
        return _extract_json(content)
