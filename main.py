"""Tkinter desktop app for marking GitLab MR commits/files as reviewed.

Review state is shared: it's stored as a JSON file on a network share (see
review_state_store.py), so anyone running this tool against the same MR sees the
same state. Only read-only GitLab API calls are made.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

import review_state_store
from gitlab_client import GitLabClient, GitLabError, parse_project_url, get_gitlab_base_url_from_project_url

program_version = "v1.0.4"

CONFIG_PATH = Path.home() / ".gitlab_review_tracker.json"
REFRESH_INTERVAL_MS = int(os.environ.get("GRT_REFRESH_SECONDS", "30")) * 1000
MAX_PROJECT_HISTORY = 15


def add_to_history(history: list[str], value: str) -> list[str]:
    value = value.strip()
    if not value:
        return history
    history = [v for v in history if v != value]
    history.insert(0, value)
    return history[:MAX_PROJECT_HISTORY]


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


class ReviewTrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"GitLab Review Tracker ({program_version})")
        root.geometry("1200x600")

        self.client: GitLabClient | None = None
        self.project_id: int | None = None
        self.project_path: str | None = None
        self.mr_iid: str | None = None
        self.state: dict = {"files": {}, "commits": {}}
        self.current_user: str | None = None
        self.commit_files_cache: dict[str, list[str]] = {}
        self.commit_is_merge: dict[str, bool] = {}
        self.active_commit_sha: str | None = None
        self._refresh_job: str | None = None
        self.all_mrs: list[dict] = []
        self.mr_by_display: dict[str, dict] = {}

        cfg = load_config()
        self._build_connection_bar(cfg)
        self._build_lists()
        self.status_var = tk.StringVar(value="Not connected.")
        ttk.Label(root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=8, pady=(0, 6))

    def _build_connection_bar(self, cfg: dict) -> None:
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=8)

        self.project_url_history: list[str] = cfg.get("project_url_history", [])
        current_project_url = cfg.get("project_url", "")
        if current_project_url:
            self.project_url_history = add_to_history(self.project_url_history, current_project_url)
        self.project_url_var = tk.StringVar(value=current_project_url)
        self.token_var = tk.StringVar(value=cfg.get("token", ""))
        self.mr_display_var = tk.StringVar(value="")
        self.version_var = tk.StringVar(value=program_version)

        ttk.Label(bar, text="Project URL").grid(row=0, column=0, sticky="w")
        self.project_url_combo = ttk.Combobox(
            bar, textvariable=self.project_url_var, values=self.project_url_history, width=68
        )
        self.project_url_combo.grid(row=0, column=1, padx=4, sticky="we")

        ttk.Label(bar, text="Token (read_api)").grid(row=1, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.token_var, width=30, show="*").grid(row=1, column=1, padx=4, pady=(4, 0), sticky="w")
        ttk.Button(bar, text="Create Token", command=lambda: webbrowser.open(f"{get_gitlab_base_url_from_project_url(self.project_url_var.get())}/-/user_settings/personal_access_tokens")).grid(row=1, column=1, padx=(200, 4), pady=(4, 0), sticky="w")

        self.fetch_button = ttk.Button(bar, text="Fetch MRs", command=self.on_fetch_mrs)
        self.fetch_button.grid(row=0, column=2, rowspan=1, padx=8)

        ttk.Label(bar, text="Merge request").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.mr_combo = ttk.Combobox(bar, textvariable=self.mr_display_var, state="disabled", width=90)
        self.mr_combo.grid(row=2, column=1, padx=4, pady=(6, 0), sticky="we")
        self.mr_combo.bind("<<ComboboxSelected>>", self.on_mr_selected)
        self.mr_display_var.set("Fetch MRs to load the list")

        self.progress = ttk.Progressbar(bar, mode="indeterminate")
        self.progress.grid(row=3, column=0, columnspan=3, padx=4, pady=(6, 0), sticky="we")
        self.progress.grid_remove()

        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, textvariable=self.version_var).grid(row=0, column=3, sticky="e")

    def _set_busy(self, busy: bool) -> None:
        self.fetch_button.configure(state="disabled" if busy else "normal")
        self.mr_combo.configure(state="disabled" if busy else "readonly")
        if busy:
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def _build_lists(self) -> None:
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        commits_frame = ttk.Labelframe(paned, text="Commits (select to see its files, double-click to toggle reviewed)")
        files_frame = ttk.Labelframe(paned, text="Files of selected commit (double-click to toggle reviewed)")
        paned.add(commits_frame, weight=1)
        paned.add(files_frame, weight=1)

        self.commits_tree = self._make_tree(
            commits_frame,
            ("sha", "author", "title", "reviewers"),
            {"sha": "SHA", "author": "Author", "title": "Message", "reviewers": "Reviewed by"},
        )
        self.commits_tree.tag_configure("merge", background="#e7f5ff")  # info color, may override with reviewed

        self.files_filter_var = tk.StringVar(value="Select a commit to see its files")
        self.files_filter_label = ttk.Label(files_frame, textvariable=self.files_filter_var, anchor="w")
        self.files_filter_label.pack(fill="x", padx=4, pady=(4, 0))
        self._default_filter_color = self.files_filter_label.cget("foreground")

        self.files_tree = self._make_tree(
            files_frame, ("path", "reviewers", "open"), {"path": "File", "reviewers": "Reviewed by", "open": "GitLab"}
        )
        self.files_tree.column("open", width=90, stretch=False, anchor="center")

        self.commits_tree.bind("<Double-1>", lambda e: self.on_toggle_commit())
        self.commits_tree.bind("<<TreeviewSelect>>", self.on_commit_selected)
        self.files_tree.bind("<Double-1>", self.on_files_tree_double_click)
        self.files_tree.bind("<Button-1>", self.on_files_tree_click)

    def _make_tree(self, parent, columns, headings) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            tree.heading(col, text=headings[col])
            width = 80 if col == "sha" else 120 if col == "reviewers" else 100 if col == "author" else 220
            tree.column(col, width=width, stretch=col != "sha")
        tree.tag_configure("reviewed", background="#d3f9d8")
        tree.pack(fill="both", expand=True, padx=4, pady=4)
        return tree

    def on_fetch_mrs(self) -> None:
        project_url = self.project_url_var.get().strip()
        token = self.token_var.get().strip()
        if not (project_url and token):
            messagebox.showerror("Missing info", "Fill in the project URL and token.")
            return

        try:
            base_url, project_path = parse_project_url(project_url)
        except ValueError as exc:
            messagebox.showerror("Invalid URL", str(exc))
            return

        self.project_url_history = add_to_history(self.project_url_history, project_url)
        self.project_url_combo["values"] = self.project_url_history
        save_config({"project_url": project_url, "token": token, "project_url_history": self.project_url_history})

        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None

        self.mr_display_var.set("Loading merge requests...")
        self._set_busy(True)
        self.status_var.set("Fetching merge requests...")
        threading.Thread(
            target=self._fetch_mrs_worker, args=(base_url, token, project_path), daemon=True
        ).start()

    def _fetch_mrs_worker(self, base_url: str, token: str, project_path: str) -> None:
        try:
            client = GitLabClient(base_url, token)
            project_id = client.project_id(project_path)
            mrs = client.merge_requests(project_id)
            user = client.current_user()["username"]
        except (GitLabError, Exception) as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return

        self.client = client
        self.project_id = project_id
        self.project_path = project_path
        self.current_user = user
        self.all_mrs = mrs
        self.root.after(0, self._on_mrs_fetched)

    def _on_mrs_fetched(self) -> None:
        self._set_busy(False)
        self._populate_mr_list()
        self.status_var.set(f"Signed in as {self.current_user}. {len(self.all_mrs)} open merge requests found.")

    def _populate_mr_list(self) -> None:
        self.mr_by_display = {}
        values = []
        for mr in sorted(self.all_mrs, key=lambda mr: int(mr["iid"]), reverse=True):
            display = f"!{mr['iid']} {mr.get('title', '')} [{mr.get('state', '')}]"
            self.mr_by_display[display] = mr
            values.append(display)
        self.mr_combo["values"] = values
        if self.mr_display_var.get() in self.mr_by_display:
            return
        self.mr_display_var.set("Select a merge request..." if values else "No open merge requests found")

    def on_mr_selected(self, _event=None) -> None:
        mr = self.mr_by_display.get(self.mr_display_var.get())
        if not mr or not (self.client and self.project_id and self.project_path):
            return
        mr_iid = str(mr["iid"])

        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None

        self._set_busy(True)
        self.status_var.set(f"Loading !{mr_iid}...")
        threading.Thread(target=self._load_worker, args=(mr_iid,), daemon=True).start()

    def _load_worker(self, mr_iid: str) -> None:
        try:
            commits = self.client.commits(self.project_id, mr_iid)
            state = review_state_store.load_state(self.project_path, mr_iid)
        except (GitLabError, Exception) as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return

        self.mr_iid = mr_iid
        self.state = state
        self.commit_files_cache = {}
        self.active_commit_sha = None
        self.root.after(0, lambda: self._populate(commits))

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.status_var.set("Error.")
        messagebox.showerror(f"GitLab Review Tracker", message)

    def _populate(self, commits: list[dict]) -> None:
        self.commits_tree.delete(*self.commits_tree.get_children())
        self.commit_is_merge = {}
        for commit in commits:
            sha = commit["id"]
            is_merge = len(commit.get("parent_ids") or []) > 1
            self.commit_is_merge[sha] = is_merge
            title = commit.get("title", "") + (" (merge commit)" if is_merge else "")
            author_data = commit.get("author") or {}
            author = commit.get("author_name") or author_data.get("name") or author_data.get("username", "")
            reviewers = self.state.get("commits", {}).get(sha, [])
            tags = (("merge",) if is_merge else ()) + (("reviewed",) if reviewers else ())
            self.commits_tree.insert(
                "", "end", iid=sha, values=(sha[:8], author, title, ", ".join(reviewers)), tags=tags
            )

        self.files_tree.delete(*self.files_tree.get_children())
        self.files_filter_var.set("Select a commit to see its files")
        self._set_busy(False)
        self.status_var.set(f"Loaded as {self.current_user}. {len(commits)} commits.")
        self._schedule_refresh()

    def _populate_files(self, sha: str, paths: list[str]) -> None:
        self.files_tree.delete(*self.files_tree.get_children())
        for path in paths:
            reviewers = self.state.get("files", {}).get(review_state_store.file_key(sha, path), [])
            tags = ("reviewed",) if reviewers else ()
            self.files_tree.insert(
                "", "end", iid=path, values=(path, ", ".join(reviewers), "\U0001F517 View diff"), tags=tags
            )

    def on_commit_selected(self, _event=None) -> None:
        selection = self.commits_tree.selection()
        if not selection or not self.client:
            return
        sha = selection[0]
        self.active_commit_sha = sha
        cached = self.commit_files_cache.get(sha)
        if cached is not None:
            self._show_commit_files(sha, cached)
            return
        self.files_filter_var.set(f"Loading files for commit {sha[:8]}...")
        threading.Thread(target=self._fetch_commit_files_worker, args=(sha,), daemon=True).start()

    def _fetch_commit_files_worker(self, sha: str) -> None:
        try:
            paths = self.client.commit_files(self.project_id, sha)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.commit_files_cache[sha] = paths
        self.root.after(0, lambda: self._show_commit_files(sha, paths))

    def _show_commit_files(self, sha: str, paths: list[str]) -> None:
        if self.active_commit_sha != sha:
            return  # user selected a different commit while this was loading
        self._populate_files(sha, paths)
        if not paths and self.commit_is_merge.get(sha):
            self.files_filter_label.configure(foreground="#3f93e2")
            self.files_filter_var.set(
                f"Merge commit {sha[:8]}: no direct file changes vs. its first parent "
                "(its changes are covered by the individual commits above)"
            )
        else:
            self.files_filter_label.configure(foreground=self._default_filter_color)
            self.files_filter_var.set(f"Files in commit {sha[:8]} ({len(paths)} files)")

    def on_toggle_commit(self) -> None:
        selection = self.commits_tree.selection()
        if not selection or not (self.client and self.project_path and self.mr_iid and self.current_user):
            return
        sha = selection[0]
        self.status_var.set("Updating...")
        threading.Thread(target=self._toggle_commit_worker, args=(sha,), daemon=True).start()

    def _toggle_commit_worker(self, sha: str) -> None:
        try:
            paths = self.commit_files_cache.get(sha)
            if paths is None:
                paths = self.client.commit_files(self.project_id, sha)
                self.commit_files_cache[sha] = paths
            state = review_state_store.toggle_commit_with_files(self.project_path, self.mr_iid, sha, paths, self.current_user)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.state = state
        self.root.after(0, lambda: self._on_commit_toggled(sha, paths))

    def _on_commit_toggled(self, sha: str, paths: list[str]) -> None:
        self._refresh_row(self.commits_tree, sha, "commits", sha)
        for path in paths:
            if self.files_tree.exists(path):
                self._refresh_row(self.files_tree, path, "files", review_state_store.file_key(sha, path))
        self.status_var.set(f"Signed in as {self.current_user}.")

    def on_toggle_file(self) -> None:
        selection = self.files_tree.selection()
        if not selection or not (
            self.client and self.project_path and self.mr_iid and self.current_user and self.active_commit_sha
        ):
            return
        path = selection[0]
        self.status_var.set("Updating...")
        threading.Thread(target=self._toggle_file_worker, args=(path,), daemon=True).start()

    def on_files_tree_double_click(self, event: tk.Event) -> None:
        if self.files_tree.identify_column(event.x) == "#3":
            return  # the "open in GitLab" cell is handled by the single-click handler
        self.on_toggle_file()

    def on_files_tree_click(self, event: tk.Event) -> None:
        if self.files_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.files_tree.identify_column(event.x) != "#3":
            return
        path = self.files_tree.identify_row(event.y)
        if path:
            self.open_file_diff(path)

    def open_file_diff(self, path: str) -> None:
        if not (self.client and self.project_path and self.mr_iid and self.active_commit_sha):
            return
        sha = self.active_commit_sha
        # GitLab anchors file diffs by the SHA1 hex digest of the file path.
        anchor = hashlib.sha1(path.encode("utf-8")).hexdigest()
        url = f"{self.client.base_url}/{self.project_path}/-/merge_requests/{self.mr_iid}/diffs?commit_id={sha}#diff-content-{anchor}"
        webbrowser.open(url)

    def _toggle_file_worker(self, path: str) -> None:
        sha = self.active_commit_sha
        try:
            key = review_state_store.file_key(sha, path)
            state = review_state_store.toggle(self.project_path, self.mr_iid, "files", key, self.current_user)
            commit_paths = self.commit_files_cache.get(sha, [])
            state = review_state_store.sync_commit_from_files(self.project_path, self.mr_iid, sha, commit_paths)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.state = state
        self.root.after(0, lambda: self._on_file_toggled(sha, path))

    def _on_file_toggled(self, sha: str, path: str) -> None:
        self._refresh_row(self.files_tree, path, "files", review_state_store.file_key(sha, path))
        self._refresh_row(self.commits_tree, sha, "commits", sha)
        self.status_var.set(f"Signed in as {self.current_user}.")

    def _refresh_row(self, tree: ttk.Treeview, item_id: str, kind: str, key: str) -> None:
        if not tree.exists(item_id):
            return
        reviewers = self.state.get(kind, {}).get(key, [])
        tree.set(item_id, "reviewers", ", ".join(reviewers))
        is_merge = kind == "commits" and self.commit_is_merge.get(item_id, False)
        tags = (("merge",) if is_merge else ()) + (("reviewed",) if reviewers else ())
        tree.item(item_id, tags=tags)

    def _schedule_refresh(self) -> None:
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(REFRESH_INTERVAL_MS, self._auto_refresh)

    def _auto_refresh(self) -> None:
        if not (self.project_path and self.mr_iid):
            return
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            state = review_state_store.load_state(self.project_path, self.mr_iid)
        except Exception:  # noqa: BLE001 - a transient network hiccup shouldn't interrupt the app
            self.root.after(0, self._schedule_refresh)
            return
        self.root.after(0, lambda: self._apply_refreshed_state(state))

    def _apply_refreshed_state(self, state: dict) -> None:
        self.state = state
        for sha in self.commits_tree.get_children():
            self._refresh_row(self.commits_tree, sha, "commits", sha)
        if self.active_commit_sha is not None:
            for path in self.files_tree.get_children():
                self._refresh_row(self.files_tree, path, "files", review_state_store.file_key(self.active_commit_sha, path))
        self._schedule_refresh()


def main() -> None:
    root = tk.Tk()
    ReviewTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
