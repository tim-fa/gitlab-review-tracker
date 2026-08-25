"""Thin, read-only GitLab REST API client for the review tracker desktop tool.

Only GET endpoints are used, so a token with the `read_api` scope is enough
- no write access to the GitLab project is required.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import requests


class GitLabError(RuntimeError):
    pass


def parse_project_url(url: str) -> tuple[str, str]:
    """Split a GitLab project URL into (base_url, project_path).

    Accepts a plain project URL (e.g. https://gitlab.example.com/group/project)
    or a merge request URL, in which case the /-/merge_requests/<iid> suffix
    is ignored.
    """
    parsed = urllib.parse.urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            "Enter the full project URL, e.g. https://gitlab.example.com/group/project"
        )
    path = parsed.path.strip("/")
    path = path.split("/-/merge_requests/")[0].strip("/")
    if not path:
        raise ValueError("URL does not contain a project path.")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    return base_url, path

def get_gitlab_base_url_from_project_url(project_url: str) -> str:
    """Extract the base URL of a GitLab instance from a project URL."""
    base_url, _ = parse_project_url(project_url)
    return base_url

class GitLabClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"PRIVATE-TOKEN": token})
        self._current_user: dict[str, Any] | None = None

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}/api/v4{path}"
        resp = self.session.get(url, timeout=15)
        if not resp.ok:
            if resp.status_code in (401, 403):
                raise GitLabError(
                    "Authentication failed: the token is invalid, expired, or lacks the "
                    "'read_api' scope. Create a new token and try again."
                )
            if resp.status_code == 404:
                raise GitLabError(f"Not found: {path} (check the project URL / permissions).")
            raise GitLabError(f"GET {path} -> {resp.status_code}: {resp.text[:300]}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def current_user(self) -> dict[str, Any]:
        if self._current_user is None:
            self._current_user = self._get("/user")
        return self._current_user

    def project_id(self, project_path: str) -> int:
        encoded = urllib.parse.quote(project_path, safe="")
        project = self._get(f"/projects/{encoded}")
        return project["id"]

    def merge_requests(self, project_id: int) -> list[dict[str, Any]]:
        """List open merge requests of the project, newest updated first."""
        return self._get(
            f"/projects/{project_id}/merge_requests?state=opened&per_page=100&order_by=updated_at&sort=desc"
        ) or []

    def commits(self, project_id: int, mr_iid: int) -> list[dict[str, Any]]:
        return self._get(f"/projects/{project_id}/merge_requests/{mr_iid}/commits?per_page=100") or []

    def commit_files(self, project_id: int, sha: str) -> list[str]:
        encoded_sha = urllib.parse.quote(sha, safe="")
        diffs = self._get(f"/projects/{project_id}/repository/commits/{encoded_sha}/diff?per_page=100") or []
        paths = {d.get("new_path") or d.get("old_path") for d in diffs}
        return sorted(p for p in paths if p)
