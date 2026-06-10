# Hugo Site Setup Reference

## Step 1 — Read the theme's README first

Before writing any config, fetch and read the chosen theme's README from its GitHub repository. Themes vary significantly in:
- What config keys they expect in `hugo.toml`
- What `params` they support
- What `mainSections` or equivalent setting controls which content appears on the home page (note whether it expects a singular or plural section name, e.g. `post` vs. `posts` — it must match your `content/` subdirectory or the home page will list nothing)
- Whether they use Hugo Pipes, asset bundling, or just static files
- Whether they require **Hugo Extended** (any theme that transpiles SCSS/SASS does)
- What front matter fields they use (e.g. `description`, `summary`, `cover`, `tags`)

Do not guess theme config. Read its README, then write `hugo.toml` accordingly.

**Check the theme's Hugo version and build prerequisites before scaffolding.** Note the theme's minimum Hugo version (often declared as `min_version` in the theme's `theme.toml`) and whether it needs **Hugo Extended** — any theme that transpiles SCSS/SASS via Hugo Pipes (look for `toCSS` / `resources.Get "...scss"` in `layouts/partials/head.html`) requires the extended build, and newer themes may also need a Dart Sass binary. A plain (non-extended) Hugo, or one missing Dart Sass, aborts the build on the SCSS step with a `TOCSS`/transpiler error. Confirm the Hugo that will build the site — both locally and in CI — satisfies this (`hugo version` should show `+extended`) before continuing.

## Step 2 — Initialize the Hugo project structure

Create the following directory structure:

```
hugo-site/
├── hugo.toml
├── content/
│   ├── _index.md
│   └── posts/     ← posts go here
├── layouts/
│   └── shortcodes/
├── assets/css/
│   └── custom.css
├── static/
└── themes/          ← populated via git submodule
```

## Step 3 — Write hugo.toml

Use this as a starting template, adapting the `[params]` section to whatever the chosen theme requires:

```toml
baseURL = "https://DOMAIN/"
languageCode = "en-us"
title = "SITE_TITLE"

copyright = "Copyright © YOUR_NAME. All rights reserved."

theme = "THEME_NAME"

# Tells Hugo which content sections to list on the home page.
# Adjust if the theme uses a different mechanism.
mainSections = ["posts"]

[permalinks]
  # Posts live at /posts/post-slug/ by default — adjust if the user prefers
  # a different prefix (must match the content/ subdirectory name).
  posts = "/posts/:slug/"

[params]
  description = "SITE_DESCRIPTION"

  # Add theme-specific params here based on the theme README.
  # Common examples:
  # colorScheme = "auto"
  # author = "YOUR_NAME"
```

Ask the user to confirm the site title, their name, and description before writing this file.

### Raw HTML in content (Goldmark `unsafe`)

By default Hugo's Markdown renderer (Goldmark) runs with `unsafe = false`, which **silently drops raw HTML** found in content. `scripts/convert_medium.py` handles the common case for you: it escapes stray angle brackets in prose (e.g. a literal `<global-exception-mapping>` mentioned in an article) to entities so the text renders instead of disappearing, and it keeps inline code and fenced code blocks verbatim. So you usually do **not** need to enable `unsafe`.

Only add the markup block below if a converted post legitimately needs raw HTML to pass through (for example a hand-written embed the converter didn't turn into a shortcode). Note some themes (e.g. Anatole) set this themselves, and enabling it sitewide means any raw HTML in any post is rendered as-is:

```toml
[markup]
  [markup.goldmark]
    [markup.goldmark.renderer]
      unsafe = true
```

## Step 4 — Configure the permalink structure

The default permalink format for posts is `/posts/:slug/`. This means:
- Canonical URL: `https://example.com/posts/my-post-title/`
- Old Medium URL: `https://example.com/my-post-title-a1b2c3d4e5f6` (redirected via alias)

This is one of the main things a user may want to customize up front. If the user prefers a different prefix (e.g. `/archive/`, `/blog/`, or no prefix), update **both** the `[permalinks]` block key in `hugo.toml` **and** the matching `content/` subdirectory name so they stay in sync. The convert script's `OUTPUT_DIR` (see `references/content-migration.md`) must point at the same subdirectory.

## Step 5 — Write content/_index.md

This is the home page content. Start with a placeholder:

```markdown
---
title: "SITE_TITLE"
---

This is a placeholder. Replace this text with your home page content.
```

## Step 6 — Create assets/css/custom.css

Create a `custom.css` placeholder so the user has a clear place to add customizations without touching theme files:

```css
/* Site-specific style overrides go here. */
```

**Do not assume the theme loads this file automatically — many do not.** Wire it up using the theme's documented mechanism (read the theme README). Some themes load custom CSS only when you register it explicitly in `hugo.toml` (e.g. Anatole expects `customCss = ["css/custom.css"]` under `[params]`), and several do so through Hugo Pipes with `resources.Get`, which **fails the entire build** if the path doesn't resolve to a real file under `assets/`. Use the exact asset-relative path the theme expects (e.g. `css/custom.css` for a file at `assets/css/custom.css`, not bare `custom.css`). If the theme has no custom-CSS hook, leave the file unreferenced rather than guessing a param name.

## Step 7 — Install the theme as a git submodule

Do not copy theme files into the repo. Add the theme as a git submodule so updates are easy:

```bash
git submodule add THEME_GITHUB_URL themes/THEME_NAME
```

Document this in `README.md` with instructions for new clones:

```bash
git submodule update --init --recursive
```

## Step 8 — Write .gitignore

```
public/
resources/
.hugo_build.lock
```

## Step 9 — Test locally (if Hugo is available)

```bash
hugo server
```

Verify:
- Home page renders correctly
- At least one post renders correctly
- A redirect alias URL (e.g. `/my-post-title-a1b2c3d4e5f6`) redirects to the canonical post URL
- Any embedded media shortcodes render without errors

If Hugo is not available in the current environment, document the local test step for the user to run themselves.

## Step 10 — Confirm and update status

Confirm the Hugo site structure with the user. Mark Phase 3 complete in `migration-status.md` and list all created files.
