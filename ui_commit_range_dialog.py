"""Modal dialog for picking a contiguous commit range from a merge request's commits."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import tk_util

TRACK_COLOR = "#dedbd4"
RANGE_COLOR = "#f97362"
SURFACE_COLOR = "#fffefa"
TEXT_COLOR = "#292e30"
MUTED_COLOR = "#777b7b"
SELECTED_COLOR = "#fbe4dc"
ENDPOINT_COLOR = "#f7c2b8"
DIALOG_WIDTH = 760
DIALOG_HEIGHT = 520


class CommitRangeDialog:
    """Modal dialog for selecting an inclusive range on a commit timeline.

    ``commits`` is expected in the newest-first order returned by the GitLab commits API.
    The public result remains ``(first_sha, last_sha)`` in oldest-to-newest order.
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel, commits: list[dict]) -> None:
        self.chronological = list(reversed(commits))
        self.result: tuple[str, str] | None = None
        self.first_index = 0
        self.last_index = len(self.chronological) - 1
        self._active_handle = "first"

        self.window = tk.Toplevel(parent)
        self.window.title("Select commit range")
        self.window.transient(parent)
        self.window.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        self.window.resizable(False, True)
        self.window.minsize(DIALOG_WIDTH, 470)
        self.window.configure(background="#f6f5f2")
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)

        content = ttk.Frame(self.window, style="Surface.TFrame", padding=20)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)

        ttk.Label(content, text="Choose commits to compare", style="Field.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        summary = ttk.Frame(content, style="Surface.TFrame")
        summary.grid(row=1, column=0, sticky="ew", pady=(10, 4))
        summary.columnconfigure((0, 1), weight=1)
        self.first_var = tk.StringVar()
        self.last_var = tk.StringVar()
        self._make_summary(summary, "FROM (OLDER)", self.first_var, 0)
        self._make_summary(summary, "TO (NEWER)", self.last_var, 1)

        self.slider = tk.Canvas(
            content,
            height=72,
            background=SURFACE_COLOR,
            highlightthickness=0,
            takefocus=True,
            cursor="hand2",
        )
        self.slider.grid(row=2, column=0, sticky="ew", pady=(2, 4))
        self.slider.bind("<Configure>", lambda _event: self._draw_slider())
        self.slider.bind("<Button-1>", self._start_drag)
        self.slider.bind("<B1-Motion>", self._drag)
        self.slider.bind("<Left>", lambda _event: self._nudge(-1))
        self.slider.bind("<Right>", lambda _event: self._nudge(1))

        ttk.Label(content, text="Older commits  ->  Newer commits", style="Muted.TLabel").grid(
            row=3, column=0, sticky="w", pady=(0, 6)
        )

        list_frame = ttk.Frame(content, style="Surface.TFrame")
        list_frame.grid(row=4, column=0, sticky="nsew")
        self.commit_list = tk.Listbox(
            list_frame,
            height=12,
            exportselection=False,
            activestyle="none",
            selectmode="browse",
            background=SURFACE_COLOR,
            foreground=TEXT_COLOR,
            selectbackground=ENDPOINT_COLOR,
            selectforeground=TEXT_COLOR,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
        )
        for index, commit in enumerate(self.chronological):
            self.commit_list.insert("end", self._format(commit, index))
        self.commit_list.bind("<Button-1>", self._on_commit_click)
        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            style="Slim.Vertical.TScrollbar",
            command=self.commit_list.yview,
        )
        self.commit_list.configure(yscrollcommand=scrollbar.set)
        self.commit_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        actions = ttk.Frame(content, style="Surface.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self.count_var = tk.StringVar()
        ttk.Label(actions, textvariable=self.count_var, style="Muted.TLabel").pack(side="left")
        ttk.Button(actions, text="Cancel", style="Secondary.TButton", command=self._cancel).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(actions, text="Compare range", style="Accent.TButton", command=self._ok).pack(side="right")

        self._refresh_selection()
        tk_util.position_over_parent(self, parent, self.window)
        self.window.grab_set()
        self.slider.focus_set()
        self.window.wait_window()

    @staticmethod
    def _make_summary(parent: ttk.Frame, heading: str, variable: tk.StringVar, column: int) -> None:
        frame = ttk.Frame(parent, style="Surface.TFrame", padding=(10, 7))
        frame.grid(row=0, column=column, sticky="ew", padx=(0, 4) if column == 0 else (4, 0))
        ttk.Label(frame, text=heading, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(frame, textvariable=variable, style="Field.TLabel").pack(anchor="w", pady=(2, 0))

    def _format(self, commit: dict, index: int) -> str:
        marker = " (oldest)" if index == 0 else " (newest)" if index == len(self.chronological) - 1 else ""
        return f"{index + 1:>3}.  {commit['id'][:8]}  {commit.get('title', '')}{marker}"

    def _summary(self, index: int) -> str:
        commit = self.chronological[index]
        title = commit.get("title", "")
        if len(title) > 48:
            title = f"{title[:45]}..."
        return f"{commit['id'][:8]}  {title}"

    def _track_bounds(self) -> tuple[float, float]:
        return 24.0, max(24.0, float(self.slider.winfo_width() - 24))

    def _x_for_index(self, index: int) -> float:
        left, right = self._track_bounds()
        if len(self.chronological) == 1:
            return (left + right) / 2
        return left + (right - left) * index / (len(self.chronological) - 1)

    def _index_for_x(self, x: float) -> int:
        left, right = self._track_bounds()
        if len(self.chronological) == 1 or right == left:
            return 0
        fraction = min(1.0, max(0.0, (x - left) / (right - left)))
        return round(fraction * (len(self.chronological) - 1))

    def _draw_slider(self) -> None:
        self.slider.delete("all")
        left, right = self._track_bounds()
        y = 38
        first_x = self._x_for_index(self.first_index)
        last_x = self._x_for_index(self.last_index)
        self.slider.create_line(left, y, right, y, fill=TRACK_COLOR, width=6)
        self.slider.create_line(first_x, y, last_x, y, fill=RANGE_COLOR, width=6)

        step = max(1, (len(self.chronological) - 1) // 12)
        tick_indexes = set(range(0, len(self.chronological), step))
        tick_indexes.add(len(self.chronological) - 1)
        for index in tick_indexes:
            x = self._x_for_index(index)
            self.slider.create_line(x, y - 7, x, y + 7, fill=MUTED_COLOR, width=1)

        self._draw_handle(first_x, y, "FROM", self._active_handle == "first")
        self._draw_handle(last_x, y, "TO", self._active_handle == "last")

    def _draw_handle(self, x: float, y: float, label: str, active: bool) -> None:
        radius = 9 if active else 8
        self.slider.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=RANGE_COLOR if active else SURFACE_COLOR,
            outline=RANGE_COLOR,
            width=3,
        )
        self.slider.create_text(
            x,
            14,
            text=label,
            fill=TEXT_COLOR if active else MUTED_COLOR,
            font=("Segoe UI", 8, "bold"),
        )

    def _start_drag(self, event: tk.Event) -> None:
        self.slider.focus_set()
        first_x = self._x_for_index(self.first_index)
        last_x = self._x_for_index(self.last_index)
        if first_x == last_x:
            self._active_handle = "first" if event.x < first_x else "last"
        else:
            self._active_handle = "first" if abs(event.x - first_x) <= abs(event.x - last_x) else "last"
        self._move_active_handle(self._index_for_x(event.x))

    def _drag(self, event: tk.Event) -> None:
        self._move_active_handle(self._index_for_x(event.x))

    def _nudge(self, amount: int) -> str:
        current = self.first_index if self._active_handle == "first" else self.last_index
        self._move_active_handle(current + amount)
        return "break"

    def _move_active_handle(self, index: int) -> None:
        index = min(len(self.chronological) - 1, max(0, index))
        if self._active_handle == "first":
            self.first_index = min(index, self.last_index)
        else:
            self.last_index = max(index, self.first_index)
        self._refresh_selection()

    def _on_commit_click(self, event: tk.Event) -> str:
        index = self.commit_list.nearest(event.y)
        distance_from_first = abs(index - self.first_index)
        distance_from_last = abs(index - self.last_index)
        self._active_handle = "first" if distance_from_first <= distance_from_last else "last"
        self._move_active_handle(index)
        return "break"

    def _refresh_selection(self) -> None:
        self.first_var.set(self._summary(self.first_index))
        self.last_var.set(self._summary(self.last_index))
        selected_count = self.last_index - self.first_index + 1
        suffix = "commit" if selected_count == 1 else "commits"
        self.count_var.set(f"{selected_count} {suffix} selected")

        self.commit_list.selection_clear(0, "end")
        for index in range(len(self.chronological)):
            in_range = self.first_index <= index <= self.last_index
            is_endpoint = index in (self.first_index, self.last_index)
            background = ENDPOINT_COLOR if is_endpoint else SELECTED_COLOR if in_range else SURFACE_COLOR
            foreground = TEXT_COLOR if in_range else MUTED_COLOR
            self.commit_list.itemconfig(index, background=background, foreground=foreground)
        visible_index = self.first_index if self._active_handle == "first" else self.last_index
        self.commit_list.see(visible_index)
        self._draw_slider()

    def _ok(self) -> None:
        self.result = (
            self.chronological[self.first_index]["id"],
            self.chronological[self.last_index]["id"],
        )
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()


def pick_commit_range(parent: tk.Tk | tk.Toplevel, commits: list[dict]) -> tuple[str, str] | None:
    """Show the commit range picker and return (first_sha, last_sha), or None if cancelled."""
    if not commits:
        return None
    return CommitRangeDialog(parent, commits).result