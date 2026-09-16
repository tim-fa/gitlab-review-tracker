"""Theme integration example for GitLab Review Tracker.

This file demonstrates how to integrate the theme loader into your application.
It shows the pattern used in main.py for applying themes to ttk styles.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from theme_loader import get_theme_loader


def apply_theme_to_styles(root: tk.Tk, font_name: str = "Segoe UI") -> None:
    """Apply the current theme to all ttk widget styles.
    
    This function should be called after creating the root window and
    before creating any ttk widgets that need styling.
    
    Args:
        root: The root Tk window.
        font_name: Default font family to use.
    """
    theme = get_theme_loader()
    colors = theme.get_theme_colors()
    
    # Create the style object
    style = ttk.Style()
    
    # Use a base theme
    style.theme_use("clam")
    
    # Apply colors from the theme
    root.configure(background=colors["background"])
    
    # Base frames
    style.configure("TFrame", background=colors["background"])
    style.configure("Surface.TFrame", background=colors["surface"])
    style.configure("Header.TFrame", background=colors["surface"])
    
    # Labels
    style.configure("TLabel", 
                   background=colors["surface"],
                   foreground=colors["text_secondary"],
                   font=(font_name, 10))
    style.configure("Muted.TLabel",
                   background=colors["surface"],
                   foreground=colors["text_muted"],
                   font=(font_name, 9))
    style.configure("Title.TLabel",
                   background=colors["surface"],
                   foreground=colors["text_primary"],
                   font=(font_name, 19, "bold"))
    style.configure("Subtitle.TLabel",
                   background=colors["surface"],
                   foreground=colors["text_muted"],
                   font=(font_name, 9))
    style.configure("Status.TLabel",
                   background=colors["background"],
                   foreground=colors["text_muted"],
                   font=(font_name, 9))
    style.configure("Field.TLabel",
                   background=colors["surface"],
                   foreground=colors["text_muted"],
                   font=(font_name, 9, "bold"))
    
    # Input fields
    style.configure("TEntry",
                   fieldbackground=colors["field_background"],
                   foreground=colors["text_primary"],
                   insertcolor=colors["text_primary"],
                   borderwidth=0)
    style.configure("TCombobox",
                   fieldbackground=colors["field_background"],
                   background=colors["field_background"],
                   foreground=colors["text_primary"],
                   borderwidth=0)
    style.map("TCombobox",
             fieldbackground=[("readonly", colors["field_background"])],
             foreground=[("readonly", colors["text_primary"])])
    
    # Checkbutton
    style.configure("TCheckbutton",
                   background=colors["surface"],
                   foreground=colors["text_secondary"],
                   font=(font_name, 9))
    style.map("TCheckbutton",
             background=[("active", colors["surface"])],
             foreground=[("active", colors["text_primary"])])
    
    # Buttons
    style.configure("Accent.TButton",
                   background=colors["accent"],
                   foreground=colors["text_primary"],
                   font=(font_name, 9, "bold"),
                   padding=(10, 5),
                   borderwidth=0)
    style.map("Accent.TButton",
             background=[
                 ("active", colors["accent_hover"]),
                 ("disabled", colors["accent_disabled"])
             ])
    
    style.configure("Secondary.TButton",
                   background=colors["secondary_button"],
                   foreground=colors["text_secondary"],
                   font=(font_name, 9),
                   padding=(9, 5),
                   borderwidth=0)
    style.map("Secondary.TButton",
             background=[("active", colors["secondary_hover"])])
    
    # Cards
    style.configure("Card.TFrame", background=colors["surface"])
    style.configure("CardValue.TLabel",
                   background=colors["surface"],
                   foreground=colors["text_primary"],
                   font=(font_name, 13, "bold"))
    style.configure("CardLabel.TLabel",
                   background=colors["surface"],
                   foreground=colors["text_muted"],
                   font=(font_name, 8))
    
    # Labelframe
    style.configure("TLabelframe",
                   background=colors["surface"],
                   bordercolor=colors["divider"],
                   relief="solid")
    style.configure("TLabelframe.Label",
                   background=colors["surface"],
                   foreground=colors["text_secondary"],
                   font=(font_name, 10, "bold"))
    
    # Treeview (tables)
    style.configure("Treeview",
                   background=colors["surface"],
                   fieldbackground=colors["surface"],
                   foreground=colors["text_secondary"],
                   rowheight=24,
                   borderwidth=0,
                   font=(font_name, 8))
    style.configure("Treeview.Heading",
                   background=colors["table_header_bg"],
                   foreground=colors["table_header_fg"],
                   font=(font_name, 9, "bold"),
                   relief="flat",
                   padding=8)
    style.map("Treeview",
             background=[("selected", colors["selection"])],
             foreground=[("selected", colors["text_primary"])])
    
    # Progressbar
    style.configure("Horizontal.TProgressbar",
                   background=colors["progressbar_bg"],
                   troughcolor=colors["progressbar_trough"],
                   borderwidth=0)
    
    # Scrollbar
    style.configure("Vertical.TScrollbar",
                   background=colors["scrollbar_bg"],
                   troughcolor=colors["scrollbar_trough"],
                   bordercolor=colors["scrollbar_trough"],
                   arrowcolor=colors["scrollbar_arrow"],
                   lightcolor=colors["scrollbar_bg"],
                   darkcolor=colors["scrollbar_bg"])
    style.map("Vertical.TScrollbar",
             background=[("active", colors["scrollbar_active"])])
    
    style.configure("Slim.Vertical.TScrollbar",
                   background=colors["scrollbar_bg"],
                   troughcolor=colors["scrollbar_trough"],
                   bordercolor=colors["scrollbar_trough"],
                   arrowcolor=colors["scrollbar_arrow"],
                   lightcolor=colors["scrollbar_bg"],
                   darkcolor=colors["scrollbar_bg"],
                   width=8)
    style.map("Slim.Vertical.TScrollbar",
             background=[("active", colors["scrollbar_active"])])


def get_color(color_key: str) -> str:
    """Get a color from the current theme.
    
    Convenience function for accessing theme colors throughout the app.
    
    Args:
        color_key: The color identifier.
        
    Returns:
        The hex color code.
        
    Example:
        >>> bg_color = get_color("surface")
    """
    return get_theme_loader().get_color(color_key)


# Example usage in main.py:
# 
# from theme_integration import apply_theme_to_styles, get_color
# from theme_loader import initialize_theme_loader
# 
# if __name__ == "__main__":
#     root = tk.Tk()
#     
#     # Initialize theme loader (optional: pass themes.json path)
#     initialize_theme_loader(Path(__file__).parent / "themes.json")
#     
#     # Apply theme to all ttk styles
#     apply_theme_to_styles(root)
#     
#     # Use theme colors in your code
#     my_frame = ttk.Frame(root, style="Surface.TFrame")
#     my_label = ttk.Label(my_frame, text="Hello", style="Title.TLabel")
#     
#     # For places where you can't use ttk styles (like tk.Canvas or tk.Text):
#     canvas = tk.Canvas(root, background=get_color("surface"))
#     text = tk.Text(root, background=get_color("field_background"), 
#                    foreground=get_color("text_primary"))
