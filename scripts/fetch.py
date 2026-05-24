#!/usr/bin/env python3
"""Fetch markdown sources listed in sources.yaml into docs/.

Reads sources.yaml, fetches each entry, hashes the content, and writes a copy
under docs/<path> only when the content has changed since the last run. The
hash cache lives at .cache/hashes.json and is committed alongside the fetched
docs so subsequent runs can detect real changes.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
DOCS_DIR = ROOT / "docs"
CACHE_FILE = ROOT / ".cache" / "hashes.json"
USER_AGENT = "pub-md-fetcher/0.1"
TIMEOUT = 30


def load_sources() -> list[dict]:
    if not SOURCES_FILE.exists():
        return []
    data = yaml.safe_load(SOURCES_FILE.read_text()) or {}
    return data.get("sources") or []


def load_cache() -> dict[str, str]:
    if not CACHE_FILE.exists():
        return {}
    return json.loads(CACHE_FILE.read_text())


def save_cache(cache: dict[str, str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def fetch_url(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset)


def render(source: dict, body: str) -> str:
    meta = {
        "title": source.get("title"),
        "source": source.get("url", ""),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    meta = {k: v for k, v in meta.items() if v is not None}
    fm = yaml.safe_dump(meta, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{fm}\n---\n\n{body}"


def safe_dest(path: str) -> Path | None:
    """Resolve <DOCS_DIR>/<path> and reject anything escaping docs/."""
    dest = (DOCS_DIR / path).resolve()
    try:
        dest.relative_to(DOCS_DIR.resolve())
    except ValueError:
        return None
    return dest


def main() -> int:
    sources = load_sources()
    cache = load_cache()
    changed: list[str] = []
    errors: list[tuple[str, str]] = []

    for src in sources:
        path = src.get("path")
        if not path:
            errors.append(("(no path)", "missing 'path'"))
            continue

        dest = safe_dest(path)
        if dest is None:
            errors.append((path, "path escapes docs/"))
            continue

        kind = src.get("type")
        try:
            if kind == "url":
                body = fetch_url(src["url"])
            else:
                errors.append((path, f"unsupported type: {kind!r}"))
                continue
        except (HTTPError, URLError, TimeoutError) as e:
            errors.append((path, f"{type(e).__name__}: {e}"))
            continue

        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if cache.get(path) == digest and dest.exists():
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render(src, body))
        cache[path] = digest
        changed.append(path)

    save_cache(cache)

    if changed:
        print(f"Updated {len(changed)} file(s):")
        for p in changed:
            print(f"  - {p}")
    else:
        print("No changes.")

    if errors:
        print(f"\n{len(errors)} error(s):", file=sys.stderr)
        for p, msg in errors:
            print(f"  - {p}: {msg}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
