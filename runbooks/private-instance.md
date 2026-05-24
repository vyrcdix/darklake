# Runbook: spinning up a private (internal) instance

When you need to publish confidential content that should NOT appear on this (public) repo's site, stand up a second darklake instance in a **private** repo, served via **Azure Static Web Apps + Microsoft Entra ID**. The public and private instances run independently — same scripts, different manifests, different hosting.

This runbook is the step-by-step. Allow ~45 minutes the first time.

## When to use this

- You have at least one document whose contents shouldn't be world-readable.
- Your viewers are employees who can be authenticated via your Entra (Azure AD) tenant.
- Mixing public + private in one site is **not** an option — separation of repos is the safety story.

## Prerequisites

- An **Azure subscription** with permission to create Static Web Apps.
- **GitHub** account with permission to create a private repo under `vyrcdix` (or your org).
- Your Entra tenant ID and (optionally) an app-registration owner.
- Local: this repo cloned, `git` and the `gh` CLI installed (the `gh` CLI is optional but convenient).

## Step 1 — Mirror this repo into a private one

```bash
# from a scratch directory:
git clone --bare git@github.com:vyrcdix/darklake.git
gh repo create vyrcdix/darklake-internal --private --description "Internal docs"
cd darklake.git
git push --mirror git@github.com:vyrcdix/darklake-internal.git
cd .. && rm -rf darklake.git
git clone git@github.com:vyrcdix/darklake-internal.git
cd darklake-internal
```

The two repos now share history but evolve independently.

## Step 2 — Reset the manifest and example content

```bash
# Drop the public example so the private site starts empty
rm -rf .cache docs/examples
```

