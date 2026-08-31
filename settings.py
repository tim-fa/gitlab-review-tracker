"""Settings UI for GitLab Review Tracker.

New settings can be added to ``SettingsDialog._build_fields`` and included in
the mapping returned by ``_settings_to_save`` without changing the main review
workflow.
"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk


class SettingsDialog:
    """Modal editor for locally stored application settings."""

    def __init__(self, parent: tk.Tk, config: dict, on_save: Callable[[dict], None]) -> None:
        self._on_save = on_save
        self.window = tk.Toplevel(parent)
        self.window.title("Settings")
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.configure(background="#f6f5f2")
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self.token_var = tk.StringVar(value=config.get("token", ""))
        self._build_fields()
        self._position_over_parent(parent)
        self.window.grab_set()
        self.window.focus_set()

    def _build_fields(self) -> None:
        content = ttk.Frame(self.window, style="Surface.TFrame", padding=20)
        content.pack(fill="both", expand=True, padx=16, pady=16)

        ttk.Label(content, text="GitLab", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(content, text="Connection settings", style="Subtitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 16)
        )
        ttk.Label(content, text="Access token", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        token_entry = ttk.Entry(content, textvariable=self.token_var, show="*", width=42)
        token_entry.grid(row=3, column=0, sticky="we", pady=(4, 0))
        token_entry.focus_set()

        actions = ttk.Frame(content, style="Surface.TFrame")
        actions.grid(row=4, column=0, sticky="e", pady=(20, 0))
        ttk.Button(actions, text="Cancel", style="Secondary.TButton", command=self.window.destroy).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(actions, text="Save", style="Accent.TButton", command=self._save).pack(side="left")

        content.columnconfigure(0, weight=1)
        self.window.bind("<Return>", lambda _event: self._save())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

    def _position_over_parent(self, parent: tk.Tk) -> None:
        self.window.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.window.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.window.winfo_height()) // 2
        x = max(0, min(x, self.window.winfo_screenwidth() - self.window.winfo_width()))
        y = max(0, min(y, self.window.winfo_screenheight() - self.window.winfo_height()))
        self.window.geometry(f"+{x}+{y}")

    def _settings_to_save(self) -> dict:
        return {"token": self.token_var.get().strip()}

    def _save(self) -> None:
        self._on_save(self._settings_to_save())
        self.window.destroy()