import json
from pathlib import Path
from subprocess import CompletedProcess

from mr_auto_reviewer.models import MergeRequest
from mr_auto_reviewer.sohu_client import SohuAgentClient


class DummyResponse:
    def __init__(self):
        self.called = False

    def raise_for_status(self):
        self.called = True


def _mr() -> MergeRequest:
    return MergeRequest(
        project_id=1,
        iid=2,
        title="feat: auth",
        web_url="https://gitlab.example.com/group/repo/-/merge_requests/2",
        source_branch="feature/auth",
        target_branch="main",
        author="reviewer",
        sha="abcdef",
    )


def test_push_report_uses_openclaw_and_resolves_recent_target(tmp_path, monkeypatch):
    home = tmp_path / "home"
    sessions = home / ".openclaw" / "agents" / "sohu" / "sessions"
    sessions.mkdir(parents=True)
    sessions_file = sessions / "sessions.json"
    sessions_file.write_text(
        json.dumps(
            {
                "agent:sohu:direct:ou_test": {
                    "lastChannel": "feishu",
                    "lastTo": "user:ou_test",
                    "lastAccountId": "sohu",
                    "updatedAt": 999,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("mr_auto_reviewer.sohu_client.Path.home", lambda: home)
    monkeypatch.setattr("mr_auto_reviewer.sohu_client.shutil.which", lambda _: "/usr/local/bin/openclaw")

    captured = {}

    def fake_run(command, check, capture_output, text, timeout):
        captured["command"] = command
        return CompletedProcess(command, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("mr_auto_reviewer.sohu_client.subprocess.run", fake_run)

    report_path = tmp_path / "report.md"
    report_path.write_text("# Merge Request Review 报告\n\n## 这次 MR 在做什么\n\n新增登录鉴权\n", encoding="utf-8")

    client = SohuAgentClient(webhook_url=None, push_mode="openclaw")
    client.push_report(
        _mr(),
        report_path.read_text(encoding="utf-8"),
        report_path,
        doc_url="https://sohu.feishu.cn/docx/doc-test",
    )

    cmd = captured["command"]
    assert cmd[:3] == ["/usr/local/bin/openclaw", "message", "send"]
    assert "--account" in cmd
    assert "sohu" in cmd
    assert "--target" in cmd
    assert "user:ou_test" in cmd
    assert "--media" not in cmd
    message = cmd[cmd.index("--message") + 1]
    assert "飞书文档" in message
    assert "https://sohu.feishu.cn/docx/doc-test" in message


def test_push_report_uses_webhook_when_configured(monkeypatch, tmp_path):
    response = DummyResponse()
    called = {}

    def fake_post(url, json, timeout):
        called["url"] = url
        called["payload"] = json
        called["timeout"] = timeout
        return response

    monkeypatch.setattr("mr_auto_reviewer.sohu_client.requests.post", fake_post)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("subprocess should not be called when webhook is configured")

    monkeypatch.setattr("mr_auto_reviewer.sohu_client.subprocess.run", fail_run)

    report_path = tmp_path / "report.md"
    report_path.write_text("demo", encoding="utf-8")

    client = SohuAgentClient(webhook_url="https://sohu.example.com/webhook", push_mode="webhook")
    client.push_report(_mr(), "demo", report_path)

    assert called["url"] == "https://sohu.example.com/webhook"
    assert response.called is True


def test_push_report_openclaw_dry_run_does_not_call_subprocess(monkeypatch, tmp_path):
    called = {"run": 0}

    def fake_run(*_args, **_kwargs):
        called["run"] += 1
        raise AssertionError("subprocess should not run in dry-run mode")

    monkeypatch.setattr("mr_auto_reviewer.sohu_client.subprocess.run", fake_run)

    report_path = tmp_path / "report.md"
    report_path.write_text("# test", encoding="utf-8")

    client = SohuAgentClient(
        webhook_url=None,
        push_mode="openclaw",
        dry_run=True,
        openclaw_bin="",
        openclaw_target="user:ou_test",
    )
    client.push_report(_mr(), "# test", report_path)

    assert called["run"] == 0


def test_push_report_openclaw_with_attachment_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr("mr_auto_reviewer.sohu_client.shutil.which", lambda _: "/usr/local/bin/openclaw")

    captured = {}

    def fake_run(command, check, capture_output, text, timeout):
        captured["command"] = command
        return CompletedProcess(command, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("mr_auto_reviewer.sohu_client.subprocess.run", fake_run)

    report_path = tmp_path / "report.md"
    report_path.write_text("# test", encoding="utf-8")

    client = SohuAgentClient(
        webhook_url=None,
        push_mode="openclaw",
        openclaw_target="user:ou_test",
        attach_report=True,
    )
    client.push_report(_mr(), "# test", report_path, doc_url=None)

    cmd = captured["command"]
    assert "--media" in cmd
