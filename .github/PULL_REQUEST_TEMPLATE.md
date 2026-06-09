<!-- markdownlint-disable-file MD041 -- a PR template is form scaffolding, not a document; it has no top-level heading -->
## What does this PR do?

<!-- A short summary of the change and the migration scenario it affects. -->

## Which areas are affected?

- [ ] `medium-to-ssg` skill
- [ ] `medium-publication-export` skill
- [ ] Helper script(s)
- [ ] Repo tooling / CI
- [ ] Docs only

## Checklist

- [ ] `python3 tools/lint_skills.py` passes
- [ ] `npx --yes markdownlint-cli2@0.22.1 "**/*.md"` passes
- [ ] Python helpers byte-compile (`python3 -m py_compile ...`)
- [ ] Related `SKILL.md` and `references/*.md` updated together so the branching paths stay consistent
- [ ] Change is scoped to a single fix/feature
