from mr_auto_reviewer.ai_reviewer import AutoReviewer
from mr_auto_reviewer.models import Change, CodeContext, MergeRequest
from mr_auto_reviewer.openclaw_reviewer import OpenClawReviewer


def _mr() -> MergeRequest:
    return MergeRequest(
        project_id=1,
        iid=9,
        title="feat: add auth",
        web_url="https://gitlab.example.com/group/repo/-/merge_requests/9",
        source_branch="feature/auth",
        target_branch="main",
        author="alice",
        sha="1234567890",
        description="增加鉴权",
        changes=[Change(new_path="auth.py", diff="+def check_token(): pass")],
    )


def test_auto_reviewer_build_prompt_includes_review_principles(monkeypatch):
    monkeypatch.setattr(
        "mr_auto_reviewer.ai_reviewer.load_review_principles",
        lambda: "动态原则: 重点找遗漏，不对日志精度较真。",
    )

    reviewer = AutoReviewer(api_key=None, model="gpt-test")

    prompt = reviewer._build_prompt(_mr())

    assert "动态原则: 重点找遗漏，不对日志精度较真。" in prompt


def test_auto_reviewer_build_prompt_includes_repo_cr_md_when_present(monkeypatch):
    monkeypatch.setattr(
        "mr_auto_reviewer.ai_reviewer.load_review_principles",
        lambda: "默认原则: 没有仓库 CR.md 时用这个。",
    )

    reviewer = AutoReviewer(api_key=None, model="gpt-test")
    mr = _mr()
    mr.repo_review_principles = "# CR.md\n- 仓库要求: 不要改日志格式。"

    prompt = reviewer._build_prompt(mr)

    assert "# CR.md" in prompt
    assert "仓库要求: 不要改日志格式。" in prompt
    assert "默认原则: 没有仓库 CR.md 时用这个。" in prompt


def test_openclaw_reviewer_build_prompt_reloads_review_principles_each_time(monkeypatch):
    values = iter(
        [
            "原则版本1: 先看关键遗漏。",
            "原则版本2: 不较真断言粒度。",
        ]
    )

    monkeypatch.setattr(
        "mr_auto_reviewer.openclaw_reviewer.load_review_principles",
        lambda: next(values),
    )

    reviewer = OpenClawReviewer(openclaw_bin="/usr/local/bin/openclaw")

    first_prompt = reviewer._build_prompt(_mr())
    second_prompt = reviewer._build_prompt(_mr())

    assert "原则版本1: 先看关键遗漏。" in first_prompt
    assert "原则版本2: 不较真断言粒度。" in second_prompt


def test_openclaw_reviewer_build_prompt_includes_related_code_context(monkeypatch):
    monkeypatch.setattr(
        "mr_auto_reviewer.openclaw_reviewer.load_review_principles",
        lambda: "原则版本: 重点关注遗漏。",
    )

    reviewer = OpenClawReviewer(openclaw_bin="/usr/local/bin/openclaw")
    mr = _mr()
    mr.related_context = [
        CodeContext(
            path="service/DanubeNewsLoader.java",
            depth=1,
            reason="imported_by_changed_file",
            content="public class DanubeNewsLoader { Map loadAsMap() { return null; } }",
        )
    ]

    prompt = reviewer._build_prompt(mr)

    assert "关联代码上下文" in prompt
    assert "service/DanubeNewsLoader.java" in prompt


def test_openclaw_reviewer_build_prompt_mentions_repo_cr_md_priority(monkeypatch):
    monkeypatch.setattr(
        "mr_auto_reviewer.openclaw_reviewer.load_review_principles",
        lambda: "默认原则: 风险优先。",
    )

    reviewer = OpenClawReviewer(openclaw_bin="/usr/local/bin/openclaw")
    mr = _mr()
    mr.repo_review_principles = "# CR.md\n- 仓库要求: 优先兼容性。"

    prompt = reviewer._build_prompt(mr)

    assert "# CR.md" in prompt
    assert "仓库要求: 优先兼容性。" in prompt
    assert "仓库级 CR.md" in prompt
