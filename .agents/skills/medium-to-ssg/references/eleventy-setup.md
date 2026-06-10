# Eleventy Site Setup Reference

This is the Eleventy counterpart to `hugo-setup.md`. Read it instead of (not in addition to) `hugo-setup.md` when the chosen SSG is **Eleventy**. Hugo remains the default; only follow this file when the user explicitly chose Eleventy.

Eleventy (11ty) is a Node.js static site generator. Unlike Hugo there is **no central theme gallery** and no single binary — a site is an npm project, and the closest equivalent to a "theme" is a **starter repository** you clone and own. This skill standardizes on the official [`eleventy-base-blog`](https://github.com/11ty/eleventy-base-blog) starter as the default; the user may pick a different starter, but the steps below assume the base blog's conventions and you must re-read the chosen starter's README if it differs.

The converter (`scripts/convert_medium.py`) must be run with `SSG = "eleventy"` for this path. That changes only the per-post front matter (`permalink:` instead of `slug:`) and the video embed (`{% video %}` instead of `{{< video >}}`); everything else it produces is identical to the Hugo path.

## Step 1 — Clone the starter into `eleventy-site/`

Create the Eleventy project by cloning the starter into `eleventy-site/` (the Eleventy parallel to `hugo-site/`). Clone, then drop the starter's git history so it becomes part of the user's own repository:

```bash
git clone https://github.com/11ty/eleventy-base-blog.git eleventy-site
rm -rf eleventy-site/.git
rm -f eleventy-site/.github/workflows/gh-pages.yml.sample
```

The base blog ships a sample GitHub Pages workflow at `.github/workflows/gh-pages.yml.sample`. Delete it: this skill generates its own deployment workflow in Phase 5 (Content Deployment) — see `references/github-pages.md` or `references/cicd.md` — and leaving the starter's sample in place only invites confusion about which workflow is authoritative.

If the user supplied a different starter, clone that instead and read its README before continuing — the directory names, config filename, and passthrough setup below may all differ. Remove any equivalent sample deploy workflow it ships for the same reason.

## Step 2 — Pin Node and install dependencies

Eleventy is Node software, so a compatible Node.js version is the first prerequisite (the analog of "Hugo Extended" on the Hugo path). The starter ships an `.nvmrc` declaring the Node version it is tested against — **read it and use that version** rather than guessing one:

```bash
cd eleventy-site
nvm use            # reads .nvmrc; install that version first with `nvm install` if needed
npm install
```

The same Node version must be used locally and in CI (Stage/Phase: Content Deployment wires `actions/setup-node` to match — see `references/cicd.md` / `references/github-pages.md`). A mismatch between local and CI Node is the most common cause of "builds for me, fails in CI" on this path.

Because the site is now an npm project, Phase 5 (Content Deployment) also adds a `package-ecosystem: npm` entry to `.github/dependabot.yml` so Eleventy and its plugins stay patched. This happens on **every** hosting platform and deployment method, including the manual AWS CLI path that generates no workflows — see "Eleventy: also track npm dependencies" in `references/cicd.md`.

## Step 3 — Configure site metadata

The base blog keeps site-wide settings in `_data/metadata.js` (read the file; a different starter may use `_data/metadata.json` or another name). Set at least the title, the production URL, the description, and the author. The `url` must be the final custom domain — it is what the feed and any absolute links use:

```js
// _data/metadata.js
export default {
  title: "SITE_TITLE",
  url: "https://DOMAIN/",
  language: "en",
  description: "SITE_DESCRIPTION",
  author: {
    name: "YOUR_NAME",
    email: "",
    url: "https://DOMAIN/about/",
  },
};
```

Ask the user to confirm the site title, their name, and the description before writing this file. Do not invent an email — leave it blank unless the user provides one. (The base blog indents its own source files with **tabs** and warns against spaces; the snippets here use spaces only to satisfy this repo's Markdown linter — match the surrounding file's indentation when you actually edit `eleventy.config.js` / `_data/metadata.js`.)

## Step 4 — Decide where posts live and which URL they get

Two settings must agree across three places — the converter and the Eleventy project — or posts will 404 or land at the wrong URL:

| Concept | Converter setting | Eleventy side |
|---|---|---|
| Where the `.md` files are written | `OUTPUT_DIR` | the posts directory (base blog: `content/blog/`) |
| The canonical post URL prefix | `PERMALINK_PREFIX` (default `/posts`) | each post's `permalink:` front matter |

Set the converter's `OUTPUT_DIR = "eleventy-site/content/blog"` so converted posts land in the starter's blog directory. The base blog tags everything in `content/blog/` with the `posts` collection tag and applies the post layout via a **directory data file** (`content/blog/blog.11tydata.js`) — read it to confirm the tag name and layout. Because the converted posts inherit that directory data, you do **not** add a `layout:` to each post.

The converter writes an explicit `permalink: "/posts/<slug>/"` into every post (built from `PERMALINK_PREFIX`). This intentionally **overrides** whatever default permalink the starter's directory data file would assign (the base blog would otherwise serve posts under `/blog/`), so the canonical URLs match the Hugo path's `/posts/:slug/` default. If the user wants a different prefix (e.g. `/archive/`), change `PERMALINK_PREFIX` in the converter **before** running it — there is no separate `[permalinks]` block to keep in sync as there is in Hugo, because each post carries its own `permalink`.

### Tags: the data-cascade merge

Each converted post may carry Medium topic tags in its front matter (`tags: [...]`). The starter's directory data file also assigns `tags: ["posts"]`. Eleventy's **deep data merge** (on by default since v1.0) *concatenates* arrays across the data cascade, so a post ends up tagged both `posts` (from the directory data file) and its own topic tags — it stays in the blog collection and also generates tag pages. After the first build, verify every converted post appears in the blog listing. If any post is missing from the listing, the cause is almost always that it lost the `posts` tag; the fix is to ensure the directory data file's tag is preserved (do not let a post's front matter replace it).

