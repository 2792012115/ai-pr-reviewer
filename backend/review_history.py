"""
AI PR Review 助手 - 评审历史存储
================================
轻量级 JSON 文件存储，记录每次评审的摘要信息，
支持趋势分析和历史查询。
"""

from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from models import ReviewResult

logger = logging.getLogger(__name__)

# 存储路径：项目根目录下的 review_history.json
HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "review_history.json"
)


def save_review_record(result: ReviewResult, pr_url: str) -> dict:
    """
    将评审记录追加到历史文件。
    
    Returns:
        dict: 保存的记录
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pr_url": pr_url,
        "pr_title": result.pr_summary.title if result.pr_summary else "N/A",
        "overall_risk_score": result.overall_risk_score,
        "files_reviewed": len(result.file_reviews),
        "total_issues": sum(len(fr.issues) for fr in result.file_reviews),
        "critical_issues": sum(
            1 for fr in result.file_reviews
            for i in fr.issues if i.risk_level.value == "critical"
        ),
        "model_used": result.model_used,
        "analysis_time_ms": result.analysis_time_ms,
    }

    # 读取已有记录
    records = _load_records()
    records.append(record)

    # 写回
    _save_records(records)
    logger.info(f"评审记录已保存 (共 {len(records)} 条)")

    return record


def get_review_history(limit: int = 20) -> list[dict]:
    """获取最近 N 条评审历史"""
    records = _load_records()
    return records[-limit:]


def get_trend_summary() -> dict:
    """
    获取评审趋势摘要。
    
    Returns:
        dict: 包含平均风险评分、总评审次数、问题分布等
    """
    records = _load_records()
    if not records:
        return {"total_reviews": 0, "message": "暂无评审记录"}

    scores = [r["overall_risk_score"] for r in records]
    return {
        "total_reviews": len(records),
        "avg_risk_score": round(sum(scores) / len(scores), 2),
        "max_risk_score": max(scores),
        "min_risk_score": min(scores),
        "total_issues_found": sum(r["total_issues"] for r in records),
        "total_critical": sum(r["critical_issues"] for r in records),
        "last_review_at": records[-1]["timestamp"],
    }


def _load_records() -> list[dict]:
    """从文件加载记录（文件不存在则返回空列表）"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"评审历史文件损坏，将重新创建: {e}")
        return []


def _save_records(records: list[dict]):
    """保存记录到文件"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
