from pathlib import Path

from mr_auto_reviewer.models import MergeRequest, ReviewResult
from mr_auto_reviewer.pipeline import MRReviewPipeline
from mr_auto_reviewer.state_store import JsonStateStore


class StubGitLabClient:
    def __init__(self, mrs):
        self._mrs = mrs
        self.comments = []
        self.events = []

    def list_review_mrs(self):
        return self._mrs

    def create_merge_request_comment(self, project_id, iid, body, mr_web_url=None):
        self.comments.append((project_id, iid, body))
        self.events.append("gitlab_comment")


class StubReviewer:
    def __init__(self):
        self.called = []

    def review(self, mr):
        self.called.append(mr.unique_key)
        return ReviewResult(
            mr_purpose="实现登录态校验",
            summary="逻辑基本可行",
            verdict="approve",
            risk_level="low",
            findings=[],
            suggestions=["补充边界测试"],
        )


class StubSohuClient:
    def __init__(self, events):
        self.payloads = []
        self.events = events

    def push_report(self, mr, markdown, report_path, doc_url=None):
        self.payloads.append((mr.unique_key, report_path.name, markdown, doc_url))
        self.events.append("sohu_push")


class StubFeishuClient:
    def __init__(self, events):
        self.sent = []
        self.events = events

    def publish_markdown_doc(self, markdown, title):
        self.sent.append((title, markdown))
        self.events.append("feishu_doc")
        return "https://sohu.feishu.cn/docx/doc-test"


def _mr(iid: int, sha: str) -> MergeRequest:
    return MergeRequest(
        project_id=7,
        iid=iid,
        title=f"feat: mr-{iid}",
        web_url=f"https://gitlab.example.com/group/repo/-/merge_requests/{iid}",
        source_branch=f"feature/{iid}",
        target_branch="main",
        author="bob",
        sha=sha,
    )


def test_run_once_processes_only_unprocessed_mrs(tmp_path):
    mr_done = _mr(iid=1, sha="old")
    mr_new = _mr(iid=2, sha="new")
    state = JsonStateStore(tmp_path / "state.json")
    state.mark_processed(mr_done.unique_key)

    reviewer = StubReviewer()
    gitlab = StubGitLabClient([mr_done, mr_new])
    sohu = StubSohuClient(events=gitlab.events)
    feishu = StubFeishuClient(events=gitlab.events)

    pipeline = MRReviewPipeline(
        gitlab_client=gitlab,
        reviewer=reviewer,
        sohu_client=sohu,
        feishu_client=feishu,
        state_store=state,
        report_dir=tmp_path,
    )

    results = pipeline.run_once()

    assert [item.mr_key for item in results] == [mr_new.unique_key]
    assert reviewer.called == [mr_new.unique_key]
    assert len(sohu.payloads) == 1
    assert sohu.payloads[0][0] == mr_new.unique_key
    assert sohu.payloads[0][3] == "https://sohu.feishu.cn/docx/doc-test"
    assert len(feishu.sent) == 1
    assert len(gitlab.comments) == 1
    assert gitlab.comments[0][0] == mr_new.project_id
    assert gitlab.comments[0][1] == mr_new.iid
    assert "## 自动化 Code Review（行业规范）" in gitlab.comments[0][2]
    assert gitlab.events == ["gitlab_comment", "feishu_doc", "sohu_push"]
    assert state.is_processed(mr_new.unique_key)
