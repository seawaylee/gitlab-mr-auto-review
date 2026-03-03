import json
import logging
import re
from typing import Optional

import requests

LOGGER = logging.getLogger(__name__)


class FeishuClient:
    def __init__(
        self,
        app_id: Optional[str],
        app_secret: Optional[str],
        receive_id: Optional[str],
        receive_id_type: str = "open_id",
        base_url: str = "https://open.feishu.cn",
        doc_folder_token: Optional[str] = None,
        doc_url_base: Optional[str] = None,
        timeout_seconds: int = 20,
    ):
        self.app_id = app_id
        self.app_secret = app_secret
        self.receive_id = receive_id
        self.receive_id_type = receive_id_type
        self.base_url = base_url.rstrip("/")
        self.doc_folder_token = (doc_folder_token or "").strip() or None
        self.doc_url_base = (doc_url_base or "").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def publish_markdown_doc(self, markdown: str, title: str) -> Optional[str]:
        if not self._api_enabled:
            LOGGER.warning("feishu config incomplete; skip publishing doc")
            return None

        token = self._tenant_access_token()
        document_id = self._create_document(token=token, title=title)
        root_block_id = self._get_root_block_id(token=token, document_id=document_id)
        blocks = self._convert_markdown_to_blocks(token=token, markdown=markdown)
        if blocks:
            try:
                self._append_blocks(
                    token=token,
                    document_id=document_id,
                    root_block_id=root_block_id,
                    blocks=blocks,
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("append converted markdown blocks failed, fallback to structured blocks: %s", exc)
                structured_blocks = self._markdown_to_structured_blocks(markdown=markdown)
                if structured_blocks:
                    self._append_blocks(
                        token=token,
                        document_id=document_id,
                        root_block_id=root_block_id,
                        blocks=structured_blocks,
                    )
        else:
            structured_blocks = self._markdown_to_structured_blocks(markdown=markdown)
            if structured_blocks:
                self._append_blocks(
                    token=token,
                    document_id=document_id,
                    root_block_id=root_block_id,
                    blocks=structured_blocks,
                )
        return self._resolve_document_url(token=token, document_id=document_id)

    def send_markdown_file(self, markdown_path, title: str) -> None:
        if not self._message_enabled:
            LOGGER.warning("feishu config incomplete; skip sending file")
            return

        token = self._tenant_access_token()
        file_key = self._upload_file(token=token, markdown_path=markdown_path, title=title)
        self._send_file_message(token=token, file_key=file_key)

    @property
    def _api_enabled(self) -> bool:
        return bool(self.app_id and self.app_secret)

    @property
    def _message_enabled(self) -> bool:
        return bool(self.app_id and self.app_secret and self.receive_id)

    def _tenant_access_token(self) -> str:
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }
        resp = requests.post(
            f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json=payload,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("tenant_access_token")
        if not token:
            raise RuntimeError(f"failed to get tenant token: {data}")
        return token

    def _create_document(self, token: str, title: str) -> str:
        payload = {"title": self._normalize_doc_title(title)}
        if self.doc_folder_token:
            payload["folder_token"] = self.doc_folder_token
        data = self._post_json(
            url=f"{self.base_url}/open-apis/docx/v1/documents",
            token=token,
            payload=payload,
            action="create docx document",
        )
        document = data.get("document") or {}
        document_id = document.get("document_id") or data.get("document_id")
        if not document_id:
            raise RuntimeError(f"failed to create docx document: {data}")
        return str(document_id)

    def _convert_markdown_to_blocks(self, token: str, markdown: str) -> list[dict]:
        data = self._post_json(
            url=f"{self.base_url}/open-apis/docx/v1/documents/blocks/convert",
            token=token,
            payload={
                "content_type": "markdown",
                "content": markdown or "",
            },
            action="convert markdown to docx blocks",
        )
        blocks = data.get("blocks") or []
        if not isinstance(blocks, list):
            return []
        normalized: list[dict] = []
        for item in blocks:
            if isinstance(item, dict):
                normalized.append(self._sanitize_block(item))
        return normalized

    def _get_root_block_id(self, token: str, document_id: str) -> str:
        data = self._get_json(
            url=f"{self.base_url}/open-apis/docx/v1/documents/{document_id}/blocks",
            token=token,
            params={"page_size": 50},
            action="load docx root block",
        )
        items = data.get("items") or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    block_id = item.get("block_id")
                    if block_id:
                        return str(block_id)
        return document_id

    def _append_blocks(self, token: str, document_id: str, root_block_id: str, blocks: list[dict]) -> None:
        if not blocks:
            return

        index = 0
        chunk_size = 50
        for start in range(0, len(blocks), chunk_size):
            batch = blocks[start : start + chunk_size]
            self._post_json(
                url=f"{self.base_url}/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children",
                token=token,
                payload={"children": batch, "index": index},
                params={"document_revision_id": -1},
                action="append docx blocks",
            )
            index += len(batch)

    def _resolve_document_url(self, token: str, document_id: str) -> str:
        try:
            data = self._get_json(
                url=f"{self.base_url}/open-apis/drive/v1/files/{document_id}",
                token=token,
                action="resolve docx url",
            )
            file_data = data.get("file") or {}
            url = file_data.get("url") or data.get("url")
            if url:
                return str(url)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("resolve feishu doc url failed, fallback to token url: %s", exc)

        if self.doc_url_base:
            return f"{self.doc_url_base}/{document_id}"
        return f"{self.base_url}/open-apis/docx/v1/documents/{document_id}"

    @staticmethod
    def _sanitize_block(block: dict) -> dict:
        if not isinstance(block, dict):
            return block
        sanitized = {}
        for key, value in block.items():
            if key == "merge_info":
                continue
            if isinstance(value, dict):
                sanitized[key] = FeishuClient._sanitize_block(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    FeishuClient._sanitize_block(item) if isinstance(item, dict) else item for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    @staticmethod
    def _normalize_doc_title(title: str) -> str:
        normalized = (title or "").strip().replace("/", "-")
        if not normalized:
            return "GitLab MR Review"
        return normalized[:120]

    @staticmethod
    def _simplify_markdown(markdown: str) -> str:
        lines = []
        for raw in (markdown or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            line = line.lstrip("#>*-` ")
            if not line:
                continue
            lines.append(line[:1200])

        if not lines:
            return "GitLab MR Review"
        return "\n\n".join(lines)

    @staticmethod
    def _markdown_to_structured_blocks(markdown: str) -> list[dict]:
        text = markdown or ""
        lines = text.splitlines()
        blocks = []
        in_code_block = False
        code_lines: list[str] = []

        for raw in lines:
            line = raw.rstrip()
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code_block:
                    for code_line in code_lines:
                        if code_line.strip():
                            blocks.append(FeishuClient._text_block(code_line.strip()))
                    code_lines = []
                    in_code_block = False
                else:
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            if not stripped:
                continue

            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = FeishuClient._normalize_inline_markdown(heading_match.group(2))
                if heading_text:
                    if level <= 1:
                        blocks.append(FeishuClient._heading_block(heading_text, level=1))
                    else:
                        blocks.append(FeishuClient._heading_block(heading_text, level=2))
                continue

            bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
            if bullet_match:
                item_text = FeishuClient._normalize_inline_markdown(bullet_match.group(1))
                if item_text:
                    blocks.append(FeishuClient._bullet_block(item_text))
                continue

            ordered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
            if ordered_match:
                item_text = FeishuClient._normalize_inline_markdown(ordered_match.group(1))
                if item_text:
                    blocks.append(FeishuClient._bullet_block(item_text))
                continue

            normalized = FeishuClient._normalize_inline_markdown(stripped)
            if normalized:
                blocks.append(FeishuClient._text_block(normalized))

        if not blocks:
            blocks.append(FeishuClient._text_block("GitLab MR Review"))
        return blocks

    @staticmethod
    def _normalize_inline_markdown(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""

        # Convert markdown links to readable text.
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        text = text.replace("`", "")
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 1200:
            text = text[:1200]
        return text

    @staticmethod
    def _style_payload() -> dict:
        return {"align": 1, "folded": False}

    @staticmethod
    def _elements_payload(content: str) -> list[dict]:
        return [{"text_run": {"content": content}}]

    @staticmethod
    def _text_block(content: str) -> dict:
        return {
            "block_type": 2,
            "text": {
                "elements": FeishuClient._elements_payload(content),
                "style": FeishuClient._style_payload(),
            },
        }

    @staticmethod
    def _bullet_block(content: str) -> dict:
        return {
            "block_type": 12,
            "bullet": {
                "elements": FeishuClient._elements_payload(content),
                "style": FeishuClient._style_payload(),
            },
        }

    @staticmethod
    def _heading_block(content: str, level: int) -> dict:
        if level <= 1:
            return {
                "block_type": 3,
                "heading1": {
                    "elements": FeishuClient._elements_payload(content),
                    "style": FeishuClient._style_payload(),
                },
            }
        return {
            "block_type": 4,
            "heading2": {
                "elements": FeishuClient._elements_payload(content),
                "style": FeishuClient._style_payload(),
            },
        }

    def _upload_file(self, token: str, markdown_path, title: str) -> str:
        from pathlib import Path

        markdown_path = Path(markdown_path)
        upload_name = f"{title[:50].replace('/', '-')}.md"
        upload_name = upload_name.strip() or markdown_path.name

        with markdown_path.open("rb") as handle:
            resp = requests.post(
                f"{self.base_url}/open-apis/im/v1/files",
                headers={"Authorization": f"Bearer {token}"},
                data={"file_type": "stream", "file_name": upload_name},
                files={"file": (upload_name, handle, "text/markdown")},
                timeout=self.timeout_seconds,
            )
        resp.raise_for_status()
        data = resp.json()
        file_key = ((data.get("data") or {}).get("file_key"))
        if not file_key:
            raise RuntimeError(f"failed to upload feishu file: {data}")
        return file_key

    def _send_file_message(self, token: str, file_key: str) -> None:
        if not self.receive_id:
            raise RuntimeError("feishu receive_id is empty")
        payload = {
            "receive_id": self.receive_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}),
        }
        resp = requests.post(
            f"{self.base_url}/open-apis/im/v1/messages?receive_id_type={self.receive_id_type}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()

    def _post_json(
        self,
        url: str,
        token: str,
        payload: dict,
        action: str,
        params: Optional[dict] = None,
    ) -> dict:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            params=params or {},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        return self._unwrap_data(data=data, action=action)

    def _get_json(
        self,
        url: str,
        token: str,
        action: str,
        params: Optional[dict] = None,
    ) -> dict:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        return self._unwrap_data(data=data, action=action)

    @staticmethod
    def _unwrap_data(data: dict, action: str) -> dict:
        if not isinstance(data, dict):
            raise RuntimeError(f"{action} failed: invalid response {data}")
        code = data.get("code")
        if code not in (None, 0):
            msg = data.get("msg") or data.get("message") or str(data)
            raise RuntimeError(f"{action} failed: {msg}")
        payload = data.get("data")
        return payload if isinstance(payload, dict) else {}
