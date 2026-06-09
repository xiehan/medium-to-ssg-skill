# Contributing

Thanks for your interest in improving these skills! This repository packages **agent skills** — structured Markdown instructions plus helper scripts that teach an AI coding agent how to migrate a Medium blog to a self-hosted Hugo site. Contributions that fix inaccuracies, cover new migration scenarios, or improve the helper scripts are very welcome.

## Repository layout

```text
.agents/skills/
  medium-to-ssg/             # Migrate a Medium export → Hugo site (AWS or GitHub Pages)
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
- **Keep the branching paths consistent.** A change to one path (AWS vs. GitHub Pages, Terraform vs. AWS CLI, personal vs. publication export) usually needs matching updates in the related `SKILL.md` and `references/*.md`.

## Running the checks locally

CI runs three checks; all three are quick and run locally:

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
```

If you change a script's behavior, also run it end to end with its dependencies installed (`pip install beautifulsoup4 requests`) against a sample export.

## Pull requests

- Keep PRs focused — one fix or feature per PR.
- Make sure the three checks above pass.
- Describe the migration scenario your change affects.

By contributing, you agree that your contributions are licensed under the repository's [MIT License](LICENSE).
