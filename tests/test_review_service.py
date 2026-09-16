from unittest.mock import MagicMock

import pytest

from review_tracker.core.review_service import ReviewService


class FakeGitLabClient:
    """Stand-in for GitLabClient, constructed the same way (base_url, token)."""

    instances: list["FakeGitLabClient"] = []

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token
        FakeGitLabClient.instances.append(self)

    def project_id(self, project_path: str) -> int:
        return 42

    def current_user(self) -> dict:
        return {"username": "alice"}

    def merge_requests(self, project_id: int, show_closed=False, show_merged=False) -> list[dict]:
        return [{"iid": "1", "title": "Add feature", "state": "opened"}]

    def commits(self, project_id: int, mr_iid: int) -> list[dict]:
        return [
            {"id": "sha1", "title": "First commit", "parent_ids": ["sha0"]},
            {"id": "sha2", "title": "Merge commit", "parent_ids": ["sha1", "other"]},
        ]

    def commit_files(self, project_id: int, sha: str) -> list[str]:
        return ["a.py", "b.py"]


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("GRT_STATE_ROOT", str(tmp_path))
    FakeGitLabClient.instances.clear()


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr("review_tracker.core.review_service.GitLabClient", FakeGitLabClient)
    return ReviewService()


def test_connect_sets_session_state(service):
    service.connect("https://gitlab.example.com/group/project", "token123")

    assert service.project_id == 42
    assert service.project_path == "group/project"
    assert service.current_user == "alice"
    assert service.all_mrs == [{"iid": "1", "title": "Add feature", "state": "opened"}]


def test_select_merge_request_loads_commits_and_derives_merge_flags(service):
    service.connect("https://gitlab.example.com/group/project", "token123")

    service.select_merge_request({"iid": "1"})

    assert service.mr_iid == 1
    assert [c["id"] for c in service.current_commits] == ["sha1", "sha2"]
    assert service.commit_is_merge == {"sha1": False, "sha2": True}
    assert service.state == {"files": {}, "commits": {}}
    assert service.current_mr_url == (
        "https://gitlab.example.com/group/project/-/merge_requests/1"
    )


def test_select_merge_request_prefers_web_url(service):
    service.connect("https://gitlab.example.com/group/project", "token123")

    service.select_merge_request({"iid": "1", "web_url": "https://gitlab.example.com/group/project/-/merge_requests/1?x=1"})

    assert service.current_mr_url == "https://gitlab.example.com/group/project/-/merge_requests/1?x=1"


def test_fetch_commit_files_caches_result(service):
    service.connect("https://gitlab.example.com/group/project", "token123")
    service.select_merge_request({"iid": "1"})
    service.client.commit_files = MagicMock(return_value=["a.py"])

    assert service.fetch_commit_files("sha1") == ["a.py"]
    assert service.fetch_commit_files("sha1") == ["a.py"]
    service.client.commit_files.assert_called_once()


def test_toggle_commit_marks_all_files_and_commit_reviewed(service):
    service.connect("https://gitlab.example.com/group/project", "token123")
    service.select_merge_request({"iid": "1"})

    service.toggle_commit("sha1")

    assert service.state["commits"]["sha1"] == ["alice"]


def test_toggle_file_recomputes_commit_from_files(service):
    service.connect("https://gitlab.example.com/group/project", "token123")
    service.select_merge_request({"iid": "1"})
    service.commit_files_cache["sha1"] = ["a.py", "b.py"]

    service.toggle_file("sha1", "a.py")
    service.toggle_file("sha1", "b.py")

    assert service.state["commits"]["sha1"] == ["alice"]


def test_refresh_state_reloads_from_store(service):
    service.connect("https://gitlab.example.com/group/project", "token123")
    service.select_merge_request({"iid": "1"})
    service.toggle_commit("sha1")
    service.state = {"files": {}, "commits": {}}  # simulate a stale in-memory copy

    service.refresh_state()

    assert service.state["commits"]["sha1"] == ["alice"]


def test_merge_request_diff_url_uses_active_commit(service):
    service.connect("https://gitlab.example.com/group/project", "token123")
    service.select_merge_request({"iid": "1"})
    service.active_commit_sha = "sha1"

    url = service.merge_request_diff_url("a.py")

    assert url.startswith(
        "https://gitlab.example.com/group/project/-/merge_requests/1/diffs?commit_id=sha1#diff-content-"
    )


def test_commit_diff_url(service):
    service.connect("https://gitlab.example.com/group/project", "token123")

    url = service.commit_diff_url("sha1", "a.py")

    assert url.startswith("https://gitlab.example.com/group/project/-/commit/sha1#diff-content-")


def test_file_key_matches_review_state_store_convention(service):
    assert service.file_key("sha1", "a.py") == "sha1::a.py"
