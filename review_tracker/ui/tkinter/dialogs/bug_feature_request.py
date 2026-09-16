"""Bug/Feature Request Dialog for GitLab Review Tracker."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .. import tk_util
from ..naming_interface import NamingInterface
from ..theme_integration import get_color
from review_tracker.data import feedback_request_store

naming_interface = NamingInterface()


class BugFeatureRequestDialog:
    """Modal dialog for submitting bug reports and feature requests."""

    def __init__(self, parent: tk.Tk, current_user: str | None = None) -> None:
        self.current_user = current_user or "Unknown"
        self.window = tk.Toplevel(parent)
        self.window.title(naming_interface.get_attr("t_bug_feature_request"))
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.geometry("600x400")
        self.window.configure(background=get_color("background"))
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

        self._build_ui()
        tk_util.position_over_parent(self, parent, self.window)
        self.window.grab_set()
        self.window.focus_set()

    def _build_ui(self) -> None:
        """Build the dialog UI."""
        content = ttk.Frame(self.window, style="Surface.TFrame", padding=16)
        content.pack(fill="both", expand=True)

        # Title
        ttk.Label(content, text=naming_interface.get_attr("t_bug_feature_request"), style="Title.TLabel").pack(
            anchor="w", pady=(0, 12)
        )

        # Request Type
        type_frame = ttk.Frame(content, style="Surface.TFrame")
        type_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(type_frame, text=naming_interface.get_attr("l_request_type"), style="Field.TLabel").pack(
            side="left", anchor="w"
        )

        self.request_type_var = tk.StringVar(value="Feature Request")
        request_type_combo = ttk.Combobox(
            type_frame,
            textvariable=self.request_type_var,
            values=["Bug Fix", "Feature Request"],
            state="readonly",
            width=20,
        )
        request_type_combo.pack(side="left", padx=(8, 0))

        # Description
        ttk.Label(content, text=naming_interface.get_attr("l_description"), style="Field.TLabel").pack(
            anchor="w", pady=(0, 4)
        )

        text_frame = ttk.Frame(content, style="Surface.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(0, 12))

        self.description_text = tk.Text(text_frame, height=12, width=70, wrap="word")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.description_text.yview)
        self.description_text.configure(yscrollcommand=scrollbar.set)
        self.description_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.description_text.focus_set()

        # User info
        ttk.Label(
            content,
            text=naming_interface.get_attr("l_submitted_by").format(user=self.current_user),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        # Buttons
        button_frame = ttk.Frame(content, style="Surface.TFrame")
        button_frame.pack(fill="x", anchor="e")

        ttk.Button(
            button_frame, text=naming_interface.get_attr("b_cancel"), style="Secondary.TButton", command=self.window.destroy
        ).pack(side="left", padx=(0, 6))

        ttk.Button(button_frame, text=naming_interface.get_attr("b_submit"), style="Accent.TButton", command=self._submit).pack(
            side="left"
        )

        # Key bindings
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
