# pub-md

A published collection of markdown documents, built automatically from a manifest of source files.

## What this is

This site renders a curated set of markdown documents. Each document is sourced from a URL or a Google Drive file, fetched on a schedule, and republished here whenever the source changes.

## Status

This is the initial scaffold — just MkDocs + Material with a single hand-written page, deployed to GitHub Pages to prove out the publish path. Upcoming work:

- [ ] `sources.yaml` manifest format
- [ ] `fetch.py` to pull URLs and detect changes via content hashing
- [ ] Auto-generated navigation from the manifest
- [ ] Google Drive support via service-account auth
- [ ] Scheduled rebuilds every 15 minutes

## Local preview

```bash
pip install -r requirements.txt
mkdocs serve
```

Then open <http://127.0.0.1:8000>.
