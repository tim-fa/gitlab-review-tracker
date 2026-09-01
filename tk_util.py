import tkinter as tk


def position_over_parent(self, parent: tk.Misc, window: tk.Toplevel) -> None:
   window.update_idletasks()
   x = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2
   y = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_height()) // 2
   window.geometry(f"+{max(0, x)}+{max(0, y)}")