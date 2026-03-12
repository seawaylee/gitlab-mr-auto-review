import base64
import logging
from pathlib import PurePosixPath
import re
from typing import List, Optional
from urllib.parse import quote

import gitlab
import requests
import urllib3

from .models import Change, MergeRequest
from .related_code_loader import RelatedCodeLoader

LOGGER = logging.getLogger(__name__)


class GitLabMRClient:
    def __init__(
        self,
        gitlab_url: str,
        reviewer_username: str,
        review_scope: str = "reviewer_or_assignee",
        username: Optional[str] = None,
        password: Optional[str] = None,
        private_token: Optional[str] = None,
        ssl_verify=True,
        max_files: int = 20,
        max_diff_chars: int = 6000,
        max_related_files: int = 8,
        max_related_depth: int = 2,
        max_related_chars: int = 4000,
    ):
        self.gitlab_url = gitlab_url
        self.reviewer_username = reviewer_username
        self.review_scope = (review_scope or "reviewer_or_assignee").strip().lower()
        self.username = username
        self.password = password
        self.private_token = private_token
        self.ssl_verify = ssl_verify
        if ssl_verify is False:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.max_files = max_files
        self.max_diff_chars = max_diff_chars
        self.max_related_files = max_related_files
        self.max_related_depth = max_related_depth
        self.max_related_chars = max_related_chars
        self._client: Optional[gitlab.Gitlab] = None
        self._session: Optional[requests.Session] = None

    def _connect(self) -> gitlab.Gitlab:
        if self._client:
            return self._client

        if self.private_token:
            client = gitlab.Gitlab(
                self.gitlab_url,
                private_token=self.private_token,
                ssl_verify=self.ssl_verify,
            )
            client.auth()
            self._client = client
            return client

        raise ValueError("Provide GITLAB_PRIVATE_TOKEN or GITLAB_USERNAME + GITLAB_PASSWORD")

    def list_review_mrs(self) -> List[MergeRequest]:
        if self.private_token:
            return self._list_review_mrs_by_private_token()
        if self.username and self.password:
            return self._list_review_mrs_by_web_session()
        raise ValueError("Provide GITLAB_PRIVATE_TOKEN or GITLAB_USERNAME + GITLAB_PASSWORD")

    def create_merge_request_comment(
        self,
        project_id: int,
        iid: int,
        body: str,
        mr_web_url: Optional[str] = None,
    ) -> None:
        content = (body or "").strip()
        if not content:
            raise ValueError("comment body is empty")

        if self.private_token:
            client = self._connect()
            project = client.projects.get(project_id)
            merge_request = project.mergerequests.get(iid)
            bot_username = self.reviewer_username or self.username

            # Find existing note
            notes = merge_request.notes.list(all=True)
            for note in notes:
                if getattr(note.author, "username", "") == bot_username or (
                    isinstance(note.author, dict) and note.author.get("username") == bot_username
                ):
                    note.body = content
                    note.save()
                    return

            # If not found, create new
            merge_request.notes.create({"body": content})
            return

        if self.username and self.password:
            session = self._login_web_session()
            headers = self._build_session_api_headers(session=session, mr_web_url=mr_web_url)

            notes_payload = self._request_json(
                 session=session,
                 path=f"/api/v4/projects/{project_id}/merge_requests/{iid}/notes",
            )
            bot_username = self.reviewer_username or self.username

            for note in notes_payload:
                if isinstance(note, dict) and note.get('author', {}).get('username') == bot_username:
                    self._put_json(
                        session=session,
                        path=f"/api/v4/projects/{project_id}/merge_requests/{iid}/notes/{note['id']}",
                        payload={"body": content},
                        headers=headers,
                    )
                    return

            self._post_json(
                session=session,
                path=f"/api/v4/projects/{project_id}/merge_requests/{iid}/notes",
                payload={"body": content},
                headers=headers,
            )
            return

        raise ValueError("Provide GITLAB_PRIVATE_TOKEN or GITLAB_USERNAME + GITLAB_PASSWORD")

    def _list_review_mrs_by_private_token(self) -> List[MergeRequest]:
        client = self._connect()
        remote_mrs = self._list_mr_summaries_by_private_token(client)
        output: List[MergeRequest] = []
        for remote_mr in remote_mrs:
            try:
                output.append(self._load_detail(client, remote_mr.project_id, remote_mr.iid))
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("skip MR %s/%s: %s", remote_mr.project_id, remote_mr.iid, exc)
        return output

    def _list_mr_summaries_by_private_token(self, client: gitlab.Gitlab):
        queries = self._build_scope_queries()
        dedup = {}
        for query in queries:
            remote_mrs = client.mergerequests.list(
                state="opened",
                scope="all",
                get_all=True,
                **query,
            )
            for remote_mr in remote_mrs:
                key = (int(remote_mr.project_id), int(remote_mr.iid))
                dedup[key] = remote_mr
        return list(dedup.values())

    def _list_review_mrs_by_web_session(self) -> List[MergeRequest]:
        session = self._login_web_session()
        output: List[MergeRequest] = []
        page = 1
        while True:
            payload = self._list_mr_summaries_by_web_session(session, page=page)
            if not isinstance(payload, list) or not payload:
                break

            for remote_mr in payload:
                try:
                    project_id = int(remote_mr.get("project_id"))
                    iid = int(remote_mr.get("iid"))
                    output.append(self._load_detail_by_web_session(session, project_id, iid))
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception(
                        "skip MR by session %s/%s: %s",
                        remote_mr.get("project_id"),
                        remote_mr.get("iid"),
                        exc,
                    )
            page += 1
        return output

    def _list_mr_summaries_by_web_session(self, session: requests.Session, page: int) -> List[dict]:
        dedup = {}
        for query in self._build_scope_queries():
            params = {
                "state": "opened",
                "scope": "all",
                "per_page": 100,
                "page": page,
            }
            params.update(query)
            payload = self._request_json(
                session=session,
                path="/api/v4/merge_requests",
                params=params,
            )
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                try:
                    key = (int(item.get("project_id")), int(item.get("iid")))
                except Exception:
                    continue
                dedup[key] = item
        return list(dedup.values())

    def _build_scope_queries(self) -> List[dict]:
        if self.review_scope == "reviewer":
            return [{"reviewer_username": self.reviewer_username}]
        if self.review_scope == "assignee":
            return [{"assignee_username": self.reviewer_username}]
        if self.review_scope == "reviewer_or_assignee":
            return [
                {"reviewer_username": self.reviewer_username},
                {"assignee_username": self.reviewer_username},
            ]
        return [{"reviewer_username": self.reviewer_username}]

    def _login_web_session(self) -> requests.Session:
        if self._session:
            return self._session
        if not self.username or not self.password:
            raise ValueError("GITLAB_USERNAME and GITLAB_PASSWORD are required for web session login")

        session = requests.Session()
        sign_in_url = f"{self.gitlab_url}/users/sign_in"
        response = session.get(sign_in_url, verify=self.ssl_verify, timeout=30)
        response.raise_for_status()

        token = self._extract_authenticity_token(response.text)
        if not token:
            raise RuntimeError("failed to parse GitLab authenticity_token from sign in page")

        login_payload = {
            "authenticity_token": token,
            "user[login]": self.username,
            "user[password]": self.password,
            "user[remember_me]": "0",
        }
        login_response = session.post(
            sign_in_url,
            data=login_payload,
            allow_redirects=False,
            verify=self.ssl_verify,
            timeout=30,
        )
        if login_response.status_code not in (302, 303):
            raise RuntimeError(f"GitLab web login failed with status {login_response.status_code}")

        verify_response = session.get(f"{self.gitlab_url}/api/v4/user", verify=self.ssl_verify, timeout=30)
        if verify_response.status_code != 200:
            raise RuntimeError(f"GitLab API auth by web session failed with status {verify_response.status_code}")

        self._session = session
        return session

    @staticmethod
    def _extract_authenticity_token(html: str) -> str:
        match = re.search(r'name="authenticity_token" value="([^"]+)"', html or "")
        return match.group(1) if match else ""

    def _request_json(
        self,
        session: requests.Session,
        path: str,
        params: Optional[dict] = None,
    ):
        response = session.get(
            f"{self.gitlab_url}{path}",
            params=params,
            verify=self.ssl_verify,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _post_json(
        self,
        session: requests.Session,
        path: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
    ):
        response = session.post(
            f"{self.gitlab_url}{path}",
            json=payload or {},
            headers=headers or {},
            verify=self.ssl_verify,
            timeout=30,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def _put_json(
        self,
        session: requests.Session,
        path: str,
        payload: Optional[dict] = None,
        headers: Optional[dict] = None,
    ):
        response = session.put(
            f"{self.gitlab_url}{path}",
            json=payload or {},
            headers=headers or {},
            verify=self.ssl_verify,
            timeout=30,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def _build_session_api_headers(
        self,
        session: requests.Session,
        mr_web_url: Optional[str] = None,
    ) -> dict:
        csrf_token = self._load_csrf_token(session=session, mr_web_url=mr_web_url)
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        if mr_web_url:
            headers["Referer"] = mr_web_url
        return headers

    def _load_csrf_token(
        self,
        session: requests.Session,
        mr_web_url: Optional[str] = None,
    ) -> str:
        urls: List[str] = []
        if mr_web_url:
            urls.append(str(mr_web_url))
        urls.append(f"{self.gitlab_url}/")

        for url in urls:
            try:
                response = session.get(url, verify=self.ssl_verify, timeout=30)
                response.raise_for_status()
                token = self._extract_csrf_token(response.text)
                if token:
                    return token
            except Exception:
                continue
        return ""

    @staticmethod
    def _extract_csrf_token(html: str) -> str:
        text = html or ""
        patterns = [
            r'name="csrf-token" content="([^"]+)"',
            r'content="([^"]+)" name="csrf-token"',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""

    def _load_detail(self, client: gitlab.Gitlab, project_id: int, iid: int) -> MergeRequest:
        project = client.projects.get(project_id)
        detailed = project.mergerequests.get(iid)
        payload = detailed.changes()
        changes = payload.get("changes", [])

        model_changes = []
        for item in changes[: self.max_files]:
            diff = item.get("diff") or ""
            model_changes.append(
                Change(
                    old_path=item.get("old_path"),
                    new_path=item.get("new_path") or item.get("old_path") or "unknown",
                    diff=diff[: self.max_diff_chars],
                )
            )

        sha = str(detailed.attributes.get("sha") or "")
        if not sha:
            diff_refs = detailed.attributes.get("diff_refs")
            if isinstance(diff_refs, dict):
                sha = str(diff_refs.get("head_sha") or "")
        related_context = self._load_related_context(
            file_loader=lambda path, ref: self._fetch_file_content_by_private_token(
                project=project,
                file_path=path,
                ref=ref,
            ),
            path_resolver=lambda path, ref: self._resolve_repository_path_by_private_token(
                project_id=project_id,
                unresolved_path=path,
                ref=ref,
            ),
            changes=model_changes,
            ref=sha,
        )
        repo_review_principles = self._fetch_file_content_by_private_token(
            project=project,
            file_path="CR.md",
            ref=sha,
        )

        return MergeRequest(
            project_id=project_id,
            iid=iid,
            title=detailed.attributes.get("title", ""),
            web_url=detailed.attributes.get("web_url", ""),
            source_branch=detailed.attributes.get("source_branch", ""),
            target_branch=detailed.attributes.get("target_branch", ""),
            author=(detailed.attributes.get("author") or {}).get("username", "unknown"),
            sha=sha,
            description=detailed.attributes.get("description") or "",
            changes=model_changes,
            related_context=related_context,
            repo_review_principles=repo_review_principles,
        )

    def _load_detail_by_web_session(
        self,
        session: requests.Session,
        project_id: int,
        iid: int,
    ) -> MergeRequest:
        payload = self._request_json(
            session=session,
            path=f"/api/v4/projects/{project_id}/merge_requests/{iid}/changes",
        )
        changes = payload.get("changes", []) if isinstance(payload, dict) else []

        model_changes = []
        for item in changes[: self.max_files]:
            if not isinstance(item, dict):
                continue
            diff = item.get("diff") or ""
            model_changes.append(
                Change(
                    old_path=item.get("old_path"),
                    new_path=item.get("new_path") or item.get("old_path") or "unknown",
                    diff=diff[: self.max_diff_chars],
                )
            )

        author = payload.get("author") if isinstance(payload, dict) else {}
        if not isinstance(author, dict):
            author = {}
        sha = ""
        if isinstance(payload, dict):
            sha = str(payload.get("sha") or "")
            if not sha:
                diff_refs = payload.get("diff_refs") if isinstance(payload.get("diff_refs"), dict) else {}
                sha = str((diff_refs or {}).get("head_sha") or "")
        related_context = self._load_related_context(
            file_loader=lambda path, ref: self._fetch_file_content_by_web_session(
                session=session,
                project_id=project_id,
                file_path=path,
                ref=ref,
            ),
            path_resolver=lambda path, ref: self._resolve_repository_path_by_web_session(
                session=session,
                project_id=project_id,
                unresolved_path=path,
                ref=ref,
            ),
            changes=model_changes,
            ref=sha,
        )
        repo_review_principles = self._fetch_file_content_by_web_session(
            session=session,
            project_id=project_id,
            file_path="CR.md",
            ref=sha,
        )

        return MergeRequest(
            project_id=project_id,
            iid=iid,
            title=str(payload.get("title") or ""),
            web_url=str(payload.get("web_url") or ""),
            source_branch=str(payload.get("source_branch") or ""),
            target_branch=str(payload.get("target_branch") or ""),
            author=str(author.get("username") or "unknown"),
            sha=sha,
            description=str(payload.get("description") or ""),
            changes=model_changes,
            related_context=related_context,
            repo_review_principles=repo_review_principles,
        )

    def _load_related_context(self, file_loader, path_resolver, changes: List[Change], ref: str):
        if not ref or not changes:
            return []
        loader = RelatedCodeLoader(
            file_loader=file_loader,
            path_resolver=path_resolver,
            max_context_files=self.max_related_files,
            max_depth=self.max_related_depth,
            max_file_chars=self.max_related_chars,
        )
        try:
            return loader.load(changes=changes, ref=ref)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("load related context failed: %s", exc)
            return []

    @staticmethod
    def _decode_repository_file_content(payload) -> str:
        if not isinstance(payload, dict):
            return ""
        content = payload.get("content")
        if not content:
            return ""
        encoding = str(payload.get("encoding") or "").lower()
        if encoding == "base64":
            try:
                decoded = base64.b64decode(content)
                return decoded.decode("utf-8", errors="replace")
            except Exception:
                return ""
        return str(content)

    def _fetch_file_content_by_private_token(self, project, file_path: str, ref: str) -> str:
        try:
            remote_file = project.files.get(file_path=file_path, ref=ref)
        except Exception:
            return ""
        payload = {
            "content": getattr(remote_file, "content", ""),
            "encoding": getattr(remote_file, "encoding", ""),
        }
        return self._decode_repository_file_content(payload)

    def _fetch_file_content_by_web_session(
        self,
        session: requests.Session,
        project_id: int,
        file_path: str,
        ref: str,
    ) -> str:
        try:
            payload = self._request_json(
                session=session,
                path=f"/api/v4/projects/{project_id}/repository/files/{quote(file_path, safe='')}",
                params={"ref": ref},
            )
        except Exception:
            return ""
        return self._decode_repository_file_content(payload)

    def _resolve_repository_path_by_private_token(
        self,
        project_id: int,
        unresolved_path: str,
        ref: str,
    ) -> list[str]:
        if not self.private_token:
            return []
        search_term = PurePosixPath(unresolved_path).stem
        if not search_term:
            return []
        try:
            response = requests.get(
                f"{self.gitlab_url}/api/v4/projects/{project_id}/search",
                params={"scope": "blobs", "search": search_term, "ref": ref},
                headers={"PRIVATE-TOKEN": self.private_token},
                verify=self.ssl_verify,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []
        return self._filter_search_paths(payload, unresolved_path)

    def _resolve_repository_path_by_web_session(
        self,
        session: requests.Session,
        project_id: int,
        unresolved_path: str,
        ref: str,
    ) -> list[str]:
        search_term = PurePosixPath(unresolved_path).stem
        if not search_term:
            return []
        try:
            payload = self._request_json(
                session=session,
                path=f"/api/v4/projects/{project_id}/search",
                params={"scope": "blobs", "search": search_term, "ref": ref},
            )
        except Exception:
            return []
        return self._filter_search_paths(payload, unresolved_path)

    @staticmethod
    def _filter_search_paths(payload, unresolved_path: str) -> list[str]:
        if not isinstance(payload, list):
            return []

        target = PurePosixPath(unresolved_path)
        target_name = target.name
        target_parts = target.parts
        scored: list[tuple[int, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("filename") or "").strip()
            if not path:
                continue
            candidate = PurePosixPath(path)
            if candidate.name != target_name:
                continue

            overlap = 0
            for left, right in zip(reversed(target_parts), reversed(candidate.parts)):
                if left != right:
                    break
                overlap += 1
            scored.append((overlap, path))

        scored.sort(key=lambda item: (-item[0], item[1]))
        output: list[str] = []
        seen: set[str] = set()
        for _, path in scored:
            if path in seen:
                continue
            seen.add(path)
            output.append(path)
        return output[:3]
