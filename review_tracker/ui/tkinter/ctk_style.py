"""Shared sizing/typography constants for the CustomTkinter UI.

``sz()`` scales every pixel dimension and font size by ``SCALE`` in one place,
so the whole UI can be made more compact by changing a single number.
"""
from __future__ import annotations

FONT = "Segoe UI"
MONO_FONT = "Consolas"

SCALE = 0.9
# Widths/heights/paddings were shrunk 10% and felt right, but text got too
# small at the same scale, so fonts get their own factor: 10% larger than
# that already-shrunk size.
FONT_SCALE = SCALE * 1.1


def sz(value: int) -> int:
    """Scale a pixel dimension (width, height, padding, corner radius), rounding to at least 1."""
    return max(1, round(value * SCALE))


def fsz(value: int) -> int:
    """Scale a font size, rounding to at least 1."""
    return max(1, round(value * FONT_SCALE))
