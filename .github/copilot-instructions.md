# Copilot instructions for this repository

## What this repository is

This repo is **not an application** — it is a collection of **agent skills**: structured Markdown instructions (plus a few helper scripts) that teach an AI coding agent how to migrate a Medium blog to a self-hosted Hugo static site.

- `.agents/skills/medium-to-ssg/` — migrate a Medium export → Hugo site on **AWS** or **GitHub Pages**.
- `.agents/skills/medium-publication-export/` — scrape a multi-author publication → a Medium-export-compatible ZIP that feeds the skill above.
- Each skill has a `SKILL.md` (entry point, with YAML frontmatter) and `references/*.md` (phase-by-phase deep guidance the agent reads on demand).
- `tools/lint_skills.py` is a zero-dependency structural linter run in CI.

When reviewing, evaluate the docs as **instructions an AI agent will follow end to end**, not as prose. The reader is a machine that will execute every branch literally, so gaps, contradictions, and dead ends are bugs.

## When reviewing a pull request, prioritize these checks

### 1. Branching-path consistency (most important)

The skills offer several either/or choices. A change to one branch usually requires matching updates elsewhere, and an agent following any single path must never hit a dead end, a missing file, or guidance meant for a different branch. For every PR, trace each path end to end and confirm it stays internally consistent:

- **Hosting platform:** AWS (S3 + CloudFront) **vs** GitHub Pages.
- **AWS infrastructure method:** Terraform **vs** AWS CLI shell scripts (both must create the *same* resources).
- **Terraform state backend:** local (default — **no** `terraform.yml` CI workflow is generated) **vs** remote S3/HCP (a `terraform.yml` workflow **is** generated). Watch for instructions that assume one but apply to the other.
- **Content deployment:** GitHub Actions **vs** manual deploy script.
- **Content source:** a personal Medium "Download your information" export **vs** the `medium-publication-export` ZIP.
- **DNS provider:** Route 53 **vs** an external registrar (Namecheap, Cloudflare, etc.).

Flag anything where: one branch was updated but its counterpart wasn't; `SKILL.md` and a `references/*.md` now disagree; a step references a file, variable, or phase that only exists on a different path; or the `migration-status.md` input options no longer match the steps that consume them.

### 2. SKILL.md and references stay in sync

`SKILL.md` summarizes; `references/*.md` give the detail. If a PR changes one, confirm the other still agrees (phase names, ordering, input names, defaults). Frontmatter `name` **must** equal the skill's directory name, and `description` should stay trigger-focused and roughly under 1024 characters.

### 3. Don't introduce guessed or fabricated specifics

Flag any **hard-coded real-world values that should be placeholders**: GitHub repo slugs, domains, AWS account IDs, emails, or URLs the contributor can't actually know. Examples should use obvious placeholders (`example.com`, `username/repo`, `OWNER/REPO`). Verify external links are real and resolve.

### 4. Security and supply-chain hygiene

- GitHub Actions must be **pinned to a full commit SHA** with a `# vX.Y.Z` comment — the skills preach this, so the repo must practice it.
- No secrets, tokens, or credentials committed; Actions should use repository secrets and least-privilege `permissions:`.
- Helper scripts should prefer the **standard library** (`convert_medium.py` needs `beautifulsoup4`; `scrape_publication.py` also needs `requests`); scrutinize any new dependency.
- The scraper must stay respectful (rate-limited, no auth bypass) and only target content the user owns/controls.

### 5. Tests for the Python helpers (and when *not* to ask for one)

The two helper scripts have a stdlib `unittest` suite under `tests/` (no pytest), run in CI. It is deliberately **regression-focused, not coverage-driven** — do not ask contributors to add a test for every change. Apply this philosophy when reviewing:

- **Worth a test:** a change to the **behavior of a pure function** in the helpers — the HTML→Markdown conversion (`node_to_md` and friends), front-matter assembly (`convert_post`), metadata/date/tag extraction, URL/slug normalization, and the export-HTML format the converter consumes. Every past *bug fix* in these areas should gain one focused test that pins the corrected behavior, so it can't silently regress.
- **Not worth a test (don't request one):** changes to the Markdown skill instructions (`SKILL.md`, `references/*.md`), CI/workflow/config edits, dependency-pin bumps, docstring/comment-only changes, and anything in the network/filesystem layer — `fetch`, `make_session`, the sitemap crawl, and file/ZIP output. Those are I/O glue around the tested core; mocking them would test the mock, not the migration. The skill docs themselves are validated by `lint_skills.py` and markdownlint, not unit tests.
- **Rule of thumb:** if a PR changes a tested function's output, the matching test should change with it. If a PR only touches docs, CI, or I/O plumbing, a missing test is *not* a defect — don't flag it.
- Tests must stay **fast and network-free** (no live HTTP); the converter tests disable image downloads and the scraper tests feed in small inline HTML fixtures.

### 6. House style and the local checks

- **Markdown is not hard-wrapped** — one line per paragraph. Don't request reflowing to a column width.
- Use **relative links** between skill docs; the linter verifies they resolve.
- A valid PR keeps all four CI checks green:
  - `python3 tools/lint_skills.py`
  - `npx --yes markdownlint-cli2@0.22.1 "**/*.md"`
  - `python3 -m py_compile` on the Python helpers.
  - `python3 -m unittest discover -s tests`

## Review style

Keep PRs **focused and reversible**. Prefer concise, actionable comments that point to the specific file/line and explain the user-facing consequence (e.g. "an agent on the GitHub Pages path would now be told to run Terraform"). If a change looks correct and consistent across all branches, say so rather than inventing nitpicks.
