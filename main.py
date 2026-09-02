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

import git_helper
import review_state_store
from gitlab_client import GitLabClient, GitLabError, parse_project_url, get_gitlab_base_url_from_project_url, get_ssh_url_from_project_url
from git_helper import get_changes_compared_to_main
from ui_commit_range_dialog import pick_commit_range
from ui_settings import SettingsDialog

DEFAULT_BEYOND_COMPARE_PATH = r"C:\Program Files\Beyond Compare 4\BCompare.exe"

program_version = "v1.2.7"

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
        root.geometry("1280x720")
        root.minsize(900, 560)
        root.configure(background="#f6f5f2")
        self._configure_styles()

        self.client: GitLabClient | None = None
        self.project_id: int | None = None
        self.project_path: str | None = None
        self.mr_iid: int | None = None
        self.state: dict = {"files": {}, "commits": {}}
        self.current_user: str | None = None
        self.commit_files_cache: dict[str, list[str]] = {}
        self.commit_is_merge: dict[str, bool] = {}
        self.active_commit_sha: str | None = None
        self._refresh_job: str | None = None
        self.all_mrs: list[dict] = []
        self.mr_by_display: dict[str, dict] = {}
        self.current_commits: list[dict] = []
        self.commit_count_var = tk.StringVar(value="0")
        self.reviewed_commit_count_var = tk.StringVar(value="0")
        self.file_count_var = tk.StringVar(value="0")
        self.reviewed_file_count_var = tk.StringVar(value="0")

        self.config = load_config()
        self.config.setdefault("beyond_compare_path", DEFAULT_BEYOND_COMPARE_PATH)
        self.status_var = tk.StringVar(value="Not connected. Enter a project URL and token to begin.")
        self._build_connection_bar(self.config)
        self._build_lists()

        project_url = self.project_url_var.get().strip()
        token = self.config.get("token", "").strip()
        if project_url and token:
            self.on_fetch_mrs()

    def _configure_styles(self) -> None:

        font: str = "Segoe UI"

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f6f5f2")
        style.configure("Surface.TFrame", background="#fffefa")
        style.configure("Header.TFrame", background="#fffefa")
        style.configure("TLabel", background="#fffefa", foreground="#3f4548", font=(font, 10))
        style.configure("Muted.TLabel", background="#fffefa", foreground="#777b7b", font=(font, 9))
        style.configure("Title.TLabel", background="#fffefa", foreground="#292e30", font=(font, 19, "bold"))
        style.configure("Subtitle.TLabel", background="#fffefa", foreground="#777b7b", font=(font, 9))
        style.configure("Status.TLabel", background="#f6f5f2", foreground="#777b7b", font=(font, 9))
        style.configure("Field.TLabel", background="#fffefa", foreground="#777b7b", font=(font, 9, "bold"))
        style.configure("TEntry", fieldbackground="#faf9f6", foreground="#292e30", insertcolor="#292e30", borderwidth=0)
        style.configure("TCombobox", fieldbackground="#faf9f6", background="#faf9f6", foreground="#292e30", borderwidth=0)
        style.map("TCombobox", fieldbackground=[("readonly", "#faf9f6")], foreground=[("readonly", "#292e30")])
        style.configure("Accent.TButton", background="#f97362", foreground="#292e30", font=(font, 9, "bold"), padding=(10, 5), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#fb8b78"), ("disabled", "#f7b0a5")])
        style.configure("Secondary.TButton", background="#ebe9e4", foreground="#3f4548", font=(font, 9), padding=(9, 5), borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#dedbd4")])
        style.configure("Card.TFrame", background="#fffefa")
        style.configure("CardValue.TLabel", background="#fffefa", foreground="#292e30", font=(font, 13, "bold"))
        style.configure("CardLabel.TLabel", background="#fffefa", foreground="#777b7b", font=(font, 8))
        style.configure("TLabelframe", background="#fffefa", bordercolor="#dedbd4", relief="solid")
        style.configure("TLabelframe.Label", background="#fffefa", foreground="#3f4548", font=(font, 10, "bold"))
        style.configure("Treeview", background="#fffefa", fieldbackground="#fffefa", foreground="#3f4548", rowheight=24, borderwidth=0, font=(font, 8))
        style.configure("Treeview.Heading", background="#f0eee9", foreground="#777b7b", font=(font, 9, "bold"), relief="flat", padding=8)
        style.map("Treeview", background=[("selected", "#fbe4dc")], foreground=[("selected", "#292e30")])
        style.configure("Horizontal.TProgressbar", background="#f97362", troughcolor="#e3e1dc", borderwidth=0)
        style.configure(
            "Slim.Vertical.TScrollbar",
            background="#d8d4cc",
            troughcolor="#f4f2ed",
            bordercolor="#f4f2ed",
            arrowcolor="#8f938f",
            relief="flat",
            width=10,
            arrowsize=10,
            gripcount=0,
        )
        style.map("Slim.Vertical.TScrollbar", background=[("active", "#c9c4ba")])

    def _build_connection_bar(self, cfg: dict) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(20, 14, 20, 12))
        header.pack(fill="x")
        ttk.Button(
            header,
            text="\u2699 Settings",
            width=14,
            style="Secondary.TButton",
            command=self.open_settings,
        ).pack(side="right", anchor="n")
        ttk.Label(header, text="Review Tracker", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Shared GitLab merge request review workspace", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 10))

        bar = ttk.Frame(self.root, style="Surface.TFrame", padding=(20, 12, 20, 14))
        bar.pack(fill="x", padx=20, pady=(12, 10))

        self.project_url_history: list[str] = cfg.get("project_url_history", [])
        current_project_url = cfg.get("project_url", "")
        if current_project_url:
            self.project_url_history = add_to_history(self.project_url_history, current_project_url)
        self.project_url_var = tk.StringVar(value=current_project_url)
        self.mr_display_var = tk.StringVar(value="")
        self.version_var = tk.StringVar(value=program_version)

        ttk.Label(bar, text="Project URL", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.project_url_combo = ttk.Combobox(
            bar, textvariable=self.project_url_var, values=self.project_url_history, width=52
        )
        self.project_url_combo.grid(row=0, column=1, padx=4, sticky="we")

        actions = ttk.Frame(bar, style="Surface.TFrame")
        actions.grid(row=0, column=3, padx=(8, 0), sticky="ne")

        self.fetch_button = ttk.Button(actions, text="Fetch MRs", width=14, style="Accent.TButton", command=self.on_fetch_mrs)
        self.fetch_button.pack(fill="x")

        ttk.Label(bar, text="Merge request", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.mr_combo = ttk.Combobox(bar, textvariable=self.mr_display_var, state="disabled", width=70)
        self.mr_combo.grid(row=2, column=1, columnspan=3, padx=0, pady=(14, 0), sticky="we")
        self.mr_combo.bind("<<ComboboxSelected>>", self.on_mr_selected)
        self.mr_display_var.set("Fetch MRs to load the list")

        self.progress = ttk.Progressbar(bar, mode="indeterminate")
        self.progress.grid(row=4, column=0, columnspan=3, pady=(6, 0), sticky="we")
        self.progress.grid_remove()

        ttk.Label(bar, textvariable=self.status_var, style="Field.TLabel").grid(
            row=3, column=0, columnspan=3, pady=(14, 0), sticky="w"
        )

        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, textvariable=self.version_var, style="Muted.TLabel").grid(row=3, column=3, sticky="e", pady=(14, 0))

    def open_settings(self) -> None:
        SettingsDialog(self.root, self.config, self._save_settings)

    def _save_settings(self, settings: dict) -> None:
        self.config.update(settings)
        save_config(self.config)

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
        metrics = ttk.Frame(self.root)
        metrics.pack(fill="x", padx=20, pady=(0, 10))
        self._metric_card(metrics, "Commits", self.commit_count_var, 0)
        self._metric_card(metrics, "Reviewed commits", self.reviewed_commit_count_var, 1)
        self._metric_card(metrics, "Changed files", self.file_count_var, 2)
        self._metric_card(metrics, "Reviewed files", self.reviewed_file_count_var, 3)
        for column in range(4):
            metrics.columnconfigure(column, weight=1)

        toolbar = ttk.Frame(self.root, style="Surface.TFrame")
        toolbar.pack(fill="x", padx=20, pady=(0, 10))
        self.beyond_compare_button = ttk.Button(
            toolbar,
            text="Open Diff in Beyond Compare",
            style="Secondary.TButton",
            command=self.on_open_beyond_compare,
        )

        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        commits_frame = ttk.Labelframe(paned, text="  Commits")
        files_frame = ttk.Labelframe(paned, text=" Changed files")
        paned.add(commits_frame, weight=1)
        paned.add(files_frame, weight=1)

        self.commits_tree = self._make_tree(
            commits_frame,
            ("sha", "author", "title", "reviewers"),
            {"sha": "SHA", "author": "Author", "title": "Message", "reviewers": "Reviewed by"},
        )
        self.commits_tree.tag_configure("merge", background="#f5eee1", foreground="#806548")

        self.files_tree = self._make_tree(
            files_frame, ("path", "reviewers", "open"), {"path": "File", "reviewers": "Reviewed by", "open": "GitLab"}
        )
        self.files_tree.column("open", width=90, stretch=False, anchor="center")

        self.commits_tree.bind("<Double-1>", lambda e: self.on_toggle_commit())
        self.commits_tree.bind("<<TreeviewSelect>>", self.on_commit_selected)
        self.commits_tree.bind("<Button-3>", self.on_commits_tree_right_click)
        self.files_tree.bind("<Double-1>", self.on_files_tree_double_click)
        self.files_tree.bind("<Button-1>", self.on_files_tree_click)
        self.files_tree.bind("<Button-3>", self.on_files_tree_right_click)

        self.commits_context_menu = tk.Menu(self.root, tearoff=0)
        self.commits_context_menu.add_command(label="Mark as reviewed", command=lambda: self.on_toggle_commit())
        self.commits_context_menu.add_command(label="Show changes compared to main", command=self._compare_selected_commit_to_main)

        self.files_context_menu = tk.Menu(self.root, tearoff=0)
        self.files_context_menu.add_command(label="Mark as reviewed", command=lambda: self.on_toggle_file())

    def _metric_card(self, parent: ttk.Frame, label: str, variable: tk.StringVar, column: int) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(12, 7))
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 6 if column < 3 else 0))
        ttk.Label(card, textvariable=variable, style="CardValue.TLabel").pack(anchor="w")
        ttk.Label(card, text=label, style="CardLabel.TLabel").pack(anchor="w", pady=(1, 0))

    def _make_tree(self, parent, columns, headings) -> ttk.Treeview:
        container = ttk.Frame(parent, style="Surface.TFrame")
        container.pack(fill="both", expand=True, padx=4, pady=4)

        tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            tree.heading(col, text=headings[col])
            width = 72 if col == "sha" else 50 if col == "reviewers" else 92 if col == "author" else 180
            tree.column(col, width=width, stretch=col != "sha")
        tree.tag_configure("reviewed", background="#dcfce7", foreground="#166534")

        scrollbar = ttk.Scrollbar(container, orient="vertical", style="Slim.Vertical.TScrollbar", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    def on_fetch_mrs(self) -> None:
        project_url = self.project_url_var.get().strip()
        token = self.config.get("token", "").strip()
        if not (project_url and token):
            messagebox.showerror("Missing info", "Enter a project URL and add an access token in Settings.")
            return

        try:
            base_url, project_path = parse_project_url(project_url)
        except ValueError as exc:
            messagebox.showerror("Invalid URL", str(exc))
            return

        self.project_url_history = add_to_history(self.project_url_history, project_url)
        self.project_url_combo["values"] = self.project_url_history
        self.config.update({"project_url": project_url, "project_url_history": self.project_url_history})
        save_config(self.config)

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
        mr_iid = int(mr["iid"])

        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None

        self._set_busy(True)
        self.status_var.set(f"Loading !{mr_iid}...")
        self.beyond_compare_button.pack_forget()
        threading.Thread(target=self._load_worker, args=(mr_iid,), daemon=True).start()

    def _load_worker(self, mr_iid: int) -> None:
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
        self.current_commits = commits
        self.root.after(0, lambda: self._populate(commits))

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.status_var.set("Error.")
        messagebox.showerror(f"GitLab Review Tracker", message)

    def on_open_beyond_compare(self) -> None:
        if not (self.client and self.project_path and self.current_commits):
            return
        result = pick_commit_range(self.root, self.current_commits)
        if not result:
            return
        first_sha, last_sha = result
        print(result)
        beyond_compare_path = self.config.get("beyond_compare_path", "").strip()
        if not beyond_compare_path:
            messagebox.showerror("Beyond Compare", "Set the Beyond Compare executable path in Settings first.")
            return

        self._set_busy(True)
        self.status_var.set("Preparing Beyond Compare diff...")
        threading.Thread(
            target=self._open_beyond_compare_worker, args=(first_sha, last_sha, beyond_compare_path), daemon=True
        ).start()

    def _open_beyond_compare_worker(self, first_sha: str, last_sha: str, beyond_compare_path: str) -> None:
        try:
           # todo
           pass
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, self._on_beyond_compare_done)

    def _on_beyond_compare_done(self) -> None:
        self._set_busy(False)
        self.status_var.set(f"Signed in as {self.current_user}.")

    def _populate(self, commits: list[dict]) -> None:
        self.commits_tree.delete(*self.commits_tree.get_children())
        self.commit_is_merge = {}
        reviewed_commits = 0
        for commit in commits:
            sha = commit["id"]
            is_merge = len(commit.get("parent_ids") or []) > 1
            self.commit_is_merge[sha] = is_merge
            title = commit.get("title", "") + (" (merge commit)" if is_merge else "")
            author_data = commit.get("author") or {}
            author = commit.get("author_name") or author_data.get("name") or author_data.get("username", "")
            reviewers = self.state.get("commits", {}).get(sha, [])
            reviewed_commits += bool(reviewers)
            tags = (("merge",) if is_merge else ()) + (("reviewed",) if reviewers else ())
            self.commits_tree.insert(
                "", "end", iid=sha, values=(sha[:8], author, title, ", ".join(reviewers)), tags=tags
            )

        self.files_tree.delete(*self.files_tree.get_children())
        self.commit_count_var.set(str(len(commits)))
        self.reviewed_commit_count_var.set(str(reviewed_commits))
        self.file_count_var.set("0")
        self.reviewed_file_count_var.set("0")
        self._set_busy(False)
        self.status_var.set(f"Loaded as {self.current_user}. {len(commits)} commits.")
        # TODO: Enable Beyond Compare button once implemented
        # self.beyond_compare_button.pack(side="right")
        self._schedule_refresh()

    def _populate_files(self, sha: str, paths: list[str]) -> None:
        self.files_tree.delete(*self.files_tree.get_children())
        reviewed_files = 0
        for path in paths:
            reviewers = self.state.get("files", {}).get(review_state_store.file_key(sha, path), [])
            tags = ("reviewed",) if reviewers else ()
            reviewed_files += bool(reviewers)
            self.files_tree.insert(
                "", "end", iid=path, values=(path, ", ".join(reviewers), "\U0001F517 View diff"), tags=tags
            )
        self.file_count_var.set(str(len(paths)))
        self.reviewed_file_count_var.set(str(reviewed_files))

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
        self._update_metrics()
        self.status_var.set(f"Signed in as {self.current_user}.")

    def on_toggle_file(self) -> None:
        selection = self.files_tree.selection()
        if not selection or not (
            self.client and self.project_path and self.mr_iid and self.current_user and self.active_commit_sha
        ):
            return
        path = selection[0]
        self.status_var.set("Updating...")
        threading.Thread(target=self._toggle_file_worker, args=(self.active_commit_sha, path), daemon=True).start()

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

    def on_commits_tree_right_click(self, event: tk.Event) -> None:
        sha = self.commits_tree.identify_row(event.y)
        if not sha:
            return
        self.commits_tree.selection_set(sha)
        self.commits_context_menu.tk_popup(event.x_root, event.y_root)

    def on_files_tree_right_click(self, event: tk.Event) -> None:
        path = self.files_tree.identify_row(event.y)
        if not path:
            return
        self.files_tree.selection_set(path)
        self.files_context_menu.tk_popup(event.x_root, event.y_root)

    def _compare_selected_commit_to_main(self) -> None:
        selection = self.commits_tree.selection()
        if not selection or not (self.client and self.project_path):
            return
        sha = selection[0]
        self._set_busy(True)
        self.status_var.set("Comparing to main...")
        threading.Thread(
            target=self._compare_to_main_worker, args=(sha,), daemon=True
        ).start()

    def _compare_to_main_worker(self, sha: str) -> None:
        try:
            diff_files, _, _ = get_changes_compared_to_main(
                project_name=self.project_path.split("/")[-1],
                repo_url=get_ssh_url_from_project_url(self.project_url_var.get()),
                commit_to_compare_sha=sha,
                previous_commit_sha=sha
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, lambda: self._on_compare_to_main_done(sha, diff_files))

    def _on_compare_to_main_done(self, sha: str, diff_files: list[str]) -> None:
        self._set_busy(False)
        self.status_var.set(f"Signed in as {self.current_user}.")
        if not diff_files:
            messagebox.showinfo("No differences", "No differences compared to main.")
            return
        self._show_diff_files_window(sha, diff_files)

    def _show_diff_files_window(self, sha: str, diff_files: list[str]) -> None:
        window = tk.Toplevel(self.root)
        window.title(f"Changes vs main - {sha[:8]}")
        window.geometry("640x420")
        window.configure(background="#f6f5f2")

        ttk.Label(
            window, text=f"Files of commit {sha[:8]} that differ from main ({len(diff_files)})", style="Field.TLabel"
        ).pack(anchor="w", padx=12, pady=(12, 6))

        container = ttk.Frame(window, style="Surface.TFrame")
        container.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        tree = ttk.Treeview(container, columns=("path", "reviewers", "open"), show="headings", selectmode="browse")
        tree.heading("path", text="File")
        tree.heading("reviewers", text="Reviewed by")
        tree.heading("open", text="GitLab")
        tree.column("path", width=360, stretch=True)
        tree.column("reviewers", width=50, stretch=False)
        tree.column("open", width=100, stretch=False, anchor="center")
        tree.tag_configure("reviewed", background="#dcfce7", foreground="#166534")
        for path in diff_files:
            reviewers = self.state.get("files", {}).get(review_state_store.file_key(sha, path), [])
            tags = ("reviewed",) if reviewers else ()
            tree.insert("", "end", iid=path, values=(path, ", ".join(reviewers), "\U0001F517 View diff"), tags=tags)

        scrollbar = ttk.Scrollbar(container, orient="vertical", style="Slim.Vertical.TScrollbar", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        diff_context_menu = tk.Menu(window, tearoff=0)
        diff_context_menu.add_command(
            label="Mark as reviewed", command=lambda: self._toggle_diff_file_reviewed(sha, tree)
        )

        def on_click(event: tk.Event) -> None:
            if tree.identify_region(event.x, event.y) != "cell":
                return
            if tree.identify_column(event.x) != "#3":
                return
            path = tree.identify_row(event.y)
            if path:
                self._open_diff_vs_main(sha, path)

        def on_right_click(event: tk.Event) -> None:
            path = tree.identify_row(event.y)
            if not path:
                return
            tree.selection_set(path)
            diff_context_menu.tk_popup(event.x_root, event.y_root)

        tree.bind("<Button-1>", on_click)
        tree.bind("<Button-3>", on_right_click)

    def _toggle_diff_file_reviewed(self, sha: str, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection or not (self.project_path and self.mr_iid and self.current_user):
            return
        path = selection[0]
        threading.Thread(target=self._toggle_file_worker, args=(sha, path, tree), daemon=True).start()

    def _open_diff_vs_main(self, sha: str, path: str) -> None:
        # GitLab anchors commit diffs by the SHA1 hex digest of the file path.
        anchor = hashlib.sha1(path.encode("utf-8")).hexdigest()
        url = f"{self.client.base_url}/{self.project_path}/-/commit/{sha}#diff-content-{anchor}"
        webbrowser.open(url)

    def _toggle_file_worker(self, sha: str, path: str, tree: ttk.Treeview | None = None) -> None:
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
        self.root.after(0, lambda: self._on_file_toggled(sha, path, tree))

    def _on_file_toggled(self, sha: str, path: str, tree: ttk.Treeview | None = None) -> None:
        # ugly but keep for now
        if tree is not None and tree.exists(path):
            self._refresh_row(tree, path, "files", review_state_store.file_key(sha, path))
        if self.files_tree.exists(path):
            self._refresh_row(self.files_tree, path, "files", review_state_store.file_key(sha, path))
        self._refresh_row(self.commits_tree, sha, "commits", sha)
        self._update_metrics()
        self.status_var.set(f"Signed in as {self.current_user}.")

    def _refresh_row(self, tree: ttk.Treeview, item_id: str, kind: str, key: str) -> None:
        if not tree.exists(item_id):
            return
        reviewers = self.state.get(kind, {}).get(key, [])
        tree.set(item_id, "reviewers", ", ".join(reviewers))
        is_merge = kind == "commits" and self.commit_is_merge.get(item_id, False)
        tags = (("merge",) if is_merge else ()) + (("reviewed",) if reviewers else ())
        tree.item(item_id, tags=tags)

    def _update_metrics(self) -> None:
        commit_rows = self.commits_tree.get_children()
        file_rows = self.files_tree.get_children()
        reviewed_commits = sum("reviewed" in self.commits_tree.item(item, "tags") for item in commit_rows)
        reviewed_files = sum("reviewed" in self.files_tree.item(item, "tags") for item in file_rows)
        self.commit_count_var.set(str(len(commit_rows)))
        self.reviewed_commit_count_var.set(str(reviewed_commits))
        self.file_count_var.set(str(len(file_rows)))
        self.reviewed_file_count_var.set(str(reviewed_files))

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
        self._update_metrics()
        self._schedule_refresh()


def main() -> None:
    root = tk.Tk()
    ReviewTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
