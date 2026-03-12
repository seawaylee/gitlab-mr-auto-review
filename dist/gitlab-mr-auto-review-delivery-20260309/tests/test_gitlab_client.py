from mr_auto_reviewer.gitlab_client import GitLabMRClient


class DummyResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.get_urls = []
        self.post_headers = None
        self.post_url = ""
        self.post_payload = None

    def get(self, url, verify, timeout):
        self.get_urls.append(url)
        return DummyResponse(
            text='<html><head><meta name="csrf-token" content="csrf-test-token"></head></html>'
        )

    def post(self, url, json, verify, timeout, headers=None):
        self.post_url = url
        self.post_payload = json
        self.post_headers = headers or {}
        return DummyResponse(status_code=201, payload={"id": 1}, text='{"id":1}')


def test_create_merge_request_comment_by_web_session_sets_csrf_headers(monkeypatch):
    session = FakeSession()
    client = GitLabMRClient(
        gitlab_url="https://gitlab.example.com",
        reviewer_username="alice",
        username="alice",
        password="secret",
        private_token=None,
    )

    monkeypatch.setattr(client, "_login_web_session", lambda: session)

    client.create_merge_request_comment(
        project_id=1,
        iid=2,
        body="hello",
        mr_web_url="https://gitlab.example.com/group/repo/-/merge_requests/2",
    )

    assert session.get_urls == ["https://gitlab.example.com/group/repo/-/merge_requests/2"]
    assert session.post_url.endswith("/api/v4/projects/1/merge_requests/2/notes")
    assert session.post_payload == {"body": "hello"}
    assert session.post_headers.get("X-CSRF-Token") == "csrf-test-token"
    assert session.post_headers.get("Referer") == "https://gitlab.example.com/group/repo/-/merge_requests/2"
