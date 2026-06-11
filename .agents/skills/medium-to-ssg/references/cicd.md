# CI/CD Workflows Reference

## Overview

What you generate here depends on the **hosting platform** and **content-deployment method** recorded in `migration-status.md`.

> **GitHub Pages hosting:** the deploy workflow is different (it uses the official Pages actions, not S3 sync). See `references/github-pages.md` for the full `deploy.yml`. The action-pinning rules and `dependabot.yml` below still apply; the AWS-specific workflows do not.

The rest of this file covers **AWS** hosting.

**GitHub Actions (default for the Terraform path):**

| File | Trigger | Purpose |
|---|---|---|
| `.github/workflows/deploy.yml` | Push to `main` | Build the site, sync to S3, invalidate CloudFront |
| `.github/workflows/terraform.yml` | PR or push to `main`, paths: `terraform/**` | Plan on PR (posts comment), apply on merge |

Plus a Dependabot config to keep action versions updated.

**Manual script (default for the AWS CLI / set-and-forget path):** Do **not** generate any GitHub Actions workflows. Instead, the user deploys with `infra/deploy.sh` (see `references/aws-cli-infra.md`), which builds the site and syncs to S3 + invalidates CloudFront from their machine. No GitHub secrets, no OIDC role.

**Method-by-method summary:**

| Hosting / method | Content deployment | Files generated |
|---|---|---|
| GitHub Pages | GitHub Actions (Pages) | `deploy.yml` (Pages actions) + `dependabot.yml` — see `references/github-pages.md` |
| AWS + Terraform, **remote state** (S3/HCP) | GitHub Actions (default) | `deploy.yml` + `terraform.yml` + `dependabot.yml` |
| AWS + Terraform, **local state** (default backend) | GitHub Actions (default) | `deploy.yml` + `dependabot.yml` — **no `terraform.yml`** (no shared state for CI; apply from your machine) |
| AWS + AWS CLI | Manual script (default) | `infra/deploy.sh` only — **no workflows** |
| AWS + AWS CLI | GitHub Actions (opt-in) | `deploy.yml` + `dependabot.yml` (**never** `terraform.yml`) + run `infra/07-iam-github.sh` to create the OIDC role |

> **Never generate `terraform.yml` for the AWS CLI path** — there is no Terraform state to plan or apply. The `deploy.yml` below works for either infrastructure method as long as the GitHub Actions OIDC role exists (created by Terraform `iam.tf`, or by `infra/07-iam-github.sh`).

---

## Action version pinning

**All `uses:` references must be pinned to a commit SHA**, not a version tag. Version tags are mutable and can be updated by the action's maintainer to point to different (potentially malicious) code.

Format:
```yaml
uses: actions/checkout@FULL_40_CHAR_SHA  # vX.Y.Z
```

Look up the current SHA for each action version by:
1. Visiting the action's GitHub releases page (e.g. `github.com/actions/checkout/releases`)
2. Finding the latest release in the relevant major version
3. Copying the full commit hash shown next to the tag

Do this for every action before writing the workflow files.

---

## deploy.yml

```yaml
name: Deploy

on:
  push:
    branches: [main]
    paths-ignore: ["terraform/**"]
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

defaults:
  run:
    working-directory: .   # Hugo build runs from repo root

jobs:
  deploy:
    name: Build and Deploy
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@SHA_HERE  # vX.Y.Z
        with:
          submodules: recursive  # Required: fetches the Hugo theme submodule

      - uses: peaceiris/actions-hugo@SHA_HERE  # vX.Y.Z
        with:
          hugo-version: "HUGO_VERSION"  # Pin to match local version: `hugo version`
          extended: true

      - name: Build site
        run: hugo --minify

      - uses: aws-actions/configure-aws-credentials@SHA_HERE  # vX.Y.Z
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Sync to S3
        run: |
          aws s3 sync public/ s3://${{ vars.S3_BUCKET }}/ \
            --delete \
            --cache-control "public, max-age=3600"

      - name: Invalidate CloudFront cache
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ vars.CLOUDFRONT_DISTRIBUTION_ID }} \
            --paths "/*"
```

**Note on `submodules: recursive`**: This is required to pull in the Hugo theme when it is installed as a git submodule. Without it, the `themes/` directory will be empty and `hugo --minify` will fail.

**Note for Hugo Module themes**: If the theme is installed as a Hugo Module (a `[module]` import in config with `go.mod`/`go.sum`, no `themes/` submodule) instead of a submodule, add a Go setup step **before** the build so Hugo can fetch the module from its cache:

```yaml
      - uses: actions/setup-go@SHA_HERE  # vX.Y.Z
        with:
          go-version: "stable"
```

The `submodules: recursive` checkout option is harmless but unnecessary on this path.

