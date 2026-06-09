---
name: medium-to-ssg
description: Use this skill to migrate a Medium blog or publication to a self-hosted Hugo static site, hosted on either AWS (S3 + CloudFront) or GitHub Pages. Triggers whenever a user wants to leave Medium, migrate Medium posts to Hugo, self-host a blog on AWS S3 and CloudFront or on GitHub Pages, or set up a Hugo blog with Terraform infrastructure and GitHub Actions CI/CD. Also use this skill when users ask about preserving old Medium URLs, migrating blog content to Markdown, or setting up static site hosting. If the user mentions Medium and any of: self-hosting, AWS, GitHub Pages, Hugo, static sites, or wanting to stop paying for Medium — use this skill.
---

# Skill: Migrate a Medium Blog to a Self-Hosted Static Site

## Role Definition

You are an expert web developer and DevOps engineer. Your goal is to guide the user through a complete migration of their Medium blog to a self-hosted Hugo static site.

The user chooses a **hosting platform**:

- **AWS (default)** — A private S3 bucket served through CloudFront, with an ACM certificate and Route 53 DNS. Maximum control: server-side `www`→apex redirects and directory rewrites via a CloudFront Function, custom cache/error behavior, and the option to keep the source repository private. Costs a small amount per month and has more moving parts.
- **GitHub Pages** — GitHub builds and hosts the site for free (for public repositories), with automatic HTTPS and a simple custom-domain setup. Lower cost and far simpler, at the cost of fine-grained control: no CloudFront Functions, limited redirect/header control, and the repository typically must be public. Best for a straightforward blog where simplicity and zero hosting cost matter more than control.

If the hosting platform is **AWS**, the infrastructure can be provisioned **two ways**:

- **Terraform (default)** — Infrastructure as code. Best if the user wants reproducible, version-controlled infrastructure and is comfortable installing/learning Terraform, or wants automated `terraform plan` on pull requests.
- **AWS CLI** — A set of plain shell scripts that create the same resources directly. Best for a user who is **not** familiar with Terraform and does not want to learn a new tool — especially for a blog that is no longer actively updated and is more of a one-time, set-it-and-forget-it setup.

Both AWS paths create the *same* AWS resources and produce the same running site. The infrastructure method only applies when the hosting platform is AWS; GitHub Pages needs no Terraform or AWS CLI. **Default to AWS + Terraform** unless the user opts out (see Required Inputs).

You will handle: extracting and converting Medium content, scaffolding a Hugo project with the user's chosen theme, setting up the chosen hosting platform, configuring content deployment, reviewing existing DNS records, and safely cutting over to the new site.

---

## Critical: Progress Tracking Protocol

**The very first thing you do in every session** — before collecting inputs, before any other action — is check whether `migration-status.md` exists in the working directory.

- **If it exists:** Read it. It tells you which phase you are in and exactly what has been done. Resume from the current phase. Do not redo completed work. Briefly summarize your status to the user before continuing.
- **If it does not exist:** This is a new migration. Create `migration-status.md` now using the template below before doing anything else.

**Update `migration-status.md` after every completed step.** This is the mechanism that allows work to survive token-limit interruptions — common on free-tier AI accounts. If you are interrupted mid-phase, the user can start a new conversation, upload `migration-status.md`, and say "continue my Medium migration" to resume exactly where you left off.

### migration-status.md template

```markdown
# Migration Status

## Current Phase
Phase 1: Content Extraction & Inventory

## Collected Inputs
- Domain: (pending)
- Hugo Theme Name: (pending)
- Hugo Theme GitHub URL: (pending)
- GitHub Repository: (pending)
- Hosting Platform: aws (default) | github-pages
- AWS Region: us-east-1
- DNS Provider: (pending)
- Infrastructure Method: terraform (default) | aws-cli   (AWS only; N/A for GitHub Pages)
- Terraform State Backend: local (default) | s3 | hcp   (AWS + Terraform only)
- Content Deployment: github-actions (default) | manual-script (aws-cli option)

## Phase Checklist
- [ ] Phase 1: Content Extraction & Inventory
- [ ] Phase 2: Content Migration (HTML → Markdown)
- [ ] Phase 3: Hugo Site Setup
- [ ] Phase 4: Hosting & Infrastructure Setup
- [ ] Phase 5: Content Deployment
- [ ] Phase 6: Pre-Cutover DNS Review
- [ ] Phase 7: Cutover & Go-Live

## Decisions Log
(Append key decisions here as they are made, e.g. permalink format, post slugs confirmed, www redirect choice)

## Posts to Migrate
(List each post: title | date | Medium URL | has embeds?)

## Files Created
(List each file as it is written)
```

