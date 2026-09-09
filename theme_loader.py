"""Theme loader for GitLab Review Tracker.

Manages theme definitions and provides centralized access to theme colors and styles.
Themes can be stored in themes.json or defined programmatically.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ThemeLoader:
    """Loads and manages UI themes from a themes file."""

    def __init__(self, themes_file: Path) -> None:
        """Initialize theme loader by loading themes from file.
        
        Args:
            themes_file: Path to themes.json file.
            
        Raises:
            FileNotFoundError: If themes_file does not exist.
            ValueError: If themes_file cannot be parsed or is invalid.
        """
        self.themes_file = themes_file
        self.themes: dict[str, dict[str, Any]] = {}
        self.current_theme_name: str | None = None
        self.current_theme: dict[str, Any] = {}

        self._load_themes_from_file()

    def _load_themes_from_file(self) -> None:
        """Load themes from JSON file.
        
        Raises:
            FileNotFoundError: If themes_file does not exist.
            ValueError: If themes_file cannot be parsed or is invalid.
        """
        if not self.themes_file.exists():
            raise FileNotFoundError(f"Themes file not found: {self.themes_file}")
        
        try:
            with open(self.themes_file) as f:
                loaded_themes = json.load(f)
                if not isinstance(loaded_themes, dict):
                    raise ValueError("Themes file must contain a JSON object")
                
                for name, theme_def in loaded_themes.items():
                    if isinstance(theme_def, dict) and "colors" in theme_def:
                        self.themes[name] = theme_def
                    else:
                        raise ValueError(f"Theme '{name}' must have a 'colors' key")
                
                if not self.themes:
                    raise ValueError("Themes file must contain at least one valid theme")
                
                # Set first theme as default
                self.current_theme_name = list(self.themes.keys())[0]
                self.current_theme = self.themes[self.current_theme_name].copy()
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse themes file {self.themes_file}: {e}")

    def set_theme(self, theme_name: str) -> bool:
        """Set the active theme.
        
        Args:
            theme_name: Name of the theme to activate.
            
        Returns:
            True if theme was set successfully, False if theme not found.
        """
        if theme_name not in self.themes:
            print(f"Warning: Theme '{theme_name}' not found. Available themes: {list(self.themes.keys())}")
            return False
        
        self.current_theme_name = theme_name
        self.current_theme = self.themes[theme_name].copy()
        return True

    def get_color(self, color_key: str, default: str | None = None) -> str:
        """Get a color from the current theme.
        
        Args:
            color_key: The color identifier (e.g., 'text_primary', 'accent').
            default: Default color to return if key not found.
            
        Returns:
            The color hex code.
        """
        return self.current_theme.get("colors", {}).get(color_key, default or "#000000")

    def get_font(self, font_key: str) -> int | tuple:
        """Get a font size or tuple from the current theme.
        
        Args:
            font_key: The font identifier (e.g., 'default', 'title').
            
        Returns:
            Font size (int) or tuple of (size, style).
        """
        return self.current_theme.get("fonts", {}).get(font_key, 10)

    def get_theme_colors(self) -> dict[str, str]:
        """Get all colors from the current theme.
        
        Returns:
            Dictionary of color_key -> hex_code mappings.
        """
        return self.current_theme.get("colors", {})

    def get_available_themes(self) -> list[str]:
        """Get list of available theme names.
        
        Returns:
            List of theme names.
        """
        return list(self.themes.keys())

    def get_theme_display_names(self) -> dict[str, str]:
        """Get display names for all available themes.
        
        Returns:
            Dictionary of theme_name -> display_name.
        """
        return {
            name: theme.get("display_name", name)
            for name, theme in self.themes.items()
        }

    def add_theme(self, theme_def: dict[str, Any]) -> bool:
        """Add a new theme programmatically.
        
        Args:
            theme_def: Theme definition dict with 'name', 'colors', and optionally 'fonts'.
            
        Returns:
            True if theme was added successfully.
        """
        if "name" not in theme_def or "colors" not in theme_def:
            print("Warning: Theme must have 'name' and 'colors' keys")
            return False
        
        name = theme_def["name"]
        self.themes[name] = theme_def
        return True

    def save_themes_to_file(self, filepath: Path | None = None) -> bool:
        """Save current themes to a JSON file.
        
        Args:
            filepath: Path where to save themes. Uses self.themes_file if not provided.
            
        Returns:
            True if save was successful.
        """
        save_path = filepath or self.themes_file
        if not save_path:
            print("Warning: No filepath specified for saving themes")
            return False
        
        try:
            with open(save_path, "w") as f:
                json.dump(self.themes, f, indent=2)
            return True
        except IOError as e:
            print(f"Warning: Failed to save themes to {save_path}: {e}")
            return False


# Singleton instance for global access
_theme_loader: ThemeLoader | None = None


def initialize_theme_loader(themes_file: Path) -> ThemeLoader:
    """Initialize the global theme loader instance.
    
    Args:
        themes_file: Path to themes.json file.
        
    Returns:
        The theme loader instance.
        
    Raises:
        FileNotFoundError: If themes_file does not exist.
        ValueError: If themes_file cannot be parsed or is invalid.
    """
    global _theme_loader
    _theme_loader = ThemeLoader(themes_file)
    return _theme_loader


def get_theme_loader() -> ThemeLoader:
    """Get the global theme loader instance.
    
    Returns:
        The theme loader instance.
        
    Raises:
        RuntimeError: If theme loader has not been initialized.
    """
    global _theme_loader
    if _theme_loader is None:
        raise RuntimeError(
            "Theme loader not initialized. Call initialize_theme_loader(themes_file) first."
        )
    return _theme_loader
