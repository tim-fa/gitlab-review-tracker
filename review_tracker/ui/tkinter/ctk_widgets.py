"""Reusable CustomTkinter widgets shared by the main window.

CTkRowList replaces the ttk.Treeview lists (commits, changed files, and the
"changes vs main" popup) with a scrollable stack of rounded row cards, since
CustomTkinter has no built-in table widget. It only implements the subset of
Treeview behavior this app relies on: tag-based row coloring, single selection,
double-click, and right-click.
"""
from __future__ import annotations

from typing import Callable, Iterator

import customtkinter as ctk


def _iter_descendants(widget) -> Iterator:
    for child in widget.winfo_children():
        yield child
        yield from _iter_descendants(child)


class CTkRowList(ctk.CTkFrame):
    """A scrollable list of rounded, clickable/tag-colored row cards."""

    def __init__(
        self,
        master,
        *,
        build_row: Callable[["CTkRowList", ctk.CTkFrame, str, dict, tuple], None],
        default_bg,
        selection_border_color,
        corner_radius: int = 8,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._build_row = build_row
        self._default_bg = default_bg
        self._selection_border_color = selection_border_color
        self._corner_radius = corner_radius

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)
        # CTkScrollableFrame's inner canvas has a fixed width/height (default
        # 200x200) that doesn't track its container on its own, so it ends up
        # sized by its content instead of filling the panel. Force it to match
        # this frame's actual allotted size on every resize.
        self.bind("<Configure>", self._on_configure)

        self._rows: dict[str, dict] = {}
        self._order: list[str] = []
        self._tag_styles: dict[str, dict] = {}
        self._selected: str | None = None
        self._enabled = True

        self.on_select: Callable[[str], None] | None = None
        self.on_double_click: Callable[[str], None] | None = None
        self.on_right_click: Callable[[str, object], None] | None = None

    def set_enabled(self, enabled: bool) -> None:
        """Gate row clicks and dim action buttons while an update is in flight."""
        self._enabled = enabled
        state = "normal" if enabled else "disabled"
        for row in self._rows.values():
            for widget in row["widgets"].get("_skip_bind", ()):
                if isinstance(widget, ctk.CTkButton):
                    widget.configure(state=state)

    def _on_configure(self, event) -> None:
        self.scroll.configure(width=event.width, height=event.height)

    # -- tag styling ------------------------------------------------------
    def tag_configure(self, tag: str, background=None, foreground=None) -> None:
        self._tag_styles[tag] = {"background": background, "foreground": foreground}

    def _row_color(self, tags: tuple):
        for tag in reversed(tags):
            style = self._tag_styles.get(tag)
            if style and style.get("background"):
                return style["background"]
        return self._default_bg

    def tag_foreground(self, tags: tuple, default):
        for tag in reversed(tags):
            style = self._tag_styles.get(tag)
            if style and style.get("foreground"):
                return style["foreground"]
        return default

    # -- row lifecycle ------------------------------------------------------
    def insert(self, iid: str, values: dict, tags: tuple = ()) -> None:
        frame = ctk.CTkFrame(
            self.scroll, corner_radius=self._corner_radius, fg_color=self._row_color(tags)
        )
        frame.pack(fill="x", pady=2, padx=2)
        widgets = self._build_row(self, frame, iid, values, tags) or {}
        self._rows[iid] = {"frame": frame, "values": dict(values), "tags": tuple(tags), "widgets": widgets}
        self._order.append(iid)
        self._bind_row(iid, skip=set(widgets.get("_skip_bind", ())))
        if not self._enabled:
            for widget in widgets.get("_skip_bind", ()):
                if isinstance(widget, ctk.CTkButton):
                    widget.configure(state="disabled")

    def _bind_row(self, iid: str, skip: set) -> None:
        frame = self._rows[iid]["frame"]
        for widget in [frame, *_iter_descendants(frame)]:
            if widget in skip:
                continue
            widget.bind("<Button-1>", lambda e, iid=iid: self._on_click(iid), add="+")
            widget.bind("<Double-Button-1>", lambda e, iid=iid: self._on_double(iid), add="+")
            widget.bind("<Button-3>", lambda e, iid=iid: self._on_right(iid, e), add="+")

    def delete_all(self) -> None:
        for iid in self._order:
            self._rows[iid]["frame"].destroy()
        self._rows.clear()
        self._order.clear()
        self._selected = None

    def exists(self, iid: str) -> bool:
        return iid in self._rows

    def get_children(self) -> list[str]:
        return list(self._order)

    def item_tags(self, iid: str, tags: tuple) -> None:
        if iid not in self._rows:
            return
        self._rows[iid]["tags"] = tuple(tags)
        self._rows[iid]["frame"].configure(fg_color=self._row_color(tags))

    def item_tags_get(self, iid: str) -> tuple:
        return self._rows.get(iid, {}).get("tags", ())

    def widget(self, iid: str, key: str):
        return self._rows.get(iid, {}).get("widgets", {}).get(key)

    # -- selection ------------------------------------------------------
    def selection(self) -> tuple:
        return (self._selected,) if self._selected else ()

    def selection_set(self, iid: str) -> None:
        self._select(iid, notify=False)

    def _select(self, iid: str, notify: bool = True) -> None:
        if self._selected and self._selected in self._rows:
            self._rows[self._selected]["frame"].configure(border_width=0)
        self._selected = iid
        if iid in self._rows:
            self._rows[iid]["frame"].configure(
                border_width=2, border_color=self._selection_border_color
            )
        if notify and self.on_select:
            self.on_select(iid)

    # -- event handlers ------------------------------------------------------
    def _on_click(self, iid: str) -> None:
        if not self._enabled:
            return
        self._select(iid)

    def _on_double(self, iid: str) -> None:
        if not self._enabled:
            return
        self._select(iid)
        if self.on_double_click:
            self.on_double_click(iid)

    def _on_right(self, iid: str, event) -> None:
        if not self._enabled:
            return
        self._select(iid)
        if self.on_right_click:
            self.on_right_click(iid, event)
