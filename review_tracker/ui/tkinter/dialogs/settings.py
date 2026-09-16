"""Settings UI for GitLab Review Tracker.

New settings can be added to ``SettingsDialog._build_fields`` and included in
the mapping returned by ``_settings_to_save`` without changing the main review
workflow.
"""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from .. import tk_util
from ..naming_interface import NamingInterface
from ..theme_integration import get_color
from ..ctk_style import FONT, sz, fsz

naming_interface = NamingInterface()


class SettingsDialog:
    """Modal editor for locally stored application settings."""

    def __init__(self, parent: ctk.CTk, config: dict, on_save: Callable[[dict], None]) -> None:
        self._on_save = on_save
        self.window = ctk.CTkToplevel(parent)
        self.window.title(naming_interface.get_attr("t_settings"))
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.configure(fg_color=get_color("background"))
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self.fields = []
        self.multiline_widgets: dict[str, ctk.CTkTextbox] = {}

        for key, value in config.items():
            if isinstance(value, str):
                self.fields.append(
                    (key, naming_interface.get_attr(f"l_settings_{key}"), tk.StringVar(value=value), key == "token", "\n" in value)
                )

        self._build_fields()
        tk_util.position_over_parent(self, parent, self.window)
        self.window.grab_set()
        self.window.focus_set()

    def _build_fields(self) -> None:
        content = ctk.CTkFrame(self.window, corner_radius=sz(14), fg_color=get_color("surface"))
        content.pack(fill="both", expand=True, padx=sz(16), pady=sz(16))
        content.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            content, text=naming_interface.get_attr("l_gitlab"), font=(FONT, fsz(18), "bold"),
            text_color=get_color("text_primary"), anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=sz(18), pady=(sz(18), 0))
        ctk.CTkLabel(
            content, text=naming_interface.get_attr("l_connection_settings"), font=(FONT, fsz(11)),
            text_color=get_color("text_muted"), anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=sz(18), pady=(sz(2), sz(14)))

        row = 2
        for key, label, variable, secret, multiline in self.fields:
            ctk.CTkLabel(
                content, text=label, font=(FONT, fsz(11), "bold"), text_color=get_color("text_muted"), anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=sz(18))
            if multiline:
                entry = ctk.CTkTextbox(content, height=sz(110), width=sz(520), wrap="word")
                entry.grid(row=row + 1, column=0, sticky="we", padx=sz(18), pady=(sz(4), sz(12)))
                entry.insert("1.0", variable.get())
                self.multiline_widgets[key] = entry
            else:
                entry = ctk.CTkEntry(
                    content, textvariable=variable, show="*" if secret else "", width=sz(520), height=sz(32),
                )
                entry.grid(row=row + 1, column=0, sticky="we", padx=sz(18), pady=(sz(4), sz(12)))
            if row == 2:
                entry.focus_set()
            row += 2

        actions = ctk.CTkFrame(content, fg_color="transparent")
        actions.grid(row=row, column=0, sticky="e", padx=sz(18), pady=(sz(8), sz(18)))
        ctk.CTkButton(
            actions, text=naming_interface.get_attr("b_cancel"), width=sz(90), height=sz(32), font=(FONT, fsz(11)),
            fg_color=get_color("secondary_button"), hover_color=get_color("secondary_hover"),
            text_color=get_color("text_secondary"), command=self.window.destroy,
        ).pack(side="left", padx=(0, sz(6)))
        ctk.CTkButton(
            actions, text=naming_interface.get_attr("b_save"), width=sz(90), height=sz(32), font=(FONT, fsz(11)),
            command=self._save,
        ).pack(side="left")

        self.window.bind("<Return>", lambda _event: self._save())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

    def _settings_to_save(self) -> dict:
        settings = {}
        for key, _label, variable, _secret, multiline in self.fields:
            settings[key] = (
                self.multiline_widgets[key].get("1.0", "end-1c").strip()
                if multiline
                else variable.get().strip()
            )
        return settings

    def _save(self) -> None:
        self._on_save(self._settings_to_save())
        self.window.destroy()
