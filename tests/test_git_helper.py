from operator import index
import subprocess
from unittest.mock import MagicMock
import pytest

from review_tracker.data import git_helper


@pytest.fixture(autouse=False)
def create_repo(tmp_path):

    main_hashes = []
    branch_hashes = []
    def get_most_recent_commit_hash() -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
    (repo_path / "file.txt").write_text("content")


    (repo_path / "file1.txt").write_text("content1")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "main-commit-1"], cwd=repo_path, check=True)
    main_hashes.append(get_most_recent_commit_hash())

    (repo_path / "file2.txt").write_text("content2")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "main-commit-2"], cwd=repo_path, check=True)
    main_hashes.append(get_most_recent_commit_hash())

    (repo_path / "file3.txt").write_text("content3")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "main-commit-3"], cwd=repo_path, check=True)
    main_hashes.append(get_most_recent_commit_hash())

    (repo_path / "file4.txt").write_text("content4")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "main-commit-4"], cwd=repo_path, check=True)
    main_hashes.append(get_most_recent_commit_hash())

    subprocess.run(["git", "checkout", "-b", "branch-1"], cwd=repo_path, check=True)
    (repo_path / "file1.txt").write_text("branch-content1")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "branch-1-commit-1"], cwd=repo_path, check=True)
    branch_hashes.append(get_most_recent_commit_hash())

    subprocess.run(["git", "checkout", "main"], cwd=repo_path, check=True)

    return repo_path, main_hashes, branch_hashes


def test_clean_repo(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    open(repo_path / "empty_file.txt", "w").close()
    open(repo_path / "file1.txt", "w").close()

    git_helper.clean_repo(str(repo_path))
    assert not (repo_path / "empty_file.txt").exists()
    assert open(repo_path / "file1.txt").read() == "content1"


def test_clone_or_update_repo_clones_when_missing(tmp_path, monkeypatch):
    mock_run = MagicMock()
    monkeypatch.setattr(git_helper.subprocess, "run", mock_run)

    local_path = str(tmp_path / "repo")  # does not exist yet

    git_helper.clone_or_update_repo("git@example.com:group/project.git", local_path)

    assert mock_run.call_count == 2
    clone_args, fetch_args = (call.args[0] for call in mock_run.call_args_list)
    assert clone_args == ["git", "clone", "git@example.com:group/project.git", local_path]
    assert fetch_args == ["git", "-C", local_path, "fetch", "--all"]


def test_clone_or_update_repo_skips_clone_when_already_present(tmp_path, monkeypatch):
    mock_run = MagicMock()
    monkeypatch.setattr(git_helper.subprocess, "run", mock_run)

    local_path = str(tmp_path / "repo")
    (tmp_path / "repo").mkdir()  # already exists -> no clone

    git_helper.clone_or_update_repo("git@example.com:group/project.git", str(local_path))

    mock_run.assert_called_once_with(
        ["git", "-C", str(local_path), "fetch", "--all"], check=True
    )

def test_checkout_commit(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    git_helper.checkout_commit(str(repo_path), main_hashes[-1])

    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert current_commit == main_hashes[-1]

def test_merge_no_interaction(tmp_path, monkeypatch):
    mock_run = MagicMock()
    monkeypatch.setattr(git_helper.subprocess, "run", mock_run)

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    git_helper.merge_no_interaction(str(repo_path), "feature-branch")

    mock_run.assert_called_once_with(
        ["git", "-C", str(repo_path), "merge", "--no-edit", "feature-branch"],
        check=False,
    )

def test_get_files_of_commit(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    files = git_helper.get_files_of_commit(main_hashes[-1], str(repo_path))
    assert files==["file4.txt"]

def test_get_commit_hashes_between_with_single_hash(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    hashes = git_helper.get_all_commit_hashes_between(main_hashes[1], main_hashes[1], str(repo_path))
    assert hashes == [main_hashes[1]]

def test_get_commit_hashes_between_with_two_hashes(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    hashes = git_helper.get_all_commit_hashes_between(main_hashes[1], main_hashes[2], str(repo_path))
    assert hashes == [main_hashes[2], main_hashes[1]]

def test_get_commit_hashes_between_with_multiple_hashes(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    hashes = git_helper.get_all_commit_hashes_between(main_hashes[1], main_hashes[3], str(repo_path))
    assert hashes == [main_hashes[3], main_hashes[2], main_hashes[1]]

def test_get_commit_before(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    commit_before = git_helper.get_commit_before(main_hashes[3], str(repo_path))
    assert commit_before == main_hashes[2]

def test_get_all_commits_on_branch_with_timestamp(create_repo):
    repo_path, main_hashes, branch_hashes = create_repo

    commits = git_helper.get_commits_on_branch_with_timestamps("main", str(repo_path))
    assert [commit[0] for commit in commits] == list(reversed(main_hashes))
