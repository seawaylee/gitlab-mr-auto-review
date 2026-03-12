import ast
import json
import logging
from typing import List, Optional

from openai import OpenAI

from .models import MergeRequest, ReviewResult

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior code reviewer for GitLab merge requests.
Analyze code diffs and output strict JSON with fields:
mr_purpose, summary, verdict, risk_level, findings, suggestions.
- verdict must be one of: approve, comment, request_changes
- risk_level must be one of: low, medium, high
- findings/suggestions must be arrays of short bullet strings
Use concise Chinese output.
"""


class AutoReviewer:
    def __init__(self, api_key: Optional[str], model: str, base_url: Optional[str] = None):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None

    def review(self, mr: MergeRequest) -> ReviewResult:
        if not self.client:
            return self._fallback(mr, reason="OPENAI_API_KEY missing")

        prompt = self._build_prompt(mr)
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            text = (response.output_text or "").strip()
            payload = json.loads(text)
            return ReviewResult(
                mr_purpose=payload.get("mr_purpose", "未给出"),
                summary=payload.get("summary", "未给出"),
                verdict=payload.get("verdict", "comment"),
                risk_level=payload.get("risk_level", "medium"),
                findings=self._normalize_list(payload.get("findings")),
                suggestions=self._normalize_list(payload.get("suggestions")),
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("AI review failed: %s", exc)
            return self._fallback(mr, reason=str(exc))

    @staticmethod
    def _normalize_list(value) -> List[str]:
        if isinstance(value, list):
            normalized = []
            for item in value:
                text = AutoReviewer._format_review_item(item)
                if text.strip():
                    normalized.append(text)
            return normalized
        if value is None:
            return []
        return [AutoReviewer._format_review_item(value)]

    @staticmethod
    def _format_review_item(item) -> str:
        if isinstance(item, str):
            stripped = item.strip()
            if (stripped.startswith("{") and stripped.endswith("}")) or (
                stripped.startswith("[") and stripped.endswith("]")
            ):
                try:
                    parsed = ast.literal_eval(stripped)
                    if isinstance(parsed, dict):
                        return AutoReviewer._format_review_item(parsed)
                except Exception:
                    pass
            return item
        if isinstance(item, dict):
            severity = str(
                item.get("severity") or item.get("level") or item.get("risk") or ""
            ).strip()
            title = str(
                item.get("title") or item.get("name") or item.get("issue") or ""
            ).strip()
            details = str(
                item.get("details")
                or item.get("detail")
                or item.get("reason")
                or item.get("description")
                or ""
            ).strip()
            file_path = str(
                item.get("file") or item.get("path") or item.get("location") or ""
            ).strip()

            head_parts = []
            if severity:
                head_parts.append(f"[{severity}]")
            if title:
                head_parts.append(title)
            head = " ".join(head_parts).strip() or "问题"

            tails = []
            if file_path:
                tails.append(f"文件: {file_path}")
            if details:
                tails.append(details)

            used_keys = {
                "severity",
                "level",
                "risk",
                "title",
                "name",
                "issue",
                "details",
                "detail",
                "reason",
                "description",
                "file",
                "path",
                "location",
            }
            for key, value in item.items():
                if key in used_keys:
                    continue
                value_text = str(value).strip()
                if value_text:
                    tails.append(f"{key}: {value_text}")
            if tails:
                return head + "\n" + "\n".join(f"- {segment}" for segment in tails)
            if head == "问题":
                return json.dumps(item, ensure_ascii=False)
            return head
        return str(item)

    def _build_prompt(self, mr: MergeRequest) -> str:
        diff_text = []
        for change in mr.changes:
            diff_text.append(f"### File: {change.new_path}\n```diff\n{change.diff}\n```")

        return (
            f"MR title: {mr.title}\n"
            f"MR description:\n{mr.description}\n\n"
            f"source -> target: {mr.source_branch} -> {mr.target_branch}\n"
            f"author: {mr.author}\n"
            f"diffs:\n{chr(10).join(diff_text)}"
        )

    def _fallback(self, mr: MergeRequest, reason: str) -> ReviewResult:
        changed_files = ", ".join(change.new_path for change in mr.changes[:5]) or "未获取到 diff"
        return ReviewResult(
            mr_purpose=(mr.description.strip() or f"修改文件包括: {changed_files}"),
            summary="自动 AI review 不可用，已输出基础摘要。",
            verdict="comment",
            risk_level="medium",
            findings=[f"AI review fallback: {reason}"],
            suggestions=["配置 OPENAI_API_KEY 后可获得更完整的代码风险分析。"],
        )
