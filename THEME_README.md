## Theme Loader System

The theme loader provides a centralized, flexible way to manage UI themes for GitLab Review Tracker. All themes are loaded from `themes.json` — there are no built-in default themes.

### Features

- **File-Based Themes**: All themes defined in `themes.json` 
- **Multiple Themes**: Support any number of custom themes
- **Centralized Management**: All colors and fonts defined in one location
- **Easy Switching**: Change themes at runtime
- **Type-Safe**: Proper type hints throughout
- **Strict Validation**: Raises exceptions if themes file is missing or invalid

### Quick Start

#### 1. Ensure themes.json Exists

The `themes.json` file must exist in the application directory with at least one valid theme. See [themes.json](themes.json) for examples.

#### 2. Initialize Theme Loader in main.py

```python
from pathlib import Path
from theme_loader import initialize_theme_loader
from theme_integration import apply_theme_to_styles

if __name__ == "__main__":
    root = tk.Tk()
    
    # Initialize theme loader with required themes.json
    initialize_theme_loader(Path(__file__).parent / "themes.json")
    
    # Apply theme to all ttk widgets
    apply_theme_to_styles(root, font_name="Segoe UI")
    
    # ... rest of your app
```

#### 3. Use Theme Colors in Your Code

**For ttk widgets** (automatic styling via `style` parameter):
```python
from tkinter import ttk
import tk.Themed as tk_themed

label = ttk.Label(root, text="Hello", style="Title.TLabel")
button = ttk.Button(root, text="Click", style="Accent.TButton")
```

**For tk widgets that don't support ttk styling**:
```python
from theme_integration import get_color

canvas = tk.Canvas(root, background=get_color("surface"))
text = tk.Text(root, background=get_color("field_background"), 
               foreground=get_color("text_primary"))
```

#### 4. Switch Themes at Runtime

```python
from theme_loader import get_theme_loader

theme = get_theme_loader()

# Set to dark theme
theme.set_theme("dark")

# Get available themes
available = theme.get_available_themes()  # ['light', 'dark', ...]

# Get display names for UI
names = theme.get_theme_display_names()  # {'light': 'Light', ...}
```

### Theme Structure

Each theme is a dictionary with the following structure:

```json
{
  "light": {
    "name": "light",
    "display_name": "Light",
    "colors": {
      "background": "#f6f5f2",
      "surface": "#fffefa",
      "text_primary": "#292e30",
      "text_secondary": "#3f4548",
      "text_muted": "#777b7b",
      "accent": "#f97362",
      "accent_hover": "#fb8b78",
      "accent_disabled": "#f7b0a5",
      "secondary_button": "#ebe9e4",
      "secondary_hover": "#dedbd4",
      "selection": "#fbe4dc",
      "selection_endpoint": "#f7c2b8",
      "row_merge_bg": "#f5eee1",
      "row_merge_fg": "#806548",
      "row_reviewed_bg": "#dcfce7",
      "row_reviewed_fg": "#166534",
      "divider": "#dedbd4",
      "scrollbar_bg": "#d8d4cc",
      "scrollbar_trough": "#f4f2ed",
      "scrollbar_arrow": "#8f938f",
      "scrollbar_active": "#c9c4ba",
      "progressbar_bg": "#f97362",
      "progressbar_trough": "#e3e1dc",
      "table_header_bg": "#f0eee9",
      "table_header_fg": "#777b7b"
    },
    "fonts": {
      "default": 10,
      "small": 8,
      "title": ["19", "bold"],
      "subtitle": 9
    }
  }
}
```

### Color Reference

| Color Key | Purpose |
|-----------|---------|
| `background` | Main app background |
| `surface` | Content surface (panels, cards) |
| `field_background` | Input field backgrounds |
| `text_primary` | Main text color |
| `text_secondary` | Secondary text color |
| `text_muted` | Muted/disabled text |
| `accent` | Primary action button |
| `accent_hover` | Button hover state |
| `accent_disabled` | Disabled button |
| `secondary_button` | Secondary action button |
| `secondary_hover` | Secondary button hover |
| `selection` | Selected item background |
| `selection_endpoint` | Range endpoint highlight |
| `row_merge_bg` | Merge commit row background |
| `row_merge_fg` | Merge commit row text |
| `row_reviewed_bg` | Reviewed row background |
| `row_reviewed_fg` | Reviewed row text |
| `divider` | Borders and dividers |
| `scrollbar_bg` | Scrollbar thumb |
| `scrollbar_trough` | Scrollbar track |
| `scrollbar_arrow` | Scrollbar arrow color |
| `scrollbar_active` | Scrollbar active state |
| `progressbar_bg` | Progress bar fill |
| `progressbar_trough` | Progress bar background |
| `table_header_bg` | Table header background |
| `table_header_fg` | Table header text |

### Adding Custom Themes

#### Method 1: Add to themes.json

