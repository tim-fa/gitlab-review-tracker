"""Shared review-state storage on a network file share.

State is stored as one JSON file per merge request under a shared network
folder, so it's visible to everyone on the team who runs this tool against
the same MR. No write access to GitLab is required.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_STATE_ROOT = Path(r"\\vi.vector.int\user\Tmp\CT_DEM\gitlab-review-tracker")


def state_root() -> Path:
    override = os.environ.get("GRT_STATE_ROOT")
    return Path(override) if override else DEFAULT_STATE_ROOT


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def state_file(project_path: str, mr_iid: int) -> Path:
    return state_root() / _safe_name(project_path) / f"mr_{mr_iid}.json"


def load_state(project_path: str, mr_iid: int) -> dict[str, Any]:
    path = state_file(project_path, mr_iid)
    if not path.exists():
        return {"files": {}, "commits": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"files": {}, "commits": {}}


def save_state(project_path: str, mr_iid: int, state: dict[str, Any]) -> None:
    path = state_file(project_path, mr_iid)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def _set_reviewer(state: dict[str, Any], kind: str, key: str, username: str, reviewed: bool) -> None:
    bucket = state.setdefault(kind, {})
    reviewers = bucket.get(key, [])
    if reviewed and username not in reviewers:
        reviewers.append(username)
    elif not reviewed and username in reviewers:
        reviewers.remove(username)
    if reviewers:
        bucket[key] = reviewers
    else:
        bucket.pop(key, None)


def file_key(sha: str, path: str) -> str:
    """A file's reviewed state is scoped to the commit it was reviewed under."""
    return f"{sha}::{path}"


def _recompute_commit_reviewers(state: dict[str, Any], sha: str, file_paths: list[str]) -> None:
    """A commit is reviewed by everyone who has reviewed all of its files.

    This makes the commit's reviewer list a pure derivation of its files'
    reviewer lists, so any number of people independently reviewing all
    files of a commit all end up listed as reviewers of that commit.
    """
    if not file_paths:
        return
    files_bucket = state.get("files", {})
    reviewer_sets = [set(files_bucket.get(file_key(sha, path), [])) for path in file_paths]
    common_reviewers = set.intersection(*reviewer_sets)
    bucket = state.setdefault("commits", {})
    if common_reviewers:
        bucket[sha] = sorted(common_reviewers)
    else:
        bucket.pop(sha, None)


def toggle(project_path: str, mr_iid: int, kind: str, key: str, username: str) -> dict[str, Any]:
    state = load_state(project_path, mr_iid)
    reviewers = state.get(kind, {}).get(key, [])
    reviewed = username not in reviewers
    _set_reviewer(state, kind, key, username, reviewed)
    save_state(project_path, mr_iid, state)
    return state


def toggle_commit_with_files(
    project_path: str, mr_iid: int, sha: str, file_paths: list[str], username: str
) -> dict[str, Any]:
    """Toggle the current user's reviewed state on all of a commit's files.

    The commit's own reviewed state is then derived (see
    _recompute_commit_reviewers) rather than set directly, so it correctly
    reflects everyone who has fully reviewed the commit, not just the user
    who just toggled it. Commits with no files of their own (e.g. merge
    commits with no diff vs. their first parent) have nothing to derive
    from, so the commit itself is toggled directly instead.
    """
    state = load_state(project_path, mr_iid)
    reviewers = state.get("commits", {}).get(sha, [])
    reviewed = username not in reviewers
    if file_paths:
        for path in file_paths:
            _set_reviewer(state, "files", file_key(sha, path), username, reviewed)
        _recompute_commit_reviewers(state, sha, file_paths)
    else:
        _set_reviewer(state, "commits", sha, username, reviewed)
    save_state(project_path, mr_iid, state)
    return state


def sync_commit_from_files(project_path: str, mr_iid: int, sha: str, file_paths: list[str]) -> dict[str, Any]:
    """Re-derive a commit's reviewed state from its files' reviewed state."""
    state = load_state(project_path, mr_iid)
    _recompute_commit_reviewers(state, sha, file_paths)
    save_state(project_path, mr_iid, state)
    return state
