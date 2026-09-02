import filecmp
import os
import subprocess
from typing import List, Tuple

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
   else:
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

def setup_repo_on_branch(repo_url: str, branch_name: str, local_path: str) -> None:
   """
   Set up a repository on a specific branch.

   Args:
      repo_url (str): The URL of the repository.
      branch_name (str): The name of the branch to checkout.
      local_path (str): The local path where the repository should be set up.
   """
   clone_or_update_repo(repo_url, local_path)
   clean_repo(local_path)
   checkout_branch_and_update(local_path, branch_name)

def setup_repo_at_commit_merge_main(repo_url: str, commit_sha: str, local_path: str) -> None:
   """
   Set up a repository at a specific commit and merge the main branch into it.

   Args:
      repo_url (str): The URL of the repository.
      commit_sha (str): The SHA of the commit to checkout.
      local_path (str): The local path where the repository should be set up.
   """
   clone_or_update_repo(repo_url, local_path)
   clean_repo(local_path)
   checkout_commit(local_path, commit_sha)
   merge_no_interaction(local_path, "main")

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

def get_changes_compared_to_main(project_name: str, repo_url: str, commit_to_compare_sha: str, previous_commit_sha: str) -> Tuple[List[str], str, str]:
   """
   Return the changes between a specific commit and the main branch.
   Two repos are checked out, one at the commit to compare and the other at the previous commit. 
   The main branch is merged into both repos, and the files with differences are returned as a list of file paths.

   Args:
      project_name (str): The name of the project.
      repo_url (str): The URL of the repository.
      commit_to_compare_sha (str): The SHA of the commit to compare.
      previous_commit_sha (str): The SHA of the previous commit to compare against.
      files_of_commit (List[str]): The list of relevant files to check for changes.

   Returns:
      Tuple[List[str], str, str]: A tuple containing the list of differing files, the base commit SHA, and the compare commit SHA.
   """
   temp_appdata: str = os.getenv("TEMP")
   temp_dir: str = os.path.join(temp_appdata, "git_helper_temp", project_name)
   base_repo: str = os.path.join(temp_dir, "base_repo")
   compare_repo: str = os.path.join(temp_dir, "compare_repo")

   if not os.path.exists(temp_dir):
      os.makedirs(temp_dir, exist_ok=True)

   print(f"[git_helper] Comparing {previous_commit_sha[:8]} -> {commit_to_compare_sha[:8]}")

   if previous_commit_sha == commit_to_compare_sha:
      print(f"[git_helper] Showing changes of single commit")
      setup_repo_at_commit_merge_main(repo_url, commit_to_compare_sha, compare_repo)
      commit_before = get_commit_before(commit_to_compare_sha, compare_repo)
      if not commit_before:
         raise ValueError(f"Could not determine the commit before {commit_to_compare_sha}")
      setup_repo_at_commit_merge_main(repo_url, commit_before, base_repo)
      print(f"[git_helper] Base repo set up at commit {commit_before[:8]} and compare repo at commit {commit_to_compare_sha[:8]}")
   else:
      print(f"[git_helper] Showing changes between commits")
      setup_repo_at_commit_merge_main(repo_url, previous_commit_sha, base_repo)
      setup_repo_at_commit_merge_main(repo_url, commit_to_compare_sha, compare_repo)
      print(f"[git_helper] Base repo set up at commit {previous_commit_sha[:8]} and compare repo at commit {commit_to_compare_sha[:8]}")

   all_files = set()
   print(f"[git_helper] Gathering all files between {previous_commit_sha[:8]} and {commit_to_compare_sha[:8]}")
   for commit_sha in get_all_commit_hashes_between(previous_commit_sha, commit_to_compare_sha, compare_repo):
      print(f"[git_helper] Found intermediate commit {commit_sha[:8]}")
      all_files.update(get_files_of_commit(commit_sha, compare_repo))

   if not all_files:
      raise ValueError(f"No files found between {previous_commit_sha[:8]} and {commit_to_compare_sha[:8]}")

   diffs: List[str] = []
   for file_path in all_files:
      base_file_path: str = os.path.join(base_repo, file_path)
      compare_file_path: str = os.path.join(compare_repo, file_path)

      if not os.path.exists(base_file_path) or not os.path.exists(compare_file_path):
         diffs.append(file_path)
         continue

      if not filecmp.cmp(base_file_path, compare_file_path, shallow=False):
         diffs.append(file_path)

   print(f"[git_helper] Found {len(diffs)} differing file(s)")
   return diffs, base_repo, compare_repo