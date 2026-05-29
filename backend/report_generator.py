"""
AI PR Review 助手 - 报告生成器
==============================
将评审结果格式化为人类可读的 Markdown / HTML 报告。
"""

from __future__ import annotations

from models import ReviewResult, RiskLevel, FileReview, ReviewIssue


class ReportGenerator:
    """
    报告生成器。
    
    支持格式：
    - Markdown（用于 README / PR comment）
    - HTML（用于 Web 展示）
    """

    # ---- 风险等级图标 ----
    RISK_ICONS = {
        RiskLevel.CRITICAL: "🔴",
        RiskLevel.HIGH: "🟠",
        RiskLevel.MEDIUM: "🟡",
        RiskLevel.LOW: "🟢",
        RiskLevel.INFO: "ℹ️",
    }

    RISK_LABELS = {
        RiskLevel.CRITICAL: "严重",
        RiskLevel.HIGH: "高风险",
        RiskLevel.MEDIUM: "中风险",
        RiskLevel.LOW: "低风险",
        RiskLevel.INFO: "提示",
    }

    # ---- 整体风险评分颜色 ----
    @staticmethod
    def _risk_color(score: float) -> str:
        if score >= 7:
            return "#d73a49"  # 红色
        elif score >= 4:
            return "#e36209"  # 橙色
        elif score >= 2:
            return "#dbab09"  # 黄色
        else:
            return "#28a745"  # 绿色

    # ============================================================
    # Markdown 报告
    # ============================================================

    def to_markdown(self, result: ReviewResult) -> str:
        """生成 Markdown 格式评审报告"""
        lines = []

        # 标题
        lines.append("# 🤖 AI PR Review 报告")
        lines.append("")

        # 元信息
        if result.pr_summary:
            lines.append(f"## 📋 PR 摘要")
            lines.append("")
            lines.append(f"**{result.pr_summary.one_line_summary}**")
            lines.append("")
            lines.append(result.pr_summary.detailed_summary)
            lines.append("")

            if result.pr_summary.key_changes:
                lines.append("### 关键变更")
                for kc in result.pr_summary.key_changes:
                    lines.append(f"- {kc}")
                lines.append("")

        # 整体风险
        lines.append("## 🎯 整体评估")
        lines.append("")
        score = result.overall_risk_score
        lines.append(f"**风险评分**: {score:.1f} / 10")
        lines.append("")
        lines.append(result.overall_assessment)
        lines.append("")

        if result.recommendations:
            lines.append("### 💡 全局建议")
            for rec in result.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        # 文件评审详情
        lines.append("## 📁 文件评审详情")
        lines.append("")

        for fr in result.file_reviews:
            lines.append(f"### `{fr.filename}`")
            lines.append(f"风险评分: {fr.risk_score:.1f} / 10")
            lines.append("")
            lines.append(fr.summary)
            lines.append("")

            if fr.issues:
                lines.append("| 等级 | 类别 | 问题 | 建议 |")
                lines.append("|------|------|------|------|")
                for issue in fr.issues:
                    icon = self.RISK_ICONS.get(issue.risk_level, "")
                    lines.append(
                        f"| {icon} {self.RISK_LABELS[issue.risk_level]} "
                        f"| {issue.category} "
                        f"| **{issue.title}**<br>{issue.description} "
                        f"| {issue.suggestion} |"
                    )
                lines.append("")

            # 每个 issue 展开详情
            for issue in fr.issues:
                lines.append(f"#### {self.RISK_ICONS[issue.risk_level]} {issue.title}")
                lines.append(f"- **位置**: `{issue.file}` {issue.line_range}")
                lines.append(f"- **类别**: {issue.category}")
                lines.append(f"- **描述**: {issue.description}")
                if issue.suggestion:
                    lines.append(f"- **建议**: {issue.suggestion}")
                if issue.code_snippet:
                    lines.append(f"\n```\n{issue.code_snippet}\n```")
                lines.append("")

        # 页脚
        lines.append("---")
        lines.append(f"*模型: {result.model_used} | 分析耗时: {result.analysis_time_ms}ms*")
        lines.append("")

        return "\n".join(lines)

    # ============================================================
    # HTML 报告（用于 Web 展示）
    # ============================================================

    def to_html(self, result: ReviewResult) -> str:
        """生成 HTML 格式评审报告"""
        md = self.to_markdown(result)

        # 简单转换为 HTML（实际使用时可引入 markdown 库）
        try:
            import markdown
            html = markdown.markdown(md, extensions=["fenced_code", "tables"])
            return self._wrap_html(html, result)
        except ImportError:
            return self._simple_html(result)

    def _wrap_html(self, body: str, result: ReviewResult) -> str:
        """包装完整 HTML 页面"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI PR Review - {result.pr_summary.title if result.pr_summary else "报告"}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 960px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #24292e; }}
        h1 {{ border-bottom: 2px solid #e1e4e8; padding-bottom: 10px; }}
        h2 {{ margin-top: 30px; border-bottom: 1px solid #e1e4e8; padding-bottom: 8px; }}
        h3 {{ margin-top: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #dfe2e5; padding: 8px 12px; text-align: left; }}
        th {{ background: #f6f8fa; }}
        code {{ background: #f6f8fa; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
        pre {{ background: #f6f8fa; padding: 16px; border-radius: 6px; overflow-x: auto; }}
        .risk-bar {{ height: 12px; border-radius: 6px; background: #e1e4e8; margin: 10px 0; }}
        .risk-fill {{ height: 100%; border-radius: 6px; transition: width 0.5s; }}
    </style>
</head>
<body>
    <div class="risk-bar">
        <div class="risk-fill" style="width:{result.overall_risk_score * 10}%;
             background:{self._risk_color(result.overall_risk_score)};"></div>
    </div>
    {body}
</body>
</html>"""

    def _simple_html(self, result: ReviewResult) -> str:
        """不依赖 markdown 库的简单 HTML 生成"""
        lines = []
        lines.append('<div class="review-report">')

        if result.pr_summary:
            lines.append(f"<h2>PR 摘要</h2>")
            lines.append(f"<p><strong>{result.pr_summary.one_line_summary}</strong></p>")
            lines.append(f"<p>{result.pr_summary.detailed_summary}</p>")

        lines.append(f"<h2>整体评估</h2>")
        lines.append(f"<p>风险评分: <strong>{result.overall_risk_score:.1f} / 10</strong></p>")
        lines.append(f"<p>{result.overall_assessment}</p>")

        for fr in result.file_reviews:
            lines.append(f"<h3>{fr.filename}</h3>")
            lines.append(f"<p>风险: {fr.risk_score:.1f} | {fr.summary}</p>")
            for issue in fr.issues:
                icon = self.RISK_ICONS.get(issue.risk_level, "")
                lines.append(
                    f"<div style='margin:10px 0;padding:10px;border-left:4px solid "
                    f"{self._risk_color({'critical':10,'high':7,'medium':4,'low':2,'info':1}.get(issue.risk_level.value,2))};"
                    f"background:#f6f8fa;'>"
                    f"<strong>{icon} {issue.title}</strong> "
                    f"<span style='color:#586069;'>({issue.category}, {issue.line_range})</span>"
                    f"<p>{issue.description}</p>"
                )
                if issue.suggestion:
                    lines.append(f"<p><em>建议: {issue.suggestion}</em></p>")
                lines.append("</div>")

        lines.append("</div>")
        return self._wrap_html("\n".join(lines), result)
