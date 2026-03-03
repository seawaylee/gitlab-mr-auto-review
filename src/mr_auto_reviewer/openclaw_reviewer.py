import ast
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .models import MergeRequest, ReviewResult

LOGGER = logging.getLogger(__name__)


class OpenClawReviewer:
    def __init__(
        self,
        agent_id: str = "sohu",
        timeout_seconds: int = 180,
        local: bool = False,
        openclaw_bin: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.timeout_seconds = timeout_seconds
        self.local = local
        self.openclaw_bin = openclaw_bin or self._resolve_openclaw_bin()

    def review(self, mr: MergeRequest) -> ReviewResult:
        if not self.openclaw_bin:
            return self._fallback(mr, reason="openclaw binary not found")

        prompt = self._build_prompt(mr)
        command = [
            self.openclaw_bin,
            "agent",
            "--agent",
            self.agent_id,
            "--message",
            prompt,
            "--json",
            "--timeout",
            str(self.timeout_seconds),
        ]
        if self.local:
            command.append("--local")

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 15,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("openclaw reviewer execution failed: %s", exc)
            return self._fallback(mr, reason=str(exc))

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            return self._fallback(mr, reason=f"openclaw exit {result.returncode}: {detail}")

        text = self._extract_agent_text(result.stdout)
        if not text:
            return self._fallback(mr, reason="empty openclaw output")

        payload = self._parse_json_object(text)
        if not isinstance(payload, dict):
            return self._fallback(mr, reason="openclaw output is not valid JSON")
        expected_keys = {"mr_purpose", "summary", "verdict", "risk_level", "findings", "suggestions"}
        if not any(key in payload for key in expected_keys):
            return self._fallback(mr, reason="openclaw JSON missing expected review fields")

        return ReviewResult(
            mr_purpose=str(payload.get("mr_purpose") or "未给出"),
            summary=str(payload.get("summary") or "未给出"),
            verdict=str(payload.get("verdict") or "comment"),
            risk_level=str(payload.get("risk_level") or "medium"),
            findings=self._normalize_list(payload.get("findings")),
            suggestions=self._normalize_list(payload.get("suggestions")),
        )

    @staticmethod
    def _resolve_openclaw_bin() -> str:
        which_bin = shutil.which("openclaw") or ""
        if which_bin:
            return which_bin

        wrapper = Path.home() / ".local" / "bin" / "openclaw"
        if wrapper.exists() and wrapper.is_file():
            return str(wrapper)

        candidate = Path.home() / ".local" / "share" / "node-v22" / "bin" / "openclaw"
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        return ""

    @staticmethod
    def _normalize_list(value) -> list[str]:
        if isinstance(value, list):
            normalized = []
            for item in value:
                text = OpenClawReviewer._format_review_item(item)
                if text.strip():
                    normalized.append(text)
            return normalized
        if value is None:
            return []
        return [OpenClawReviewer._format_review_item(value)]

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
                        return OpenClawReviewer._format_review_item(parsed)
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
        diffs = []
        for change in mr.changes:
            diffs.append(f"### File: {change.new_path}\\n```diff\\n{change.diff}\\n```")

        return (
            "你是资深代码评审工程师。请基于下面 MR 信息，输出严格 JSON，不要输出任何额外文本。\\n"
            "JSON字段: mr_purpose, summary, verdict, risk_level, findings, suggestions\\n"
            "约束: verdict in [approve, comment, request_changes], risk_level in [low, medium, high]\\n\\n"
            f"MR title: {mr.title}\\n"
            f"MR description: {mr.description}\\n"
            f"source -> target: {mr.source_branch} -> {mr.target_branch}\\n"
            f"author: {mr.author}\\n"
            f"url: {mr.web_url}\\n"
            f"diffs:\\n{chr(10).join(diffs)}"
        )

    def _fallback(self, mr: MergeRequest, reason: str) -> ReviewResult:
        changed_files = ", ".join(change.new_path for change in mr.changes[:5]) or "未获取到 diff"
        return ReviewResult(
            mr_purpose=(mr.description.strip() or f"修改文件包括: {changed_files}"),
            summary="OpenClaw reviewer 不可用，已输出基础摘要。",
            verdict="comment",
            risk_level="medium",
            findings=[f"openclaw fallback: {reason}"],
            suggestions=["检查 openclaw sohu agent 可用性，或临时切换 REVIEW_PROVIDER=openai。"],
        )

    def _extract_agent_text(self, stdout: str) -> str:
        payload = self._parse_json_object(stdout)
        if isinstance(payload, dict):
            result = payload.get("result")
            if isinstance(result, dict):
                payloads = result.get("payloads")
                if isinstance(payloads, list):
                    for item in payloads:
                        if isinstance(item, dict):
                            text = item.get("text")
                            if isinstance(text, str) and text.strip():
                                return text.strip()

        return stdout.strip()

    def _parse_json_object(self, text: str):
        raw = (text or "").strip()
        if not raw:
            return None

        try:
            return json.loads(raw)
        except Exception:
            pass

        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except Exception:
                continue

        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            fragment = raw[start : end + 1]
            try:
                return json.loads(fragment)
            except Exception:
                return None
        return None
