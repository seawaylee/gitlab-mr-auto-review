from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import MergeRequest
from .reporting import build_gitlab_comment, build_markdown_report


@dataclass
class ProcessResult:
    mr_key: str
    report_path: Optional[Path]
    status: str
    error: Optional[str] = None


class MRReviewPipeline:
    def __init__(
        self,
        gitlab_client,
        reviewer,
        sohu_client,
        feishu_client,
        state_store,
        report_dir: Path,
    ):
        self.gitlab_client = gitlab_client
        self.reviewer = reviewer
        self.sohu_client = sohu_client
        self.feishu_client = feishu_client
        self.state_store = state_store
        self.report_dir = Path(report_dir)

    def run_once(self) -> list[ProcessResult]:
        results: List[ProcessResult] = []
        for mr in self.gitlab_client.list_review_mrs():
            if self.state_store.is_processed(mr.unique_key):
                continue
            results.append(self._process_single_mr(mr))
        return results

    def _process_single_mr(self, mr: MergeRequest) -> ProcessResult:
        try:
            review = self.reviewer.review(mr)
            generated_at = datetime.now(timezone.utc)
            markdown = build_markdown_report(
                mr=mr,
                review=review,
                generated_at=generated_at,
            )
            comment = build_gitlab_comment(
                mr=mr,
                review=review,
                generated_at=generated_at,
            )
            report_path = self._write_report(mr, markdown)
            self.gitlab_client.create_merge_request_comment(
                project_id=mr.project_id,
                iid=mr.iid,
                body=comment,
                mr_web_url=mr.web_url,
            )
            doc_url = self.feishu_client.publish_markdown_doc(markdown=markdown, title=mr.title)
            self.sohu_client.push_report(
                mr=mr,
                markdown=markdown,
                report_path=report_path,
                doc_url=doc_url,
            )
            self.state_store.mark_processed(mr.unique_key)
            return ProcessResult(mr_key=mr.unique_key, report_path=report_path, status="ok")
        except Exception as exc:  # noqa: BLE001
            return ProcessResult(
                mr_key=mr.unique_key,
                report_path=None,
                status="failed",
                error=str(exc),
            )

    def _write_report(self, mr: MergeRequest, markdown: str) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"mr-{mr.project_id}-{mr.iid}-{mr.sha[:8]}.md"
        path = self.report_dir / file_name
        path.write_text(markdown, encoding="utf-8")
        return path