**Note on Hugo version**: The version string in the workflow must match the user's local Hugo version to avoid build differences. Ask the user to run `hugo version` locally and use that exact version number.

### Eleventy variant

The `deploy.yml` above is written for the **Hugo** path. For an **Eleventy** site, only the *build* portion changes; the AWS credential, S3 sync, and CloudFront-invalidation steps are identical except that the sync source is the Eleventy output directory. Replace the checkout + Hugo + build steps with a Node toolchain, and sync `_site/` instead of `public/`:

```yaml
      - uses: actions/checkout@SHA_HERE  # vX.Y.Z
        # No `submodules: recursive` needed — the Eleventy starter is committed,
        # not a theme submodule (unless you separately added one).

      - uses: actions/setup-node@SHA_HERE  # vX.Y.Z
        with:
          node-version-file: ".nvmrc"   # matches the version the starter ships

      - name: Install dependencies
        run: npm ci

      - name: Build site
        run: npx @11ty/eleventy

      # ... configure-aws-credentials step is unchanged ...

      - name: Sync to S3
        run: |
          aws s3 sync _site/ s3://${{ vars.S3_BUCKET }}/ \
            --delete \
            --cache-control "public, max-age=3600"

      # ... CloudFront invalidation step is unchanged ...
```

Use `node-version-file: ".nvmrc"` so CI builds with the same Node the user builds with locally (a local/CI Node mismatch is the most common Eleventy CI failure). Do not add the `peaceiris/actions-hugo` step on this path. The `run: npx @11ty/eleventy` build matches the `eleventy-base-blog` starter; if the chosen starter's `package.json` `scripts.build` does more than call `eleventy` (e.g. bundles JS or sets `ELEVENTY_ENV=production`), use that command (typically `npm run build`) here instead — see "Adapting to a different starter" in `references/eleventy-setup.md`.

### Astro variant

Astro is the same shape as the Eleventy variant — a Node toolchain replaces the Hugo steps — with two differences: the build command is `npm run build` and the output directory is `dist/` (not `_site/`). Sync `dist/` instead of `public/`:

```yaml
      - uses: actions/checkout@SHA_HERE  # vX.Y.Z
        # No `submodules: recursive` needed — the Astro starter is committed,
        # not a theme submodule.

      - uses: actions/setup-node@SHA_HERE  # vX.Y.Z
        with:
          node-version-file: ".nvmrc"   # matches the version pinned in Step 2

      - name: Install dependencies
        run: npm ci

      - name: Build site
        run: npm run build

      # ... configure-aws-credentials step is unchanged ...

      - name: Sync to S3
        run: |
          aws s3 sync dist/ s3://${{ vars.S3_BUCKET }}/ \
            --delete \
            --cache-control "public, max-age=3600"

      # ... CloudFront invalidation step is unchanged ...
```

Pin `.nvmrc` to the Node version the starter's `package.json` `engines` requires (Astro's floor is higher than this skill's other paths and rises over time — read it from the starter, don't hard-code it; see Step 2 in `references/astro-setup.md`). `npm run build` runs the starter's `astro build`; if the chosen starter wraps the build in extra steps (e.g. `astro check` first), that same `npm run build` still runs them — see "Adapting to a different starter" in `references/astro-setup.md`.

**If the theme's lockfile names pnpm or bun instead of npm**, swap the toolchain to match (the lockfile names the manager — see "Install with the package manager the theme's lockfile names" in `references/astro-setup.md`). For **pnpm**, add `pnpm/action-setup@SHA` *before* `actions/setup-node`, set the node step's `cache: pnpm`, and use `pnpm install --frozen-lockfile` / `pnpm run build`. For **bun**, add `oven-sh/setup-bun@SHA` and use `bun install --frozen-lockfile` / `bun run build`, keeping `actions/setup-node` so Astro's `engines` floor is satisfied (a bun-only theme like erudite ships no `.nvmrc`, so pin a concrete `node-version:` rather than `node-version-file`). Pin any added action to a commit SHA like the rest.

---

## terraform.yml

