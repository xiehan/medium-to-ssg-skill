# GitHub Pages Hosting Reference

This is the **alternative to AWS** for users who want the lowest-cost, simplest setup and are willing to cede fine-grained control. GitHub builds and hosts the Hugo site for free (for public repositories), provisions HTTPS automatically, and serves a custom domain — with **no S3, CloudFront, ACM, Route 53, Terraform, or AWS account**.

Use this path only when the hosting platform recorded in `migration-status.md` is `github-pages`. The content extraction/conversion (Phases 1–2) and Hugo scaffolding (Phase 3) are identical to the AWS path; only hosting (Phase 4), deployment (Phase 5), and DNS cutover (Phases 6–7) differ.

> Requirements for the user: a GitHub account and a repository. For **free** Pages the repository must be **public**. Private repositories require a paid plan (GitHub Pro, Team, or Enterprise). Confirm this with the user before proceeding.

---

## What carries over from the AWS path

- **Hugo aliases still preserve old Medium URLs.** They generate static `<meta refresh>` redirect pages that work on GitHub Pages exactly as they do on S3. No change needed.
- **`404.html`** is served automatically by GitHub Pages for missing paths.
- **Permalink structure** (`/posts/<slug>/`) and the converted post files are unchanged.

## What is different from AWS (the control tradeoffs)

| Capability | AWS (CloudFront) | GitHub Pages |
|---|---|---|
| `www` → apex redirect | CloudFront Function (server-side) | GitHub's built-in custom-domain redirect to the primary host |
| Directory → `index.html` | CloudFront Function | Handled natively by Pages (serves `index.html` for directories) |
| Custom headers / caching TTLs | Full control | None |
| Custom error responses | 403/404 → `404.html` | Serves `404.html` for 404s only |
| Private source repo | Yes | Only on paid plans |
| Cost | Small monthly bill | Free (public repos) |
| Bandwidth / size | Effectively unlimited | Soft limits (~1 GB site, ~100 GB/month soft bandwidth) |

For a typical personal blog these limits are not a problem. If the user needs any of the server-side controls above, steer them back to the AWS path.

---

## Phase 4 — Repository & Hugo configuration

### 1. Confirm repository visibility

Confirm the repo is public (free Pages) or that the user has a plan that allows Pages on a private repo. Do not proceed assuming a private repo works on the free tier.

### 2. Set `baseURL` in `hugo.toml`

The site must build with the final custom domain as its `baseURL`:

```toml
baseURL = "https://example.com/"
```

### 3. Add the `CNAME` file

GitHub Pages reads a `CNAME` file at the site root to bind the custom domain. With Hugo, put it in `static/` so it is copied verbatim into the built `public/` output:

```
hugo-site/static/CNAME
```

Contents (apex domain only, no scheme, no `www`):

```
example.com
```

> Note: GitHub also writes this file automatically when you set the custom domain in the repo UI. Committing it in `static/CNAME` keeps it from being wiped on each Actions deploy, which is the recommended approach when deploying via GitHub Actions.

### 4. Theme submodule or module

If the chosen theme is added as a git submodule, ensure `.gitmodules` is committed. The deploy workflow checks out submodules so the theme is present at build time.

If the theme is instead installed as a **Hugo Module** (a `[module]` import with `go.mod`/`go.sum` and no `themes/` submodule), commit `go.mod` and `go.sum`, and add an `actions/setup-go` step to the deploy workflow before the build so Hugo can fetch the module (see the module note in `references/cicd.md`).

---

## Phase 5 — Deploy workflow

GitHub Pages with Hugo deploys via the official Pages actions. Write `.github/workflows/deploy.yml`. **Pin every action to a commit SHA** (look up the current SHA for each, as in `references/cicd.md`).

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

# Allow the GITHUB_TOKEN to deploy to Pages and verify the origin
permissions:
  contents: read
  pages: write
  id-token: write

