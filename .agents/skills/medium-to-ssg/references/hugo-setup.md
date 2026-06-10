# Hugo Site Setup Reference

## Step 1 — Read the theme's README first

Before writing any config, fetch and read the chosen theme's README from its GitHub repository. Themes vary significantly in:
- What config keys they expect in `hugo.toml`
- What `params` they support
- What `mainSections` or equivalent setting controls which content appears on the home page (note whether it expects a singular or plural section name, e.g. `post` vs. `posts` — it must match your `content/` subdirectory or the home page will list nothing)
- Whether they use Hugo Pipes, asset bundling, or just static files
- Whether they require **Hugo Extended** (any theme that transpiles SCSS/SASS does) and/or a separate **Dart Sass** binary (themes whose SCSS uses the `dartsass` transpiler — e.g. Anatole — need it; Extended alone is not enough), or a **Node.js PostCSS toolchain** (themes that pipe CSS through `postCSS` / `css.PostCSS` — e.g. the Introduction theme — need it)
- Whether they require specific **output formats** — some themes hard-error without them (e.g. DoIt's built-in search needs `home = ["HTML", "RSS", "JSON"]` under `[outputs]` to produce its search index)
- What front matter fields they use (e.g. `description`, `summary`, `cover`, `tags`), and the **shape** they expect (some themes `range` over `author`, requiring it to be a YAML list rather than a plain string)

Do not guess theme config. Read its README, then write `hugo.toml` accordingly.

**Check the theme's Hugo version and build prerequisites before scaffolding.** Note the theme's minimum Hugo version (often declared as `min_version` in the theme's `theme.toml`) and whether it needs **Hugo Extended** — any theme that transpiles SCSS/SASS via Hugo Pipes (look for `toCSS` / `resources.Get "...scss"` in `layouts/partials/head.html`) requires the extended build. A plain (non-extended) Hugo aborts the build on the SCSS step with a `TOCSS` error. Confirm the Hugo that will build the site — both locally and in CI — is extended (`hugo version` should show `+extended`) before continuing.

**Hugo Extended is not the same as Dart Sass.** Extended bundles only **LibSass**; it does *not* include Dart Sass. If the theme's SCSS sets `"transpiler" "dartsass"` (grep the theme's `head.html` / partials for `dartsass`), you must install a separate Dart Sass binary even though `hugo version` already shows `+extended`. Verify with `hugo env`: it should list a `github.com/sass/dart-sass/...` line, not just `libsass`. Install options:

- **macOS (standalone, no extra taps):** download the latest `dart-sass-<version>-macos-<arch>.tar.gz` from <https://github.com/sass/dart-sass/releases>, extract it, and put the `sass` executable on your `PATH` (keep it alongside its sibling `src/` folder — the binary is a wrapper that needs it).
- **Linux/CI:** do the same with the matching `linux-<arch>` archive, or use the theme/Hugo documented install. In GitHub Actions, add a step that downloads Dart Sass and adds it to `PATH` before `hugo --minify`.

**Some themes need a Node.js PostCSS toolchain instead of (or in addition to) Dart Sass.** If the theme pipes CSS through `postCSS` or `css.PostCSS` (grep its partials for `postCSS`), Hugo shells out to the `postcss` binary at build time. You must run `npm install` (or add a `package.json`) at the **site root** providing `postcss`, `postcss-cli`, and whatever plugins the theme uses (commonly `autoprefixer`) — the theme's own `package.json` lists them. Without it the build fails with `POSTCSS: ... binary with name "postcss" not found in PATH`.

- **Node version matters.** Recent Hugo runs the PostCSS process inside Node's permission sandbox (it injects `--permission --allow-fs-read=...`). That flag was only stabilized in **Node v20.16 / v22**; on older Node 20.x you get a cryptic `node: bad option: --permission` even though PostCSS is installed. Use Node ≥ 20.16 (Node 22 LTS is safest); with nvm, `nvm use 22`.
- **In CI:** add a Node setup step (e.g. `actions/setup-node` pinned to a SHA, Node 22) and an `npm ci` before `hugo --minify`, mirroring the local toolchain.

Gotcha: a missing CSS toolchain is often **masked in one build mode but not the other** — themes branch on `hugo.IsProduction` or `hugo.IsServer`, so the failure can show up only under `hugo server` (Anatole's Dart Sass) *or* only under a one-shot `hugo` build (Introduction's PostCSS), not both. Don't treat a passing build in one mode as proof the toolchain is present; confirm SCSS via `hugo env` (look for a `dart-sass` line) and test an actual production `hugo` build for PostCSS themes.

**With feature-rich themes, start from a minimal config and get a clean compile first; layer the bells & whistles on afterward.** Themes like DoIt ship a huge example config (hundreds of lines of params for search, comments, analytics, PWA, social, galleries, etc.), but they also ship internal defaults, so a tiny `hugo.toml` — theme, `[outputs]` (if the theme requires one, see above), `[permalinks]`, `[taxonomies]`, and a handful of `[params]` — is usually enough to build. Do **not** copy the entire example `params.toml` up front: it pulls in optional integrations that need credentials or extra assets and turns a quick compile into a debugging session. Get the site building and rendering content, then enable individual features with the user as they ask for them.

**For a multilingual theme, keep `defaultContentLanguageInSubdir = false`.** Many popular themes (e.g. Stack, Blowfish) are i18n-driven and expect a `[languages]` block with `defaultContentLanguage`. The content the converter produces carries **no language suffix**, so Hugo treats it as the default language — which is what you want. The critical setting is `defaultContentLanguageInSubdir`: leave it `false` so default-language pages render at the site root (`/posts/<slug>/`) and the original Medium-URL aliases keep resolving. Flipping it to `true` relocates every default-language page under `/<lang>/` (e.g. `/en/posts/<slug>/`) and **breaks every root-level alias** the migration depends on. (Hugo still emits a small `/<lang>/index.html` home and per-language sitemap even when the flag is `false` — that's harmless; the posts and their aliases stay at the root.) Use the current language keys `locale` and `label`, not the deprecated `languageCode`/`languageName`. Only add a second language block if the user actually has translated content; an empty extra language just produces a near-empty `/<lang>/` section.

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

## Step 7 — Install the theme (git submodule or Hugo Module)

Do not copy theme files into the repo. Install the theme one of two ways, and use the method the theme's README recommends — some themes (e.g. Blowfish, Congo) are distributed primarily as Hugo Modules and may not vendor cleanly as a submodule.

**Option A — git submodule (default, no Go required).** Adds the theme under `themes/` and sets `theme = "THEME_NAME"` in your config:

```bash
git submodule add THEME_GITHUB_URL themes/THEME_NAME
```

Document this in `README.md` with instructions for new clones:

```bash
git submodule update --init --recursive
```

**Option B — Hugo Module (requires Go installed).** The theme is fetched into Hugo's module cache instead of `themes/`. There is **no `theme =` line**; you declare the import in config and let Hugo pull it:

```toml
# hugo.toml
[module]
  [[module.imports]]
    path = "github.com/OWNER/THEME"   # often versioned, e.g. github.com/nunocoracao/blowfish/v2
```

```bash
hugo mod init github.com/OWNER/YOUR_SITE   # creates go.mod
hugo mod get github.com/OWNER/THEME        # writes go.sum, fetches into the module cache
```

Commit `go.mod` and `go.sum`. `themes/` stays empty (don't list it in `.gitignore` expecting theme files there). To update later, `hugo mod get -u`.

**Watch for a Hugo-version compatibility window.** Module themes can declare a *minimum and maximum* compatible Hugo version in their `theme.toml`/`go.mod`. If your Hugo is newer than the theme's tested ceiling, `hugo mod get` and every build print a non-fatal `Module "..." is not compatible with this Hugo version: X/Y` warning. It is usually safe to ignore, but if the build actually breaks, pin a Hugo version inside the supported window rather than fighting it. On this path the CI workflow must also install **Go** (in addition to Hugo) so `hugo --minify` can fetch the module — see the `setup-go` note in `cicd.md`/`github-pages.md`.

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