```yaml
name: Terraform

on:
  push:
    branches: [main]
    paths: ["terraform/**"]
  pull_request:
    branches: [main]
    paths: ["terraform/**"]

permissions:
  contents: read
  pull-requests: write

defaults:
  run:
    working-directory: terraform

jobs:
  plan:
    name: Plan
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'

    steps:
      - uses: actions/checkout@SHA_HERE  # vX.Y.Z

      - uses: hashicorp/setup-terraform@SHA_HERE  # vX.Y.Z
        with:
          cli_config_credentials_token: ${{ secrets.TF_API_TOKEN }}

      - name: Terraform Init
        run: terraform init

      - name: Terraform Plan
        id: plan
        shell: bash
        continue-on-error: true
        run: |
          terraform plan -no-color 2>&1 | tee /tmp/plan.txt
          echo "exit_code=${PIPESTATUS[0]}" >> $GITHUB_OUTPUT

      - name: Extract HCP Terraform run URL
        id: run_url
        shell: bash
        run: |
          URL=$(grep -oE 'https://app\.terraform\.io/[^[:space:]]+' /tmp/plan.txt \
            | grep '/runs/' | head -1)
          echo "url=${URL}" >> $GITHUB_OUTPUT

      - name: Post plan comment to PR
        uses: actions/github-script@SHA_HERE  # vX.Y.Z
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            const fs = require('fs');
            const output = fs.readFileSync('/tmp/plan.txt', 'utf8');
            const runUrl = '${{ steps.run_url.outputs.url }}';
            const succeeded = '${{ steps.plan.outputs.exit_code }}' === '0';
            const trimmed = output.length > 20000
              ? '(trimmed — see HCP Terraform for full output)\n...\n' + output.slice(-20000)
              : output;
            const body = [
              '## Terraform Plan',
              `**Status:** ${succeeded ? '✅ Plan succeeded' : '❌ Plan failed'}`,
              runUrl && `**HCP Terraform:** [View run ↗](${runUrl})`,
              '<details><summary>Plan output</summary>',
              '```', trimmed, '```', '</details>',
            ].filter(Boolean).join('\n');
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner, repo: context.repo.repo, body,
            });

      - name: Fail if plan failed
        if: steps.plan.outputs.exit_code != '0'
        run: exit 1

  apply:
    name: Apply
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@SHA_HERE  # vX.Y.Z

      - uses: hashicorp/setup-terraform@SHA_HERE  # vX.Y.Z
        with:
          cli_config_credentials_token: ${{ secrets.TF_API_TOKEN }}

      - name: Terraform Init
        run: terraform init

      - name: Terraform Apply
        run: terraform apply -auto-approve -no-color
```

**Note on `cli_config_credentials_token`**: This is for HCP Terraform. If the user is using a plain S3 backend instead, remove this input and add AWS credential configuration (the `configure-aws-credentials` action) instead. If the user kept **local** state, don't generate `terraform.yml` at all — there's no shared remote state for CI to use, so they apply from their own machine. See "Choosing a state backend" in `references/terraform.md`.

---

## dependabot.yml

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

This single entry covers all workflows under `.github/workflows/`. Dependabot will open PRs to update pinned SHAs when new action versions are released, keeping the version comments in sync automatically.

### Eleventy or Astro: also track npm dependencies

When the SSG is **Eleventy** or **Astro**, the site is an npm project (`package.json` at the repo root, alongside `.github/`), so add a second `npm` ecosystem entry to keep the generator and its plugins/integrations patched. (Dependabot's `npm` ecosystem also covers pnpm and yarn projects; for a bun-only theme it still tracks `package.json`, though Dependabot's bun-lockfile support is limited.) Do this **regardless of hosting platform or deployment method** — it is about the project's JavaScript dependencies, not CI:

```yaml
version: 2
updates:
  - package-ecosystem: github-actions   # omit this entry if no workflows are generated
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: npm
    directory: /                        # package.json lives at the repo root
    schedule:
      interval: weekly
```

On the **AWS CLI + manual deploy** Eleventy or Astro path there are no workflows, so there is no `github-actions` entry and no `.github/workflows/` folder — but still create `.github/dependabot.yml` with **just the `npm` entry** so dependencies stay current. On the Hugo path, omit the `npm` entry entirely (Hugo is a single binary with no `package.json` to track, unless a theme adds a PostCSS toolchain — see `references/hugo-setup.md`).

---

## GitHub repository secrets and variables

Only needed if using GitHub Actions deploy. After provisioning, set these in GitHub → Settings → Secrets and variables → Actions. The "Value" column shows the Terraform output; for the AWS CLI path, read the same values from the scripts' output (bucket name = your domain, role ARN printed by `infra/07-iam-github.sh`, distribution id saved in `infra/.dist_id`).

| Name | Type | Value (Terraform) | Value (AWS CLI) |
|---|---|---|---|
| `AWS_ROLE_ARN` | Secret | `terraform output -raw github_actions_role_arn` | ARN printed by `infra/07-iam-github.sh` |
| `TF_API_TOKEN` | Secret | HCP Terraform API token (if using HCP Terraform) | not used |
| `AWS_REGION` | Variable | e.g. `us-east-1` | e.g. `us-east-1` |
| `S3_BUCKET` | Variable | `terraform output -raw s3_bucket_name` | your domain (the bucket name) |
| `CLOUDFRONT_DISTRIBUTION_ID` | Variable | `terraform output -raw cloudfront_distribution_id` | value in `infra/.dist_id` |
