#!/usr/bin/env python3
"""Lint the agent skills in this repository.

This is a zero-dependency structural linter (standard library only) that checks
the things contributors most commonly get wrong when editing skills:

1. Every skill has a SKILL.md with valid YAML frontmatter containing a `name`
   and a `description`.
2. The frontmatter `name` matches the skill's directory name (so the skill is
   discoverable under the name it claims).
3. The `description` is non-empty and within a sane length budget.
4. Relative Markdown links inside the docs actually resolve to files that exist
   — this catches broken cross-references between SKILL.md and references/*.md,
   the single most common rot in a multi-file skill.

It scans every SKILL.md under `.agents/skills/<skill>/` plus the repository
README, and exits non-zero (with a readable report) if anything fails, so it
can gate pull requests in CI.

Usage:
    python3 tools/lint_skills.py [REPO_ROOT]

REPO_ROOT defaults to the current working directory.
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import unquote

# Max characters allowed in a skill `description`. Skill loaders truncate or
# reject very long descriptions; keep them tight and trigger-focused.
MAX_DESCRIPTION_LEN = 1024

SKILLS_SUBDIR = os.path.join(".agents", "skills")

# Markdown inline link: [text](target "optional title")
_LINK_RE = re.compile(r"\[(?:[^\]]*)\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
# Fenced code blocks (``` or ~~~), so we don't lint example links inside them.
_FENCE_RE = re.compile(r"(?ms)^([ \t]*)(`{3,}|~{3,}).*?^\1\2[ \t]*$")

# Link targets we never resolve against the filesystem.
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "//", "#")


def _strip_code_fences(text: str) -> str:
    """Blank out fenced code blocks while preserving line numbers."""
    def _blank(match: re.Match) -> str:
        return "\n" * match.group(0).count("\n")

    return _FENCE_RE.sub(_blank, text)


def parse_frontmatter(text: str):
    """Return (dict_of_simple_scalars, error_or_None) for a Markdown file.

    Only the top-level `key: value` scalars used by skill frontmatter are
    parsed; this avoids a YAML dependency for the simple shapes we use.
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return None, "missing YAML frontmatter (file must start with '---')"

    fields: dict[str, str] = {}
    i += 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return fields, None
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            fields[key] = value
        i += 1
    return None, "frontmatter is not closed with a terminating '---'"


def extract_link_targets(text: str):
    """Yield (line_number, raw_target) for resolvable relative links."""
    stripped = _strip_code_fences(text)
    for match in _LINK_RE.finditer(stripped):
        target = match.group(1).strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        if not target or target.startswith(_EXTERNAL_PREFIXES):
            continue
        # Drop any anchor fragment; resolve only the path portion.
        path = target.split("#", 1)[0].strip()
        if not path:
            continue
        line_number = stripped.count("\n", 0, match.start()) + 1
        yield line_number, unquote(path)


def check_frontmatter(skill_dir: str, skill_md: str, errors: list[str]) -> None:
    skill_name = os.path.basename(skill_dir)
    with open(skill_md, encoding="utf-8") as handle:
        text = handle.read()

    fields, err = parse_frontmatter(text)
    if err:
        errors.append(f"{skill_md}: {err}")
        return

    name = fields.get("name", "").strip()
    if not name:
        errors.append(f"{skill_md}: frontmatter is missing a 'name'")
    elif name != skill_name:
        errors.append(
            f"{skill_md}: frontmatter name '{name}' does not match "
            f"directory name '{skill_name}'"
        )

    description = fields.get("description", "").strip()
    if not description:
        errors.append(f"{skill_md}: frontmatter is missing a 'description'")
    elif len(description) > MAX_DESCRIPTION_LEN:
        errors.append(
            f"{skill_md}: description is {len(description)} chars "
            f"(max {MAX_DESCRIPTION_LEN})"
        )


def check_links(md_path: str, errors: list[str]) -> None:
    with open(md_path, encoding="utf-8") as handle:
        text = handle.read()
    base = os.path.dirname(md_path)
    for line_number, rel in extract_link_targets(text):
        resolved = os.path.normpath(os.path.join(base, rel))
        if not os.path.exists(resolved):
            errors.append(
                f"{md_path}:{line_number}: broken relative link -> '{rel}'"
            )


def find_markdown_files(root: str):
    skills_root = os.path.join(root, SKILLS_SUBDIR)
    for dirpath, _dirnames, filenames in os.walk(skills_root):
        for filename in filenames:
            if filename.endswith(".md"):
                yield os.path.join(dirpath, filename)
    readme = os.path.join(root, "README.md")
    if os.path.exists(readme):
        yield readme


def find_skill_dirs(root: str):
    skills_root = os.path.join(root, SKILLS_SUBDIR)
    if not os.path.isdir(skills_root):
        return
    for entry in sorted(os.listdir(skills_root)):
        skill_dir = os.path.join(skills_root, entry)
        if os.path.isdir(skill_dir):
            yield skill_dir


def main(argv: list[str]) -> int:
    root = os.path.abspath(argv[1]) if len(argv) > 1 else os.getcwd()
    skills_root = os.path.join(root, SKILLS_SUBDIR)
    if not os.path.isdir(skills_root):
        print(f"error: no skills directory found at {skills_root}", file=sys.stderr)
        return 2

    errors: list[str] = []

    skill_dirs = list(find_skill_dirs(root))
    if not skill_dirs:
        errors.append(f"{skills_root}: no skills found")

    for skill_dir in skill_dirs:
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md):
            errors.append(f"{skill_dir}: missing SKILL.md")
            continue
        check_frontmatter(skill_dir, skill_md, errors)

    markdown_files = sorted(set(find_markdown_files(root)))
    for md_path in markdown_files:
        check_links(md_path, errors)

    rel_skills = [os.path.basename(d) for d in skill_dirs]
    print(
        f"Checked {len(skill_dirs)} skill(s) "
        f"({', '.join(rel_skills) or 'none'}) "
        f"and {len(markdown_files)} Markdown file(s)."
    )

    if errors:
        print(f"\n{len(errors)} problem(s) found:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("All skill checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
