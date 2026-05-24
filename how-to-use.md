# How to use pub-md

Task-oriented recipes for common workflows. For reference material — manifest field definitions, file layout, theme config — see the [README](README.md).

## I want to publish a document from a public URL

The simplest case. No auth, no secrets.

1. Get the **raw** URL. On GitHub: open the file, click **Raw**, copy.
2. Add an entry to `sources.yaml`:

   ```yaml
   sources:
     - title: "My Document"
       type: url
       url: https://raw.githubusercontent.com/owner/repo/main/PATH.md
       path: my-section/my-doc.md
       section: My Section
   ```

3. Commit and push.

The cron picks it up within 15 minutes. To publish immediately, trigger the workflow manually (Actions tab → **Publish site** → **Run workflow**).

## I want to publish a document from a private GitHub repo

You'll need a fine-grained PAT with read access to the **source** repo (not darklake).

1. Create the PAT:
   - GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens** → **Generate new token**.
   - **Repository access**: select the source repo.
   - **Permissions**: **Contents: Read-only**.
   - Copy the generated token (starts with `github_pat_`).
2. Add it as a darklake secret:
   - Darklake repo → **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `GH_PAT`. Value: `Bearer github_pat_xxxxxxx` (include the `Bearer ` prefix).
3. Map the secret in `.github/workflows/publish.yml` — uncomment the matching line under `jobs.build.env`:

   ```yaml
   GH_PAT: ${{ secrets.GH_PAT }}
   ```

4. Add the manifest entry with `auth_env: GH_PAT`:

   ```yaml
   sources:
     - title: "Internal Runbook"
       type: url
       url: https://raw.githubusercontent.com/your-org/private-repo/main/RUNBOOK.md
       path: ops/runbook.md
       auth_env: GH_PAT
       section: Ops
   ```

5. Commit and push.

## I want to publish a document from Unfuddle

1. Generate an Unfuddle API key: **Personal Settings → API Keys**.
2. Base64-encode `username:apikey`:

   ```bash
   echo -n "your-username:your-api-key" | base64
   ```

3. Add a darklake secret:
   - Name: `UNFUDDLE_AUTH`. Value: `Basic <base64-output>`.
4. Map it in `.github/workflows/publish.yml` under `jobs.build.env`:

   ```yaml
   UNFUDDLE_AUTH: ${{ secrets.UNFUDDLE_AUTH }}
   ```

5. Find the file's download URL. For Unfuddle Stack repos the typical pattern is:

   ```
   https://your-account.unfuddle.com/api/v1/repositories/<REPO_ID>/download?path=<FILE_PATH>
   ```

   Confirm against your Unfuddle account's API docs — exact URL shape can vary by product tier.

6. Add the manifest entry:

   ```yaml
   sources:
     - title: "Project Spec"
       type: url
       url: https://your-account.unfuddle.com/api/v1/repositories/123/download?path=SPEC.md
       path: specs/project.md
       auth_env: UNFUDDLE_AUTH
       section: Specs
   ```

7. Commit and push.

## I want to publish a document from Azure DevOps Repos

1. Create an Azure DevOps PAT: **User settings → Personal access tokens → New token**. Scope: **Code (Read)**.
2. Base64-encode `:pat` (empty username, PAT as password):

   ```bash
   echo -n ":your-pat-value" | base64
   ```

3. Add a darklake secret: `AZDO_PAT` = `Basic <base64-output>`.
4. Map it in `.github/workflows/publish.yml`:

   ```yaml
   AZDO_PAT: ${{ secrets.AZDO_PAT }}
   ```

5. Get the file's API URL:

   ```
   https://dev.azure.com/<ORG>/<PROJECT>/_apis/git/repositories/<REPO>/items?path=<FILE>&api-version=7.1
   ```

6. Add the manifest entry with `auth_env: AZDO_PAT`. Commit and push.

## I want to publish a Google Doc