# Allow one concurrent deployment; don't cancel in-progress production deploys
concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@SHA_HERE  # vX.Y.Z
        with:
          submodules: recursive   # fetch the Hugo theme submodule

      - uses: peaceiris/actions-hugo@SHA_HERE  # vX.Y.Z
        with:
          hugo-version: "HUGO_VERSION"   # match local `hugo version`
          extended: true

      - uses: actions/configure-pages@SHA_HERE  # vX.Y.Z

      - name: Build with Hugo
        run: hugo --minify --baseURL "https://example.com/"

      - uses: actions/upload-pages-artifact@SHA_HERE  # vX.Y.Z
        with:
          path: ./public

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@SHA_HERE  # vX.Y.Z
```

Also add `.github/dependabot.yml` (identical to the AWS path) to keep the pinned SHAs updated:

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

**Do not** generate `terraform.yml`, any AWS credential steps, OIDC role, or S3 sync — none apply to GitHub Pages.

### Enable Pages in repo settings

Before the first deploy succeeds, the repo's **Settings → Pages → Build and deployment → Source** must be set to **GitHub Actions** (not "Deploy from a branch"). Tell the user to set this; it cannot be done from the workflow.

---

## Phases 6–7 — Custom domain & DNS cutover

GitHub Pages does **not** require migrating DNS to a new provider. The user keeps their current DNS host and only adds/updates the records that point the domain at GitHub Pages. All other records (email MX/TXT, verification, etc.) stay exactly as they are — still review them per `references/dns-cutover.md` Part 1 so nothing is accidentally removed.

### Step 1 — First deploy

Push to `main` (or run the workflow via `workflow_dispatch`) and confirm the build **succeeds**. The site is published to a temporary Pages URL (`https://<user>.github.io/<repo>/`, or `https://<user>.github.io/` for a `<user>.github.io` repo).

> **Expect the github.io preview to look unstyled, and don't treat that as a failure.** The build sets `baseURL` to the final custom domain (`https://example.com/`), so at the temporary github.io URL the CSS/JS and internal links point at the not-yet-live custom domain and won't resolve. This is normal and resolves itself once the custom domain is live (Step 4). For real **pre-DNS content verification** — that posts render and that the Medium-style aliases exist — use a local build instead (`hugo server` from Phase 3, or inspect the built `public/` for the alias redirect files). Full styling, alias redirects, and HTTPS are verified after the custom domain resolves in Step 5.

### Step 2 — Set the custom domain

In **Settings → Pages → Custom domain**, enter the apex domain (`example.com`) and save. This triggers GitHub's domain-verification process. (The committed `static/CNAME` file keeps this setting stable across deploys.)

### Step 3 — Add DNS records at the user's existing provider

Add these at whatever DNS host the user already uses (Namecheap, Cloudflare, Route 53, etc.). The exact UI differs per provider; the records are the same.

**Apex domain `A` records** (GitHub Pages IPv4 addresses):

```
@   A   185.199.108.153
@   A   185.199.109.153
@   A   185.199.110.153
@   A   185.199.111.153
```

**Apex `AAAA` records** (IPv6, recommended):

```
@   AAAA   2606:50c0:8000::153
@   AAAA   2606:50c0:8001::153
@   AAAA   2606:50c0:8002::153
@   AAAA   2606:50c0:8003::153
```

**`www` subdomain `CNAME`:**

```
www   CNAME   <user>.github.io.
```

> Verify the current GitHub Pages IP addresses against GitHub's official docs at deploy time (search "GitHub Pages apex domain IP addresses"). They change rarely but should be confirmed rather than assumed.

> If the domain is on **Cloudflare**, set the apex/www records to **DNS only** (grey cloud), not proxied, while GitHub provisions the certificate — proxying can block domain verification and certificate issuance.

### Step 4 — Wait for verification and enable HTTPS

After DNS propagates, GitHub verifies the domain and automatically provisions a Let's Encrypt certificate (this can take a few minutes up to ~24 hours). Once available, enable **Enforce HTTPS** in Settings → Pages.

### Step 5 — Verify the live site

- [ ] `https://example.com` loads the site over HTTPS
- [ ] `https://www.example.com` redirects to the primary host
- [ ] At least one post loads at its canonical URL (`/posts/post-slug/`)
- [ ] A Medium-style alias URL redirects correctly (`/post-slug-a1b2c3d4` → `/posts/post-slug/`)
- [ ] The `404.html` page shows for an invalid path
- [ ] Email and any preserved records still work (send a test email if applicable)

### Step 6 — Mark migration complete

Update `migration-status.md`: check off Phase 7, record the live URL and date, and note any follow-ups (e.g. cancelling the old Medium subscription, making the repo public if it wasn't already).

---

## Switching platforms later

If the user outgrows GitHub Pages (needs private hosting, server-side redirects, custom headers, or higher limits), they can migrate to the AWS path later: generate the `terraform/` or `infra/` files (`references/terraform.md` or `references/aws-cli-infra.md`), then repoint DNS. The Hugo site, content, and aliases are reused unchanged — only the hosting layer moves.