Edit `themes.json` and add a new theme:

```json
{
  "light": { ... },
  "dark": { ... },
  "solarized_dark": {
    "name": "solarized_dark",
    "display_name": "Solarized Dark",
    "colors": {
      "background": "#002b36",
      "surface": "#073642",
      ...
    }
  }
}
```

#### Method 2: Add Programmatically

```python
from theme_loader import get_theme_loader

theme = get_theme_loader()

custom_theme = {
    "name": "custom",
    "display_name": "My Custom Theme",
    "colors": {
        "background": "#ffffff",
        "surface": "#f5f5f5",
        # ... all other required colors
    }
}

theme.add_theme(custom_theme)
theme.set_theme("custom")
```

### Integration with Settings

To allow users to select themes via the Settings dialog, add this to `ui_settings.py`:

```python
from theme_loader import get_theme_loader

class SettingsDialog:
    def _build_fields(self) -> None:
        # ... existing code ...
        
        # Add theme selector
        theme_loader = get_theme_loader()
        available_themes = theme_loader.get_available_themes()
        
        theme_var = tk.StringVar(value=theme_loader.current_theme_name)
        theme_combo = ttk.Combobox(
            content,
            textvariable=theme_var,
            values=available_themes,
            state="readonly"
        )
        theme_combo.grid(row=row, column=1)
        
        self.fields.append(("theme", "Theme", theme_var, False, False))
    
    def _save(self) -> None:
        # ... existing save code ...
        
        if "theme" in settings:
            theme_loader = get_theme_loader()
            theme_loader.set_theme(settings["theme"])
            # Optionally: re-apply styles to update live
```

### API Reference

#### ThemeLoader Class

```python
# Initialization
theme = ThemeLoader(themes_file=Path("themes.json"))

# Set active theme
theme.set_theme("dark")

# Get colors
color = theme.get_color("text_primary")
all_colors = theme.get_theme_colors()

# Get fonts
font_size = theme.get_font("default")
title_font = theme.get_font("title")

# Manage themes
available = theme.get_available_themes()
names = theme.get_theme_display_names()
theme.add_theme(custom_theme_dict)
theme.save_themes_to_file(Path("custom_themes.json"))
```

#### Global Access

```python
from theme_loader import get_theme_loader, initialize_theme_loader

# Initialize (required - must be called before using get_theme_loader)
initialize_theme_loader(Path("themes.json"))

# Get global instance
theme = get_theme_loader()
color = theme.get_color("accent")
```

#### Integration Helpers

```python
from theme_integration import apply_theme_to_styles, get_color

# Apply all theme styles to ttk widgets
apply_theme_to_styles(root, font_name="Segoe UI")

# Get color for manual use
bg = get_color("surface")
```

### Files Included

- **theme_loader.py**: Core theme management system
- **theme_integration.py**: Integration helpers and styling application
- **themes.json**: Example theme definitions (light and dark)
- **THEME_README.md**: This documentation

### Migration from Hardcoded Colors

To migrate existing code:

1. Replace hardcoded colors with `get_color()` calls
2. Remove style configuration code from main.py
3. Call `apply_theme_to_styles()` once during app initialization
4. Use theme colors in new code going forward

**Before:**
```python
style.configure("Title.TLabel", foreground="#292e30", background="#fffefa")
canvas = tk.Canvas(root, background="#f6f5f2")
```

**After:**
```python
# ttk styles handled by apply_theme_to_styles()
canvas = tk.Canvas(root, background=get_color("background"))
```

### Best Practices

1. ✅ Use ttk widgets with predefined styles when possible
2. ✅ Use `get_color()` for tk widgets that need manual coloring
3. ✅ Add new color keys to themes instead of hardcoding colors
4. ✅ Test all themes regularly to ensure consistency
5. ✅ Keep font definitions consistent across themes
6. ❌ Don't hardcode colors in widgets directly
7. ❌ Don't create theme-specific code paths (use theme switching instead)

### Troubleshooting

**Theme colors not applied to ttk widgets:**
- Ensure `apply_theme_to_styles()` is called before creating widgets
- Check that `theme_use("clam")` is called (required for color customization)

**FileNotFoundError when starting app:**
- Ensure `themes.json` file exists in the application directory
- Verify the path passed to `initialize_theme_loader()` is correct
- Check file permissions

**ValueError when loading themes:**
- Verify `themes.json` is valid JSON (use an online JSON validator)
- Ensure every theme has required "colors" key
- Check that at least one valid theme is defined

**RuntimeError: "Theme loader not initialized":**
- Ensure `initialize_theme_loader(Path(...))` is called before using `get_theme_loader()`
- This must happen in the main module before creating any UI

**Colors different between light and dark themes:**
- Review color values in `themes.json`
- Test with a color picker tool to verify hex codes
- Ensure sufficient contrast for accessibility
