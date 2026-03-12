# Update Existing GitLab Comments Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Modify the AI Reviewer to update (overwrite) its existing Merge Request comment instead of creating duplicate comments on every push.

**Architecture:** We will modify `GitLabMRClient` to conditionally update a comment if one authored by our configured bot user already exists in the MR, or create a new comment otherwise. This will abstract the logic for both `private_token` and `web_session` authentication modes.

**Tech Stack:** Python, `python-gitlab` (for token auth), `requests` (for web session auth), `pytest` (for tests).

---

### Task 1: Add update note capability for Private Token Auth

**Files:**
- Modify: `src/mr_auto_reviewer/gitlab_client.py:86`
- Modify: `tests/test_main.py` (or a dedicated `tests/test_gitlab_client.py` if preferred)

**Step 1: Write the failing test**
Create/Modify tests replacing `create_merge_request_comment` to verify `upsert_merge_request_comment` or modification of existing handles token updates.

```python
# Create a test setup with mock gitlab classes to verify note.save() is called when author matches

def test_token_comment_creates_new():
    # Setup mock author != bot username
    # Assert notes.create is called
    pass

def test_token_comment_updates_existing():
    # Setup mock author == bot username
    # Assert note.save() is called
    pass
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/test_main.py -k test_token_comment`
Expected: FAIL due to unimplemented functions

**Step 3: Write minimal implementation**
Modify `create_merge_request_comment` in `gitlab_client.py`. (Assuming bot identity is available, fallback on `self.reviewer_username`)

```python
        if self.private_token:
            client = self._connect()
            project = client.projects.get(project_id)
            merge_request = project.mergerequests.get(iid)
            bot_username = self.reviewer_username or self.username

            # Find existing note
            notes = merge_request.notes.list(all=True)
            for note in notes:
                if getattr(note.author, 'username', '') == bot_username:
                    note.body = content
                    note.save()
                    return

            # If not found, create new
            merge_request.notes.create({"body": content})
            return
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/ -k test_token_comment`
Expected: PASS

**Step 5: Commit**
```bash
git add src/mr_auto_reviewer/gitlab_client.py tests/test_main.py
git commit -m "feat: Support updating existing comments for token auth"
```

---

### Task 2: Add update note capability for Web Session Auth

**Files:**
- Modify: `src/mr_auto_reviewer/gitlab_client.py:92`

**Step 1: Write the failing test**
Use mocks on `_request_json` and `_post_json` (create a mock for `_put_json` or expand `_request`).

```python
def test_session_comment_updates_existing():
    # Mock _request_json to return [{'id': 123, 'author': {'username': 'bot'}}]
    # Assert a PUT request is sent to /api/v4/projects/.../notes/123
    pass
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/ -k test_session`
Expected: FAIL

**Step 3: Write minimal implementation**
First, create `_put_json` (or similar helper if required) and modify the `web_session` path in `create_merge_request_comment`:

```python
        if self.username and self.password:
            session = self._login_web_session()
            headers = self._build_session_api_headers(session=session, mr_web_url=mr_web_url)

            # Fetch existing notes
            notes_payload = self._request_json(
                 session=session,
                 path=f"/api/v4/projects/{project_id}/merge_requests/{iid}/notes",
            )
            bot_username = self.reviewer_username or self.username

            for note in notes_payload:
                if isinstance(note, dict) and note.get('author', {}).get('username') == bot_username:
                    # Found, update via PUT
                    self._put_json(
                        session=session,
                        path=f"/api/v4/projects/{project_id}/merge_requests/{iid}/notes/{note['id']}",
                        payload={"body": content},
                        headers=headers,
                    )
                    return

            # Not found, create via POST
            self._post_json(
                session=session,
                path=f"/api/v4/projects/{project_id}/merge_requests/{iid}/notes",
                payload={"body": content},
                headers=headers,
            )
            return
```
*(Also define `_put_json` using `session.put` similar to `_post_json` if we don't have it.)*

**Step 4: Run test to verify it passes**
Run: `pytest tests/ -v`
Expected: PASS

**Step 5: Commit**
```bash
git add src/mr_auto_reviewer/gitlab_client.py
git commit -m "feat: Support updating existing comments for web session auth"
```