1. **One-time only** — set up a Google Cloud service account: see [README → One-time service-account setup](README.md#one-time-service-account-setup). End result is a `GDRIVE_SA_JSON` secret in the repo.
2. Share the doc with the service account's email (Viewer is enough).
3. Get the file ID from the doc URL — the long string between `/d/` and `/edit`:

   ```
   https://docs.google.com/document/d/<FILE_ID>/edit
   ```

4. Add the manifest entry:

   ```yaml
   sources:
     - title: "Design Overview"
       type: gdrive
       file_id: 1AbCdEfG_the_id_from_the_url
       path: design/overview.md
       section: Design
   ```

5. Commit and push.

Google Docs are exported as Markdown automatically. Native `.md`/`.txt` files in Drive are downloaded as-is. Other file types are rejected with an `unsupported Drive mimeType` error.

## I want to update a published document

Don't edit anything in darklake — edit the source. The next cron run picks up the change automatically (or trigger the workflow manually for immediate publish).

If you need a one-off fix to the published copy without changing the source, you can edit `docs/<path>` directly and push. The next fetch will overwrite your edit when upstream changes.

## I want to remove a published document

1. Delete the entry from `sources.yaml`.
2. Commit and push.

On the next run, `fetch.py` detects the orphan, deletes its `docs/` file, and removes the cache entry. No manual cleanup needed.

## I want to rename or move a document

Change the `path:` (and/or `title:`, `section:`) of the entry. Commit and push. The old file is auto-pruned, the new one is fetched into its new location.

## I want to add a new nav section

Use a new `section:` value in any manifest entry. The nav regenerates on every run. Sections appear in the order they **first show up** in `sources.yaml`; reorder entries to reorder sections.

To put an item directly at the top level (no section), omit `section:` entirely.

## I want to trigger a republish right now

Don't wait for the 15-minute cron:

1. GitHub repo → **Actions** tab.
2. **Publish site** in the left sidebar.
3. **Run workflow** → **Run workflow**.

The pipeline finishes in ~30 seconds. Refresh the site URL after the deploy job goes green.

## I want to see what's currently published

| Where | Shows |
|---|---|
| `https://vyrcdix.github.io/darklake/` | The live site |
| `sources.yaml` | Intended manifest |
| `docs/` in the repo | Actual fetched content (hand-written `index.md` + everything fetched) |
| `Actions` tab → latest "Publish site" | When it last ran, what changed |

Each published page has a footer with the source link and last-fetched timestamp — quick way to spot stale or wrong-source content.

## I want to debug a broken source

1. **Actions** tab → most recent run → expand the **Fetch sources** step.
2. Look for lines starting with `! <path>:` — the error message names the failure.
3. Common fixes:
   - **`404`** — URL is wrong, or the source moved/was deleted.
   - **`401` / `403`** — credential expired, lacks scope, or doesn't have access. For GitHub fine-grained PATs: rotate the token and confirm the source repo is selected in **Repository access**.
   - **`auth_env 'X' not set`** — the env var isn't mapped in `jobs.build.env`, or the secret is missing.
   - **`DefaultCredentialsError`** — `GDRIVE_SA_JSON` secret is missing.
   - **`unsupported Drive mimeType`** — the Drive file isn't a Google Doc or a native `.md`/`.txt`. Convert it.

Locally, you can reproduce the fetch loudly:

```bash
.venv/bin/python scripts/fetch.py
```

(Default mode exits 1 on errors — louder than the cron's `--continue` mode, which logs but keeps going.)

## I want to preview changes before pushing

```bash
# pull the latest from every source
.venv/bin/python scripts/fetch.py

# regenerate the nav
.venv/bin/python scripts/build_nav.py

# serve locally
.venv/bin/mkdocs serve
# then open http://127.0.0.1:8000
```

`mkdocs serve` hot-reloads on file changes — edit anything under `docs/`, refresh the browser.

## I want to publish something confidential

Do **not** add it to `sources.yaml` here — anything in this manifest ends up on the public site. Spin up a private mirror instead. Step-by-step: [`runbooks/private-instance.md`](runbooks/private-instance.md).
