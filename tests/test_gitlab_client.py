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

class MockAuthor:
    def __init__(self, username):
        self.username = username

class MockNote:
    def __init__(self, body, author_username):
        self.body = body
        self.author = MockAuthor(author_username)
        self.saved = False

    def save(self):
        self.saved = True

class MockNotesManager:
    def __init__(self, notes):
        self._notes = notes
        self.created = []

    def list(self, all=False):
        return self._notes

    def create(self, data):
        self.created.append(data)

class MockMergeRequest:
    def __init__(self, notes=None):
        self.notes = MockNotesManager(notes or [])

class MockMergeRequestsManager:
    def __init__(self, mr):
        self.mr = mr

    def get(self, iid):
        return self.mr

class MockProject:
    def __init__(self, mr):
        self.mergerequests = MockMergeRequestsManager(mr)

class MockProjectsManager:
    def __init__(self, project):
        self.project = project

    def get(self, project_id):
        return self.project

class MockGitlabClient:
    def __init__(self, project):
        self.projects = MockProjectsManager(project)

def test_token_comment_creates_new(monkeypatch):
    mr = MockMergeRequest([MockNote("old body", "someone_else")])
    client = GitLabMRClient(
        gitlab_url="https://gitlab.example.com",
        reviewer_username="bot",
        private_token="secret",
    )
    monkeypatch.setattr(client, "_connect", lambda: MockGitlabClient(MockProject(mr)))
    
    client.create_merge_request_comment(
        project_id=1,
        iid=2,
        body="hello",
    )
    
    assert len(mr.notes.created) == 1
    assert mr.notes.created[0] == {"body": "hello"}
    assert mr.notes._notes[0].saved is False

def test_token_comment_updates_existing(monkeypatch):
    existing_note = MockNote("old body", "bot")
    mr = MockMergeRequest([existing_note])
    client = GitLabMRClient(
        gitlab_url="https://gitlab.example.com",
        reviewer_username="bot",
        private_token="secret",
    )
    monkeypatch.setattr(client, "_connect", lambda: MockGitlabClient(MockProject(mr)))
    
    client.create_merge_request_comment(
        project_id=1,
        iid=2,
        body="hello",
    )
    
    assert len(mr.notes.created) == 0
    assert existing_note.body == "hello"
    assert existing_note.saved is True

