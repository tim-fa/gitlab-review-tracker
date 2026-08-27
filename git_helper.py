import filecmp
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
   subprocess.run(["git", "-C", local_path, "merge", "--no-edit", source_branch], check=True)

def show_changes_compared_to_main(repo_url: str, commit_to_compare_sha: str, previous_commit_sha: str, files_of_commit: List[str]) -> List[str]:
   """
   Show the changes between a specific commit and the main branch.
   Two repos are checked out, one at the commit to compare and the other at the previous commit. 
   The main branch is merged into both repos, and the files with differences are returned as a list of file paths.

   Args:
      repo_url (str): The URL of the repository.
      commit_to_compare_sha (str): The SHA of the commit to compare.
      previous_commit_sha (str): The SHA of the previous commit to compare against.
      files_of_commit (List[str]): The list of relevant files to check for changes.
   """
   temp_appdata: str = os.getenv("TEMP")
   temp_dir: str = os.path.join(temp_appdata, "git_helper_temp")
   base_repo: str = os.path.join(temp_dir, "base_repo")
   compare_repo: str = os.path.join(temp_dir, "compare_repo")

   print(f"[git_helper] Comparing {previous_commit_sha[:8]} -> {commit_to_compare_sha[:8]} ({len(files_of_commit)} file(s))")

   clean_repo(base_repo)
   clone_or_update_repo(repo_url, base_repo)
   checkout_commit(base_repo, previous_commit_sha)
   merge_no_interaction(base_repo, "main")

   clean_repo(compare_repo)
   clone_or_update_repo(repo_url, compare_repo)
   checkout_commit(compare_repo, commit_to_compare_sha)
   merge_no_interaction(compare_repo, "main")

   diffs: List[str] = []
   for file_path in files_of_commit:
      base_file_path: str = os.path.join(base_repo, file_path)
      compare_file_path: str = os.path.join(compare_repo, file_path)

      if not os.path.exists(base_file_path):
         diffs.append(file_path)

      if not filecmp.cmp(base_file_path, compare_file_path, shallow=False):
         diffs.append(file_path)

   print(f"[git_helper] Found {len(diffs)} differing file(s)")
   return diffs