from unittest.mock import MagicMock

import pytest

from review_tracker.data.gitlab_client import (
    GitLabClient,
    GitLabError,
    get_ssh_url_from_project_url,
    parse_project_url,
)


def test_parse_project_url_plain_project():
    base_url, path = parse_project_url("https://gitlab.example.com/group/project")
    assert base_url == "https://gitlab.example.com"
    assert path == "group/project"


def test_parse_project_url_strips_merge_request_suffix():
    base_url, path = parse_project_url(
        "https://gitlab.example.com/group/project/-/merge_requests/42"
    )
    assert base_url == "https://gitlab.example.com"
    assert path == "group/project"


def test_parse_project_url_rejects_missing_scheme():
    with pytest.raises(ValueError):
        parse_project_url("not-a-url")


def test_parse_project_url_rejects_missing_path():
    with pytest.raises(ValueError):
        parse_project_url("https://gitlab.example.com")


def test_get_ssh_url_from_project_url():
    assert (
        get_ssh_url_from_project_url("https://gitlab.example.com/group/project")
        == "git@gitlab.example.com:group/project.git"
    )


def _client_with_response(status_code, json_body=None, text=""):
    client = GitLabClient("https://gitlab.example.com", "token")
    response = MagicMock()
    response.ok = status_code < 400
    response.status_code = status_code
    response.content = b"{}" if json_body is not None else b""
    response.json.return_value = json_body
    response.text = text
    client.session.get = MagicMock(return_value=response)
    return client


def test_get_raises_gitlab_error_on_401():
    client = _client_with_response(401)
    with pytest.raises(GitLabError, match="Authentication failed"):
        client.current_user()


def test_get_raises_gitlab_error_on_404():
    client = _client_with_response(404)
    with pytest.raises(GitLabError, match="Not found"):
        client.project_id("group/project")


def test_current_user_caches_result():
    client = _client_with_response(200, json_body={"username": "alice"})
    assert client.current_user() == {"username": "alice"}
    assert client.current_user() == {"username": "alice"}
    client.session.get.assert_called_once()


def test_commit_files_dedupes_and_sorts_paths():
    client = _client_with_response(
        200,
        json_body=[
            {"new_path": "b.py"},
            {"new_path": "a.py", "old_path": "a.py"},
            {"old_path": None, "new_path": None},
        ],
    )
    assert client.commit_files(1, "sha") == ["a.py", "b.py"]
