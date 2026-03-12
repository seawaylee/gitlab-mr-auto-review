import json
import logging
from pathlib import Path
import shutil
import subprocess
from typing import Optional

import requests

from .models import MergeRequest

LOGGER = logging.getLogger(__name__)


class SohuAgentClient:
    def __init__(
        self,
        webhook_url: Optional[str],
        timeout_seconds: int = 20,
        push_mode: str = "openclaw",
        openclaw_bin: Optional[str] = None,
        openclaw_channel: str = "feishu",
        openclaw_account: str = "sohu",
        openclaw_target: Optional[str] = None,
        attach_report: bool = False,
        dry_run: bool = False,
    ):
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.push_mode = (push_mode or "openclaw").strip().lower()
        self.openclaw_bin = (openclaw_bin or "").strip()
        self.openclaw_channel = (openclaw_channel or "feishu").strip()
        self.openclaw_account = (openclaw_account or "sohu").strip()
        self.openclaw_target = (openclaw_target or "").strip() or None
        self.attach_report = bool(attach_report)
        self.dry_run = dry_run

    def push_report(
        self,
        mr: MergeRequest,
        markdown: str,
        report_path: Path,
        doc_url: Optional[str] = None,
    ) -> None:
        if self.push_mode == "webhook":
            self._push_via_webhook(
                mr=mr,
                markdown=markdown,
                report_path=report_path,
                doc_url=doc_url,
            )
            return

        self._push_via_openclaw(
            mr=mr,
            markdown=markdown,
            report_path=report_path,
            doc_url=doc_url,
        )

    def _push_via_webhook(
        self,
        mr: MergeRequest,
        markdown: str,
        report_path: Path,
        doc_url: Optional[str],
    ) -> None:
        if not self.webhook_url:
            raise RuntimeError("SOHU_AGENT_WEBHOOK_URL is empty while SOHU_PUSH_MODE=webhook")

        payload = {
            "title": f"[MR Review] {mr.title}",
            "mr": {
                "project_id": mr.project_id,
                "iid": mr.iid,
                "url": mr.web_url,
                "source_branch": mr.source_branch,
                "target_branch": mr.target_branch,
                "author": mr.author,
            },
            "report_markdown": markdown,
            "report_file": str(report_path),
            "feishu_doc_url": doc_url,
        }
        if self.dry_run:
            LOGGER.info("dry-run webhook payload prepared for MR %s/%s", mr.project_id, mr.iid)
            return

        response = requests.post(self.webhook_url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()

    def _push_via_openclaw(
        self,
        mr: MergeRequest,
        markdown: str,
        report_path: Path,
        doc_url: Optional[str],
    ) -> None:
        account = self.openclaw_account or "sohu"
        channel = self.openclaw_channel or "feishu"
        target = self.openclaw_target or self._resolve_recent_openclaw_target(account=account)
        if not target:
            raise RuntimeError("SOHU_OPENCLAW_TARGET is empty and no recent target found")

        message = self._build_message(mr=mr, markdown=markdown, doc_url=doc_url)

        openclaw_bin = self._resolve_openclaw_bin()
        if not openclaw_bin:
            if self.dry_run:
                openclaw_bin = self.openclaw_bin or "openclaw"
            else:
                raise RuntimeError("openclaw binary not found")

        command = [openclaw_bin, "message", "send", "--channel", channel]
        if account:
            command.extend(["--account", account])
        command.extend(["--target", target, "--message", message])
        if self.attach_report:
            staged_report = self._stage_openclaw_media(report_path)
            command.extend(["--media", str(staged_report)])

        if self.dry_run:
            LOGGER.info("dry-run openclaw command: %s", " ".join(command))
            return

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(30, self.timeout_seconds),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            if not detail:
                detail = f"exit code {result.returncode}"
            raise RuntimeError("OpenClaw push failed: " + detail)

    def _resolve_openclaw_bin(self) -> str:
        if self.openclaw_bin:
            return self.openclaw_bin

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
    def _stage_openclaw_media(media_path: Path) -> Path:
        source = Path(media_path).expanduser()
        if not source.exists() or not source.is_file():
            return source

        inbound_dir = Path.home() / ".openclaw" / "media" / "inbound"
        staged = inbound_dir / source.name
        try:
            inbound_dir.mkdir(parents=True, exist_ok=True)
            try:
                if source.resolve() == staged.resolve():
                    return source
            except Exception:
                pass
            shutil.copy2(source, staged)
            return staged
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("OpenClaw media staging failed, use original path: %s", exc)
            return source

    @staticmethod
    def _resolve_recent_openclaw_target(account: str) -> Optional[str]:
        account_id = str(account or "").strip()
        if not account_id:
            return None

        sessions_file = Path.home() / ".openclaw" / "agents" / account_id / "sessions" / "sessions.json"
        if not sessions_file.exists() or not sessions_file.is_file():
            return None

        try:
            payload = json.loads(sessions_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        key_prefix = f"agent:{account_id}:direct:"
        best_target = None
        best_updated_at = -1
        for key, value in payload.items():
            if not isinstance(key, str) or not key.startswith(key_prefix):
                continue
            if not isinstance(value, dict):
                continue

            last_channel = str(value.get("lastChannel", "") or "").strip().lower()
            if last_channel and last_channel != "feishu":
                continue
            last_account = str(value.get("lastAccountId", "") or "").strip()
            if last_account and last_account != account_id:
                continue

            raw_target = str(value.get("lastTo", "") or "").strip()
            if not raw_target:
                continue
            target = raw_target if ":" in raw_target else f"user:{raw_target}"
            if not target.startswith("user:ou_"):
                continue

            try:
                updated_at = int(value.get("updatedAt", 0) or 0)
            except Exception:
                updated_at = 0
            if updated_at >= best_updated_at:
                best_updated_at = updated_at
                best_target = target
        return best_target

    @staticmethod
    def _extract_markdown_section(markdown: str, section_name: str) -> str:
        marker = f"## {section_name}"
        start = markdown.find(marker)
        if start < 0:
            return ""

        body_start = markdown.find("\n", start)
        if body_start < 0:
            return ""
        body = markdown[body_start + 1 :]
        next_section = body.find("\n## ")
        if next_section >= 0:
            body = body[:next_section]
        return body.strip()

    def _build_message(self, mr: MergeRequest, markdown: str, doc_url: Optional[str]) -> str:
        purpose = self._extract_markdown_section(markdown, "这次 MR 在做什么")
        verdict = self._extract_markdown_section(markdown, "Review 结论")
        risk = self._extract_markdown_section(markdown, "风险级别")

        lines = [
            "【GitLab MR 自动Review】",
            f"MR: {mr.title}",
            f"链接: {mr.web_url}",
        ]
        if purpose:
            lines.append(f"这次 MR 在做什么: {purpose}")
        if verdict:
            lines.append(f"Review 结论: {verdict}")
        if risk:
            lines.append(f"风险级别: {risk}")
        if doc_url:
            lines.append(f"飞书文档: {doc_url}")
            lines.append("详细内容见飞书在线文档。")
        elif self.attach_report:
            lines.append("详细内容见附件 Markdown。")
        else:
            lines.append("详细内容见上方摘要。")
        return "\n".join(lines)
