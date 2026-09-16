"""UI-agnostic core of the review tracker.

``ReviewService`` holds the session state for one connected GitLab project
and merge request, and exposes the app's use-cases as plain, synchronous
methods: no threading, no callbacks, no UI-toolkit imports. A UI adapter
(the Tkinter app today, potentially a web UI later) decides how to run these
off its own event loop/request handler and how to present progress and
errors. Exceptions (``GitLabError``, ``ValueError``, ...) are left to
propagate so each UI can present them its own way.
"""
from __future__ import annotations

import hashlib
from typing import Any

from review_tracker.core import commit_comparator
from review_tracker.data import review_state_store
from review_tracker.data.gitlab_client import (
    GitLabClient,
    GitLabError,
    get_ssh_url_from_project_url,
    parse_project_url,
)

__all__ = ["ReviewService", "GitLabError"]


class ReviewService:
    """Session state and use-cases for reviewing one merge request at a time."""

    def __init__(self) -> None:
        self.client: GitLabClient | None = None
        self.project_id: int | None = None
        self.project_path: str | None = None
        self.project_url: str | None = None
        self.current_user: str | None = None
        self.all_mrs: list[dict[str, Any]] = []

        self.mr_iid: int | None = None
        self.current_mr_url: str | None = None
        self.current_commits: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {"files": {}, "commits": {}}
        self.commit_files_cache: dict[str, list[str]] = {}
        self.commit_is_merge: dict[str, bool] = {}
        self.active_commit_sha: str | None = None

    def connect(
        self, project_url: str, token: str, show_closed: bool = False, show_merged: bool = False
    ) -> None:
        """Sign in to GitLab and list the project's merge requests (see ``all_mrs``)."""
        base_url, project_path = parse_project_url(project_url)
        client = GitLabClient(base_url, token)
        project_id = client.project_id(project_path)
        mrs = client.merge_requests(project_id, show_closed=show_closed, show_merged=show_merged)
        user = client.current_user()["username"]

        self.client = client
        self.project_id = project_id
        self.project_path = project_path
        self.project_url = project_url
        self.current_user = user
        self.all_mrs = mrs

    def select_merge_request(self, mr: dict[str, Any]) -> None:
        """Load a merge request's commits (see ``current_commits``) and review state (see ``state``)."""
        mr_iid = int(mr["iid"])
        commits = self.client.commits(self.project_id, mr_iid)
        state = review_state_store.load_state(self.project_path, mr_iid)

        self.mr_iid = mr_iid
        self.current_mr_url = mr.get("web_url") or (
            f"{self.client.base_url}/{self.project_path}/-/merge_requests/{mr_iid}"
        )
        self.current_commits = commits
        self.state = state
        self.commit_files_cache = {}
        self.commit_is_merge = {
            commit["id"]: len(commit.get("parent_ids") or []) > 1 for commit in commits
        }
        self.active_commit_sha = None

    def fetch_commit_files(self, sha: str) -> list[str]:
        """List a commit's changed file paths, caching the result per commit."""
        cached = self.commit_files_cache.get(sha)
        if cached is not None:
            return cached
        paths = self.client.commit_files(self.project_id, sha)
        self.commit_files_cache[sha] = paths
        return paths

    def toggle_commit(self, sha: str) -> None:
        """Toggle the current user's reviewed state on all of a commit's files (see ``state``)."""
        paths = self.fetch_commit_files(sha)
        self.state = review_state_store.toggle_commit_with_files(
            self.project_path, self.mr_iid, sha, paths, self.current_user
        )

    def toggle_file(self, sha: str, path: str) -> None:
        """Toggle the current user's reviewed state on one file of a commit (see ``state``)."""
        key = review_state_store.file_key(sha, path)
        review_state_store.toggle(self.project_path, self.mr_iid, "files", key, self.current_user)
        commit_paths = self.commit_files_cache.get(sha, [])
        self.state = review_state_store.sync_commit_from_files(self.project_path, self.mr_iid, sha, commit_paths)

    def refresh_state(self) -> None:
        """Reload review state from the shared store (see ``state``), e.g. for periodic polling."""
        self.state = review_state_store.load_state(self.project_path, self.mr_iid)

    def compare_commit_to_main(self, sha: str) -> list[str]:
        """List files that differ between a commit and main as of when it was made."""
        diff_files, _base_repo, _compare_repo = commit_comparator.get_changes_compared_to_main(
            project_name=self.project_path.split("/")[-1],
            repo_url=get_ssh_url_from_project_url(self.project_url),
            commit_to_compare_sha=sha,
            previous_commit_sha=sha,
        )
        return diff_files

    def open_beyond_compare(self, first_sha: str, last_sha: str, beyond_compare_path: str) -> None:
        """Open the diff between two commits (each vs. main) in Beyond Compare."""
        commit_comparator.open_diff_in_beyond_compare(
            project_name=self.project_path.split("/")[-1],
            repo_url=get_ssh_url_from_project_url(self.project_url),
            commit_to_compare_sha=last_sha,
            previous_commit_sha=first_sha,
            beyond_compare_path=beyond_compare_path,
        )

    def merge_request_diff_url(self, path: str) -> str:
        """GitLab URL for a file's diff within the current MR, anchored to the active commit."""
        anchor = hashlib.sha1(path.encode("utf-8")).hexdigest()
        return (
            f"{self.client.base_url}/{self.project_path}/-/merge_requests/{self.mr_iid}"
            f"/diffs?commit_id={self.active_commit_sha}#diff-content-{anchor}"
        )

    def commit_diff_url(self, sha: str, path: str) -> str:
        """GitLab URL for a file's diff within a specific commit."""
        anchor = hashlib.sha1(path.encode("utf-8")).hexdigest()
        return f"{self.client.base_url}/{self.project_path}/-/commit/{sha}#diff-content-{anchor}"

    @staticmethod
    def file_key(sha: str, path: str) -> str:
        """Key identifying a file's reviewed state, scoped to the commit it was reviewed under."""
        return review_state_store.file_key(sha, path)
