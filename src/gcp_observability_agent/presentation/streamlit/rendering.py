"""Safe rendering helpers for untrusted investigation content."""

from __future__ import annotations

import html
import json
from collections.abc import Callable


def safe_text(value: object) -> str:
    """Return dynamic content as escaped plain text, never trusted markup."""
    return html.escape(str(value), quote=True)


def safe_json(value: object) -> str:
    """Serialize dynamic structures for plain-text code rendering."""
    return safe_text(json.dumps(value, default=str, indent=2, sort_keys=True))


def render_untrusted_text(renderer: Callable[[str], object], value: object) -> None:
    """Send escaped content to a plain-text Streamlit renderer."""
    renderer(safe_text(value))
