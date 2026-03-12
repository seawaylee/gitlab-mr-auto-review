# GitLab Merge Request AI Review: Update existing comments

## Overview
Currently, the AI Reviewer creates a new comment on a GitLab Merge Request every time a review pipeline runs. This causes MRs with multiple pushed updates to become cluttered with duplicate and outdated review comments from the bot.
We need to change the behavior to **overwrite an existing comment** if the bot has already posted a review for the MR.

## Context
When a review payload is generated, the pipeline (`pipeline.py`) currently calls `gitlab_client.create_merge_request_comment()`, which blindly issues a POST request to add a new note.

## Design

### 1. Identify Existing Bot Comments
We will identify our existing comment by checking the `author.username` of the notes in the MR thread. The username to look for is `GITLAB_REVIEWER_USERNAME` (which falls back to `GITLAB_USERNAME` and represents the bot's identity).

### 2. Update `GitLabMRClient` Logic
- **Determine Bot Username**: Store the effective bot identity during initialization or fetch it dynamically to use for matching.
- **`upsert_merge_request_comment`**:
  We will modify `create_merge_request_comment` to act as an "upsert" mechanism (or create a new method and modify `pipeline.py` to use it).
  - First, fetch the notes payload for the MR.
  - Iterate through the returned comments to find a note matching the bot's account username.

#### Support for Both Authentication Methods:
- **Private Token (`python-gitlab`)**:
  - `notes = merge_request.notes.list(all=True)`
  - Find `note` where `note.author['username'] == bot_username`.
  - Update found: `note.body = content; note.save()`
  - Not found: `merge_request.notes.create({"body": content})`

- **Web Session (REST API with token auth via session cookie)**:
  - `GET /api/v4/projects/{id}/merge_requests/{iid}/notes`
  - Find item in response where `author['username'] == bot_username`.
  - Update found: `_put_json(...)` to `PUT /api/v4/projects/{id}/merge_requests/{iid}/notes/{note_id}` using `body=content`.
  - Not found: fallback to existing `_post_json(...)` to create it.

## Edge Cases & Error Handling
- Only overwriting comments from the specific bot username.
- If pagination of notes is large, we might need a paginated fetch (or at least `all=True` for the client SDK) for the Web Session mode. However MRs shouldn't easily exceed hundreds of bot comments, and scanning recent notes should suffice since the bot typically modifies the latest or leaves exactly one comment.

## Testing Strategy
- Create mock tests to ensure our payload correctly issues `PUT` when a comment by the AI user exists, and `POST` otherwise.
- Validate matching via `bot_username` so we don't accidentally update a real human developer's reviews.
