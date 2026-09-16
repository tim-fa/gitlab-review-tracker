import os
import subprocess
from typing import List

def clean_repo(local_path: str) -> None:
   """
   Clean the repository by removing untracked files and resetting changes.

   Args:
      local_path (str): The local path of the repository to clean.
   """
   subprocess.run(["git", "-C", local_path, "reset", "--hard"], check=True)
   subprocess.run(["git", "-C", local_path, "clean", "-fdx"], check=True)

def clone_or_update_repo(repo_url: str, local_path: str) -> None:
   """
   Clone the repository if it doesn't exist locally, or update it if it does.

   Args:
      repo_url (str): The URL of the repository to clone or update.
      local_path (str): The local path where the repository should be cloned or updated.
   """
   if not os.path.exists(local_path):
      print(f"[git_helper] Cloning {repo_url} -> {local_path}")
      subprocess.run(["git", "clone", repo_url, local_path], check=True)

   print(f"[git_helper] Updating {local_path}")
   subprocess.run(["git", "-C", local_path, "fetch", "--all"], check=True)

def checkout_commit(local_path: str, commit_sha: str) -> None:
   """
   Checkout a specific commit in the repository.

   Args:
      local_path (str): The local path of the repository.
      commit_sha (str): The SHA of the commit to checkout.
   """
   print(f"[git_helper] Checking out {commit_sha[:8]} in {local_path}")
   subprocess.run(["git", "-C", local_path, "checkout", commit_sha], check=True)

def checkout_branch_and_update(local_path: str, branch_name: str) -> None:
   """
   Checkout a specific branch in the repository.

   Args:
      local_path (str): The local path of the repository.
      branch_name (str): The name of the branch to checkout.
   """
   subprocess.run(["git", "-C", local_path, "checkout", branch_name], check=True)
   subprocess.run(["git", "-C", local_path, "pull"], check=True)

def merge_no_interaction(local_path: str, source_branch: str) -> None:
   """
   Merge the source branch into the target branch without any user interaction. This function assumes that the target branch is already checked out.

   Args:
      local_path (str): The local path of the repository.
      source_branch (str): The name of the source branch to merge into the current branch.
   """
   print(f"[git_helper] Merging {source_branch} into {local_path}")
   subprocess.run(["git", "-C", local_path, "merge", "--no-edit", source_branch], check=False)

def get_files_of_commit(commit_sha: str, local_path: str) -> List[str]:
   """
   Get the list of files changed in a specific commit.

   Args:
      commit_sha (str): The SHA of the commit to inspect.
      local_path (str): The local path where the repository should be set up.

   Returns:
      List[str]: A list of file paths changed in the commit.
   """
   result = subprocess.run(
         ["git", "-C", local_path, "diff", "--name-only", f"{commit_sha}~1", commit_sha],
       check=True,
       capture_output=True,
       text=True,
   )
   return result.stdout.strip().split("\n") if result.stdout.strip() else []

def get_all_commit_hashes_between(start_commit_sha: str, end_commit_sha: str, local_path: str) -> List[str]:
   """
   Get first-parent commit hashes from the starting through ending commit, inclusively.

   For merge commits, commits introduced from the merged branch are excluded.

   Args:
      start_commit_sha (str): The SHA of the starting commit.
      end_commit_sha (str): The SHA of the ending commit.
      local_path (str): The local path where the repository should be set up.

   Returns:
        List[str]: First-parent commit hashes including the start and end commits.
   """
   result = subprocess.run(
         ["git", "-C", local_path, "rev-list", "--first-parent", end_commit_sha, f"^{start_commit_sha}^"],
       check=True,
       capture_output=True,
       text=True,
   )
   return result.stdout.strip().split("\n") if result.stdout.strip() else []

def get_commit_before(commit_sha: str, local_path: str) -> str:
   """
   Get the first-parent commit immediately before the specified commit.

   For a merge commit, the first parent is the branch that was checked out
   when the merge was created.

   Args:
      commit_sha (str): The SHA of the commit to inspect.
      local_path (str): The local path where the repository should be set up.

   Returns:
      str: The SHA of the first-parent commit, or an empty string for a root commit.
   """
   result = subprocess.run(
       ["git", "-C", local_path, "rev-list", "--parents", "-n", "1", commit_sha],
       check=True,
       capture_output=True,
       text=True,
   )
   commits = result.stdout.strip().split()
   return commits[1] if len(commits) > 1 else ""

def get_commit_timestamp(commit_sha: str, local_path: str) -> int:
   """
   Get the Unix timestamp of when a commit was made.

   Args:
      commit_sha (str): The SHA of the commit.
      local_path (str): The local path where the repository is set up.

   Returns:
      int: Unix timestamp of the commit.
   """
   result = subprocess.run(
       ["git", "-C", local_path, "log", "-1", "--format=%ct", commit_sha],
       check=True,
       capture_output=True,
       text=True,
   )
   return int(result.stdout.strip())

def get_commits_on_branch_with_timestamps(branch_name: str, local_path: str) -> List[tuple[str, int]]:
   """
   Get all commits on a branch with their timestamps.

   Args:
      branch_name (str): The name of the branch (e.g., "main").
      local_path (str): The local path where the repository is set up.

   Returns:
      List[tuple[str, int]]: List of (commit_sha, timestamp) tuples in reverse chronological order.
   """
   result = subprocess.run(
       ["git", "-C", local_path, "log", "--format=%H %ct", branch_name],
       check=True,
       capture_output=True,
       text=True,
   )
   commits = []
   for line in result.stdout.strip().split("\n"):
      if line:
         sha, timestamp = line.split()
         commits.append((sha, int(timestamp)))
   return commits

def get_main_commit_at_compare_time(commit_to_compare_sha: str, repo_path: str) -> str:

   main_commits_with_timestamps = get_commits_on_branch_with_timestamps("main", repo_path)
   compare_commit_timestamp = get_commit_timestamp(commit_to_compare_sha, repo_path)

   main_commit_at_compare_time = None
   for main_commit, main_timestamp in reversed(main_commits_with_timestamps):

      print(f"Checking main commit {main_commit} with timestamp {main_timestamp} against compare commit {commit_to_compare_sha} timestamp {compare_commit_timestamp}")

      if main_timestamp > compare_commit_timestamp:
         break

      main_commit_at_compare_time = main_commit

   if not main_commit_at_compare_time:
      raise ValueError(f"Could not determine the main commit at the time of {commit_to_compare_sha}")
   return main_commit_at_compare_time