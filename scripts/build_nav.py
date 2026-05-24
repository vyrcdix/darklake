#!/usr/bin/env python3
"""Regenerate the MkDocs nav from sources.yaml.

The nav block lives between two marker comments in mkdocs.yml, so the
static config (theme, plugins, extensions) and generated nav share one
file. Sections are grouped by the manifest's `section` field, preserving
manifest order both for sections and for items within a section.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
MKDOCS_FILE = ROOT / "mkdocs.yml"

START = "# >>> BEGIN AUTO-GENERATED NAV (managed by scripts/build_nav.py)"
END = "# <<< END AUTO-GENERATED NAV"


def load_sources() -> list[dict]:
    if not SOURCES_FILE.exists():
        return []
    data = yaml.safe_load(SOURCES_FILE.read_text()) or {}
    return data.get("sources") or []


def build_nav(sources: list[dict]) -> list:
    nav: list = [{"Home": "index.md"}]

    by_section: "OrderedDict[str, list]" = OrderedDict()
    flat: list = []

    for src in sources:
        path = src.get("path")
        if not path:
            continue
        title = src.get("title") or path
        section = src.get("section")
        entry = {title: path}
        if section:
            by_section.setdefault(section, []).append(entry)
        else:
            flat.append(entry)

    for section, items in by_section.items():
        nav.append({section: items})
    nav.extend(flat)
    return nav


def render_nav_yaml(nav: list) -> str:
    return yaml.safe_dump(
        {"nav": nav},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    ).rstrip()


def replace_block(text: str, payload: str) -> str:
    if START in text and END in text:
        pre, _, rest = text.partition(START)
        _, _, post = rest.partition(END)
        return f"{pre}{START}\n{payload}\n{END}{post}"
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}\n{START}\n{payload}\n{END}\n"


def main() -> int:
    nav = build_nav(load_sources())
    payload = render_nav_yaml(nav)
    text = MKDOCS_FILE.read_text()
    new_text = replace_block(text, payload)
    if new_text != text:
        MKDOCS_FILE.write_text(new_text)
        print(f"Regenerated nav in {MKDOCS_FILE.name}")
    else:
        print("Nav already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
