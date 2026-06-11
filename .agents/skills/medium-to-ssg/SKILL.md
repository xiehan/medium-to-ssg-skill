---
name: medium-to-ssg
description: Use this skill to migrate a Medium blog or publication to a self-hosted static site built with Hugo (default), Eleventy, or Astro, hosted on either AWS (S3 + CloudFront) or GitHub Pages. Triggers whenever a user wants to leave Medium, migrate Medium posts to Hugo, Eleventy, or Astro, self-host a blog on AWS S3 and CloudFront or on GitHub Pages, or set up a Hugo, Eleventy, or Astro blog with Terraform infrastructure and GitHub Actions CI/CD. Also use this skill when users ask about preserving old Medium URLs, migrating blog content to Markdown, or setting up static site hosting. If the user mentions Medium and any of: self-hosting, AWS, GitHub Pages, Hugo, Eleventy, 11ty, Astro, static sites, or wanting to stop paying for Medium — use this skill.
---

# Skill: Migrate a Medium Blog to a Self-Hosted Static Site

## Role Definition

You are an expert web developer and DevOps engineer. Your goal is to guide the user through a complete migration of their Medium blog to a self-hosted static site.

The user chooses a **static site generator (SSG)**:

- **Hugo (default)** — A single fast Go binary, configured with `hugo.toml` and a theme from <https://themes.gohugo.io>. Best for most users: no Node toolchain, a large theme gallery, and built-in URL-alias support. Builds with `hugo --minify` to `public/`.
- **Eleventy (11ty)** — A Node.js generator scaffolded from a starter repository (this skill standardizes on the official `eleventy-base-blog`). Best for users who prefer a JavaScript/Node ecosystem and hand-owned templates over a packaged theme. Builds with `npx @11ty/eleventy` to `_site/`. It has no central theme gallery, and old-URL preservation is wired up explicitly with a small redirects template rather than built in.
- **Astro** — A Node.js generator scaffolded from a starter template (this skill standardizes on the official free `blog` example). Best for users who want a modern component-based JavaScript toolchain with hand-owned templates. Builds with `npm run build` to `dist/`. Like Eleventy it has no installable theme system (its showcase is mostly paid templates); it additionally type-checks every post against a schema (a missing required field fails the build, so the skill relaxes the starter's schema), and old-URL preservation is wired up explicitly with a small redirect route rather than built in.

**Default to Hugo** unless the user asks for Eleventy or Astro. The SSG choice affects content conversion (Phase 2), site scaffolding (Phase 3), and the build command + output directory that every hosting path consumes (Phases 4–5). It is **independent** of the hosting, infrastructure, and DNS choices below — any SSG works with any hosting platform.

The user chooses a **hosting platform**:

- **AWS (default)** — A private S3 bucket served through CloudFront, with an ACM certificate and Route 53 DNS. Maximum control: server-side `www`→apex redirects and directory rewrites via a CloudFront Function, custom cache/error behavior, and the option to keep the source repository private. Costs a small amount per month and has more moving parts.
- **GitHub Pages** — GitHub builds and hosts the site for free (for public repositories), with automatic HTTPS and a simple custom-domain setup. Lower cost and far simpler, at the cost of fine-grained control: no CloudFront Functions, limited redirect/header control, and the repository typically must be public. Best for a straightforward blog where simplicity and zero hosting cost matter more than control.

If the hosting platform is **AWS**, the infrastructure can be provisioned **two ways**:

- **Terraform (default)** — Infrastructure as code. Best if the user wants reproducible, version-controlled infrastructure and is comfortable installing/learning Terraform, or wants automated `terraform plan` on pull requests.
- **AWS CLI** — A set of plain shell scripts that create the same resources directly. Best for a user who is **not** familiar with Terraform and does not want to learn a new tool — especially for a blog that is no longer actively updated and is more of a one-time, set-it-and-forget-it setup.

Both AWS paths create the *same* AWS resources and produce the same running site. The infrastructure method only applies when the hosting platform is AWS; GitHub Pages needs no Terraform or AWS CLI. **Default to AWS + Terraform** unless the user opts out (see Required Inputs).

You will handle: extracting and converting Medium content, scaffolding the chosen SSG project (a Hugo theme, or an Eleventy or Astro starter), setting up the chosen hosting platform, configuring content deployment, reviewing existing DNS records, and safely cutting over to the new site.

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
- SSG: hugo (default) | eleventy | astro
- Theme / Starter Name: (pending)            # Hugo theme name, or Eleventy/Astro starter (defaults: eleventy-base-blog / Astro blog example)
- Theme / Starter GitHub URL: (pending)
- Build Command: hugo --minify (hugo) | npx @11ty/eleventy (eleventy) | npm run build (astro)
- Build Output Directory: public/ (hugo) | _site/ (eleventy) | dist/ (astro)
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
- [ ] Phase 3: Site Setup
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
| **Static site generator** | Which SSG builds the site: `hugo` (default), `eleventy`, or `astro`. **Default to `hugo`.** Choose `eleventy` or `astro` only if the user prefers a Node.js/JavaScript workflow with a hand-owned starter over Hugo's packaged themes (`astro` for a modern component-based toolchain). Record it in `migration-status.md`; it sets the build command (`hugo --minify` vs `npx @11ty/eleventy` vs `npm run build`) and output directory (`public/` vs `_site/` vs `dist/`) used by later phases. |
| **Theme (Hugo) or starter (Eleventy/Astro)** | **Hugo:** the user must browse <https://themes.gohugo.io/tags/blog/> and pick one — require both the theme name and its GitHub repository URL, and **do not assume a default theme or proceed without this.** **Eleventy:** this skill defaults to the official [`eleventy-base-blog`](https://github.com/11ty/eleventy-base-blog) starter; the user may name a different starter repo instead. **Astro:** this skill defaults to the official free [`blog` example](https://github.com/withastro/astro/tree/latest/examples/blog) (`npm create astro@latest -- --template blog`); the user may name a different starter, but note Astro's showcase is largely paid themes — confirm licensing before cloning one. |
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

**Eleventy aliases**: Eleventy has no built-in alias feature, so the same `aliases` front-matter field is preserved by a small **redirects collection + template** the skill adds (see `references/eleventy-setup.md`). It generates the identical `<meta http-equiv="refresh">` stub at each old path, using only core, long-stable Eleventy APIs (no third-party plugin). The end result is byte-for-byte equivalent to a Hugo alias and works the same on S3 and GitHub Pages.

**Astro aliases**: Astro is the same story as Eleventy. The `aliases` field (added to the content-collection schema) is preserved by a small **catch-all redirect route** the skill adds (see `references/astro-setup.md`). Using only core, long-stable Astro APIs (`getCollection` + `getStaticPaths`, no third-party plugin), it emits the identical `<meta http-equiv="refresh">` stub at each old path. (Astro ships a built-in `redirects` config, but it expects a static map at config-load time, not per-post front matter, so the skill uses the route instead.) The end result is byte-for-byte equivalent to a Hugo alias and works the same on S3 and GitHub Pages.

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

Use `scripts/convert_medium.py` to convert the confirmed posts from Medium's HTML export format to SSG-ready Markdown with correct front matter and `aliases`. **Set the script's `SSG` to match the chosen generator** (`hugo` default, `eleventy`, or `astro`) — and, for Eleventy or Astro, point `OUTPUT_DIR`/`STATIC_DIR` at `eleventy-site/` or `astro-site/`. Review output for each post. Note any embedded media (video iframes, etc.) that need shortcode handling.

### Phase 3 — Site Setup

→ **Branch on the chosen SSG (recorded in `migration-status.md`).**
→ **Hugo (default):** Read `references/hugo-setup.md` before starting.
→ **Eleventy:** Read `references/eleventy-setup.md` before starting.
→ **Astro:** Read `references/astro-setup.md` before starting.

Scaffold the chosen SSG project. **Hugo:** read the chosen theme's README to understand its configuration requirements before writing `hugo.toml`, set the permalink structure (default `/posts/:slug/`), add any required shortcodes, and place the converted post files in `content/posts/`. **Eleventy:** clone the starter into `eleventy-site/`, configure it, wire up the redirects template that preserves old Medium URLs, and place the converted posts in the starter's posts directory (`content/blog/`). **Astro:** scaffold the `blog` starter into `astro-site/`, relax its content-collection schema so posts without a description build, wire up the catch-all redirect route that preserves old Medium URLs, and place the converted posts in the collection directory (`src/content/blog/`). Either way the canonical post URLs default to `/posts/<slug>/` and old Medium URLs are preserved as redirect stubs. Record the build command and output directory in `migration-status.md` — later phases read those two values.

### Phase 4 — Hosting & Infrastructure Setup

→ **Branch on the chosen hosting platform (recorded in `migration-status.md`).**
→ **AWS + Terraform (default):** Read `references/terraform.md` before starting.
→ **AWS + AWS CLI:** Read `references/aws-cli-infra.md` before starting.
→ **GitHub Pages:** Read `references/github-pages.md` before starting.

**AWS:** Provision the infrastructure — S3 bucket (private), CloudFront distribution + OAC + CloudFront Function, ACM certificate (us-east-1), and Route 53 hosted zone. For the **Terraform** path, also write the GitHub Actions OIDC IAM role plus optional AWS Budget and Resource Group resources, and provide `backend.tf.example`. Help the user **choose a Terraform state backend** (local vs. S3 vs. HCP Terraform) — don't assume one; walk them through the trade-offs in the "Choosing a state backend" section of `references/terraform.md`, especially if they're newer to Terraform, and record the choice in `migration-status.md`. For the **AWS CLI** path, generate idempotent shell scripts under `infra/`; create the GitHub Actions OIDC IAM role only if the user opts into automated GitHub Actions deployment. Do not run the scripts that touch DNS/CloudFront until after the Phase 6 DNS review.

**GitHub Pages:** There is no cloud infrastructure to provision. Configure the repository for Pages: confirm it is public (or that the user has a plan supporting Pages on private repos), set the site's base/canonical URL to the custom domain (Hugo `baseURL` in `hugo.toml`; Eleventy `metadata.url` in `_data/metadata.js`; Astro `site` in `astro.config.mjs`), add a `CNAME` file containing the apex domain to the SSG's passthrough root (`hugo-site/static/CNAME` for Hugo, `eleventy-site/public/CNAME` for Eleventy, `astro-site/public/CNAME` for Astro), and prepare the repo's Pages settings (source = GitHub Actions). The actual deploy workflow is written in Phase 5 and DNS is handled in Phases 6–7.

### Phase 5 — Content Deployment

→ **Read `references/cicd.md` before starting.** (GitHub Pages deploy details are in `references/github-pages.md`.)

Set up how the built site is published, based on the hosting platform and chosen deployment method. **Every workflow/script below builds with the SSG's build command and deploys its output directory** (recorded in `migration-status.md`): `hugo --minify` → `public/` for Hugo, `npx @11ty/eleventy` → `_site/` for Eleventy, `npm run build` → `dist/` for Astro. The reference files show the Hugo commands inline with the Eleventy/Astro variants alongside.

- **GitHub Pages:** Write `.github/workflows/deploy.yml` that builds the site and deploys via the official Pages actions (`actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`). No AWS credentials, OIDC role, or S3 sync. Add `.github/dependabot.yml`. Pin all actions to commit SHAs.
- **AWS + GitHub Actions (default for Terraform):** Write `.github/workflows/deploy.yml` (site build + S3 sync + CloudFront invalidation on push to main). For the Terraform path **with a remote state backend (S3 or HCP)** also write `.github/workflows/terraform.yml` (plan on PR, apply on merge). **If the user kept the default local state, do not write `terraform.yml`** — CI has no shared state to plan against, so they apply Terraform from their own machine (only `deploy.yml` is generated; see the state-backend note in `references/terraform.md`). Add `.github/dependabot.yml`. Pin all actions to commit SHAs.
- **AWS + Manual script (default for AWS CLI / set-and-forget sites):** Provide `infra/deploy.sh` that builds the site and syncs to S3 + invalidates CloudFront from the user's machine. No GitHub Actions, secrets, or OIDC role required.

**Eleventy or Astro: always add an `npm` Dependabot entry.** When the SSG is Eleventy or Astro, `.github/dependabot.yml` gets a second `package-ecosystem: npm` entry (`directory: /`) to keep the starter's JavaScript dependencies patched — on **every** hosting platform and deployment method (see `references/cicd.md`). On the manual AWS CLI path that has no workflows, still create `.github/dependabot.yml` with just the `npm` entry.

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

Place all generated files under the SSG project directory in the working directory: **`hugo-site/` for Hugo**, **`eleventy-site/` for Eleventy**, or **`astro-site/` for Astro**. The hosting-specific files (infrastructure folder and CI/CD) depend on the chosen platform and method, and attach under whichever project directory was created — they are identical either way.

**Hugo project (common to all platforms):**

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

**Eleventy project (common to all platforms):** scaffolded by cloning the `eleventy-base-blog` starter into `eleventy-site/`, then adding/modifying the files marked below. The starter brings its own `_includes/`, `css/`, `_data/`, etc.; only the migration-specific pieces are listed here.

```
eleventy-site/
├── eleventy.config.js       (modified: add the `video` shortcode + `redirects` collection)
├── _data/
│   └── metadata.js          (modified: site title, url, description, author)
├── content/
│   ├── blog/
│   │   └── *.md             (converted posts; OUTPUT_DIR target)
│   └── redirects.njk        (added: emits the Medium-URL redirect stubs)
├── public/
│   ├── images/              (added: self-hosted post images; STATIC_DIR target)
│   └── CNAME                (only for GitHub Pages: contains the apex domain)
├── package.json             (from starter)
├── .gitignore
└── README.md
```

**Astro project (common to all platforms):** scaffolded from the official `blog` example (`npm create astro@latest -- --template blog`) into `astro-site/`, then adding/modifying the files marked below. The starter brings its own `src/components/`, `src/layouts/`, `src/styles/`, etc.; only the migration-specific pieces are listed here.

```
astro-site/
├── astro.config.mjs         (modified: set `site` to the custom domain)
├── src/
│   ├── content.config.ts    (modified: relax schema — optional description/heroImage, add `aliases`)
│   ├── consts.ts            (modified: site title + description)
│   ├── content/
│   │   └── blog/
│   │       └── *.md         (converted posts; OUTPUT_DIR target)
│   └── pages/
│       ├── posts/
│       │   └── [...slug].astro   (moved from blog/; serves posts at /posts/<slug>/)
│       └── [...alias].astro      (added: emits the Medium-URL redirect stubs)
├── public/
│   ├── images/              (added: self-hosted post images; STATIC_DIR target)
│   └── CNAME                (only for GitHub Pages: contains the apex domain)
├── package.json             (from starter)
├── .gitignore
└── README.md
```

```
<site>/                      # hugo-site/, eleventy-site/, or astro-site/
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
<site>/                         # hugo-site/, eleventy-site/, or astro-site/
├── infra/
│   ├── 00-config.sh            # shared variables (domain, region, repo)
│   ├── 01-s3.sh                # private bucket + public access block
│   ├── 02-acm.sh               # request ACM cert in us-east-1
│   ├── 03-route53-zone.sh      # create hosted zone, print nameservers
│   ├── 04-acm-validation.sh    # add ACM validation records to the zone
│   ├── 05-cloudfront.sh        # OAC, CloudFront Function, distribution, bucket policy
│   ├── 06-route53-records.sh   # apex/www alias records + preserved DNS records
│   ├── 07-iam-github.sh        # OPTIONAL: OIDC role (only if using GitHub Actions deploy)
│   ├── deploy.sh               # build site + sync to S3 + invalidate CloudFront
│   ├── functions/
│   │   └── viewer_request.js
│   └── README.md
└── .github/                    # ONLY if the user opts into GitHub Actions deploy
    ├── workflows/
    │   └── deploy.yml          # no terraform.yml in the AWS CLI path
    └── dependabot.yml
```

For an **Eleventy** or **Astro** site, create `.github/dependabot.yml` with a `package-ecosystem: npm` entry even on this manual path (no workflows) so JavaScript dependencies stay patched — see Phase 5 and `references/cicd.md`.

**If hosting platform is `github-pages`:**

```
<site>/                         # hugo-site/ or eleventy-site/
├── static/                     # Hugo; for Eleventy the CNAME goes in public/ instead
│   └── CNAME                   # contains the apex domain (e.g. example.com)
└── .github/
    ├── workflows/
    │   └── deploy.yml          # site build + deploy via official Pages actions
    └── dependabot.yml
```

No `terraform/` or `infra/` folder is generated for GitHub Pages — there is no cloud infrastructure to manage.

---

## Constraints

- **Default to Hugo, but support Eleventy or Astro when asked.** Hugo is the default SSG. Switch to Eleventy or Astro only when the user prefers a Node.js/JavaScript workflow with a hand-owned starter (Astro for a modern component-based toolchain). Generate only the project for the chosen SSG (`hugo-site/`, `eleventy-site/`, or `astro-site/`), never more than one, and use the matching build command (`hugo --minify` / `npx @11ty/eleventy` / `npm run build`) and output directory (`public/` / `_site/` / `dist/`) in every deployment file.
- **Never assume a Hugo theme.** On the Hugo path, always require the user to pick a theme from <https://themes.gohugo.io/tags/blog/> and provide its GitHub URL before scaffolding anything. On the Eleventy path, default to the `eleventy-base-blog` starter; on the Astro path, default to the official `blog` example (the user may name a different starter on either), since neither has a Hugo-style theme gallery.
- **Preserve old Medium URLs on every path.** Hugo's `aliases` does this automatically; on Eleventy you must add the redirects collection + template (`references/eleventy-setup.md`) and on Astro the catch-all redirect route (`references/astro-setup.md`), then verify a stub actually builds. Never ship an Eleventy or Astro site without the redirects wired up.
- **Default to AWS, but make GitHub Pages easy to choose.** AWS is the default hosting platform. If the user wants the lowest-cost, simplest setup and is fine with a public repo and less control, use GitHub Pages instead. Generate only the files for the chosen platform — never produce a `terraform/`/`infra/` folder for a GitHub Pages site.
- **Default to Terraform within AWS, but make opting out easy.** When hosting on AWS, Terraform is the default. If the user is unfamiliar with Terraform, doesn't want to install/learn it, or describes a set-and-forget blog, use the AWS CLI path instead. Generate only the infrastructure folder for the chosen method (`terraform/` or `infra/`), never both. The infrastructure method does not apply to GitHub Pages.
- **Never require Terraform for the AWS CLI path.** The AWS CLI path must work with only the AWS CLI installed — no Terraform, no HCP Terraform account, and (unless the user opts into GitHub Actions) no OIDC role or GitHub secrets.
- **Never require AWS for GitHub Pages.** The GitHub Pages path must work with no AWS account, no Terraform, and no AWS CLI.
- **Never assume an email provider or specific DNS records.** Always review the user's existing DNS records with them before any cutover.
- **Confirm the post inventory with the user** before running the conversion script. Medium exports include all contributions across all publications.
- **Pin GitHub Actions to commit SHAs**, not version tags (e.g. `uses: actions/checkout@11bd71...` not `@v4`). Always include a `# vX.Y.Z` comment.
- **Update `migration-status.md` after every step** without exception. This is the user's recovery mechanism if the session ends unexpectedly.
- Do not mark a phase complete in `migration-status.md` until the user has confirmed the output looks correct.
