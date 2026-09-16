"""Theme color access for GitLab Review Tracker."""
from __future__ import annotations

from .theme_loader import get_theme_loader


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
