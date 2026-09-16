"""Modal dialog for picking a contiguous commit range from a merge request's commits."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from .. import tk_util
from ..naming_interface import NamingInterface
from ..theme_integration import get_color
from ..ctk_style import FONT, MONO_FONT, sz, fsz

naming_interface = NamingInterface()

DIALOG_WIDTH = sz(760)
DIALOG_HEIGHT = sz(520)


class CommitRangeDialog:
    """Modal dialog for selecting an inclusive range on a commit timeline.

    ``commits`` is expected in the newest-first order returned by the GitLab commits API.
    Commits are displayed newest-first to match the main UI.
    The public result is ``(oldest_sha, newest_sha)`` in oldest-to-newest order.
    """

    def __init__(self, parent: ctk.CTk, commits: list[dict]) -> None:
        self.commits = commits  # Newest-first order, same as main.py display
        self.result: tuple[str, str] | None = None
        self.first_index = 0
        self.last_index = len(self.commits) - 1

        self.window = ctk.CTkToplevel(parent)
        self.window.title(naming_interface.get_attr("t_select_commit_range"))
        self.window.transient(parent)
        self.window.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        self.window.resizable(False, True)
        self.window.minsize(DIALOG_WIDTH, sz(470))
        self.window.configure(fg_color=get_color("background"))
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)

        content = ctk.CTkFrame(self.window, corner_radius=sz(14), fg_color=get_color("surface"))
        content.pack(fill="both", expand=True, padx=sz(16), pady=sz(16))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)

        ctk.CTkLabel(
            content, text=naming_interface.get_attr("l_choose_commits"), font=(FONT, fsz(11), "bold"),
            text_color=get_color("text_muted"), anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=sz(18), pady=(sz(18), 0))

        summary = ctk.CTkFrame(content, fg_color="transparent")
        summary.grid(row=1, column=0, sticky="ew", padx=sz(18), pady=(sz(10), sz(4)))
        summary.columnconfigure((0, 1), weight=1)
        self.first_var = tk.StringVar()
        self.last_var = tk.StringVar()
        self._make_summary(summary, naming_interface.get_attr("l_from_older"), self.first_var, 0)
        self._make_summary(summary, naming_interface.get_attr("l_to_newer"), self.last_var, 1)

        ctk.CTkLabel(
            content, text=naming_interface.get_attr("l_commit_direction"), font=(FONT, fsz(10)),
            text_color=get_color("text_muted"), anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=sz(18), pady=(sz(10), sz(6)))

        list_frame = ctk.CTkFrame(content, fg_color="transparent")
        list_frame.grid(row=3, column=0, sticky="nsew", padx=sz(18))
        self.commit_list = tk.Listbox(
            list_frame,
            height=12,
            exportselection=False,
            activestyle="none",
            selectmode="browse",
            background=get_color("surface"),
            foreground=get_color("text_primary"),
            selectbackground=get_color("selection_endpoint"),
            selectforeground=get_color("text_primary"),
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            font=(MONO_FONT, fsz(10)),
        )
        for index, commit in enumerate(self.commits):
            self.commit_list.insert("end", self._format(commit, index))
        self.commit_list.bind("<Button-1>", self._on_commit_click)
        scrollbar = ctk.CTkScrollbar(list_frame, orientation="vertical", command=self.commit_list.yview)
        self.commit_list.configure(yscrollcommand=scrollbar.set)
        self.commit_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        actions = ctk.CTkFrame(content, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=sz(18), pady=(sz(12), sz(18)))
        self.count_var = tk.StringVar()
        ctk.CTkLabel(
            actions, textvariable=self.count_var, font=(FONT, fsz(10)), text_color=get_color("text_muted"),
        ).pack(side="left")
        ctk.CTkButton(
            actions, text=naming_interface.get_attr("b_cancel"), width=sz(90), height=sz(32), font=(FONT, fsz(11)),
            fg_color=get_color("secondary_button"), hover_color=get_color("secondary_hover"),
            text_color=get_color("text_secondary"), command=self._cancel,
        ).pack(side="right", padx=(sz(6), 0))
        ctk.CTkButton(
            actions, text=naming_interface.get_attr("b_compare_range"), width=sz(120), height=sz(32), font=(FONT, fsz(11)),
            command=self._ok,
        ).pack(side="right")

        self._refresh_selection()
        tk_util.position_over_parent(self, parent, self.window)
        self.window.grab_set()
        self.commit_list.focus_set()
        self.window.wait_window()

    @staticmethod
    def _make_summary(parent: ctk.CTkFrame, heading: str, variable: tk.StringVar, column: int) -> None:
        frame = ctk.CTkFrame(parent, corner_radius=sz(10), fg_color=get_color("field_background"))
        frame.grid(row=0, column=column, sticky="ew", padx=(0, sz(4)) if column == 0 else (sz(4), 0))
        ctk.CTkLabel(
            frame, text=heading, font=(FONT, fsz(9)), text_color=get_color("text_muted"), anchor="w",
        ).pack(anchor="w", padx=sz(10), pady=(sz(7), 0))
        ctk.CTkLabel(
            frame, textvariable=variable, font=(FONT, fsz(11), "bold"), text_color=get_color("text_primary"), anchor="w",
        ).pack(anchor="w", padx=sz(10), pady=(sz(2), sz(7)))

    def _format(self, commit: dict, index: int) -> str:
        marker = naming_interface.get_attr("v_newest") if index == 0 else naming_interface.get_attr("v_oldest") if index == len(self.commits) - 1 else ""
        return f"{index + 1:>3}.  {commit['id'][:8]}  {commit.get('title', '')}{marker}"

    def _summary(self, index: int) -> str:
        commit = self.commits[index]
        title = commit.get("title", "")
        if len(title) > 48:
            title = f"{title[:45]}..."
        return f"{commit['id'][:8]}  {title}"

    def _on_commit_click(self, event: tk.Event) -> str:
        """Handle commit list click: single click selects one, Shift+click extends range."""
        index = self.commit_list.nearest(event.y)

        if event.state & 0x1:  # Shift key is pressed
            # Shift+click: extend range to include clicked index (no gaps)
            self.first_index = min(self.first_index, index)
            self.last_index = max(self.last_index, index)
        else:
            # Regular click: select only this commit
            self.first_index = index
            self.last_index = index

        self._refresh_selection()
        return "break"

    def _refresh_selection(self) -> None:
        # first_index and last_index are the numeric indices; first is the older commit (higher index)
        older_index = max(self.first_index, self.last_index)
        newer_index = min(self.first_index, self.last_index)
        self.first_var.set(self._summary(older_index))
        self.last_var.set(self._summary(newer_index))
        selected_count = abs(self.last_index - self.first_index) + 1
        suffix = naming_interface.get_attr("v_commit") if selected_count == 1 else naming_interface.get_attr("v_commits")
        self.count_var.set(naming_interface.get_attr("v_selected_commits").format(count=selected_count, suffix=suffix))

        self.commit_list.selection_clear(0, "end")
        min_idx = min(self.first_index, self.last_index)
        max_idx = max(self.first_index, self.last_index)
        for index in range(len(self.commits)):
            in_range = min_idx <= index <= max_idx
            is_endpoint = index in (self.first_index, self.last_index)
            background = get_color("selection_endpoint") if is_endpoint else get_color("selection") if in_range else get_color("surface")
            foreground = get_color("text_primary") if in_range else get_color("text_muted")
            self.commit_list.itemconfig(index, background=background, foreground=foreground)
        visible_index = newer_index
        self.commit_list.see(visible_index)

    def _ok(self) -> None:
        # Return (oldest, newest) order regardless of which index is which
        older_index = max(self.first_index, self.last_index)
        newer_index = min(self.first_index, self.last_index)
        self.result = (
            self.commits[older_index]["id"],
            self.commits[newer_index]["id"],
        )
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


def pick_commit_range(parent: ctk.CTk, commits: list[dict]) -> tuple[str, str] | None:
    """Show the commit range picker and return (first_sha, last_sha), or None if cancelled."""
    if not commits:
        return None
    return CommitRangeDialog(parent, commits).result
