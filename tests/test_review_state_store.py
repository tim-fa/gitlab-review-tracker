import pytest

from review_tracker.data import review_state_store


@pytest.fixture(autouse=True)
def state_root(tmp_path, monkeypatch):
    monkeypatch.setenv("GRT_STATE_ROOT", str(tmp_path))
    return tmp_path


def test_state_root_uses_env_override(tmp_path):
    assert review_state_store.state_root() == tmp_path


def test_load_state_missing_file_returns_empty_state():
    state = review_state_store.load_state("group/project", 1)
    assert state == {"files": {}, "commits": {}}


def test_file_key_scopes_path_to_commit():
    assert review_state_store.file_key("abc123", "src/app.py") == "abc123::src/app.py"


def test_toggle_adds_and_removes_reviewer():
    state = review_state_store.toggle("group/project", 1, "files", "sha::path", "alice")
    assert state["files"]["sha::path"] == ["alice"]

    state = review_state_store.toggle("group/project", 1, "files", "sha::path", "alice")
    assert "sha::path" not in state["files"]


def test_toggle_commit_with_files_marks_commit_reviewed_when_all_files_reviewed():
    sha = "deadbeef"
    paths = ["a.py", "b.py"]

    state = review_state_store.toggle_commit_with_files("group/project", 1, sha, paths, "alice")

    assert state["commits"][sha] == ["alice"]
    assert state["files"][review_state_store.file_key(sha, "a.py")] == ["alice"]
    assert state["files"][review_state_store.file_key(sha, "b.py")] == ["alice"]


def test_commit_reviewers_are_intersection_of_file_reviewers():
    sha = "deadbeef"
    paths = ["a.py", "b.py"]

    review_state_store.toggle("group/project", 1, "files", review_state_store.file_key(sha, "a.py"), "alice")
    review_state_store.toggle("group/project", 1, "files", review_state_store.file_key(sha, "a.py"), "bob")
    review_state_store.toggle("group/project", 1, "files", review_state_store.file_key(sha, "b.py"), "alice")

    state = review_state_store.sync_commit_from_files("group/project", 1, sha, paths)

    assert state["commits"][sha] == ["alice"]


def test_toggle_commit_with_files_no_files_toggles_commit_directly():
    sha = "mergecommit"

    state = review_state_store.toggle_commit_with_files("group/project", 1, sha, [], "alice")
    assert state["commits"][sha] == ["alice"]

    state = review_state_store.toggle_commit_with_files("group/project", 1, sha, [], "alice")
    assert sha not in state["commits"]


def test_save_and_load_round_trip():
    state = {"files": {"sha::a.py": ["alice"]}, "commits": {"sha": ["alice"]}}
    review_state_store.save_state("group/project", 2, state)

    loaded = review_state_store.load_state("group/project", 2)

    assert loaded == state
