"""CustomTkinter desktop app for marking GitLab MR commits/files as reviewed.

Review state is shared: it's stored as a JSON file on a network share (see
review_state_store.py), so anyone running this tool against the same MR sees the
same state. Only read-only GitLab API calls are made.
"""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from review_tracker.core.review_service import ReviewService
from review_tracker.data.gitlab_client import parse_project_url
from review_tracker.data.config_store import load_config, save_config, add_to_history
from .dialogs.commit_range import pick_commit_range
from .dialogs.settings import SettingsDialog
from .dialogs.bug_feature_request import BugFeatureRequestDialog
from .naming_interface import NamingInterface
from .theme_loader import initialize_theme_loader
from .theme_integration import get_color
from .ctk_style import FONT, MONO_FONT, sz, fsz
from .ctk_widgets import CTkRowList

naming_interface = NamingInterface()

DEFAULT_BEYOND_COMPARE_PATH = r"C:\Program Files\Beyond Compare 4\BCompare.exe"

program_version = "v1.6.0"

DEFAULT_REFRESH_INTERVAL_SECONDS = 30


class ReviewTrackerApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        root.title(naming_interface.get_attr("app_title").format(version=program_version))
        root.geometry(f"{sz(1280)}x{sz(760)}")
        root.minsize(sz(980), sz(600))
        root.configure(fg_color=get_color("background"))

        self.service = ReviewService()
        self._refresh_job: str | None = None
        self.mr_by_display: dict[str, dict] = {}
        self.commit_count_var = tk.StringVar(value="0")
        self.reviewed_commit_count_var = tk.StringVar(value="0")
        self.file_count_var = tk.StringVar(value="0")
        self.reviewed_file_count_var = tk.StringVar(value="0")
        self.show_closed_mrs = False
        self.show_merged_mrs = False
        self._active_toggle_tree: CTkRowList | None = None

        self.config = load_config()
        self.config.setdefault("beyond_compare_path", DEFAULT_BEYOND_COMPARE_PATH)
        self.config.setdefault("refresh_interval_seconds", str(DEFAULT_REFRESH_INTERVAL_SECONDS))
        self.config.setdefault("token", "")
        self.config.setdefault("project_url", "")
        self.config.setdefault("project_url_history", [])
        self.status_var = tk.StringVar(value=naming_interface.get_attr("v_status_not_connected"))
        self._build_header()
        self._build_connection_bar(self.config)
        self._build_metrics()
        self._build_toolbar()
        self._build_lists()

        project_url = self.project_url_var.get().strip()
        token = self.config.get("token", "").strip()
        if project_url and token:
            self.on_fetch_mrs()

    # ------------------------------------------------------------------ layout
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.root, corner_radius=0, fg_color=get_color("surface"))
        header.pack(fill="x")

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", anchor="w", padx=sz(24), pady=(sz(16), sz(12)))
        ctk.CTkLabel(
            title_box,
            text=naming_interface.get_attr("l_app_name"),
            font=(FONT, fsz(20), "bold"),
            text_color=get_color("text_primary"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text=naming_interface.get_attr("l_app_subtitle"),
            font=(FONT, fsz(12)),
            text_color=get_color("text_muted"),
            anchor="w",
        ).pack(anchor="w", pady=(sz(2), 0))

        btn_box = ctk.CTkFrame(header, fg_color="transparent")
        btn_box.pack(side="right", anchor="e", padx=sz(24), pady=(sz(16), sz(12)))
        ctk.CTkButton(
            btn_box,
            text=naming_interface.get_attr("b_settings"),
            width=sz(110),
            height=sz(30),
            font=(FONT, fsz(11)),
            fg_color=get_color("secondary_button"),
            hover_color=get_color("secondary_hover"),
            text_color=get_color("text_secondary"),
            command=self.open_settings,
        ).pack(side="right")
        ctk.CTkButton(
            btn_box,
            text=naming_interface.get_attr("b_bug_feature_request"),
            width=sz(230),
            height=sz(30),
            font=(FONT, fsz(11)),
            fg_color=get_color("secondary_button"),
            hover_color=get_color("secondary_hover"),
            text_color=get_color("text_secondary"),
            command=self.open_bug_feature_request,
        ).pack(side="right", padx=(0, sz(8)))

    def _build_connection_bar(self, cfg: dict) -> None:
        card = ctk.CTkFrame(self.root, corner_radius=sz(14), fg_color=get_color("surface"))
        card.pack(fill="x", padx=sz(20), pady=(sz(16), sz(10)))
        card.grid_columnconfigure(1, weight=1)

        self.project_url_history: list[str] = cfg.get("project_url_history", [])
        current_project_url = cfg.get("project_url", "")
        if current_project_url:
            self.project_url_history = add_to_history(self.project_url_history, current_project_url)
        self.project_url_var = tk.StringVar(value=current_project_url)
        self.mr_display_var = tk.StringVar(value="")
        self.version_var = tk.StringVar(value=program_version)

        ctk.CTkLabel(
            card,
            text=naming_interface.get_attr("l_project_url"),
            font=(FONT, fsz(11), "bold"),
            text_color=get_color("text_muted"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(sz(18), sz(8)), pady=(sz(18), sz(6)))

        url_row = ctk.CTkFrame(card, fg_color="transparent")
        url_row.grid(row=0, column=1, sticky="we", padx=(0, sz(18)), pady=(sz(18), sz(6)))
        url_row.grid_columnconfigure(0, weight=1)
        self.project_url_combo = ctk.CTkComboBox(
            url_row,
            variable=self.project_url_var,
            values=self.project_url_history,
            font=(FONT, fsz(12)),
            height=sz(34),
            command=self.on_project_url_selected,
        )
        self.project_url_combo.grid(row=0, column=0, sticky="we")
        self.fetch_button = ctk.CTkButton(
            url_row,
            text=naming_interface.get_attr("b_refresh"),
            width=sz(40),
            height=sz(34),
            font=(FONT, fsz(14)),
            command=self.on_fetch_mrs,
        )
        self.fetch_button.grid(row=0, column=1, padx=(sz(8), 0))

        ctk.CTkLabel(
            card,
            text=naming_interface.get_attr("l_merge_request"),
            font=(FONT, fsz(11), "bold"),
            text_color=get_color("text_muted"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(sz(18), sz(8)), pady=sz(6))
        self.mr_combo = ctk.CTkComboBox(
            card,
            variable=self.mr_display_var,
            values=[],
            state="disabled",
            font=(FONT, fsz(12)),
            height=sz(34),
            command=self.on_mr_selected,
        )
        self.mr_combo.grid(row=1, column=1, sticky="we", padx=(0, sz(18)), pady=sz(6))
        self.mr_display_var.set(naming_interface.get_attr("v_fetch_mrs_to_load"))

        check_row = ctk.CTkFrame(card, fg_color="transparent")
        check_row.grid(row=2, column=0, columnspan=2, sticky="w", padx=sz(18), pady=(sz(4), sz(4)))
        self.show_closed_var = tk.BooleanVar(value=False)
        self.show_merged_var = tk.BooleanVar(value=False)
        self.show_closed_mrs_checkbox = ctk.CTkCheckBox(
            check_row,
            text=naming_interface.get_attr("cb_show_closed_mrs"),
            variable=self.show_closed_var,
            font=(FONT, fsz(11)),
            command=self._on_filter_changed,
        )
        self.show_closed_mrs_checkbox.pack(side="left", padx=(0, sz(20)))
        self.show_merged_mrs_checkbox = ctk.CTkCheckBox(
            check_row,
            text=naming_interface.get_attr("cb_show_merged_mrs"),
            variable=self.show_merged_var,
            font=(FONT, fsz(11)),
            command=self._on_filter_changed,
        )
        self.show_merged_mrs_checkbox.pack(side="left")

        self.progress = ctk.CTkProgressBar(card, mode="indeterminate")
        self.progress.grid(row=3, column=0, columnspan=2, padx=sz(18), pady=(sz(2), 0), sticky="we")
        self.progress.grid_remove()

        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.grid(row=4, column=0, columnspan=2, sticky="we", padx=sz(18), pady=(sz(10), sz(18)))
        status_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            status_row,
            textvariable=self.status_var,
            font=(FONT, fsz(11)),
            text_color=get_color("text_muted"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            status_row,
            textvariable=self.version_var,
            font=(FONT, fsz(10)),
            text_color=get_color("text_muted"),
        ).grid(row=0, column=1, sticky="e")

    def open_settings(self) -> None:
        SettingsDialog(self.root, self.config, self._save_settings)

    def open_bug_feature_request(self) -> None:
        BugFeatureRequestDialog(self.root, self.service.current_user)

    def _on_filter_changed(self) -> None:
        """Handle checkbox changes for MR filtering."""
        self.show_closed_mrs = self.show_closed_var.get()
        self.show_merged_mrs = self.show_merged_var.get()
        # Re-fetch MRs if we have a project URL and token
        if self.service.client and self.service.project_id:
            self.on_fetch_mrs()

    def _save_settings(self, settings: dict) -> None:
        self.config.update(settings)
        save_config(self.config)
        if self.service.project_path and self.service.mr_iid:
            self._schedule_refresh()

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.fetch_button.configure(state=state)
        self.mr_combo.configure(state=state)
        self.show_closed_mrs_checkbox.configure(state=state)
        self.show_merged_mrs_checkbox.configure(state=state)
        if busy:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def _set_toggle_busy(self, busy: bool, extra_tree: CTkRowList | None = None) -> None:
        """Disable the lists and show progress while a reviewed-toggle write is in flight."""
        if busy:
            self._active_toggle_tree = extra_tree
        else:
            extra_tree = extra_tree or self._active_toggle_tree
            self._active_toggle_tree = None
        self.commits_tree.set_enabled(not busy)
        self.files_tree.set_enabled(not busy)
        if extra_tree is not None:
            extra_tree.set_enabled(not busy)
        if busy:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def _build_metrics(self) -> None:
        row = ctk.CTkFrame(self.root, fg_color="transparent")
        row.pack(fill="x", padx=sz(20), pady=(0, sz(10)))
        for column in range(4):
            row.grid_columnconfigure(column, weight=1)
        self._metric_card(row, naming_interface.get_attr("l_commits"), self.commit_count_var, 0)
        self._metric_card(row, naming_interface.get_attr("l_reviewed_commits"), self.reviewed_commit_count_var, 1, accent=True)
        self._metric_card(row, naming_interface.get_attr("l_changed_files"), self.file_count_var, 2)
        self._metric_card(row, naming_interface.get_attr("l_reviewed_files"), self.reviewed_file_count_var, 3, accent=True)

    def _metric_card(self, parent, label: str, variable: tk.StringVar, column: int, accent: bool = False) -> None:
        card = ctk.CTkFrame(parent, corner_radius=sz(12), fg_color=get_color("surface"))
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else sz(6), 0))
        ctk.CTkLabel(
            card,
            textvariable=variable,
            font=(FONT, fsz(22), "bold"),
            text_color=get_color("row_reviewed_fg") if accent else get_color("text_primary"),
        ).pack(anchor="w", padx=sz(14), pady=(sz(12), 0))
        ctk.CTkLabel(
            card, text=label, font=(FONT, fsz(11)), text_color=get_color("text_muted"),
        ).pack(anchor="w", padx=sz(14), pady=(0, sz(12)))

    def _build_toolbar(self) -> None:
        toolbar = ctk.CTkFrame(self.root, fg_color="transparent")
        toolbar.pack(fill="x", padx=sz(20), pady=(0, sz(10)))
        self.beyond_compare_button = ctk.CTkButton(
            toolbar,
            text=naming_interface.get_attr("b_open_beyond_compare"),
            font=(FONT, fsz(11)),
            fg_color=get_color("secondary_button"),
            hover_color=get_color("secondary_hover"),
            text_color=get_color("text_secondary"),
            height=sz(30),
            command=self.on_open_beyond_compare,
        )
        self.open_mr_button = ctk.CTkButton(
            toolbar,
            text=naming_interface.get_attr("b_open_mr_in_gitlab"),
            font=(FONT, fsz(11)),
            fg_color=get_color("secondary_button"),
            hover_color=get_color("secondary_hover"),
            text_color=get_color("text_secondary"),
            height=sz(30),
            command=self.on_open_mr_in_gitlab,
        )

    def _build_lists(self) -> None:
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=sz(20), pady=(0, sz(20)))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            body,
            text=naming_interface.get_attr("l_commits_panel"),
            font=(FONT, fsz(13), "bold"),
            text_color=get_color("text_secondary"),
        ).grid(row=0, column=0, sticky="w", pady=(0, sz(6)))
        ctk.CTkLabel(
            body,
            text=naming_interface.get_attr("l_changed_files_panel"),
            font=(FONT, fsz(13), "bold"),
            text_color=get_color("text_secondary"),
        ).grid(row=0, column=1, sticky="w", padx=(sz(16), 0), pady=(0, sz(6)))

        commits_panel = ctk.CTkFrame(body, corner_radius=sz(14), fg_color=get_color("surface"))
        commits_panel.grid(row=1, column=0, sticky="nsew", padx=(0, sz(8)))
        files_panel = ctk.CTkFrame(body, corner_radius=sz(14), fg_color=get_color("surface"))
        files_panel.grid(row=1, column=1, sticky="nsew", padx=(sz(8), 0))

        self.commits_tree = CTkRowList(
            commits_panel,
            build_row=self._build_commit_row,
            default_bg=get_color("surface"),
            selection_border_color=get_color("accent"),
            corner_radius=sz(8),
        )
        self.commits_tree.pack(fill="both", expand=True, padx=sz(8), pady=sz(8))
        self.commits_tree.tag_configure("merge", background=get_color("row_merge_bg"), foreground=get_color("row_merge_fg"))
        self.commits_tree.tag_configure("reviewed", background=get_color("row_reviewed_bg"), foreground=get_color("row_reviewed_fg"))
        self.commits_tree.on_select = self.on_commit_selected
        self.commits_tree.on_double_click = lambda iid: self.on_toggle_commit()
        self.commits_tree.on_right_click = self.on_commits_tree_right_click

        self.files_tree = CTkRowList(
            files_panel,
            build_row=lambda rl, f, i, v, t: self._build_file_row(rl, f, i, v, t, open_callback=self.open_file_diff),
            default_bg=get_color("surface"),
            selection_border_color=get_color("accent"),
            corner_radius=sz(8),
        )
        self.files_tree.pack(fill="both", expand=True, padx=sz(8), pady=sz(8))
        self.files_tree.tag_configure("reviewed", background=get_color("row_reviewed_bg"), foreground=get_color("row_reviewed_fg"))
        self.files_tree.on_double_click = lambda iid: self.on_toggle_file()
        self.files_tree.on_right_click = self.on_files_tree_right_click

        self.commits_context_menu = tk.Menu(self.root, tearoff=0)
        self.commits_context_menu.add_command(label=naming_interface.get_attr("m_mark_reviewed"), command=lambda: self.on_toggle_commit())
        self.commits_context_menu.add_command(label=naming_interface.get_attr("m_compare_to_main"), command=self._compare_selected_commit_to_main)

        self.files_context_menu = tk.Menu(self.root, tearoff=0)
        self.files_context_menu.add_command(label=naming_interface.get_attr("m_mark_reviewed"), command=lambda: self.on_toggle_file())

    # ------------------------------------------------------------- row builders
    @staticmethod
    def _reviewers_text(reviewers: str) -> str:
        return f"\u2713 {reviewers}" if reviewers else "not reviewed"

    @staticmethod
    def _reviewers_color(reviewers: str) -> str:
        return get_color("row_reviewed_fg") if reviewers else get_color("text_muted")

    def _build_commit_row(self, row_list: CTkRowList, frame: ctk.CTkFrame, iid: str, values: dict, tags: tuple) -> dict:
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            frame,
            text=values["sha"],
            font=(MONO_FONT, fsz(11)),
            width=sz(72),
            anchor="w",
            text_color=get_color("text_muted"),
        ).grid(row=0, column=0, sticky="w", padx=(sz(10), sz(4)), pady=sz(5))

        text_box = ctk.CTkFrame(frame, fg_color="transparent")
        text_box.grid(row=0, column=1, sticky="we", pady=sz(2))
        title_label = ctk.CTkLabel(
            text_box, text=values["title"], font=(FONT, fsz(11)), anchor="w", text_color=get_color("text_primary"),
        )
        title_label.pack(anchor="w")
        author_label = ctk.CTkLabel(
            text_box, text=values["author"], font=(FONT, fsz(10)), anchor="w", text_color=get_color("text_muted"),
        )
        author_label.pack(anchor="w")

        reviewers_label = ctk.CTkLabel(
            frame,
            text=self._reviewers_text(values["reviewers"]),
            font=(FONT, fsz(10)),
            text_color=self._reviewers_color(values["reviewers"]),
        )
        reviewers_label.grid(row=0, column=2, sticky="e", padx=sz(10))
        return {"title": title_label, "author": author_label, "reviewers": reviewers_label}

    def _build_file_row(self, row_list: CTkRowList, frame: ctk.CTkFrame, iid: str, values: dict, tags: tuple, open_callback) -> dict:
        frame.grid_columnconfigure(0, weight=1)
        path_label = ctk.CTkLabel(
            frame, text=values["path"], font=(FONT, fsz(11)), anchor="w", text_color=get_color("text_primary"),
        )
        path_label.grid(row=0, column=0, sticky="w", padx=(sz(12), sz(6)), pady=sz(6))
        reviewers_label = ctk.CTkLabel(
            frame,
            text=self._reviewers_text(values["reviewers"]),
            font=(FONT, fsz(10)),
            text_color=self._reviewers_color(values["reviewers"]),
        )
        reviewers_label.grid(row=0, column=1, sticky="e", padx=(sz(6), sz(6)))
        diff_button = ctk.CTkButton(
            frame,
            text=naming_interface.get_attr("v_view_diff"),
            width=sz(90),
            height=sz(24),
            font=(FONT, fsz(10)),
            command=lambda path=iid: open_callback(path),
        )
        diff_button.grid(row=0, column=2, sticky="e", padx=(0, sz(10)))
        return {"path": path_label, "reviewers": reviewers_label, "_skip_bind": [diff_button]}

    # --------------------------------------------------------------- data flow
    def on_fetch_mrs(self) -> None:
        project_url = self.project_url_var.get().strip()
        token = self.config.get("token", "").strip()
        if not (project_url and token):
            messagebox.showerror(naming_interface.get_attr("t_missing_info"), naming_interface.get_attr("m_missing_info"))
            return

        try:
            parse_project_url(project_url)
        except ValueError as exc:
            messagebox.showerror(naming_interface.get_attr("t_invalid_url"), str(exc))
            return

        self.project_url_history = add_to_history(self.project_url_history, project_url)
        self.project_url_combo.configure(values=self.project_url_history)
        self.config.update({"project_url": project_url, "project_url_history": self.project_url_history})
        save_config(self.config)

        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None

        self.open_mr_button.pack_forget()
        self.beyond_compare_button.pack_forget()
        self.mr_display_var.set(naming_interface.get_attr("v_loading_merge_requests"))
        self._set_busy(True)
        self.status_var.set(naming_interface.get_attr("v_fetching_merge_requests"))
        threading.Thread(
            target=self._fetch_mrs_worker, args=(project_url, token), daemon=True
        ).start()

    def _fetch_mrs_worker(self, project_url: str, token: str) -> None:
        try:
            self.service.connect(project_url, token, self.show_closed_mrs, self.show_merged_mrs)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, self._on_mrs_fetched)

    def _on_mrs_fetched(self) -> None:
        self._set_busy(False)
        self._populate_mr_list()
        self.status_var.set(
            naming_interface.get_attr("v_signed_in_mrs_found").format(
                user=self.service.current_user, count=len(self.service.all_mrs)
            )
        )

    def _populate_mr_list(self) -> None:
        self.mr_by_display = {}
        values = []
        for mr in sorted(self.service.all_mrs, key=lambda mr: int(mr["iid"]), reverse=True):
            display = f"!{mr['iid']} {mr.get('title', '')} [{mr.get('state', '')}]"
            self.mr_by_display[display] = mr
            values.append(display)
        self.mr_combo.configure(values=values)
        if self.mr_display_var.get() in self.mr_by_display:
            return
        self.mr_display_var.set(naming_interface.get_attr("v_select_merge_request") if values else naming_interface.get_attr("v_no_open_merge_requests"))

    def on_project_url_selected(self, _value: str | None = None) -> None:
        project_url = self.project_url_var.get()
        if project_url:
            self.on_fetch_mrs()

    def on_mr_selected(self, _value: str | None = None) -> None:
        mr = self.mr_by_display.get(self.mr_display_var.get())
        if not mr or not (self.service.client and self.service.project_id and self.service.project_path):
            return
        mr_iid = int(mr["iid"])

        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None

        self._set_busy(True)
        self.status_var.set(naming_interface.get_attr("v_loading_mr").format(iid=mr_iid))
        self.beyond_compare_button.pack_forget()
        self.open_mr_button.pack(side="right", padx=(sz(8), 0))
        threading.Thread(target=self._load_worker, args=(mr,), daemon=True).start()

    def _load_worker(self, mr: dict) -> None:
        try:
            self.service.select_merge_request(mr)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, lambda: self._populate(self.service.current_commits))

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self._set_toggle_busy(False)
        self.status_var.set(naming_interface.get_attr("v_error"))
        messagebox.showerror(naming_interface.get_attr("l_app_name"), message)

    def on_open_mr_in_gitlab(self) -> None:
        if self.service.current_mr_url:
            webbrowser.open(self.service.current_mr_url)

    def on_open_beyond_compare(self) -> None:
        if not (self.service.client and self.service.project_path and self.service.current_commits):
            return
        result = pick_commit_range(self.root, self.service.current_commits)
        if not result:
            return
        first_sha, last_sha = result
        beyond_compare_path = self.config.get("beyond_compare_path", "").strip()
        if not beyond_compare_path:
            messagebox.showerror(naming_interface.get_attr("t_beyond_compare"), naming_interface.get_attr("m_beyond_compare_path"))
            return

        self._set_busy(True)
        self.status_var.set(naming_interface.get_attr("v_preparing_beyond_compare"))
        threading.Thread(
            target=self._open_beyond_compare_worker, args=(first_sha, last_sha, beyond_compare_path), daemon=True
        ).start()

    def _open_beyond_compare_worker(self, first_sha: str, last_sha: str, beyond_compare_path: str) -> None:
        try:
            self.service.open_beyond_compare(first_sha, last_sha, beyond_compare_path)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, self._on_beyond_compare_done)

    def _on_beyond_compare_done(self) -> None:
        self._set_busy(False)
        self.status_var.set(naming_interface.get_attr("v_signed_in").format(user=self.service.current_user))

    def _populate(self, commits: list[dict]) -> None:
        self.commits_tree.delete_all()
        reviewed_commits = 0
        for commit in commits:
            sha = commit["id"]
            is_merge = self.service.commit_is_merge.get(sha, False)
            title = commit.get("title", "") + (naming_interface.get_attr("v_merge_commit") if is_merge else "")
            author_data = commit.get("author") or {}
            author = commit.get("author_name") or author_data.get("name") or author_data.get("username", "")
            reviewers = self.service.state.get("commits", {}).get(sha, [])
            reviewed_commits += bool(reviewers)
            tags = (("merge",) if is_merge else ()) + (("reviewed",) if reviewers else ())
            self.commits_tree.insert(
                sha, {"sha": sha[:8], "author": author, "title": title, "reviewers": ", ".join(reviewers)}, tags=tags
            )

        self.files_tree.delete_all()
        self.commit_count_var.set(str(len(commits)))
        self.reviewed_commit_count_var.set(str(reviewed_commits))
        self.file_count_var.set("0")
        self.reviewed_file_count_var.set("0")
        self._set_busy(False)
        self.status_var.set(naming_interface.get_attr("v_loaded_commits").format(user=self.service.current_user, count=len(commits)))
        self.beyond_compare_button.pack(side="right")
        self._schedule_refresh()

    def _populate_files(self, sha: str, paths: list[str]) -> None:
        self.files_tree.delete_all()
        reviewed_files = 0
        for path in paths:
            reviewers = self.service.state.get("files", {}).get(self.service.file_key(sha, path), [])
            tags = ("reviewed",) if reviewers else ()
            reviewed_files += bool(reviewers)
            self.files_tree.insert(path, {"path": path, "reviewers": ", ".join(reviewers)}, tags=tags)
        self.file_count_var.set(str(len(paths)))
        self.reviewed_file_count_var.set(str(reviewed_files))

    def on_commit_selected(self, sha: str) -> None:
        if not self.service.client:
            return
        self.service.active_commit_sha = sha
        cached = self.service.commit_files_cache.get(sha)
        if cached is not None:
            self._show_commit_files(sha, cached)
            return
        threading.Thread(target=self._fetch_commit_files_worker, args=(sha,), daemon=True).start()

    def _fetch_commit_files_worker(self, sha: str) -> None:
        try:
            paths = self.service.fetch_commit_files(sha)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, lambda: self._show_commit_files(sha, paths))

    def _show_commit_files(self, sha: str, paths: list[str]) -> None:
        if self.service.active_commit_sha != sha:
            return  # user selected a different commit while this was loading
        self._populate_files(sha, paths)

    def on_toggle_commit(self) -> None:
        selection = self.commits_tree.selection()
        if not selection or not (
            self.service.client and self.service.project_path and self.service.mr_iid and self.service.current_user
        ):
            return
        sha = selection[0]
        self.status_var.set(naming_interface.get_attr("v_updating"))
        self._set_toggle_busy(True)
        threading.Thread(target=self._toggle_commit_worker, args=(sha,), daemon=True).start()

    def _toggle_commit_worker(self, sha: str) -> None:
        try:
            self.service.toggle_commit(sha)
            paths = self.service.commit_files_cache.get(sha, [])
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, lambda: self._on_commit_toggled(sha, paths))

    def _on_commit_toggled(self, sha: str, paths: list[str]) -> None:
        self._refresh_row(self.commits_tree, sha, "commits", sha)
        for path in paths:
            if self.files_tree.exists(path):
                self._refresh_row(self.files_tree, path, "files", self.service.file_key(sha, path))
        self._update_metrics()
        self._set_toggle_busy(False)
        self.status_var.set(naming_interface.get_attr("v_signed_in").format(user=self.service.current_user))

    def on_toggle_file(self) -> None:
        selection = self.files_tree.selection()
        if not selection or not (
            self.service.client
            and self.service.project_path
            and self.service.mr_iid
            and self.service.current_user
            and self.service.active_commit_sha
        ):
            return
        path = selection[0]
        self.status_var.set(naming_interface.get_attr("v_updating"))
        self._set_toggle_busy(True)
        threading.Thread(target=self._toggle_file_worker, args=(self.service.active_commit_sha, path), daemon=True).start()

    def open_file_diff(self, path: str) -> None:
        if not (
            self.service.client and self.service.project_path and self.service.mr_iid and self.service.active_commit_sha
        ):
            return
        webbrowser.open(self.service.merge_request_diff_url(path))

    def on_commits_tree_right_click(self, iid: str, event) -> None:
        self.commits_context_menu.tk_popup(event.x_root, event.y_root)

    def on_files_tree_right_click(self, iid: str, event) -> None:
        self.files_context_menu.tk_popup(event.x_root, event.y_root)

    def _compare_selected_commit_to_main(self) -> None:
        selection = self.commits_tree.selection()
        if not selection or not (self.service.client and self.service.project_path):
            return
        sha = selection[0]
        self._set_busy(True)
        self.status_var.set(naming_interface.get_attr("v_comparing_to_main"))
        threading.Thread(
            target=self._compare_to_main_worker, args=(sha,), daemon=True
        ).start()

    def _compare_to_main_worker(self, sha: str) -> None:
        try:
            diff_files = self.service.compare_commit_to_main(sha)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, lambda: self._on_compare_to_main_done(sha, diff_files))

    def _on_compare_to_main_done(self, sha: str, diff_files: list[str]) -> None:
        self._set_busy(False)
        self.status_var.set(naming_interface.get_attr("v_signed_in").format(user=self.service.current_user))
        if not diff_files:
            messagebox.showinfo(naming_interface.get_attr("t_no_differences"), naming_interface.get_attr("m_no_differences"))
            return
        self._show_diff_files_window(sha, diff_files)

    def _show_diff_files_window(self, sha: str, diff_files: list[str]) -> None:
        window = ctk.CTkToplevel(self.root)
        window.title(naming_interface.get_attr("t_changes_vs_main").format(sha=sha[:8]))
        window.geometry(f"{sz(640)}x{sz(460)}")
        window.configure(fg_color=get_color("background"))

        ctk.CTkLabel(
            window,
            text=naming_interface.get_attr("l_files_differ_from_main").format(sha=sha[:8], count=len(diff_files)),
            font=(FONT, fsz(12)),
            text_color=get_color("text_secondary"),
            anchor="w",
        ).pack(anchor="w", padx=sz(16), pady=(sz(16), sz(8)))

        panel = ctk.CTkFrame(window, corner_radius=sz(14), fg_color=get_color("surface"))
        panel.pack(fill="both", expand=True, padx=sz(16), pady=(0, sz(16)))

        tree = CTkRowList(
            panel,
            build_row=lambda rl, f, i, v, t: self._build_file_row(
                rl, f, i, v, t, open_callback=lambda path: self._open_diff_vs_main(sha, path)
            ),
            default_bg=get_color("surface"),
            selection_border_color=get_color("accent"),
            corner_radius=sz(8),
        )
        tree.pack(fill="both", expand=True, padx=sz(8), pady=sz(8))
        tree.tag_configure("reviewed", background=get_color("row_reviewed_bg"), foreground=get_color("row_reviewed_fg"))

        for path in diff_files:
            reviewers = self.service.state.get("files", {}).get(self.service.file_key(sha, path), [])
            tags = ("reviewed",) if reviewers else ()
            tree.insert(path, {"path": path, "reviewers": ", ".join(reviewers)}, tags=tags)

        diff_context_menu = tk.Menu(window, tearoff=0)
        diff_context_menu.add_command(
            label=naming_interface.get_attr("m_mark_reviewed"), command=lambda: self._toggle_diff_file_reviewed(sha, tree)
        )
        tree.on_right_click = lambda iid, event: diff_context_menu.tk_popup(event.x_root, event.y_root)

    def _toggle_diff_file_reviewed(self, sha: str, tree: CTkRowList) -> None:
        selection = tree.selection()
        if not selection or not (self.service.project_path and self.service.mr_iid and self.service.current_user):
            return
        path = selection[0]
        self.status_var.set(naming_interface.get_attr("v_updating"))
        self._set_toggle_busy(True, extra_tree=tree)
        threading.Thread(target=self._toggle_file_worker, args=(sha, path, tree), daemon=True).start()

    def _open_diff_vs_main(self, sha: str, path: str) -> None:
        webbrowser.open(self.service.commit_diff_url(sha, path))

    def _toggle_file_worker(self, sha: str, path: str, tree: CTkRowList | None = None) -> None:
        try:
            self.service.toggle_file(sha, path)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            message = str(exc)
            self.root.after(0, lambda: self._on_error(message))
            return
        self.root.after(0, lambda: self._on_file_toggled(sha, path, tree))

    def _on_file_toggled(self, sha: str, path: str, tree: CTkRowList | None = None) -> None:
        if tree is not None and tree.exists(path):
            self._refresh_row(tree, path, "files", self.service.file_key(sha, path))
        if self.files_tree.exists(path):
            self._refresh_row(self.files_tree, path, "files", self.service.file_key(sha, path))
        self._refresh_row(self.commits_tree, sha, "commits", sha)
        self._update_metrics()
        self._set_toggle_busy(False, extra_tree=tree)
        self.status_var.set(naming_interface.get_attr("v_signed_in").format(user=self.service.current_user))

    def _refresh_row(self, tree: CTkRowList, item_id: str, kind: str, key: str) -> None:
        if not tree.exists(item_id):
            return
        reviewers = self.service.state.get(kind, {}).get(key, [])
        reviewers_text = ", ".join(reviewers)
        label = tree.widget(item_id, "reviewers")
        if label is not None:
            label.configure(text=self._reviewers_text(reviewers_text), text_color=self._reviewers_color(reviewers_text))
        is_merge = kind == "commits" and self.service.commit_is_merge.get(item_id, False)
        tags = (("merge",) if is_merge else ()) + (("reviewed",) if reviewers else ())
        tree.item_tags(item_id, tags)

    def _update_metrics(self) -> None:
        commit_rows = self.commits_tree.get_children()
        file_rows = self.files_tree.get_children()
        reviewed_commits = sum("reviewed" in self.commits_tree.item_tags_get(item) for item in commit_rows)
        reviewed_files = sum("reviewed" in self.files_tree.item_tags_get(item) for item in file_rows)
        self.commit_count_var.set(str(len(commit_rows)))
        self.reviewed_commit_count_var.set(str(reviewed_commits))
        self.file_count_var.set(str(len(file_rows)))
        self.reviewed_file_count_var.set(str(reviewed_files))

    def _schedule_refresh(self) -> None:
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        try:
            interval_seconds = max(1, int(self.config.get("refresh_interval_seconds", DEFAULT_REFRESH_INTERVAL_SECONDS)))
        except (TypeError, ValueError):
            interval_seconds = DEFAULT_REFRESH_INTERVAL_SECONDS
        self._refresh_job = self.root.after(interval_seconds * 1000, self._auto_refresh)

    def _auto_refresh(self) -> None:
        if not (self.service.project_path and self.service.mr_iid):
            return
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self) -> None:
        try:
            self.service.refresh_state()
        except Exception:  # noqa: BLE001 - a transient network hiccup shouldn't interrupt the app
            self.root.after(0, self._schedule_refresh)
            return
        self.root.after(0, self._apply_refreshed_state)

    def _apply_refreshed_state(self) -> None:
        for sha in self.commits_tree.get_children():
            self._refresh_row(self.commits_tree, sha, "commits", sha)
        if self.service.active_commit_sha is not None:
            for path in self.files_tree.get_children():
                self._refresh_row(
                    self.files_tree, path, "files", self.service.file_key(self.service.active_commit_sha, path)
                )
        self._update_metrics()
        self._schedule_refresh()


def main() -> None:
    # Initialize theme loader with optional themes.json
    initialize_theme_loader(Path(__file__).parent / "themes.json")

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    ReviewTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
