import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AppConfig:
    gitlab_url: str
    gitlab_username: Optional[str]
    gitlab_password: Optional[str]
    gitlab_private_token: Optional[str]
    gitlab_ssl_verify: object
    gitlab_reviewer_username: str
    gitlab_review_scope: str

    openai_api_key: Optional[str]
    openai_base_url: Optional[str]
    openai_model: str
    review_provider: str
    openclaw_review_agent: str
    openclaw_review_timeout_seconds: int
    openclaw_review_local: bool
    openclaw_review_bin: Optional[str]

    sohu_agent_webhook_url: Optional[str]
    sohu_push_mode: str
    sohu_openclaw_bin: Optional[str]
    sohu_openclaw_channel: str
    sohu_openclaw_account: str
    sohu_openclaw_target: Optional[str]
    sohu_attach_report: bool
    dry_run: bool

    feishu_app_id: Optional[str]
    feishu_app_secret: Optional[str]
    feishu_receive_id: Optional[str]
    feishu_receive_id_type: str
    feishu_base_url: str
    feishu_doc_folder_token: Optional[str]
    feishu_doc_url_base: Optional[str]

    report_dir: Path
    state_file: Path

    @classmethod
    def from_env(cls) -> "AppConfig":
        gitlab_reviewer = os.getenv("GITLAB_REVIEWER_USERNAME") or os.getenv("GITLAB_USERNAME")
        if not gitlab_reviewer:
            raise ValueError("GITLAB_REVIEWER_USERNAME or GITLAB_USERNAME is required")

        gitlab_url = os.getenv("GITLAB_URL")
        if not gitlab_url:
            raise ValueError("GITLAB_URL is required")

        ssl_verify_raw = (os.getenv("GITLAB_SSL_VERIFY", "true") or "").strip()
        lowered = ssl_verify_raw.lower()
        if lowered in {"false", "0", "no", "off"}:
            gitlab_ssl_verify: object = False
        elif lowered in {"true", "1", "yes", "on", ""}:
            gitlab_ssl_verify = True
        else:
            gitlab_ssl_verify = ssl_verify_raw

        openclaw_local_raw = (os.getenv("OPENCLAW_REVIEW_LOCAL", "false") or "").strip().lower()
        openclaw_review_local = openclaw_local_raw in {"1", "true", "yes", "on"}
        dry_run_raw = (os.getenv("DRY_RUN", "false") or "").strip().lower()
        dry_run = dry_run_raw in {"1", "true", "yes", "on"}
        attach_report_raw = (os.getenv("SOHU_ATTACH_REPORT", "false") or "").strip().lower()
        attach_report = attach_report_raw in {"1", "true", "yes", "on"}

        return cls(
            gitlab_url=gitlab_url.rstrip("/"),
            gitlab_username=os.getenv("GITLAB_USERNAME"),
            gitlab_password=os.getenv("GITLAB_PASSWORD"),
            gitlab_private_token=os.getenv("GITLAB_PRIVATE_TOKEN"),
            gitlab_ssl_verify=gitlab_ssl_verify,
            gitlab_reviewer_username=gitlab_reviewer,
            gitlab_review_scope=os.getenv("GITLAB_REVIEW_SCOPE", "reviewer_or_assignee").strip().lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv("OPENAI_BASE_URL"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1"),
            review_provider=os.getenv("REVIEW_PROVIDER", "openclaw").strip().lower(),
            openclaw_review_agent=os.getenv("OPENCLAW_REVIEW_AGENT", "sohu").strip(),
            openclaw_review_timeout_seconds=int(
                (os.getenv("OPENCLAW_REVIEW_TIMEOUT_SECONDS", "180") or "180").strip()
            ),
            openclaw_review_local=openclaw_review_local,
            openclaw_review_bin=os.getenv("OPENCLAW_REVIEW_BIN"),
            sohu_agent_webhook_url=os.getenv("SOHU_AGENT_WEBHOOK_URL"),
            sohu_push_mode=os.getenv("SOHU_PUSH_MODE", "openclaw").strip().lower(),
            sohu_openclaw_bin=os.getenv("SOHU_OPENCLAW_BIN"),
            sohu_openclaw_channel=os.getenv("SOHU_OPENCLAW_CHANNEL", "feishu").strip(),
            sohu_openclaw_account=os.getenv("SOHU_OPENCLAW_ACCOUNT", "sohu").strip(),
            sohu_openclaw_target=os.getenv("SOHU_OPENCLAW_TARGET"),
            sohu_attach_report=attach_report,
            dry_run=dry_run,
            feishu_app_id=os.getenv("FEISHU_APP_ID"),
            feishu_app_secret=os.getenv("FEISHU_APP_SECRET"),
            feishu_receive_id=os.getenv("FEISHU_RECEIVE_ID"),
            feishu_receive_id_type=os.getenv("FEISHU_RECEIVE_ID_TYPE", "open_id"),
            feishu_base_url=os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/"),
            feishu_doc_folder_token=os.getenv("FEISHU_DOC_FOLDER_TOKEN"),
            feishu_doc_url_base=os.getenv("FEISHU_DOC_URL_BASE"),
            report_dir=Path(os.getenv("REPORT_DIR", "reports")),
            state_file=Path(os.getenv("STATE_FILE", "data/processed_mrs.json")),
        )
