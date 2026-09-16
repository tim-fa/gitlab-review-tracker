"""Bug/Feature Request Dialog for GitLab Review Tracker."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from .. import tk_util
from ..naming_interface import NamingInterface
from ..theme_integration import get_color
from ..ctk_style import FONT, sz, fsz
from review_tracker.data import feedback_request_store

naming_interface = NamingInterface()


class BugFeatureRequestDialog:
    """Modal dialog for submitting bug reports and feature requests."""

    def __init__(self, parent: ctk.CTk, current_user: str | None = None) -> None:
        self.current_user = current_user or "Unknown"
        self.window = ctk.CTkToplevel(parent)
        self.window.title(naming_interface.get_attr("t_bug_feature_request"))
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.geometry(f"{sz(600)}x{sz(400)}")
        self.window.configure(fg_color=get_color("background"))
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self._build_ui()
        tk_util.position_over_parent(self, parent, self.window)
        self.window.grab_set()
        self.window.focus_set()

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        content = ctk.CTkFrame(self.window, corner_radius=sz(14), fg_color=get_color("surface"))
        content.pack(fill="both", expand=True, padx=sz(16), pady=sz(16))

        ctk.CTkLabel(
            content, text=naming_interface.get_attr("t_bug_feature_request"), font=(FONT, fsz(18), "bold"),
            text_color=get_color("text_primary"), anchor="w",
        ).pack(anchor="w", padx=sz(18), pady=(sz(18), sz(12)))

        type_frame = ctk.CTkFrame(content, fg_color="transparent")
        type_frame.pack(fill="x", padx=sz(18), pady=(0, sz(12)))
        ctk.CTkLabel(
            type_frame, text=naming_interface.get_attr("l_request_type"), font=(FONT, fsz(11), "bold"),
            text_color=get_color("text_muted"),
        ).pack(side="left", anchor="w")
        self.request_type_var = tk.StringVar(value="Feature Request")
        ctk.CTkComboBox(
            type_frame, variable=self.request_type_var, values=["Bug Fix", "Feature Request"],
            state="readonly", width=sz(180), height=sz(30), font=(FONT, fsz(11)),
        ).pack(side="left", padx=(sz(8), 0))

        ctk.CTkLabel(
            content, text=naming_interface.get_attr("l_description"), font=(FONT, fsz(11), "bold"),
            text_color=get_color("text_muted"), anchor="w",
        ).pack(anchor="w", padx=sz(18), pady=(0, sz(4)))

        self.description_text = ctk.CTkTextbox(content, height=sz(190), wrap="word")
        self.description_text.pack(fill="both", expand=True, padx=sz(18), pady=(0, sz(12)))
        self.description_text.focus_set()

        ctk.CTkLabel(
            content,
            text=naming_interface.get_attr("l_submitted_by").format(user=self.current_user),
            font=(FONT, fsz(10)),
            text_color=get_color("text_muted"),
            anchor="w",
        ).pack(anchor="w", padx=sz(18), pady=(0, sz(12)))

        button_frame = ctk.CTkFrame(content, fg_color="transparent")
        button_frame.pack(fill="x", anchor="e", padx=sz(18), pady=(0, sz(18)))
        ctk.CTkButton(
            button_frame, text=naming_interface.get_attr("b_cancel"), width=sz(90), height=sz(32), font=(FONT, fsz(11)),
            fg_color=get_color("secondary_button"), hover_color=get_color("secondary_hover"),
            text_color=get_color("text_secondary"), command=self.window.destroy,
        ).pack(side="right", padx=(sz(6), 0))
        ctk.CTkButton(
            button_frame, text=naming_interface.get_attr("b_submit"), width=sz(90), height=sz(32), font=(FONT, fsz(11)),
            command=self._submit,
        ).pack(side="right")

        self.window.bind("<Return>", lambda _event: self._submit())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

    def _submit(self) -> None:
        """Submit the request and save it to the network file."""
        description = self.description_text.get("1.0", "end-1c").strip()

        if not description:
            messagebox.showwarning(
                naming_interface.get_attr("t_empty_request"), naming_interface.get_attr("m_empty_request")
            )
            return

        try:
            feedback_request_store.save_request(self.request_type_var.get(), description, self.current_user)
            messagebox.showinfo(
                naming_interface.get_attr("t_request_saved"), naming_interface.get_attr("m_request_saved")
            )
            self.window.destroy()
        except Exception as exc:
            messagebox.showerror(
                naming_interface.get_attr("t_save_error"), f"{naming_interface.get_attr('m_save_error')}\n{str(exc)}"
            )