## Step 5 — Self-hosted images passthrough

The converter downloads remote images into `STATIC_DIR/images` and rewrites references to site-root paths like `/images/<file>` (identical to the Hugo path). For that path to resolve, `STATIC_DIR` must point at the folder the starter **passthrough-copies to the site root**.

In the base blog that folder is `public/` — read its `eleventy.config.js` to confirm (look for `addPassthroughCopy`; the README states the `public` folder is copied to the output root, so `public/images/foo.jpg` is served at `/images/foo.jpg`). Set the converter's `STATIC_DIR = "eleventy-site/public"` and keep `IMAGE_DIR_NAME = "images"`. If the chosen starter passes a different folder through to the root, point `STATIC_DIR` there instead so the `/images/...` references still resolve.

## Step 6 — Add the `video` shortcode

When a post embeds a video, the converter emits `{% video "https://..." %}`. Define that universal shortcode in `eleventy.config.js` so it renders to an iframe (the analog of Hugo's `layouts/shortcodes/video.html`). Add it inside the config's exported function:

```js
// eleventy.config.js — inside the default export, alongside the other addX calls
eleventyConfig.addShortcode("video", function (src) {
  return `<div class="video-embed"><iframe src="${src}" title="Embedded video" loading="lazy" allow="fullscreen" allowfullscreen></iframe></div>`;
});
```

Two things make this work, and both are worth verifying:

- **Shortcodes run inside Markdown.** Eleventy only expands `{% video %}` in a `.md` file if that file is processed by a template engine. The base blog leaves `markdownTemplateEngine` enabled, and the `{% ... %}` syntax is identical in both Liquid and Nunjucks, so the shortcode runs either way. If you ever see a literal `{% video ... %}` in the built HTML, the starter has set `markdownTemplateEngine: false` — set it to `"njk"` in `eleventy.config.js` to re-enable shortcode processing in Markdown.
- **Raw HTML passes through.** Eleventy's Markdown library (markdown-it) runs with `html: true` by default, so the iframe HTML the shortcode returns renders as markup rather than being escaped. (This is the opposite of Hugo's Goldmark, which drops raw HTML unless `unsafe = true`. The converter's escaping of stray angle brackets in prose is harmless here — escaped entities simply render as the literal characters, which is the intent.)

Add a little CSS for `.video-embed` to `public/css/` (or the starter's CSS entry) if you want responsive sizing; it is not required for the embed to work.

## Step 7 — Preserve old Medium URLs (aliases → redirect stubs)

This is the most important step on the Eleventy path, and the one with no built-in equivalent. On Hugo, the `aliases:` front matter field automatically generates a `<meta http-equiv="refresh">` stub at each old URL. Eleventy has no such feature, so this skill **builds the same behavior with a few lines of core Eleventy** — deliberately **without a community plugin**.

### Why a template instead of a plugin

URL preservation is the migration's central promise: every old Medium link (`/post-title-a1b2c3d4e5f6`) must keep resolving forever. Community redirect plugins (e.g. `eleventy-plugin-redirectfrom`) can do this in fewer lines, but a third-party plugin is a long-term liability for a set-and-forget blog: it can fall out of maintenance and break on a future Eleventy major release (e.g. a v4.0), at which point the *redirects themselves* — the thing users most need to never break — would silently stop building. The approach below depends only on **core, long-stable Eleventy APIs** (`addCollection`, pagination, and `permalink`), which have been present and stable since Eleventy v1/v2 and remain so in v3. It produces plain static HTML stubs that work on any host (S3 + CloudFront, GitHub Pages) with no server config, exactly like Hugo's aliases. If a future Eleventy release ever changes one of these core APIs, the fix lives in two small files you own and can read in full — not in an unmaintained dependency.

### 7a — Flatten posts into redirect pairs (collection)

The converter writes one alias per post today, but a user may add more by hand later, so handle *zero or many* aliases per post. Add this collection to `eleventy.config.js` (inside the default-exported function):

```js
// eleventy.config.js — builds a flat list of { from, to } redirect pairs.
// `from` is an old Medium URL path; `to` is the post's current canonical URL.
eleventyConfig.addCollection("redirects", (collectionApi) => {
  const redirects = [];
  for (const page of collectionApi.getAll()) {
    const aliases = page.data.aliases;
    if (!aliases) continue;
    for (const from of [].concat(aliases)) {
      if (from) redirects.push({ from, to: page.url });
    }
  }
  return redirects;
});
```

`[].concat(aliases)` accepts both a single string and a list, and `page.url` is the canonical URL Eleventy assigns from the post's `permalink:` (e.g. `/posts/my-post/`). Posts without an `aliases` field are skipped.

> **Keep `redirects` out of the tag listing.** The base blog auto-generates a tag page for every key in `collections`, so a named collection like `redirects` would otherwise show up as a bogus tag (a `/tags/redirects/` page plus a "redirects" entry on the all-tags page). Exclude it the same way the starter already excludes `all` and `posts`, in **two** places:
>
> - In `_config/filters.js`, add `"redirects"` to the `filterTagList` exclusion array:
>
>   ```js
>   return (tags || []).filter(tag => ["all", "posts", "redirects"].indexOf(tag) === -1);
>   ```
>
> - In `content/tag-pages.njk`, add `"redirects"` to the pagination `filter` list:
>
>   ```js
>   filter: ["all", "posts", "redirects"],
>   ```
>
> (Exact filenames may differ slightly between starter versions — search the starter for the existing `["all", "posts"]` list and add `"redirects"` everywhere it appears.)

### 7b — Emit one redirect stub per pair (template)

Create `eleventy-site/content/redirects.njk`. It paginates over the collection one entry at a time and writes a refresh stub at each old path. `eleventyExcludeFromCollections: true` keeps these stub pages out of the blog listing, tag pages, and sitemap:

```njk
---
pagination:
  data: collections.redirects
  size: 1
  alias: redirect
permalink: "{{ redirect.from }}/index.html"
eleventyExcludeFromCollections: true
---
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url={{ redirect.to }}">
    <link rel="canonical" href="{{ redirect.to }}">
    <meta name="robots" content="noindex">
    <title>Redirecting…</title>
  </head>
  <body>
    <p>This page has moved to <a href="{{ redirect.to }}">{{ redirect.to }}</a>.</p>
  </body>
</html>
```

How this maps to Hugo's aliases, stub for stub:

- The converter wrote `aliases: [ /post-title-a1b2c3d4e5f6 ]` into each post (leading slash, no trailing slash — the original Medium path).
- `permalink: "{{ redirect.from }}/index.html"` outputs `_site/post-title-a1b2c3d4e5f6/index.html`. That directory-with-`index.html` shape serves the page for both `/post-title-…` and `/post-title-…/`, the same way Hugo's alias output does — so it resolves on S3 + CloudFront (with the directory-rewrite function) and on GitHub Pages without any extra config.
- The `<meta http-equiv="refresh">` plus `<link rel="canonical">` is byte-for-byte the behavior of a Hugo alias page: instant client-side redirect, canonical pointing at the real post, and `noindex` so search engines consolidate on the canonical URL.

### 7c — Verify

After a build (Step 10), confirm a stub exists and points to the right place, e.g.:

```bash
cat _site/post-title-a1b2c3d4e5f6/index.html   # use a real alias from a converted post
```

It must contain the `meta refresh` to the post's `/posts/<slug>/` URL. Do this for at least one post before considering the path done — a broken alias is the highest-impact failure in the whole migration.

## Step 8 — Confirm the canonical base URL

Make sure the site's production URL is set to the custom domain (Step 3's `metadata.url`) and that the post layout emits a `<link rel="canonical">` (the base blog's `post.njk` already does). For deploying to a subpath the base blog uses Eleventy's HTML `<base>` plugin, but a root-domain blog (the normal case here) needs no special handling — the apex domain is the base.

## Step 9 — `.gitignore`

Ensure the Eleventy build output and Node modules are ignored (the starter's `.gitignore` already lists these; confirm):

```gitignore
_site/
node_modules/
```

## Step 10 — Build and test locally

Eleventy builds with Node, not a separate binary. Produce a one-shot production build (output goes to `_site/`) and also run the dev server to spot-check:

```bash
npx @11ty/eleventy            # production build -> _site/
npx @11ty/eleventy --serve    # local server with live reload
```

Verify:

- The home page lists the converted posts.
- At least one post renders correctly at its `/posts/<slug>/` URL.
- A redirect alias URL (e.g. `/post-title-a1b2c3d4e5f6`) redirects to the canonical post URL — test the built stub (Step 7c) and, ideally, the live redirect under `--serve`.
- Any `{% video %}` embed renders as an iframe, not as literal shortcode text.
- Images load from `/images/...` (i.e. the passthrough is wired correctly).

If Node/Eleventy is not available in the current environment, document these steps for the user to run themselves, exactly as the Hugo path documents `hugo server`.

## Step 11 — Confirm and update status

Confirm the Eleventy site structure with the user. Mark the Site Setup phase complete in `migration-status.md` and list all created files. Record the build command (`npx @11ty/eleventy`) and output directory (`_site/`) in `migration-status.md` — the hosting and deployment phases read those two values (the "SSG seam") instead of Hugo's `hugo --minify` / `public/`.

## Eleventy ⇄ Hugo quick reference

For cross-checking the two paths when wiring later phases:

| Concern | Hugo | Eleventy (base blog) |
|---|---|---|
| Project directory | `hugo-site/` | `eleventy-site/` |
| Config file | `hugo.toml` | `eleventy.config.js` |
| Posts directory | `content/posts/` | `content/blog/` |
| Build command | `hugo --minify` | `npx @11ty/eleventy` |
| Build output directory | `public/` | `_site/` |
| Static/passthrough root | `static/` → `/` | `public/` → `/` |
| Canonical post URL | `slug:` + `[permalinks]` | per-post `permalink:` |
| Old-URL preservation | `aliases:` (built in) | `aliases:` + redirects collection/template (Step 7) |
| Video embed | `{{< video >}}` shortcode | `{% video %}` shortcode |
| Raw HTML in Markdown | dropped unless `unsafe = true` | rendered (`html: true` by default) |
| Build toolchain | Hugo (Extended for SCSS) | Node.js (version from `.nvmrc`) |
