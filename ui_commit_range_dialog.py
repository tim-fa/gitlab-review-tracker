"""Modal dialog for picking a contiguous commit range from a merge request's commits."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import tk_util

VALID_FG = "#292e30"
DISABLED_FG = "#b9b6ad"


class CommitRangeDialog:
    """Modal dialog that lets the user pick a first/last commit from a chronological list.

    Both lists show the same commits in the same order (newest first, top to bottom) so the
    two selections are easy to compare. Picking a commit in one list grays out the commits in
    the other list that would make the range invalid (last must not be older than first).

    ``commits`` is expected in the same (newest-first) order returned by the GitLab commits API.
    """

    def __init__(self, parent: tk.Misc, commits: list[dict]) -> None:
        self.chronological = list(reversed(commits))
        self.result: tuple[str, str] | None = None
        last_index = len(self.chronological) - 1
        self._labels = [self._format(commit, index, last_index) for index, commit in enumerate(self.chronological)]
        # The lists display newest-first (row 0 = newest); chronological index and display row
        # are mirror images of each other, so the same flip function converts between them.
        display_labels = list(reversed(self._labels))

        self.window = tk.Toplevel(parent)
        self.window.title("Select commit range")
        self.window.transient(parent)
        self.window.resizable(True, False)
        self.window.configure(background="#f6f5f2")
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)

        content = ttk.Frame(self.window, style="Surface.TFrame", padding=20)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="Newest \u2191 \u00b7\u00b7\u00b7 \u2193 Oldest", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        ttk.Label(content, text="Last commit", style="Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Label(content, text="First commit", style="Field.TLabel").grid(row=1, column=1, sticky="w")

        self.last_list = self._make_listbox(content, column=0, labels=display_labels)
        self.first_list = self._make_listbox(content, column=1, labels=display_labels)

        self.first_list.selection_set(self._flip(0))
        self.last_list.selection_set(self._flip(last_index))
        self._apply_constraints(source=None)

        self.first_list.bind("<<ListboxSelect>>", lambda _e: self._apply_constraints("first"))
        self.last_list.bind("<<ListboxSelect>>", lambda _e: self._apply_constraints("last"))

        actions = ttk.Frame(content, style="Surface.TFrame")
        actions.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancel", style="Secondary.TButton", command=self._cancel).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="OK", style="Accent.TButton", command=self._ok).pack(side="left")

        tk_util.position_over_parent(self, parent, self.window)
        self.window.grab_set()
        self.window.focus_set()
        self.window.wait_window()

    def _flip(self, index: int) -> int:
        """Convert a chronological index to its mirrored display row, or vice versa."""
        return len(self._labels) - 1 - index

    def _make_listbox(self, parent: ttk.Frame, column: int, labels: list[str]) -> tk.Listbox:
        frame = ttk.Frame(parent, style="Surface.TFrame")
        frame.grid(row=2, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
        listbox = tk.Listbox(
            frame,
            height=14,
            width=60,
            exportselection=False,
            activestyle="none",
            selectmode="browse",
            background="#fffefa",
            foreground=VALID_FG,
            selectbackground="#fbe4dc",
            selectforeground=VALID_FG,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
        )
        for label in labels:
            listbox.insert("end", label)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", style="Slim.Vertical.TScrollbar", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return listbox

    @staticmethod
    def _format(commit: dict, index: int, last_index: int) -> str:
        marker = " (oldest)" if index == 0 else " (newest)" if index == last_index else ""
        return f"{index + 1:>3}. {commit['id'][:8]}  {commit.get('title', '')}{marker}"

    def _selected_index(self, listbox: tk.Listbox, fallback: int) -> int:
        selection = listbox.curselection()
        return self._flip(selection[0]) if selection else fallback

    def _apply_constraints(self, source: str | None) -> None:
        last_valid_index = len(self._labels) - 1
        first_index = self._selected_index(self.first_list, 0)
        last_index = self._selected_index(self.last_list, last_valid_index)

        # Whichever list the user just changed is authoritative; snap the other selection back
        # into range instead of letting it silently move the list the user didn't touch.
        if source == "first" and first_index > last_index:
            last_index = first_index
            self.last_list.selection_clear(0, "end")
            self.last_list.selection_set(self._flip(last_index))
        elif source == "last" and last_index < first_index:
            first_index = last_index
            self.first_list.selection_clear(0, "end")
            self.first_list.selection_set(self._flip(first_index))

        for index in range(len(self._labels)):
            row = self._flip(index)
            self.first_list.itemconfig(row, foreground=VALID_FG if index <= last_index else DISABLED_FG)
            self.last_list.itemconfig(row, foreground=VALID_FG if index >= first_index else DISABLED_FG)

        self.first_list.see(self._flip(first_index))
        self.last_list.see(self._flip(last_index))

    def _ok(self) -> None:
        first_index = self._selected_index(self.first_list, 0)
        last_index = self._selected_index(self.last_list, len(self._labels) - 1)
        self.result = (self.chronological[first_index]["id"], self.chronological[last_index]["id"])
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


def pick_commit_range(parent: tk.Misc, commits: list[dict]) -> tuple[str, str] | None:
    """Show the commit range picker and return (first_sha, last_sha), or None if cancelled."""
    if not commits:
        return None
    return CommitRangeDialog(parent, commits).result
