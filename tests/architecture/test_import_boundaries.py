"""Keep documented module dependencies mechanically enforceable."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "gcp_observability_agent"
PACKAGE_NAME = "gcp_observability_agent"


def _imported_project_modules(path: Path) -> set[str]:
    """Return project modules imported by *path* without importing it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    current_package = [PACKAGE_NAME, *path.relative_to(PACKAGE_ROOT).parts[:-1]]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names if alias.name.startswith(PACKAGE_NAME))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module and node.module.startswith(PACKAGE_NAME):
                    modules.add(node.module)
            else:
                base = current_package[: len(current_package) - (node.level - 1)]
                suffix = node.module.split(".") if node.module else []
                modules.add(".".join([*base, *suffix]))
    return modules


@pytest.mark.parametrize("source_file", sorted(PACKAGE_ROOT.rglob("*.py")))
def test_all_source_files_parse(source_file: Path) -> None:
    """Foundation modules remain syntactically valid without importing dependencies."""
    ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))


@pytest.mark.parametrize("source_file", sorted((PACKAGE_ROOT / "domain").rglob("*.py")))
def test_domain_does_not_depend_on_outer_layers(source_file: Path) -> None:
    forbidden = (
        f"{PACKAGE_NAME}.application",
        f"{PACKAGE_NAME}.infrastructure",
        f"{PACKAGE_NAME}.presentation",
        f"{PACKAGE_NAME}.bootstrap",
    )
    assert not any(module.startswith(forbidden) for module in _imported_project_modules(source_file))


@pytest.mark.parametrize("source_file", sorted((PACKAGE_ROOT / "application").rglob("*.py")))
def test_application_does_not_depend_on_infrastructure(source_file: Path) -> None:
    forbidden = f"{PACKAGE_NAME}.infrastructure"
    assert not any(module.startswith(forbidden) for module in _imported_project_modules(source_file))


@pytest.mark.parametrize("source_file", sorted((PACKAGE_ROOT / "presentation").rglob("*.py")))
def test_presentation_invokes_application_only(source_file: Path) -> None:
    forbidden = (f"{PACKAGE_NAME}.domain", f"{PACKAGE_NAME}.infrastructure")
    assert not any(module.startswith(forbidden) for module in _imported_project_modules(source_file))
