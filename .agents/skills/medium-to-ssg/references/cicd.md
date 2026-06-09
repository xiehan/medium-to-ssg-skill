# CI/CD Workflows Reference

## Overview

What you generate here depends on the **hosting platform** and **content-deployment method** recorded in `migration-status.md`.

> **GitHub Pages hosting:** the deploy workflow is different (it uses the official Pages actions, not S3 sync). See `references/github-pages.md` for the full `deploy.yml`. The action-pinning rules and `dependabot.yml` below still apply; the AWS-specific workflows do not.

The rest of this file covers **AWS** hosting.

**GitHub Actions (default for the Terraform path):**

| File | Trigger | Purpose |
|---|---|---|
| `.github/workflows/deploy.yml` | Push to `main` | Build Hugo site, sync to S3, invalidate CloudFront |
| `.github/workflows/terraform.yml` | PR or push to `main`, paths: `terraform/**` | Plan on PR (posts comment), apply on merge |

Plus a Dependabot config to keep action versions updated.

**Manual script (default for the AWS CLI / set-and-forget path):** Do **not** generate any GitHub Actions workflows. Instead, the user deploys with `infra/deploy.sh` (see `references/aws-cli-infra.md`), which builds Hugo and syncs to S3 + invalidates CloudFront from their machine. No GitHub secrets, no OIDC role.

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

**Note on `submodules: recursive`**: This is required to pull in the Hugo theme. Without it, the `themes/` directory will be empty and `hugo --minify` will fail.

**Note on Hugo version**: The version string in the workflow must match the user's local Hugo version to avoid build differences. Ask the user to run `hugo version` locally and use that exact version number.

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
