from datetime import datetime
from typing import List

from .models import MergeRequest, ReviewResult

VERDICT_LABELS = {
    "approve": "通过",
    "comment": "建议关注",
    "request_changes": "需修改后再提交",
}

RISK_LEVEL_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


def _format_items(items: List[str], empty_text: str = "- None") -> str:
    if not items:
        return empty_text
    lines = []
    for item in items:
        segments = [seg for seg in str(item).splitlines() if seg.strip()]
        if not segments:
            continue
        lines.append(f"- {segments[0]}")
        for seg in segments[1:]:
            lines.append(f"  {seg}")
    return "\n".join(lines) if lines else empty_text


def _format_verdict(value: str) -> str:
    key = (value or "").strip().lower()
    return VERDICT_LABELS.get(key, value)


def _format_risk_level(value: str) -> str:
    key = (value or "").strip().lower()
    return RISK_LEVEL_LABELS.get(key, value)


def build_markdown_report(
    mr: MergeRequest,
    review: ReviewResult,
    generated_at: datetime,
) -> str:
    timestamp = generated_at.strftime("%Y-%m-%d %H:%M:%S %Z")
    verdict_text = _format_verdict(review.verdict)
    risk_level_text = _format_risk_level(review.risk_level)
    return f"""# Merge Request Review 报告

- 生成时间: {timestamp}
- 项目 ID: {mr.project_id}
- MR IID: {mr.iid}
- 标题: {mr.title}
- 链接: {mr.web_url}
- 分支: `{mr.source_branch}` -> `{mr.target_branch}`
- 作者: {mr.author}

## 这次 MR 在做什么

{review.mr_purpose}

## Review 概览

{review.summary}

## Review 结论

{verdict_text}

## 风险级别

{risk_level_text}

## 主要问题

{_format_items(review.findings)}

## 建议

{_format_items(review.suggestions)}
"""


def build_gitlab_comment(
    mr: MergeRequest,
    review: ReviewResult,
    generated_at: datetime,
) -> str:
    timestamp = generated_at.strftime("%Y-%m-%d %H:%M:%S %Z")
    verdict_text = _format_verdict(review.verdict)
    risk_level_text = _format_risk_level(review.risk_level)
    findings_text = _format_items(
        review.findings,
        empty_text="- 未发现阻断合并的问题。",
    )
    suggestions_text = _format_items(
        review.suggestions,
        empty_text="- 可直接进入人工抽样复核后合并。",
    )

    return f"""## 自动化 Code Review（行业规范）

### 范围
- MR: [{mr.title}]({mr.web_url})
- 分支: `{mr.source_branch}` -> `{mr.target_branch}`
- 作者: {mr.author}
- 生成时间: {timestamp}

### 变更意图
{review.mr_purpose}

### 审查结论
- Verdict: {verdict_text}
- 风险等级: {risk_level_text}

### 评审摘要
{review.summary}

### 主要问题
{findings_text}

### 建议动作
{suggestions_text}

> 说明：这是基于 MR diff 的自动化审查结果，合并前请结合业务上下文做人工复核。
"""
