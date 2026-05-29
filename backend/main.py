"""
AI PR Review 助手 - FastAPI 主应用
==================================
应用程序入口，定义 API 路由与中间件。
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import time
import logging

from config import config
from models import ReviewRequest, ReviewResult, ReviewStatus
from github_client import GitHubClient, PRReference
from ai_reviewer import AIReviewer
from report_generator import ReportGenerator
from review_history import save_review_record, get_review_history, get_trend_summary

# ---- 日志 ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai-pr-reviewer")

# ---- FastAPI 应用 ----
app = FastAPI(
    title="AI PR Review 助手",
    description="基于 AI 的 GitHub Pull Request 智能代码评审工具",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 依赖注入 ----
github_client = GitHubClient(config)
ai_reviewer = AIReviewer(config)
report_generator = ReportGenerator()


# ============================================================
# API 路由
# ============================================================

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "service": "AI PR Review Assistant",
        "model": config.openai_model,
    }


@app.post("/api/review", response_model=dict)
async def review_pr(request: ReviewRequest):
    """
    核心接口：对指定 PR 进行 AI 评审。
    
    流程：
    1. 解析 PR URL → 提取 owner/repo/number
    2. 调用 GitHub API 获取 PR 数据与 diff
    3. 将 diff 分文件送给 AI 引擎分析
    4. 汇总生成评审报告
    """
    t0 = time.time()

    # 1. 解析 URL
    try:
        pr_ref = github_client.parse_pr_url(request.pr_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"开始评审: {pr_ref.owner}/{pr_ref.repo}#{pr_ref.pr_number}")

    # 2. 获取 PR 数据
    try:
        pr_data = await github_client.fetch_pr_data(pr_ref)
    except Exception as e:
        logger.error(f"获取 PR 数据失败: {e}")
        raise HTTPException(status_code=502, detail=f"GitHub API 错误: {e}")

    # 3. 文件数与 diff 行数检查
    if pr_data.total_files > config.max_files_per_review:
        logger.warning(
            f"PR 文件数 {pr_data.total_files} 超过上限 {config.max_files_per_review}，"
            f"仅分析前 {config.max_files_per_review} 个文件"
        )
        pr_data.files = pr_data.files[: config.max_files_per_review]

    total_diff_lines = sum(
        len(f.patch.split("\n")) if f.patch else 0 for f in pr_data.files
    )
    if total_diff_lines > config.max_diff_lines:
        logger.warning(
            f"PR diff 行数 {total_diff_lines} 超过上限 {config.max_diff_lines}，"
            f"当前仍继续处理但可能耗时较长"
        )

    # 4. AI 评审
    try:
        result = await ai_reviewer.review(
            pr_data, request.include_file_context, request.focus_areas or None
        )
    except Exception as e:
        logger.error(f"AI 评审失败: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": ReviewStatus.FAILED.value,
                "error_message": str(e),
            },
        )

    # 5. 附加元信息
    elapsed_ms = int((time.time() - t0) * 1000)
    result.analysis_time_ms = elapsed_ms
    result.model_used = config.openai_model

    logger.info(
        f"评审完成: {pr_ref.owner}/{pr_ref.repo}#{pr_ref.pr_number} "
        f"耗时 {elapsed_ms}ms 风险评分 {result.overall_risk_score:.1f}"
    )

    # 6. 保存评审历史
    try:
        save_review_record(result, request.pr_url)
    except Exception as e:
        logger.warning(f"保存评审历史失败（不影响主流程）: {e}")

    # 7. 发布 PR Comment（如果请求）
    comment_url = ""
    if request.post_comment:
        try:
            comment_md = report_generator.to_markdown(result)
            comment_resp = await github_client.post_review_comment_with_retry(
                pr_ref, comment_md
            )
            comment_url = comment_resp.get("html_url", "")
            logger.info(f"评审报告已作为 PR Comment 发布: {comment_url}")
        except ValueError as e:
            logger.warning(f"无法发布 PR Comment: {e}")
        except Exception as e:
            logger.error(f"发布 PR Comment 失败: {e}")

    # 8. 转换为可序列化的字典返回
    serialized = _serialize_result(result)
    if comment_url:
        serialized["comment_url"] = comment_url
    return serialized


@app.get("/api/review/{owner}/{repo}/{pr_number}", response_model=dict)
async def review_pr_by_path(owner: str, repo: str, pr_number: int):
    """通过 URL 路径参数发起评审（便捷方式）"""
    request = ReviewRequest(
        pr_url=f"https://github.com/{owner}/{repo}/pull/{pr_number}"
    )
    return await review_pr(request)


# ============================================================
# 评审历史接口
# ============================================================

@app.get("/api/history")
async def review_history(limit: int = 20):
    """获取评审历史记录"""
    records = get_review_history(limit)
    return {"count": len(records), "records": records}


@app.get("/api/trends")
async def review_trends():
    """获取评审趋势摘要"""
    return get_trend_summary()


# ============================================================
# 辅助函数
# ============================================================

def _serialize_result(result: ReviewResult) -> dict:
    """将 ReviewResult 序列化为 JSON 兼容字典"""
    output = {
        "status": result.status.value,
        "model_used": result.model_used,
        "analysis_time_ms": result.analysis_time_ms,
        "overall_risk_score": result.overall_risk_score,
        "overall_assessment": result.overall_assessment,
        "recommendations": result.recommendations,
    }

    if result.pr_summary:
        output["pr_summary"] = {
            "title": result.pr_summary.title,
            "one_line_summary": result.pr_summary.one_line_summary,
            "detailed_summary": result.pr_summary.detailed_summary,
            "changed_files": result.pr_summary.changed_files,
            "key_changes": result.pr_summary.key_changes,
        }

    output["file_reviews"] = []
    for fr in result.file_reviews:
        file_review_dict = {
            "filename": fr.filename,
            "summary": fr.summary,
            "risk_score": fr.risk_score,
            "issues": [
                {
                    "file": issue.file,
                    "line_range": issue.line_range,
                    "risk_level": issue.risk_level.value,
                    "category": issue.category,
                    "title": issue.title,
                    "description": issue.description,
                    "suggestion": issue.suggestion,
                    "code_snippet": issue.code_snippet,
                }
                for issue in fr.issues
            ],
        }
        output["file_reviews"].append(file_review_dict)

    if result.error_message:
        output["error_message"] = result.error_message

    return output


# ============================================================
# 前端页面
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面"""
    from fastapi.templating import Jinja2Templates
    from fastapi import Request
    import os

    templates = Jinja2Templates(
        directory=os.path.join(os.path.dirname(__file__), "..", "frontend")
    )

    # 直接返回 HTML
    frontend_path = os.path.join(
        os.path.dirname(__file__), "..", "frontend", "index.html"
    )
    with open(frontend_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info",
    )
