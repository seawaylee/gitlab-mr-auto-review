from subprocess import CompletedProcess

from mr_auto_reviewer.models import Change, MergeRequest
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


def test_openclaw_reviewer_parses_payload_text_json(monkeypatch):
    stdout = (
        '{"status":"ok","result":{"payloads":[{"text":"{\\"mr_purpose\\":\\"新增鉴权\\",'
        '\\"summary\\":\\"核心逻辑可读\\",\\"verdict\\":\\"comment\\",'
        '\\"risk_level\\":\\"low\\",\\"findings\\":[\\"缺少异常处理\\"],'
        '\\"suggestions\\":[\\"补充单测\\"]}"}]}}'
    )

    def fake_run(command, check, capture_output, text, timeout):
        return CompletedProcess(command, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("mr_auto_reviewer.openclaw_reviewer.subprocess.run", fake_run)

    reviewer = OpenClawReviewer(agent_id="sohu", timeout_seconds=10, local=False, openclaw_bin="/usr/local/bin/openclaw")
    result = reviewer.review(_mr())

    assert result.mr_purpose == "新增鉴权"
    assert result.verdict == "comment"
    assert result.risk_level == "low"
    assert result.findings == ["缺少异常处理"]


def test_openclaw_reviewer_fallback_on_failure(monkeypatch):
    def fake_run(command, check, capture_output, text, timeout):
        return CompletedProcess(command, returncode=1, stdout="", stderr="failed")

    monkeypatch.setattr("mr_auto_reviewer.openclaw_reviewer.subprocess.run", fake_run)

    reviewer = OpenClawReviewer(agent_id="sohu", timeout_seconds=10, local=False, openclaw_bin="/usr/local/bin/openclaw")
    result = reviewer.review(_mr())

    assert result.verdict == "comment"
    assert "fallback" in result.findings[0]


def test_openclaw_reviewer_formats_dict_findings(monkeypatch):
    stdout = (
        '{\"status\":\"ok\",\"result\":{\"payloads\":[{\"text\":\"{'
        '\\\"mr_purpose\\\":\\\"改造\\\",\\\"summary\\\":\\\"ok\\\",\\\"verdict\\\":\\\"comment\\\",'
        '\\\"risk_level\\\":\\\"medium\\\",\\\"findings\\\":[{'
        '\\\"severity\\\":\\\"high\\\",\\\"title\\\":\\\"依赖升级风险\\\",'
        '\\\"details\\\":\\\"回归面较大\\\",\\\"file\\\":\\\"pom.xml\\\"}],'
        '\\\"suggestions\\\":[\\\"先做兼容验证\\\"]}\"}]}}'
    )

    def fake_run(command, check, capture_output, text, timeout):
        return CompletedProcess(command, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("mr_auto_reviewer.openclaw_reviewer.subprocess.run", fake_run)
    reviewer = OpenClawReviewer(agent_id="sohu", timeout_seconds=10, local=False, openclaw_bin="/usr/local/bin/openclaw")
    result = reviewer.review(_mr())

    assert result.findings[0].startswith("[high] 依赖升级风险")
    assert "文件: pom.xml" in result.findings[0]
    assert "回归面较大" in result.findings[0]


def test_openclaw_reviewer_formats_stringified_dict_findings(monkeypatch):
    import json

    review_json = json.dumps(
        {
            "mr_purpose": "改造",
            "summary": "ok",
            "verdict": "comment",
            "risk_level": "medium",
            "findings": ["{'severity': 'high', 'file': 'pom.xml', 'detail': '依赖升级'}"],
            "suggestions": ["先做回归"],
        },
        ensure_ascii=False,
    )
    stdout = json.dumps(
        {
            "status": "ok",
            "result": {"payloads": [{"text": review_json}]},
        },
        ensure_ascii=False,
    )

    def fake_run(command, check, capture_output, text, timeout):
        return CompletedProcess(command, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("mr_auto_reviewer.openclaw_reviewer.subprocess.run", fake_run)
    reviewer = OpenClawReviewer(agent_id="sohu", timeout_seconds=10, local=False, openclaw_bin="/usr/local/bin/openclaw")
    result = reviewer.review(_mr())

    assert result.findings[0].startswith("[high]")
    assert "文件: pom.xml" in result.findings[0]
    assert "依赖升级" in result.findings[0]
