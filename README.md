# Medium → Self-Hosted Static Site (Agent Skill)

This repository contains an **agent skill** that walks an AI coding assistant (like GitHub Copilot in VS Code, Claude, or any agent that supports skills) through migrating your **Medium blog** to a **self-hosted static site**.

You choose your **static site generator (SSG)**:

- **[Hugo](https://gohugo.io) (default)** — a single fast Go binary with a huge theme gallery and built-in URL-alias support. No Node toolchain. Best for most users.
- **[Eleventy (11ty)](https://www.11ty.dev)** — a Node.js generator scaffolded from the official `eleventy-base-blog` starter. Best if you prefer a JavaScript/Node ecosystem and hand-owned templates over a packaged theme.

Both produce the same posts, the same preserved Medium URLs, and work with either hosting option below. **If you're unsure, pick Hugo** — it's the default and my personal favorite. See [Choosing your static site generator](#choosing-your-static-site-generator).

You choose **where to host** the site:

- **AWS (default)** — S3 + CloudFront. Maximum control; small monthly cost.
- **GitHub Pages** — free hosting (public repos), automatic HTTPS, far simpler setup, at the cost of less control. Great for a low-maintenance personal blog.

If you host on **AWS**, you also choose how the infrastructure is created:

- **Terraform (default)** — infrastructure as code, plus optional GitHub Actions CI/CD.
- **AWS CLI** — plain shell scripts that create the same resources. **No Terraform to install or learn.** Ideal if you're new to Terraform or your blog is a one-time, set-it-and-forget-it project.

Not sure which to pick? See [Choosing where to host your site](#choosing-where-to-host-your-site) — it walks you through the tradeoffs.

You don't run a single big script. Instead, you **talk to an AI agent**, and the skill gives that agent a detailed, phase-by-phase playbook so it produces consistent, correct output and never skips a step.

---

## Two scenarios: personal blog vs. publication

How you get your content out of Medium depends on who wrote it.

- **Personal blog (one author).** Use Medium's built-in export (**Settings → Security and apps → Download your information**) to get a ZIP of your posts, then go straight to the **`medium-to-ssg`** skill below.
- **Multi-author publication.** A team or company blog — like an engineering blog where many current and former employees published from their own personal accounts — can't be exported that way. Medium's export is per-account, and there's no "export this publication" button. For this case there's a companion skill, **[`medium-publication-export`](.agents/skills/medium-publication-export/SKILL.md)**, that collects every post in the publication and rebuilds the **same ZIP format** Medium's personal export produces. You run it first, then hand its ZIP to `medium-to-ssg` exactly like a personal-export user would.

In other words:

```
personal blog:      Medium "Download your information"  ─┐
                                                         ├─►  medium-to-ssg  ─►  Hugo or Eleventy site
multi-author pub:   medium-publication-export  ─►  ZIP  ─┘
```

The rest of this README is about the `medium-to-ssg` skill. The publication-export skill has its own [SKILL.md](.agents/skills/medium-publication-export/SKILL.md) and reference docs.

### A note on tags

There's one catch worth knowing about if your posts have **tags** (Medium's topic labels). Medium's built-in **"Download your information"** export **does not include tags** — they're simply absent from the exported HTML, so a personal-export migration can't preserve them. The **[`medium-publication-export`](.agents/skills/medium-publication-export/SKILL.md)** skill, on the other hand, reads each post from its live page, where the tags *are* present, and carries them through to your generated front matter (`tags:`).

This means tags are a reason to choose `medium-publication-export` **even for a single-author/personal blog**. It works just as well for one author as for a whole publication — point it at your own posts instead of a company blog. So if you have a personal blog **and** you care about keeping your tags, run `medium-publication-export` first to build the ZIP (it grabs the tags), then hand that ZIP to `medium-to-ssg`. If you don't care about tags, Medium's built-in export is the simpler path. Either way, the publication-export skill lets you **review your tags and drop ones you don't want** before migrating (for example, a publication-wide tag that's redundant on a self-hosted site, or a tag used on only one post) — see its [SKILL.md](.agents/skills/medium-publication-export/SKILL.md).

---

## What is an "agent skill"?

If you're new to skills, here's the short version:

- A **skill** is a folder of instructions (Markdown) plus helper files (scripts, reference docs) that teaches an AI agent how to do a specialized task really well.
- The agent **automatically loads the skill** when your request matches what the skill is for. You don't call it like a command — you just describe what you want in plain English.
- The main file the agent reads is [`.agents/skills/medium-to-ssg/SKILL.md`](.agents/skills/medium-to-ssg/SKILL.md). It tells the agent its role, the inputs to collect, and the 7 phases to follow.

You interact with the skill simply by **chatting with your agent** in a workspace where this skill is available.

---

## What you'll end up with

After completing the migration, you'll have:

- A **Hugo or Eleventy site** with all your Medium posts converted to Markdown.
- **Preserved old Medium URLs** — visitors clicking old links still land on the right post (via Hugo `aliases`, or an equivalent redirects template on Eleventy, that generate redirect pages).
- **Hosting on your terms** — either **AWS** (a private S3 bucket served through CloudFront with HTTPS via ACM) or **GitHub Pages** (free, GitHub-managed hosting with automatic HTTPS).
- **Infrastructure created your way** (AWS only) — either reproducible **Terraform** code, or a set of plain **AWS CLI** shell scripts if you'd rather not use Terraform.
- **Content deployment** — **GitHub Actions** that rebuild and deploy on every push, or (on the AWS CLI path) a simple **`deploy.sh` script** you run by hand when you update the blog.
- A custom domain pointed at your new site, with your existing email/DNS records preserved.

All generated files land in a `hugo-site/` (Hugo) or `eleventy-site/` (Eleventy) folder in your working directory.

---

## Before you start: prerequisites

You'll need the following ready. The agent will ask you for them, so it helps to gather them up front.

| What you need | Where to get it / notes |
|---|---|
| **Your Medium export** | In Medium: **Settings → Security and apps → Download your information**. You'll get a ZIP. Extract it somewhere in your project. **Multi-author publication?** That export only covers your own account, so it can't export a whole team/company publication. Use the companion [`medium-publication-export`](.agents/skills/medium-publication-export/SKILL.md) skill first — it produces a ZIP in the same format. See [Two scenarios: personal blog vs. publication](#two-scenarios-personal-blog-vs-publication). |
| **A domain name** | The bare domain, e.g. `example.com` (not `www.example.com`). |
| **A theme (Hugo) or starter (Eleventy)** | **Hugo:** browse <https://themes.gohugo.io/tags/blog/>, pick one, and copy **both** its name and its **GitHub repository URL** (the skill won't assume a theme for you). **Eleventy:** no choice needed — the skill defaults to the official [`eleventy-base-blog`](https://github.com/11ty/eleventy-base-blog) starter (name a different starter repo if you prefer). |
| **A GitHub repository** | In `username/repo` format, e.g. `jsmith/example.com`. This is where your site and CI/CD live. For free GitHub Pages it must be **public**. |
| **An AWS account** *(AWS hosting only)* | With permission to create S3, CloudFront, ACM, Route 53, and IAM resources. Default region is `us-east-1`. **Not needed if you host on GitHub Pages.** |
| **Access to your DNS** | Know where your domain's DNS is currently managed (Route 53, Namecheap, Cloudflare, your registrar, etc.). You'll point it at your new host at the end. |
| **Static site generator** *(optional choice)* | Which SSG builds your site: **Hugo** (default) or **Eleventy**. See [Choosing your static site generator](#choosing-your-static-site-generator). |
| **Hosting platform** *(optional choice)* | Where the site is hosted: **AWS** (default) or **GitHub Pages**. See [Choosing where to host your site](#choosing-where-to-host-your-site). |
| **Infrastructure method** *(AWS only, optional choice)* | How AWS resources get created: **Terraform** (default) or **AWS CLI** (no Terraform needed). See [Choosing how AWS infrastructure is created](#choosing-how-aws-infrastructure-is-created). |

**Tools to have installed locally** (the agent can help you install/verify these):

- [Hugo](https://gohugo.io/installation/) (extended version recommended) — **Hugo path only** (the default SSG)
- [Node.js](https://nodejs.org/) **22 or newer** — **Eleventy path only** (the `eleventy-base-blog` starter needs Node 22+)
- [Git](https://git-scm.com/) — required for all paths
- [Python 3](https://www.python.org/) with `beautifulsoup4` (`pip install beautifulsoup4`) — used by the content conversion script
- [AWS CLI](https://aws.amazon.com/cli/), logged in (`aws configure`) — **AWS hosting only** (required for both AWS infrastructure methods). Not needed for GitHub Pages.
- [Terraform](https://developer.hashicorp.com/terraform/install) **1.10 or newer** — **only** for the AWS Terraform method (the skill enforces 1.10+ as the minimum). Skip it for the AWS CLI method and for GitHub Pages.

So a **GitHub Pages** setup needs only your SSG's tool (Hugo *or* Node.js), Git, and Python — no AWS account, no AWS CLI, no Terraform.

> 💡 You don't have to be an expert in any of these. The agent guides each step and explains what it's doing. You **do** need a domain you control. If you want the simplest, cheapest path, tell the agent you'd like to host on **GitHub Pages** (see [Choosing where to host your site](#choosing-where-to-host-your-site)).

---

## How to use the skill

### 1. Open this workspace in your agent

Open the folder containing this repository in VS Code (or your skill-aware agent). The skill in [`.agents/skills/`](.agents/skills/) becomes available automatically.

### 2. Start the conversation

Just tell the agent what you want. The skill triggers on phrases involving **Medium**, **self-hosting**, **Hugo** or **Eleventy**, **AWS/S3/CloudFront**, **static sites**, or **leaving Medium**.

**Example opening prompts:**

> "I want to migrate my Medium blog to a self-hosted Hugo site on AWS. Help me get started."

> "Help me move off Medium. I want to self-host my posts as a static site and stop paying for Medium."

> "Set up a Hugo blog with Terraform and GitHub Actions, and migrate my Medium posts to it."

The agent will then **collect the required inputs** (see below), create a progress-tracking file, and start Phase 1.

### 3. Provide your inputs when asked

The skill collects these before doing anything. You can also volunteer them up front to move faster:

> "Here are my details: domain is `example.com`, GitHub repo is `jsmith/example.com`, AWS region `us-east-1`, DNS is currently at Namecheap. I want to use the **Hugo theme [Anatole](https://github.com/lxndrblz/anatole)**. My Medium export is unzipped in `./work/medium-export/`."

### 4. Confirm at each checkpoint

The skill deliberately **pauses for your confirmation** at key moments — for example, before converting posts, and before any DNS changes. Review what it shows you and reply to continue.

---

## Configuration options (the "Required Inputs")

These are the choices that shape your migration. The agent records each one in a status file as it receives them.

| Input | Required? | Default | Example | Notes |
|---|---|---|---|---|
| **Medium export ZIP** | Yes | — | `work/medium-export/` | Extract it first. Note: the export includes posts from **every** publication you ever wrote for, not just your own blog. |
| **Domain name** | Yes | — | `example.com` | Use the bare/apex domain. The skill sets up `www → apex` redirects automatically. |
| **Static site generator** | No | `hugo` | `eleventy` | Which SSG builds the site. Defaults to Hugo. Choose Eleventy for a Node.js/JavaScript workflow. Sets the build command and output directory used by later phases. See [Choosing your static site generator](#choosing-your-static-site-generator). |
| **Theme (Hugo) or starter (Eleventy)** | Hugo: yes | Hugo: *none — you must choose*; Eleventy: `eleventy-base-blog` | `Anatole` + GitHub URL | **Hugo:** pick from <https://themes.gohugo.io/tags/blog/> and provide **both** the name and the repo URL. **Eleventy:** defaults to the official `eleventy-base-blog` starter; name a different starter repo to override. |
| **Permalink format** | No | `/posts/:slug/` | `/blog/:slug/`, `/archive/:slug/`, `/:slug/` | The URL path for your posts. Defaults to `/posts/:slug/`. Tell the agent up front if you want a different prefix (it keeps the content folder and redirects in sync). |
| **GitHub repository** | Yes | — | `jsmith/example.com` | `username/repo` format. Hosts the site and CI/CD. Must be **public** for free GitHub Pages. |
| **Hosting platform** | No | `aws` | `github-pages` | Where the site is hosted. Defaults to AWS. Choose GitHub Pages for the cheapest, simplest path. See below. |
| **AWS region** | No | `us-east-1` | `eu-west-1` | AWS only. ACM certs are always created in `us-east-1` regardless (CloudFront requirement). |
| **DNS provider** | Yes | — | `Namecheap`, `Cloudflare`, `Route 53` | Where DNS lives today. AWS migrates you to Route 53; GitHub Pages keeps your current provider. |
| **Infrastructure method** | No | `terraform` | `aws-cli` | AWS only. How AWS resources are created. Defaults to Terraform. Choose `aws-cli` to avoid Terraform entirely. See below. |

### Things the skill will *not* assume (by design)

- **It won't pick a Hugo theme for you.** On the Hugo path you must choose one and give the GitHub URL. (On the Eleventy path it defaults to the `eleventy-base-blog` starter, so there's nothing to pick.)
- **It won't guess your DNS/email records.** Before any cutover it asks you to share your current DNS records so important ones (MX, TXT, domain verification, third-party services) are preserved.
- **It won't run the content conversion until you confirm the post list.** Because Medium exports contain all your contributions, you confirm exactly which posts to migrate.

---

## Choosing your static site generator

Before hosting, you pick the **static site generator (SSG)** that builds your site. Both options convert the same Medium posts, preserve the same old URLs, and work with either hosting platform — they differ mainly in tooling and how you customize the look.

### Hugo vs. Eleventy at a glance

| | **Hugo** (default) | **Eleventy (11ty)** |
|---|---|---|
| **Toolchain** | A single Go binary | Node.js 22+ (npm) |
| **Theming** | Large gallery at <https://themes.gohugo.io> | No gallery — scaffolded from the `eleventy-base-blog` starter; you own the templates |
| **Build** | `hugo --minify` → `public/` | `npx @11ty/eleventy` → `_site/` |
| **Old-URL redirects** | Built in via front-matter `aliases` | A small redirects collection + template the skill adds (same end result) |
| **Project folder** | `hugo-site/` | `eleventy-site/` |
| **Best for** | Most users; no Node toolchain — pick a theme and go | Those who prefer a JavaScript/Node workflow and hand-owned templates |

### Pick **Hugo** if…

- You want the **simplest, fastest** path with no Node toolchain.
- You'd rather **choose a ready-made theme** than build templates.
- You're not sure — it's the default and recommended choice.

### Pick **Eleventy** if…

- You prefer a **JavaScript/Node.js ecosystem** and are comfortable with npm.
- You want to **own and hand-edit your templates** rather than configure a packaged theme.

### How to choose Eleventy

Hugo is the default. To use Eleventy, just tell the agent — up front or when asked:

> "Use **Eleventy**, not Hugo. I'd rather work in a Node.js project I can customize myself."

The agent records your choice in `migration-status.md`, scaffolds the `eleventy-base-blog` starter into `eleventy-site/`, and wires up a redirects template so your old Medium URLs still work. If you don't say anything, you get Hugo.

---

## Choosing where to host your site

This is the **first big decision**. The skill needs to know where your site will live. Both options give you the same Hugo site, the same posts, and the same preserved Medium URLs — they differ in cost, simplicity, and how much control you have.

### At a glance

| | **AWS** (default) | **GitHub Pages** |
|---|---|---|
| **Cost** | A small monthly bill (often a dollar or two for a low-traffic blog) | **Free** for public repositories |
| **Setup complexity** | Higher — AWS account, infrastructure, DNS migration | Lower — GitHub builds and hosts it for you |
| **HTTPS** | Automatic via ACM | Automatic via GitHub (Let's Encrypt) |
| **Repository privacy** | Can stay **private** | Must be **public** (free tier) |
| **Control** | High — server-side `www`→apex redirects, custom caching, headers, error pages | Lower — GitHub handles redirects/serving; little fine-grained control |
| **DNS** | Migrates to AWS Route 53 (nameserver change) | Stays with your current DNS provider (add a few records) |
| **Needs an AWS account?** | Yes | No |
| **Limits** | Effectively unlimited | Soft limits (~1 GB site, ~100 GB/month bandwidth) |

### Pick **GitHub Pages** if…

- You want the **cheapest and simplest** setup and don't want an AWS account.
- Your repo can be **public** (your post source becomes visible — fine for most blogs).
- It's a **low-maintenance personal blog** and you don't need server-side redirects, custom headers, or fine-grained caching.

### Pick **AWS** if…

- You want **maximum control**: server-side `www`→apex redirects and directory rewrites, custom cache/error behavior, custom headers.
- You need the source repository to stay **private**.
- You're already comfortable with AWS, or expect higher traffic.

### How to choose GitHub Pages

AWS is the default. To use GitHub Pages, just tell the agent — up front or when asked:

> "Host this on **GitHub Pages**, not AWS. I want the simplest, free option and I'm fine with a public repo."

The agent records your choice in `migration-status.md`, skips all the AWS/Terraform steps, and generates a GitHub Pages deploy workflow plus a `CNAME` file instead. If you don't say anything, you get AWS.

> Changed your mind later? You can switch hosts after the fact — your Hugo site, posts, and URL aliases are reused unchanged; only the hosting layer moves. Tell the agent, e.g. "Switch my site from GitHub Pages to AWS."

---

## Choosing how AWS infrastructure is created

*(This section applies only if you chose **AWS** above. GitHub Pages users can skip it.)*

On AWS, the skill needs to create resources (S3, CloudFront, ACM, Route 53). You pick **how**:

### Option A — Terraform (the default)

Infrastructure as code. The skill writes `.tf` files you apply with `terraform apply`. Choose this if you want **reproducible, version-controlled infrastructure**, are comfortable installing Terraform, or want automated `terraform plan` comments on pull requests.

You get a `terraform/` folder and (by default) GitHub Actions workflows.

#### Picking a Terraform state backend

If you go the Terraform route, you'll also choose where Terraform keeps its **state file** (the record of what it created). This trips up a lot of newcomers, so the skill walks you through it — you don't need to know the answer up front. In short:

- **Local (default, simplest)** — state lives in a file on your machine. Zero setup; great for a learning project. You can move to a remote backend later without recreating anything.
- **S3 backend (recommended once you go live or add CI/CD)** — durable, locked state stored in your own AWS account. One extra bucket to create.
- **HCP Terraform / Terraform Cloud** — a free hosted option with a web dashboard, run history, and PR plan comments.

A good path if you're learning: start **local**, then graduate to the **S3 backend** when you set up GitHub Actions. Ask the agent *"help me choose a Terraform backend"* and it'll explain the trade-offs for your situation.

### Option B — AWS CLI (no Terraform)

The skill writes plain **shell scripts** under `infra/` that create the exact same resources using only the AWS CLI. Choose this if:

- You're **not familiar with Terraform** and don't want to learn a new tool.
- Your blog is **no longer actively updated** — a one-time, set-it-and-forget-it setup.
- You'd rather **deploy by hand** with a small `deploy.sh` script than wire up CI/CD.

You need **no Terraform installation, no Terraform Cloud account, and no GitHub secrets** (unless you later decide you want automated deploys). The end result — the live site — is identical to the Terraform path.

### How to opt out of Terraform

Terraform is on by default. To use the AWS CLI method instead, just say so when the agent asks (or up front). For example:

> "I'm not familiar with Terraform and don't want to learn it for this. Please set up the infrastructure using the **AWS CLI** instead. This blog is basically set-and-forget, so a simple deploy script is fine — no GitHub Actions needed."

or simply:

> "Use the AWS CLI method, not Terraform."

The agent records your choice in `migration-status.md` and generates the `infra/` scripts instead of `terraform/`. If you don't say anything, you get Terraform.

> Already started with one method and want to switch? Tell the agent — e.g. "Switch my infrastructure to the AWS CLI method." It will generate the other folder and update the status file.

---

## The 7 phases (what to expect)

The skill works through these phases in order. Each one reads a dedicated reference doc and updates the progress file when done.

| Phase | What happens | Your involvement |
|---|---|---|
| **1. Content Extraction & Inventory** | Unzips the export, lists candidate posts, builds an inventory table. | Confirm which posts belong to *your* blog. |
| **2. Content Migration (HTML → Markdown)** | Runs [`convert_medium.py`](.agents/skills/medium-to-ssg/scripts/convert_medium.py) to turn posts into Markdown with front matter and preserved URLs (Hugo `aliases`, or the Eleventy redirects template). | Review converted posts; flag embedded media. |
| **3. Site Setup** | Scaffolds the chosen project — Hugo (`hugo-site/`, your theme) or Eleventy (`eleventy-site/`, the starter) — with permalinks (default `/posts/:slug/`) and the converted post files. | Confirm the site looks right locally. |
| **4. Hosting & Infrastructure Setup** | **AWS:** provisions S3, CloudFront + OAC, ACM, Route 53 — as Terraform (`terraform/`) or AWS CLI scripts (`infra/`). **GitHub Pages:** configures the repo for Pages and adds a `CNAME` file (no cloud infra). | Review; for Pages, confirm the repo can be public. |
| **5. Content Deployment** | Sets up how the built site is published: a GitHub Actions workflow (Pages deploy, or S3 sync for AWS) **or** a manual `deploy.sh` script (AWS CLI option). | Confirm and commit, or run the script. |
| **6. Pre-Cutover DNS Review** | Reviews your current DNS so nothing (especially email) breaks. | **Share your current DNS records.** |
| **7. Cutover & Go-Live** | **AWS:** two-phase provisioning + nameserver change to Route 53. **GitHub Pages:** set the custom domain and add GitHub's DNS records at your current provider. Verifies the live site. | Update DNS at your registrar/provider. |

---

## Built-in recovery (important for free-tier AI users)

AI sessions can hit token limits or get interrupted. This skill is designed to survive that:

- On its **first action in every session**, the agent checks for a `migration-status.md` file in your working directory.
- If it exists, the agent **resumes exactly where you left off** instead of starting over.
- The agent **updates `migration-status.md` after every completed step**, logging the current phase, your inputs, decisions made, and files created.

If a conversation ends unexpectedly, just start a new one, make sure `migration-status.md` is in the workspace, and say:

> "Continue my Medium migration."

The agent reads the status file and picks up from the right phase.

---

## Example prompts for common situations

Use these as templates — adjust the details to your setup.

**Kick off a fresh migration with everything ready:**

> "Let's migrate my Medium blog to Hugo on AWS. Domain `myblog.com`, repo `me/myblog.com`, region `us-east-1`, DNS at Cloudflare, theme **PaperMod** (`https://github.com/adityatelange/hugo-PaperMod`). My export is in `./work/medium/`."

**Resume after an interruption:**

> "Continue my Medium migration — `migration-status.md` is in this folder."

**Migrate only some posts:**

> "From my Medium export, I only want to migrate the posts I wrote on my personal blog, not the ones from publications I contributed to. Let's review the list before converting."

**Use Eleventy instead of Hugo:**

> "Migrate my Medium blog, but use **Eleventy** instead of Hugo — I'd rather work in a Node.js project I can customize myself. Host on GitHub Pages, repo `me/myblog.com`, DNS at Cloudflare."

**Be careful with DNS / email:**

> "Before we change any DNS, here are my current records [paste/screenshot]. I use Google Workspace for email, so make sure MX and verification records are preserved."

**Just the infrastructure:**

> "I already have my Hugo posts. Help me set up just the Terraform and GitHub Actions parts for S3 + CloudFront hosting."

**Avoid Terraform entirely (set-and-forget):**

> "I'm new to Terraform and don't want to learn it. Set up the AWS infrastructure with the **AWS CLI** scripts instead, and give me a simple deploy script — no GitHub Actions."

**Host on GitHub Pages for free (simplest option):**

> "Host this on **GitHub Pages**, not AWS. I want the cheapest, simplest setup and I'm fine with a public repo. Domain `myblog.com`, repo `me/myblog.com`, DNS at Namecheap, theme **PaperMod** (`https://github.com/adityatelange/hugo-PaperMod`)."

**Compare hosting options before deciding:**

> "Before we start, help me decide between AWS and GitHub Pages for my blog. It's a small personal site I rarely update and I'd like to keep costs near zero."

**Ask the agent to explain before acting:**

> "Before Phase 4, explain in plain English what AWS resources you're about to create and roughly what they'll cost me."

---

## Output structure

Everything the skill generates goes under your SSG project folder — `hugo-site/` for Hugo or `eleventy-site/` for Eleventy — in your working directory. The trees below show the **Hugo** layout; the [Eleventy layout](#eleventy-project-layout) differs and is summarized at the end. The hosting-specific files depend on your chosen platform and method.

**Always created:**

```
hugo-site/
├── hugo.toml                  # Hugo configuration
├── content/
│   ├── _index.md
│   └── posts/                 # Your converted posts
│       └── *.md
├── layouts/
│   └── shortcodes/
│       └── video.html         # Only if embedded video is detected
├── assets/css/custom.css      # Your place for style/font customizations
├── static/
├── .gitignore
└── README.md
```

**If you chose AWS + Terraform (default):**

```
hugo-site/
├── terraform/                 # All AWS infrastructure as code
│   ├── s3.tf, cloudfront.tf, acm.tf, route53.tf, iam.tf, ...
│   ├── backend.tf.example     # State backend options (local, S3, or HCP Terraform)
│   ├── outputs.tf
│   └── functions/viewer_request.js   # www redirect + index rewrite
└── .github/
    ├── workflows/deploy.yml   # Build + deploy on push to main
    ├── workflows/terraform.yml# Plan on PR, apply on merge (remote state only)
    └── dependabot.yml
```

> `terraform.yml` is only generated if you use a **remote** Terraform state backend (S3 or HCP Terraform). With the default **local** state there's nothing shared for CI to plan against, so you get just `deploy.yml` and run `terraform apply` from your own machine.

**If you chose AWS + the AWS CLI method:**

```
hugo-site/
└── infra/                     # Shell scripts that create the same AWS resources
    ├── 00-config.sh           # your domain, region, repo
    ├── 01-s3.sh ... 06-route53-records.sh   # run in order
    ├── 07-iam-github.sh       # only if you opt into GitHub Actions
    ├── deploy.sh              # build + upload the site by hand
    ├── functions/viewer_request.js
    └── README.md              # the exact run order
```

(With the AWS CLI method you get a `.github/` folder only if you opt into automated deploys.)

**If you chose GitHub Pages:**

```
hugo-site/
├── static/CNAME               # your apex domain (binds the custom domain)
└── .github/
    ├── workflows/deploy.yml   # Hugo build + deploy via official GitHub Pages actions
    └── dependabot.yml
```

No `terraform/` or `infra/` folder — GitHub hosts the site, so there's no cloud infrastructure to manage.

### Eleventy project layout

If you chose **Eleventy**, the project lives in `eleventy-site/` instead, scaffolded from the official [`eleventy-base-blog`](https://github.com/11ty/eleventy-base-blog) starter. The starter brings its own `_includes/`, `css/`, and `_data/`; the migration adds or edits a few pieces:

```
eleventy-site/
├── content/blog/               # Your converted posts (the starter's posts dir)
│   └── *.md
├── content/redirects.njk       # Generates the old-Medium-URL redirect stubs
├── _data/metadata.js           # Site metadata, incl. the canonical base URL
├── eleventy.config.js          # Eleventy config (redirects collection + video shortcode)
├── .nvmrc                      # Pins Node 22 for local + CI
└── public/                     # Passthrough static root (CNAME goes here for Pages)
```

The hosting-specific folders are **identical** to the Hugo path and attach the same way: `terraform/` or `infra/` for AWS, and `.github/workflows/deploy.yml` for CI/CD. Only the build command (`npx @11ty/eleventy`) and output directory (`_site/`) differ — the skill fills those into every deployment file for you.

---

## Customizing the look & feel

The skill scaffolds a clean, theme-driven site and intentionally leaves the styling to you, so you're free to make the blog your own. Almost all of the appearance is controlled by two things: the **Hugo theme you chose** and a small set of files in your `hugo-site/` folder. You can change these yourself, or just ask the agent — e.g. *"Change the body font to a serif typeface"* or *"Show only post titles and dates on the homepage."*

> **On Eleventy** the mechanics differ: there's no separate theme layer — you own the `eleventy-base-blog` starter's templates (`_includes/`) and CSS (`css/`) directly, and edit them in `eleventy-site/`. The rest of this section is written for the Hugo path, but the same agent prompts (*"change the body font…"*) work either way — the agent edits the right files for your SSG.

### Start with your theme's options

Most look-and-feel choices (color scheme, dark/light mode, author avatar, social links, homepage style, menu) are exposed as **theme parameters** in `hugo.toml` under `[params]`. Your theme's README and `exampleSite/` are the best reference for what's available. To explore or change these, ask the agent: *"What params does my theme support, and how do I enable dark mode?"*

### Change what's on the homepage

By default the homepage is driven by your theme plus the content in `content/_index.md`:

- **Edit the intro text/bio:** change `content/_index.md`.
- **Control which posts are listed:** the `mainSections` setting in `hugo.toml` decides which content sections appear (it defaults to `["posts"]`).
- **Fully custom homepage:** Hugo lets you override the theme by adding your own `layouts/index.html`. This is an advanced option — the skill doesn't create one by default, since most themes already provide a good homepage. Ask the agent if you want a bespoke landing page (e.g. avatar + social links instead of a post list), and it will create the override for you.

### Change fonts, colors, and other CSS

The skill creates `assets/css/custom.css` as your dedicated place for style overrides — most themes load it automatically, so you don't have to edit theme files. For example, to change the font you can add an `@import` for a web font and set it on `body`:

```css
@import url('https://fonts.googleapis.com/css2?family=Lora&display=swap');

body {
  font-family: 'Lora', Georgia, serif;
}

/* Tweak accent colors, spacing, etc. here too. */
a { color: #b5512d; }
```

If your theme doesn't pick up `custom.css` automatically, ask the agent to wire it in for your specific theme. Run `hugo server` locally to preview changes instantly before deploying.

### Changing the post URL format

If you didn't set a permalink format up front, you can still change it later (e.g. from `/posts/:slug/` to `/blog/:slug/`). Ask the agent — it updates the `[permalinks]` block in `hugo.toml`, renames the `content/` subfolder to match, and preserves your old-Medium-URL redirects so nothing breaks.

---

## How the skill is organized

If you're curious what's under the hood:

```
.agents/skills/medium-to-ssg/
├── SKILL.md                   # Main playbook the agent reads
├── references/                # Loaded on-demand, one per phase
│   ├── content-migration.md
│   ├── hugo-setup.md           # Site setup — Hugo path
│   ├── eleventy-setup.md       # Site setup — Eleventy path
│   ├── terraform.md           # AWS — Terraform infrastructure path
│   ├── aws-cli-infra.md       # AWS — AWS CLI infrastructure path (Terraform alternative)
│   ├── github-pages.md        # GitHub Pages hosting path (AWS alternative)
│   ├── cicd.md
│   └── dns-cutover.md
└── scripts/
    └── convert_medium.py      # Medium HTML → Hugo/Eleventy Markdown converter
```

You generally **don't edit these** — the agent reads them. The one exception is `convert_medium.py`, which has a small config block (`SSG`, `INPUT_DIR`, `OUTPUT_DIR`, and a `posts` list mapping each Medium HTML file to a clean URL slug). The agent fills this in for you, but you can review it.

---

## Tips for a smooth migration

- **Decide where to host first** — AWS or GitHub Pages. It shapes every later step. If in doubt and you want cheap and simple, start with GitHub Pages.
- **Gather your inputs first** — domain, repo, theme URL, DNS provider — so the agent isn't blocked waiting on you.
- **Don't rush the DNS phase.** Share your real current records. Preserving email (MX/TXT) is the easiest thing to get wrong — this matters on both hosting platforms.
- **Verify before you cut over.** The skill lets you preview the site at a temporary URL (the CloudFront URL on AWS, or the `*.github.io` URL on GitHub Pages) *before* you repoint your domain.
- **Keep `migration-status.md`** in your repo — it's your safety net.
- **Review costs.** GitHub Pages is free for public repos. S3 + CloudFront for a small blog is typically very cheap, and the skill can add an AWS Budget for peace of mind — ask the agent to walk you through it.
- **GitHub Pages needs a public repo** on the free tier. If your repo must stay private, use AWS (or a paid GitHub plan).

---

## Troubleshooting

- **The agent didn't pick up the skill.** Make sure you opened the workspace that contains `.agents/skills/`, and phrase your request around Medium/Hugo/AWS/self-hosting. You can also say: "Use the medium-to-ssg skill."
- **It wants a theme and won't continue.** That's intentional on the **Hugo** path — provide a theme name *and* its GitHub URL from <https://themes.gohugo.io/tags/blog/>. (On the **Eleventy** path there's no theme to pick; it uses the `eleventy-base-blog` starter.)
- **Old Medium links break.** Confirm the converted posts kept their `aliases` front matter; those generate the redirect pages. (Aliases work on both AWS and GitHub Pages.)
- **HTTPS/cert validation is stuck (AWS).** ACM validation only completes after you update your nameservers to the Route 53 ones the skill outputs — that's the two-phase provisioning step.
- **HTTPS isn't available yet (GitHub Pages).** GitHub provisions the certificate only after it verifies your custom domain via DNS; this can take a few minutes up to ~24 hours. Then enable "Enforce HTTPS" in the repo's Pages settings. On Cloudflare, set the records to "DNS only" (grey cloud) until the certificate is issued.
- **You don't want to install Terraform.** Tell the agent to use the **AWS CLI method** ("Use the AWS CLI method, not Terraform"), or skip AWS entirely with **GitHub Pages**.
- **You don't want an AWS account at all.** Choose **GitHub Pages** ("Host this on GitHub Pages, not AWS"). It needs only Hugo, Git, and Python — no AWS, no Terraform.
