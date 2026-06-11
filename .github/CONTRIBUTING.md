# Contributing

Thanks for your interest in improving these skills! This repository packages **agent skills** — structured Markdown instructions plus helper scripts that teach an AI coding agent how to migrate a Medium blog to a self-hosted static site built with Hugo (the default) or Eleventy. Contributions that fix inaccuracies, cover new migration scenarios, or improve the helper scripts are very welcome.

## Repository layout

```text
.agents/skills/
  medium-to-ssg/             # Migrate a Medium export → Hugo or Eleventy site (AWS or GitHub Pages)
    SKILL.md                 # Entry point: role, inputs, phases, constraints
    references/*.md          # Phase-by-phase deep guidance (read on demand)
    scripts/convert_medium.py
  medium-publication-export/ # Scrape a whole publication → Medium-export ZIP
    SKILL.md
    references/*.md
    scripts/scrape_publication.py
    scripts/*.bookmarklet.js
tools/lint_skills.py         # Structural linter for the skills (runs in CI)
README.md
```

Each skill is self-contained: a `SKILL.md` with YAML frontmatter (`name` + `description`) that an agent loads, and `references/` docs it reads on demand.

## Conventions

- **Markdown is not hard-wrapped.** Write one line per paragraph and let the editor soft-wrap. (See [`.editorconfig`](.editorconfig) and [`.markdownlint.jsonc`](.markdownlint.jsonc).)
- **Two-space indent, LF line endings, final newline** for all files; Python uses four-space indent (enforced by `.editorconfig`).
- **The `name` in frontmatter must match the skill's directory name.**
- **Keep `description` trigger-focused** and under ~1024 characters — it's what makes an agent pick the right skill.
- **Use relative links** between skill docs (e.g. `references/terraform.md`, `../medium-publication-export/SKILL.md`). The linter verifies they resolve.
- **Helper scripts target the standard library where practical.** `convert_medium.py` needs `beautifulsoup4`; `scrape_publication.py` also uses `requests`. Avoid adding new dependencies without a good reason.
- **Pin GitHub Actions to commit SHAs** (with a `# vX.Y.Z` comment) — the same practice the skills themselves recommend.
- **Keep the branching paths consistent.** A change to one path (Hugo vs. Eleventy, AWS vs. GitHub Pages, Terraform vs. AWS CLI, personal vs. publication export) usually needs matching updates in the related `SKILL.md` and `references/*.md`.

## Proposing a new static site generator

The skill supports **Hugo** (the default) and **Eleventy**, and **Astro** is planned next. Beyond that, the bar for adding another SSG is **deliberately very high**, and the reason is the previous bullet: every SSG multiplies the branching paths this project has to keep correct and in sync (front matter, build command, output directory, URL-preservation mechanism, and every hosting/deploy reference doc). That maintenance cost — not the merits of any one generator — is the constraint.

**Open a Feature Request issue to discuss any new SSG before writing code** — use the repository's **"Skill improvement or new guidance"** issue template and select `medium-to-ssg`. Please don't open a PR that adds an SSG cold; it will likely be declined regardless of quality, because the decision is about long-term maintenance, not implementation. A proposal should make the case against these requirements (suggestions for further criteria are welcome in the issue):

- **Popular and actively maintained.** It needs a large, healthy community and a steady release/security cadence so the guidance doesn't rot. (This is the main reason we're cautious about, e.g., Jekyll.)
- **Markdown + front matter content model.** The converter (`convert_medium.py`) emits Markdown with YAML-ish front matter; an SSG that maps cleanly onto that output is far cheaper to support than one that needs a bespoke content format.
- **URL preservation with core, stable features.** Recreating old Medium URLs (the migration's central promise) must be possible using the SSG's own long-lived APIs, not an unmaintained third-party plugin that could break on a future major release.
- **Plain static output that works on *both* hosting paths unchanged.** It must build to static files that serve as-is on S3 + CloudFront *and* GitHub Pages, with no server runtime — otherwise it doesn't fit the existing hosting/deploy matrix.
- **A build toolchain that fits the current CI/deploy model** (a single documented build command and output directory the deploy workflows can consume).

If a generator you care about doesn't clear this bar but you still want it, the friendliest path is to **maintain a fork** — the skills are MIT-licensed and structured so an additional SSG branch is self-contained. We'd rather point you to a clean fork than carry a path we can't commit to maintaining well.

## Running the checks locally

CI runs four checks; all four are quick and run locally:

```bash
# 1. Skill structure + cross-reference links (zero dependencies)
python3 tools/lint_skills.py

# 2. Markdown lint (uses .markdownlint.jsonc)
npx --yes markdownlint-cli2@0.22.1 "**/*.md"

# 3. Byte-compile the Python helpers
python3 -m py_compile \
  tools/lint_skills.py \
  .agents/skills/medium-to-ssg/scripts/convert_medium.py \
  .agents/skills/medium-publication-export/scripts/scrape_publication.py

# 4. Unit tests for the Python helpers (needs beautifulsoup4)
python3 -m unittest discover -s tests
```

The unit tests in [`tests/`](tests/) cover the pure parsing and transform functions of both helpers (HTML->Markdown conversion, front-matter assembly, metadata/date/tag extraction, URL handling) and are regression-focused: each past bug fix has a test that pins it. They touch no network. When you change a script's behavior, add or update a test alongside it.

If you change a script's behavior, also run it end to end with its dependencies installed (`pip install beautifulsoup4 requests`) against a sample export.

## Pull requests

- Keep PRs focused — one fix or feature per PR.
- Make sure the four checks above pass.
- Describe the migration scenario your change affects.

By contributing, you agree that your contributions are licensed under the repository's [MIT License](LICENSE).
