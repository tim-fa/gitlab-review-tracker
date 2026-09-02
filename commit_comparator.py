import shutil
import subprocess

import git_helper
import filecmp
import os
from typing import List, Tuple

def delete_nonempty_directory(directory_path: str) -> None:
   """
   Delete a non-empty directory and all its contents.

   Args:
      directory_path (str): The path to the directory to delete.
   """
   if os.path.exists(directory_path):
      for root, dirs, files in os.walk(directory_path, topdown=False):
         for name in files:
            os.remove(os.path.join(root, name))
         for name in dirs:
            os.rmdir(os.path.join(root, name))
      os.rmdir(directory_path)

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

   print(f"[commit_comparator] Comparing {previous_commit_sha[:8]} -> {commit_to_compare_sha[:8]}")

   if previous_commit_sha == commit_to_compare_sha:
      print(f"[commit_comparator] Showing changes of single commit")
      git_helper.setup_repo_at_commit_merge_main(repo_url, commit_to_compare_sha, compare_repo)
      commit_before = git_helper.get_commit_before(commit_to_compare_sha, compare_repo)
      if not commit_before:
         raise ValueError(f"Could not determine the commit before {commit_to_compare_sha}")
      git_helper.setup_repo_at_commit_merge_main(repo_url, commit_before, base_repo)
      print(f"[commit_comparator] Base repo set up at commit {commit_before[:8]} and compare repo at commit {commit_to_compare_sha[:8]}")
   else:
      print(f"[commit_comparator] Showing changes between commits")
      # Previous commit shall be included in the diff
      real_previous = git_helper.get_commit_before(previous_commit_sha, compare_repo)
      if not real_previous:
         raise ValueError(f"Could not determine the commit before {previous_commit_sha}")
      git_helper.setup_repo_at_commit_merge_main(repo_url, real_previous, base_repo)
      git_helper.setup_repo_at_commit_merge_main(repo_url, commit_to_compare_sha, compare_repo)
      print(f"[commit_comparator] Base repo set up at commit {real_previous[:8]} and compare repo at commit {commit_to_compare_sha[:8]}")

   all_files = set()
   print(f"[commit_comparator] Gathering all files between {previous_commit_sha[:8]} and {commit_to_compare_sha[:8]}")
   for commit_sha in git_helper.get_all_commit_hashes_between(previous_commit_sha, commit_to_compare_sha, compare_repo):
      print(f"[commit_comparator] Found intermediate commit {commit_sha[:8]}")
      all_files.update(git_helper.get_files_of_commit(commit_sha, compare_repo))
      print(f"Files in commit {commit_sha[:8]}: {git_helper.get_files_of_commit(commit_sha, compare_repo)}")

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

   print(f"[commit_comparator] Found {len(diffs)} differing file(s)")
   return diffs, base_repo, compare_repo

def open_diff_in_beyond_compare(project_name: str, repo_url: str, commit_to_compare_sha: str, previous_commit_sha: str, beyond_compare_path: str) -> None:
   """
   Open the differing files in Beyond Compare for visual comparison.

   Args:
      project_name (str): The name of the project.
      repo_url (str): The URL of the repository.
      commit_to_compare_sha (str): The SHA of the commit to compare.
      previous_commit_sha (str): The SHA of the previous commit to compare against.
      beyond_compare_path (str): The path to the Beyond Compare executable.
   """

   diff_files, base_repo, compare_repo = get_changes_compared_to_main(project_name, repo_url, commit_to_compare_sha, previous_commit_sha)

   temp_appdata: str = os.getenv("TEMP")
   temp_dir: str = os.path.join(temp_appdata, "git_helper_temp", "beyond_compare")
   old_temp_dir: str = os.path.join(temp_dir, "beyond_compare_old")
   new_temp_dir: str = os.path.join(temp_dir, "beyond_compare_new")

   if os.path.exists(temp_dir):
      delete_nonempty_directory(temp_dir)

   print(f"[commit_comparator] Temporary directories set up at {old_temp_dir} and {new_temp_dir}")

   for file_path in diff_files:
      base_file_path = os.path.join(base_repo, file_path)
      compare_file_path = os.path.join(compare_repo, file_path)

      old_file_path = os.path.join(old_temp_dir, file_path)
      new_file_path = os.path.join(new_temp_dir, file_path)

      if os.path.isfile(base_file_path):
         os.makedirs(os.path.dirname(old_file_path), exist_ok=True)
         shutil.copy2(base_file_path, old_file_path)

      if os.path.isfile(compare_file_path):
         os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
         shutil.copy2(compare_file_path, new_file_path)

   subprocess.run([beyond_compare_path, old_temp_dir, new_temp_dir], check=False)
