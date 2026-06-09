# Hugo Site Setup Reference

## Step 1 — Read the theme's README first

Before writing any config, fetch and read the chosen theme's README from its GitHub repository. Themes vary significantly in:
- What config keys they expect in `hugo.toml`
- What `params` they support
- What `mainSections` or equivalent setting controls which content appears on the home page
- Whether they use Hugo Pipes, asset bundling, or just static files
- What front matter fields they use (e.g. `description`, `summary`, `cover`, `tags`)

Do not guess theme config. Read its README, then write `hugo.toml` accordingly.

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

Most themes load a `custom.css` file from the assets directory automatically. Create it with a placeholder comment:

```css
/* Site-specific style overrides go here. */
```

This gives the user a clear place to add customizations without touching theme files.

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