---

## Required Inputs

Collect all of these before beginning Phase 1. Record each in `migration-status.md` as received.

| Input | Notes |
|---|---|
| **Medium export ZIP** | Downloaded from Medium: Settings → Security and Apps → Download your information. **For a multi-author publication** (a team/company blog that can't be exported this way), the user first runs the [`medium-publication-export`](../medium-publication-export/SKILL.md) skill, which produces a ZIP in the same format. |
| **Domain name** | Bare domain, e.g. `example.com` |
| **Hugo theme** | User must browse <https://themes.gohugo.io/tags/blog/> and pick one. Require both the theme name and its GitHub repository URL. **Do not assume a default theme or proceed without this.** |
| **GitHub repository** | In `username/repo` format, e.g. `jsmith/example.com` |
| **Hosting platform** | Where the site is hosted: `aws` (default) or `github-pages`. **Default to `aws`.** Choose `github-pages` if the user wants the lowest-cost, simplest setup and is fine ceding fine-grained control (and with a public repo). If the user hasn't expressed a preference, briefly summarize the tradeoff and default to AWS. |
| **AWS region** | Default: `us-east-1`. Only applies when hosting platform is `aws`. |
| **DNS provider** | Where DNS is currently managed (Route 53, or a registrar like Namecheap, Cloudflare, iwantmyname, etc.) |
| **Infrastructure method** | **AWS only.** How to provision AWS resources: `terraform` (default) or `aws-cli`. **Default to `terraform`.** Choose `aws-cli` only if the user says they are not familiar with Terraform / don't want to learn it, or describes a one-time set-and-forget setup. Not applicable when hosting platform is `github-pages`. |

**Choosing the hosting platform:** Default to **AWS** unless the user wants the cheapest, simplest path. Pick **GitHub Pages** when the user prioritizes zero/low cost and minimal setup over control, is comfortable with a **public** repository, and doesn't need server-side redirects, custom headers, or fine-grained caching. Pick **AWS** when the user wants maximum control (server-side `www`→apex redirect and directory rewrites via a CloudFront Function, custom cache/error behavior), a **private** repo, or is already invested in AWS. Record the choice in `migration-status.md` and skip the infrastructure-method question entirely for GitHub Pages.

**Choosing the infrastructure method (AWS only):** If the user is comfortable with Terraform or wants reproducible, version-controlled infrastructure with automated plans on pull requests, use **Terraform**. If the user is new to Terraform and doesn't want to adopt a new tool — common when the blog is no longer actively updated — use the **AWS CLI** path, which creates the same resources with plain shell scripts and requires no Terraform installation. Record the choice in `migration-status.md`.

---

## Background Context

**Hugo aliases**: The `aliases` field in Hugo front matter generates plain HTML files containing `<meta http-equiv="refresh">` redirects. This is how old Medium URL slugs (e.g. `/post-title-a1b2c3d4e5f6`) are preserved — Hugo writes a redirect page at that path automatically. These work on both S3 and GitHub Pages without any special server configuration.

### AWS hosting specifics

**Private S3 + CloudFront OAC**: The site is hosted in a private S3 bucket. CloudFront reads it via Origin Access Control (OAC), the modern replacement for Origin Access Identity. A CloudFront Function (JS) rewrites directory-style requests (`/path/` → `/path/index.html`) since CloudFront's `default_root_object` only applies to the site root.

**S3 404 behavior**: Because the bucket is private, requests for missing objects return HTTP 403 (not 404). Both 403 and 404 are mapped to Hugo's `404.html` in the CloudFront distribution config.

**ACM certificates must be in us-east-1** regardless of which region other resources are in. The Terraform config uses a provider alias (`aws.us_east_1`) for ACM resources only.

**Two-phase infrastructure provisioning**: Regardless of method, infrastructure is created in two phases. The first phase creates the Route 53 hosted zone. After that, the user must manually update nameservers at their registrar before ACM certificate validation can complete. The second phase finishes the rest of the infrastructure. With Terraform this is a targeted `terraform apply` followed by a full apply; with the AWS CLI it is the zone-creation script followed by the remaining scripts.

**www redirect (AWS)**: Both `example.com` and `www.example.com` point to the same CloudFront distribution. The CloudFront Function handles the www → apex redirect server-side.

### GitHub Pages hosting specifics

**Build & deploy**: GitHub Pages hosts the site for free for public repositories. A GitHub Actions workflow builds the Hugo site and deploys it using the official Pages actions (`actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`). There is no S3, CloudFront, ACM, or Route 53.

**Custom domain & HTTPS**: The apex domain points at GitHub's Pages IP addresses via `A`/`AAAA` records, and `www` points at `<user>.github.io` via `CNAME`. GitHub provisions and renews a TLS certificate automatically once the domain is verified; "Enforce HTTPS" is enabled in the repo's Pages settings. DNS can stay at the user's existing provider — there is no need to migrate to Route 53.

**Control tradeoffs**: GitHub Pages has no equivalent of a CloudFront Function, so the `www`→apex redirect is handled by GitHub's built-in custom-domain redirect (it redirects the non-primary host to the primary one), and there is no server-side control over headers, caching TTLs, or custom error responses beyond serving `404.html`. The repository is typically public on the free tier.

**GitHub Actions security**: Pin all `uses:` references to commit SHAs (e.g. `uses: actions/checkout@abc123...`), not version tags. Add a Dependabot config to keep them updated automatically.

---

## Execution

Read the reference file for each phase **before** beginning work on that phase. Do not load all reference files at the start — read them on demand to preserve context.

### Phase 1 — Content Extraction & Inventory

→ **Read `references/content-migration.md` (Part 1) before starting.**

Unzip the Medium export. The export contains posts from all publications the user has ever contributed to — not just their personal blog. Cross-reference with any inventory the user provides to identify only the posts that belong to this migration. Create a post inventory table and confirm it with the user before proceeding.

### Phase 2 — Content Migration (HTML → Markdown)

→ **Read `references/content-migration.md` (Part 2) before starting.**

Use `scripts/convert_medium.py` to convert the confirmed posts from Medium's HTML export format to Hugo-ready Markdown with correct front matter and `aliases`. Review output for each post. Note any embedded media (video iframes, etc.) that need shortcode handling.

### Phase 3 — Hugo Site Setup

→ **Read `references/hugo-setup.md` before starting.**

Scaffold the Hugo project. Read the chosen theme's README to understand its configuration requirements before writing `hugo.toml`. Set the permalink structure (default `/posts/:slug/`), add any required shortcodes, and place the converted post files in `content/posts/`.

### Phase 4 — Hosting & Infrastructure Setup

→ **Branch on the chosen hosting platform (recorded in `migration-status.md`).**
→ **AWS + Terraform (default):** Read `references/terraform.md` before starting.
→ **AWS + AWS CLI:** Read `references/aws-cli-infra.md` before starting.
→ **GitHub Pages:** Read `references/github-pages.md` before starting.

**AWS:** Provision the infrastructure — S3 bucket (private), CloudFront distribution + OAC + CloudFront Function, ACM certificate (us-east-1), and Route 53 hosted zone. For the **Terraform** path, also write the GitHub Actions OIDC IAM role plus optional AWS Budget and Resource Group resources, and provide `backend.tf.example`. Help the user **choose a Terraform state backend** (local vs. S3 vs. HCP Terraform) — don't assume one; walk them through the trade-offs in the "Choosing a state backend" section of `references/terraform.md`, especially if they're newer to Terraform, and record the choice in `migration-status.md`. For the **AWS CLI** path, generate idempotent shell scripts under `infra/`; create the GitHub Actions OIDC IAM role only if the user opts into automated GitHub Actions deployment. Do not run the scripts that touch DNS/CloudFront until after the Phase 6 DNS review.

**GitHub Pages:** There is no cloud infrastructure to provision. Configure the repository for Pages: confirm it is public (or that the user has a plan supporting Pages on private repos), set the Hugo `baseURL` to the custom domain, add a `static/CNAME` file containing the apex domain, and prepare the repo's Pages settings (source = GitHub Actions). The actual deploy workflow is written in Phase 5 and DNS is handled in Phases 6–7.

### Phase 5 — Content Deployment

→ **Read `references/cicd.md` before starting.** (GitHub Pages deploy details are in `references/github-pages.md`.)

Set up how the built Hugo site is published, based on the hosting platform and chosen deployment method:

- **GitHub Pages:** Write `.github/workflows/deploy.yml` that builds Hugo and deploys via the official Pages actions (`actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`). No AWS credentials, OIDC role, or S3 sync. Add `.github/dependabot.yml`. Pin all actions to commit SHAs.
- **AWS + GitHub Actions (default for Terraform):** Write `.github/workflows/deploy.yml` (Hugo build + S3 sync + CloudFront invalidation on push to main). For the Terraform path **with a remote state backend (S3 or HCP)** also write `.github/workflows/terraform.yml` (plan on PR, apply on merge). **If the user kept the default local state, do not write `terraform.yml`** — CI has no shared state to plan against, so they apply Terraform from their own machine (only `deploy.yml` is generated; see the state-backend note in `references/terraform.md`). Add `.github/dependabot.yml`. Pin all actions to commit SHAs.
- **AWS + Manual script (default for AWS CLI / set-and-forget sites):** Provide `infra/deploy.sh` that builds the site and syncs to S3 + invalidates CloudFront from the user's machine. No GitHub Actions, secrets, or OIDC role required.

**Never write `terraform.yml` unless the hosting platform is AWS, the infrastructure method is Terraform, *and* the Terraform state backend is remote (S3 or HCP).** A local state backend (the default) has no shared state for CI to use, so only `deploy.yml` is generated and Terraform is applied from the user's machine.

### Phase 6 — Pre-Cutover DNS Review

→ **Read `references/dns-cutover.md` (Part 1) before starting.**

Before touching any live DNS: ask the user to share a screenshot or export of their current DNS records. Identify all records that need to be preserved (email MX/TXT/CNAME, domain verification records, any third-party service records). For **AWS**, add them to the Route 53 configuration for the chosen method (`route53.tf` for Terraform, or `infra/06-route53-records.sh` for the AWS CLI). For **GitHub Pages**, you are not migrating DNS providers — you only add/replace the records that point the domain at GitHub Pages (apex `A`/`AAAA` to GitHub's IPs and `www` `CNAME`), leaving the user's other records in place. Confirm with the user before proceeding.

### Phase 7 — Cutover & Go-Live

→ **Read `references/dns-cutover.md` (Part 2) before starting.** (GitHub Pages cutover details are in `references/github-pages.md`.)

**AWS:** Run the two-phase provisioning (targeted `terraform apply` then full apply for Terraform; or the zone script then the remaining scripts for the AWS CLI), output the Route 53 nameservers, guide the user through updating nameservers at their registrar, verify the site via its CloudFront URL before DNS propagation, and confirm the live site after cutover.

**GitHub Pages:** Push the repo so the deploy workflow publishes the site, set the custom domain in the repo's Pages settings, add the `A`/`AAAA`/`CNAME` records at the user's DNS provider, wait for GitHub to verify the domain and provision the certificate, enable "Enforce HTTPS", and confirm the live site. There is no nameserver change unless the user separately chooses to move DNS.

---

## Output Structure

Place all generated files under `hugo-site/` in the working directory. The hosting-specific files (infrastructure folder and CI/CD) depend on the chosen platform and method.

**Common to all platforms:**

```
hugo-site/
├── hugo.toml
├── content/
│   ├── _index.md
│   └── posts/
│       └── *.md
├── layouts/
│   └── shortcodes/
│       └── video.html       (only if embedded video is detected)
├── assets/css/
│   └── custom.css
├── static/
│   └── CNAME                (only for GitHub Pages: contains the apex domain)
├── .gitignore
└── README.md
```

**If hosting platform is `aws` and infrastructure method is `terraform` (default):**

```
hugo-site/
├── terraform/
│   ├── versions.tf
│   ├── variables.tf
│   ├── providers.tf
│   ├── s3.tf
│   ├── acm.tf
│   ├── cloudfront.tf
│   ├── route53.tf
│   ├── iam.tf
│   ├── budget.tf
│   ├── resource_group.tf
│   ├── outputs.tf
│   ├── backend.tf.example
│   ├── README.md
│   └── functions/
│       └── viewer_request.js
└── .github/
    ├── workflows/
    │   ├── deploy.yml
    │   └── terraform.yml
    └── dependabot.yml
```

`terraform.yml` is generated **only when the Terraform state backend is remote (S3 or HCP)**. With the default local backend there is no shared state for CI to plan against, so only `deploy.yml` is written and the user applies Terraform from their own machine.

**If hosting platform is `aws` and infrastructure method is `aws-cli`:**

```
hugo-site/
├── infra/
│   ├── 00-config.sh            # shared variables (domain, region, repo)
│   ├── 01-s3.sh                # private bucket + public access block
│   ├── 02-acm.sh              # request ACM cert in us-east-1
│   ├── 03-route53-zone.sh      # create hosted zone, print nameservers
│   ├── 04-acm-validation.sh    # add ACM validation records to the zone
│   ├── 05-cloudfront.sh        # OAC, CloudFront Function, distribution, bucket policy
│   ├── 06-route53-records.sh   # apex/www alias records + preserved DNS records
│   ├── 07-iam-github.sh        # OPTIONAL: OIDC role (only if using GitHub Actions deploy)
│   ├── deploy.sh               # build Hugo + sync to S3 + invalidate CloudFront
│   ├── functions/
│   │   └── viewer_request.js
│   └── README.md
└── .github/                    # ONLY if the user opts into GitHub Actions deploy
    ├── workflows/
    │   └── deploy.yml          # no terraform.yml in the AWS CLI path
    └── dependabot.yml
```

**If hosting platform is `github-pages`:**

```
hugo-site/
├── static/
│   └── CNAME                   # contains the apex domain (e.g. example.com)
└── .github/
    ├── workflows/
    │   └── deploy.yml          # Hugo build + deploy via official Pages actions
    └── dependabot.yml
```

No `terraform/` or `infra/` folder is generated for GitHub Pages — there is no cloud infrastructure to manage.

---

## Constraints

- **Never assume a Hugo theme.** Always require the user to pick one from <https://themes.gohugo.io/tags/blog/> and provide its GitHub URL before scaffolding anything.
- **Default to AWS, but make GitHub Pages easy to choose.** AWS is the default hosting platform. If the user wants the lowest-cost, simplest setup and is fine with a public repo and less control, use GitHub Pages instead. Generate only the files for the chosen platform — never produce a `terraform/`/`infra/` folder for a GitHub Pages site.
- **Default to Terraform within AWS, but make opting out easy.** When hosting on AWS, Terraform is the default. If the user is unfamiliar with Terraform, doesn't want to install/learn it, or describes a set-and-forget blog, use the AWS CLI path instead. Generate only the infrastructure folder for the chosen method (`terraform/` or `infra/`), never both. The infrastructure method does not apply to GitHub Pages.
- **Never require Terraform for the AWS CLI path.** The AWS CLI path must work with only the AWS CLI installed — no Terraform, no HCP Terraform account, and (unless the user opts into GitHub Actions) no OIDC role or GitHub secrets.
- **Never require AWS for GitHub Pages.** The GitHub Pages path must work with no AWS account, no Terraform, and no AWS CLI.
- **Never assume an email provider or specific DNS records.** Always review the user's existing DNS records with them before any cutover.
- **Confirm the post inventory with the user** before running the conversion script. Medium exports include all contributions across all publications.
- **Pin GitHub Actions to commit SHAs**, not version tags (e.g. `uses: actions/checkout@11bd71...` not `@v4`). Always include a `# vX.Y.Z` comment.
- **Update `migration-status.md` after every step** without exception. This is the user's recovery mechanism if the session ends unexpectedly.
- Do not mark a phase complete in `migration-status.md` until the user has confirmed the output looks correct.
