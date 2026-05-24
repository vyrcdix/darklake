#!/usr/bin/env python3
"""Fetch markdown sources listed in sources.yaml into docs/.

Supports two source types:

- type: url     HTTP(S) GET of a markdown file. Optionally authenticated
                via an `auth_env:` field naming an env var whose contents
                become the `Authorization` header (covers private GitHub
                with a PAT, Unfuddle Basic auth, Azure DevOps, etc).
- type: gdrive  Google Drive file by file_id; Google Docs are exported as
                Markdown, native .md/.txt files are downloaded as-is.

Reads sources.yaml, fetches each entry, hashes the upstream content, and
writes a copy under docs/<path> only when the content has changed since
the last run. The hash cache lives at .cache/hashes.json and is committed
alongside the fetched docs so subsequent runs can detect real changes.
Removing an entry from sources.yaml prunes its file and cache entry on
the next run.

Google Drive authentication uses a service-account JSON key. The path to
that key is read from the standard GOOGLE_APPLICATION_CREDENTIALS env var.

Exits 1 on any per-source error by default (good for local feedback).
Pass --continue to exit 0 with errors logged to stderr, so a single
broken source does not block a cron run from publishing the rest.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.yaml"
DOCS_DIR = ROOT / "docs"
CACHE_FILE = ROOT / ".cache" / "hashes.json"
USER_AGENT = "pub-md-fetcher/0.1"
TIMEOUT = 30

GDOC_MIME = "application/vnd.google-apps.document"
NATIVE_MD_MIMES = {"text/markdown", "text/x-markdown", "text/plain"}
DRIVE_API = "https://www.googleapis.com/drive/v3/files"


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


def fetch_url(url: str, auth_env: str | None = None) -> str:
    headers = {"User-Agent": USER_AGENT}
    if auth_env:
        token = os.environ.get(auth_env)
        if not token:
            raise RuntimeError(f"auth_env {auth_env!r} not set")
        headers["Authorization"] = token
    r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def build_drive_session():
    """Build an authenticated Drive session using application-default credentials."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return AuthorizedSession(creds)


def fetch_gdrive(file_id: str, session) -> str:
    meta = session.get(
        f"{DRIVE_API}/{file_id}",
        params={"fields": "mimeType,name"},
        timeout=TIMEOUT,
    )
    meta.raise_for_status()
    mime = meta.json().get("mimeType", "")

    if mime == GDOC_MIME:
        r = session.get(
            f"{DRIVE_API}/{file_id}/export",
            params={"mimeType": "text/markdown"},
            timeout=TIMEOUT,
        )
    elif mime in NATIVE_MD_MIMES:
        r = session.get(
            f"{DRIVE_API}/{file_id}",
            params={"alt": "media"},
            timeout=TIMEOUT,
        )
    else:
        raise ValueError(f"unsupported Drive mimeType: {mime!r}")

    r.raise_for_status()
    return r.text


def source_ref(source: dict) -> str:
    kind = source.get("type")
    if kind == "url":
        return source.get("url", "")
    if kind == "gdrive":
        fid = source.get("file_id", "")
        return f"https://drive.google.com/file/d/{fid}/view" if fid else ""
    return ""


def render(source: dict, body: str) -> str:
    ref = source_ref(source)
    title = source.get("title") or ""
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta = {
        "title": title or None,
        "source": ref or None,
        "fetched_at": fetched,
    }
    meta = {k: v for k, v in meta.items() if v}
    fm = yaml.safe_dump(meta, sort_keys=False, default_flow_style=False).strip()

    link = f"[{title or 'source'}]({ref})" if ref else (title or "source")
    footer = f"\n\n---\n\n*Source: {link} &middot; Fetched: {fetched}*\n"

    return f"---\n{fm}\n---\n\n{body.rstrip()}{footer}"


def safe_dest(path: str) -> Path | None:
    dest = (DOCS_DIR / path).resolve()
    try:
        dest.relative_to(DOCS_DIR.resolve())
    except ValueError:
        return None
    return dest


def main() -> int:
    strict = "--continue" not in sys.argv[1:]

    sources = load_sources()
    cache = load_cache()
    changed: list[str] = []
    unchanged: list[str] = []
    pruned: list[str] = []
    errors: list[tuple[str, str]] = []
    declared: set[str] = set()
    drive = None

    for src in sources:
        path = src.get("path")
        if not path:
            errors.append(("(no path)", "missing 'path'"))
            continue

        declared.add(path)

        dest = safe_dest(path)
        if dest is None:
            errors.append((path, "path escapes docs/"))
            continue

        kind = src.get("type")
        try:
            if kind == "url":
                body = fetch_url(src["url"], src.get("auth_env"))
            elif kind == "gdrive":
                if drive is None:
                    drive = build_drive_session()
                body = fetch_gdrive(src["file_id"], drive)
            else:
                errors.append((path, f"unsupported type: {kind!r}"))
                continue
        except Exception as e:
            errors.append((path, f"{type(e).__name__}: {e}"))
            continue

        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if cache.get(path) == digest and dest.exists():
            unchanged.append(path)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render(src, body))
        cache[path] = digest
        changed.append(path)

    for orphan in sorted(set(cache) - declared):
        dest = safe_dest(orphan)
        if dest and dest.exists():
            dest.unlink()
        cache.pop(orphan, None)
        pruned.append(orphan)

    save_cache(cache)

    print(f"Fetched:   {len(changed)}")
    for p in changed:
        print(f"  + {p}")
    print(f"Unchanged: {len(unchanged)}")
    print(f"Pruned:    {len(pruned)}")
    for p in pruned:
        print(f"  - {p}")
    print(f"Errors:    {len(errors)}")
    sys.stdout.flush()
    for p, msg in errors:
        print(f"  ! {p}: {msg}", file=sys.stderr)

    if errors and strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