Edit `sources.yaml` to leave `sources: []` (you'll add real entries in step 8).

```bash
git add -A
git commit -m "Reset manifest for internal instance"
git push
```

## Step 3 — Create the Azure Static Web App

In the Azure Portal:

1. **Create a resource** → search "Static Web App" → Create.
2. Subscription / resource group: pick or create a group like `rg-darklake-internal`.
3. Name: `darklake-internal` (whatever's free in the region).
4. Plan type: **Free** (sufficient for docs).
5. Region: nearest to your team.
6. Deployment source: **GitHub**. Authorize if prompted.
7. Org / Repo / Branch: `vyrcdix` / `darklake-internal` / `master`.
8. Build presets: **Custom**:
   - App location: `/`
   - Api location: (leave blank)
   - Output location: `site`
9. **Review + create** → **Create**.

Azure does two things:

- Adds an API token as a repo secret named `AZURE_STATIC_WEB_APPS_API_TOKEN_<random>`.
- Generates a workflow at `.github/workflows/azure-static-web-apps-<random>.yml` that builds with Oryx (won't work for our pipeline).

## Step 4 — Replace the auto-generated deploy with our pipeline

In the new repo:

1. **Delete** the auto-generated `.github/workflows/azure-static-web-apps-*.yml`.
2. In **Settings → Secrets and variables → Actions**, rename `AZURE_STATIC_WEB_APPS_API_TOKEN_<random>` to plain `AZURE_STATIC_WEB_APPS_API_TOKEN` (delete + recreate with the same value).
3. Edit `.github/workflows/publish.yml`:

   **Remove** these blocks (GitHub Pages specifics):

   ```yaml
   permissions:
     pages: write
     id-token: write

   concurrency:
     group: pages
     cancel-in-progress: false
   ```

   ```yaml
   - uses: actions/upload-pages-artifact@v3
     with:
       path: site

   deploy:
     needs: build
     runs-on: ubuntu-latest
     environment:
       name: github-pages
       url: ${{ steps.deployment.outputs.page_url }}
     steps:
       - id: deployment
         uses: actions/deploy-pages@v4
   ```

   **Add** an Azure deploy step at the end of the `build` job:

   ```yaml
   - name: Deploy to Azure Static Web Apps
     uses: Azure/static-web-apps-deploy@v1
     with:
       azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}
       repo_token: ${{ secrets.GITHUB_TOKEN }}
       action: upload
       app_location: site
       skip_app_build: true
   ```

   Keep `permissions: contents: write` so the cron's commit-back still works.

## Step 5 — Lock the site behind Entra auth

Create `docs/staticwebapp.config.json` (MkDocs copies anything non-markdown under `docs/` straight to the site root):

```json
{
  "routes": [
    { "route": "/.auth/login/aad", "rewrite": "/.auth/login/aad" },
    { "route": "/*", "allowedRoles": ["authenticated"] }
  ],
  "responseOverrides": {
    "401": { "redirect": "/.auth/login/aad", "statusCode": 302 }
  }
}
```

Commit and push.

## Step 6 — Wire up Microsoft Entra ID

In the Azure Portal → your Static Web App → **Authentication** (or **Settings → Identity providers** depending on UI version):

1. **Add identity provider** → **Microsoft**.
2. App registration type: **Create new** (simplest), or **Provide details of existing app registration** if you already have one.
3. Supported account types: **Accounts in this organizational directory only** (single-tenant).
4. Save.

The SWA now redirects unauthenticated requests to your tenant's login page.

To restrict to a subset of employees, swap `"authenticated"` in `staticwebapp.config.json` for a custom role and assign that role per-user in the SWA's **Role management** blade.

## Step 7 — Custom domain (optional but recommended)

In the Azure Portal → SWA → **Custom domains** → **Add custom domain on other DNS**:

1. Enter `docs.your-tenant.com` (or whatever).
2. Azure shows the required `CNAME` (and validation `TXT` for apex domains).
3. Add those records in your DNS provider.
4. Wait for validation (10-60 min). SSL is auto-provisioned via Azure.

## Step 8 — First publish

Add a real internal source to `sources.yaml`, commit, push:

```yaml
sources:
  - title: "Internal Runbook"
    type: url
    url: https://raw.githubusercontent.com/your-org/private-repo/main/RUNBOOK.md
    path: ops/runbook.md
    auth_env: GH_PAT
    section: Ops
```

Add the matching secret (`GH_PAT`) in the new repo's Settings → Secrets. Trigger the workflow from the **Actions** tab. When the build is green, visit your SWA URL (or custom domain) — you should see the Entra login, then the site.

## Maintenance: keeping the two instances in sync

`fetch.py`, `build_nav.py`, `mkdocs.yml`, `requirements.txt` should stay identical across the two repos. When you change one of them in `darklake` (public), apply the same change in `darklake-internal`.

For a codebase this size (~470 LOC), manual sync is fine. Options if it grows:

- **Git remote sync** — add the public repo as a second remote in the private repo and cherry-pick / merge the code changes (not the manifest).
- **Extract pub-md into a Python package** — both repos `pip install pub-md`, only `sources.yaml` and `docs/index.md` differ.

## Troubleshooting

**Workflow succeeds but site 404s on first visit.** Check the SWA "Deployment" tab in the Azure Portal — usually `app_location` or `output_location` is wrong, or the deploy step ran but with empty `site/` because `mkdocs build` was skipped.

**Site loads without prompting for login.** `staticwebapp.config.json` didn't reach `site/`. Confirm it's at `docs/staticwebapp.config.json` in source, and check the deployed artifact under `site/` in a local build.

**Login loops, or "user not authorized".** The user's role doesn't match `allowedRoles`. Start with `authenticated` (any signed-in user) before adding custom roles.

**Workflow can't push fetched changes.** Workflow permissions in the new repo's Settings → Actions are still default. Set to "Read and write permissions" as you did for the public repo.

**Want to switch the private site off temporarily.** Delete `staticwebapp.config.json`'s route restriction → the site becomes open. **Don't** do this if anything sensitive is published; instead disable the workflow in Actions settings.
