# Content Migration Reference

## Part 1: Content Extraction & Inventory

### Step 1 — Unzip the Medium export

The Medium export ZIP contains a `posts/` directory with one HTML file per post/response/reply. File names follow the pattern:

```
YYYY-MM-DD_Post-Title-Slug-{hash}.html
```

The export includes **everything the user has ever published on Medium** — posts on their own blog, responses to other posts, contributions to other publications, and imported content from other platforms. You must filter to only the posts the user wants to migrate.

> **Multi-author publication?** Medium's "Download your information" export is per-account, so it cannot export a whole publication where many people published from their own accounts (e.g. a company engineering blog). If that's the situation, the user first runs the sibling [`medium-publication-export`](../../medium-publication-export/SKILL.md) skill, which scrapes the publication into a ZIP in exactly this format. Once they have that ZIP, continue here unchanged.

### Step 2 — Identify posts to migrate

List all files in `posts/` and cross-reference against any inventory the user provides. If the user has no inventory, help them build one:

1. Extract the title and date from each HTML file's `<title>` tag and `<time class="dt-published">` element
2. Present the full list to the user
3. Ask them to confirm which posts belong to their blog (vs. responses, contributions to other pubs, etc.)

> **Skip drafts.** Medium's personal export names unpublished drafts `draft_<Title>-<hash>.html`. Draft files have no `<time class="dt-published">` element, so they are not published posts and the converter in Part 2 will reject them (it raises an error naming the draft). Exclude every `draft_`-prefixed file when building the inventory and the `posts` list below.

### Step 3 — Build the post inventory

Create a table with these columns and confirm it with the user before proceeding to Part 2:

| Title | Date | Medium URL | Has embeds? |
|---|---|---|---|

To get the canonical Medium URL for each post, look for:
```html
<a class="p-canonical" href="https://...">
```

Note any posts that contain `<iframe>` elements (the converter turns these into a video embed — a `video` shortcode on Hugo and Eleventy, raw responsive `<iframe>` HTML on Astro). You do not need to track `<img>` tags by hand — the conversion script in Part 2 downloads remote images and rewrites their references automatically.

### Step 4 — Embedded images (handled automatically)

Images hosted on Medium's CDN (`miro.medium.com`, `cdn-images-*.medium.com`) or any other external URL are self-hosted automatically by `scripts/convert_medium.py` in Part 2: each remote image is downloaded into the SSG's static/passthrough images folder (`hugo-site/static/images/` for Hugo, `eleventy-site/public/images/` for Eleventy, `astro-site/public/images/` for Astro — set by the script's `STATIC_DIR`) and its Markdown reference is rewritten to a local `/images/<file>` path, so the migrated site keeps working even after Medium's CDN stops serving them. No manual downloading or reference-fixing is required.

The converter prints an image summary when it finishes (e.g. `Images: 12 downloaded, 0 reused, 0 failed`). If a download fails (network issue, deleted asset), that image keeps its original remote URL so nothing is lost, the failure is counted, and you can re-run the script to retry. To skip self-hosting entirely and keep all remote URLs, set `DOWNLOAD_IMAGES = False` at the top of the script.

---

## Part 2: Content Migration (HTML → Markdown)

### Step 1 — Run the conversion script

Use `scripts/convert_medium.py`. Before running it:

- Set **`SSG`** at the top of the script to match the generator chosen in `migration-status.md`: `"hugo"` (default), `"eleventy"`, or `"astro"`. This controls only the per-post front matter and the video-embed syntax; the rest of the conversion is identical.
- Edit the **`posts`** list to include only the confirmed posts from your inventory, mapping each HTML filename to its intended clean slug (title without the Medium hash suffix).
- For **Eleventy**, also point `OUTPUT_DIR` at the starter's posts directory (`eleventy-site/content/blog`) and `STATIC_DIR` at its passthrough root (`eleventy-site/public`); the defaults target Hugo's `hugo-site/`. See `references/eleventy-setup.md`.
- For **Astro**, point `OUTPUT_DIR` at the content-collection directory (`astro-site/src/content/blog`) and `STATIC_DIR` at the public root (`astro-site/public`). See `references/astro-setup.md`.

```bash
python3 scripts/convert_medium.py
```

Output files are written to `OUTPUT_DIR` (default `hugo-site/content/posts/` for Hugo; `eleventy-site/content/blog/` for Eleventy; `astro-site/src/content/blog/` for Astro).

### Step 2 — Understand the front matter format

The script generates front matter in this format (the canonical-URL field depends on `SSG`):

```yaml
---
title: "Post Title Here"
date: 2024-01-15                  # Astro writes `pubDate:` instead of `date:`
author: "Author Name"
slug: "post-title-here"          # Hugo & Astro: clean URL path under /posts/
# permalink: "/posts/post-title-here/"   # Eleventy writes this line instead of slug
aliases:
  - /post-title-here-a1b2c3d4e5f6
tags:
  - "Engineering"
  - "Open Source"
---
```

For **Hugo**, `slug` is the clean URL path under `/posts/`, and the `aliases` value (the full Medium-style slug, title + hash) is one Hugo creates a redirect page for automatically. For **Eleventy** the script writes an explicit `permalink: "/posts/<slug>/"` instead of `slug:` (its prefix comes from the script's `PERMALINK_PREFIX`), and the same `aliases` field is consumed by the redirects template described in `references/eleventy-setup.md` to produce the equivalent stub pages. For **Astro** the script writes `slug:` (like Hugo) plus `pubDate:` instead of `date:` (matching the content-collection schema), and the same `aliases` field is consumed by the catch-all redirect route described in `references/astro-setup.md`. Either way the canonical URL is `/posts/<slug>/` and the old Medium URL keeps resolving.

`author:` and `tags:` are optional and only appear when the source provides them. A personal Medium "Download your information" export carries no tags, so `tags:` is omitted for those posts; content captured with the `medium-publication-export` skill recovers each post's topic tags and the converter writes them here. To omit tags even when they're available, set `EXTRACT_TAGS = False` at the top of `convert_medium.py`.

### Step 3 — Review each converted post

Open each output `.md` file and verify:
- Title and date are correct
- Body content rendered cleanly (no leftover HTML tags)
- Links are intact
- Bold and italic formatting is preserved
- Any lists are properly formatted
- **No Medium promo CTAs remain** — `convert_medium.py` strips Medium's inline subscribe / membership widgets ("Get \<author\>'s stories in your inbox", "Join Medium for free", "Sign up … Medium", "By signing up, you will create a Medium account …"). These most commonly appear in content captured with the `medium-publication-export` skill, but can occur from any source. If you still see any such CTA text in a converted file (Medium occasionally changes the wording), remove that block manually and add the new phrase to the `_CTA_PATTERNS` list in `convert_medium.py`, then re-run.
- **No leading byline chrome remains** — content captured from a live page (via the `medium-publication-export` skill) can prepend the on-page byline (author name, "N min read", and the publish date) to the body. `convert_medium.py` detects and removes that leading block, so the post should start at its real first paragraph. Personal "Download your information" exports don't include this, so it's a no-op for them. If a stray "N min read" line survives at the top of a converted file, delete it manually.

### Step 4 — Handle embedded media

If a post contains an `<iframe>` (e.g. a YouTube or Vimeo embed), the script converts it to a video embed whose form depends on `SSG`.

**Hugo** emits:

```
{{< video src="IFRAME_SRC_URL" >}}
```

which requires a custom Hugo shortcode at `hugo-site/layouts/shortcodes/video.html`:

```html
<div class="video-embed">
  <iframe
    src="{{ .Get "src" }}"
    frameborder="0"
    allow="autoplay; fullscreen; picture-in-picture"
    allowfullscreen
    style="width: 100%; aspect-ratio: 16/9;"
  ></iframe>
</div>
```

**Eleventy** emits `{% video "IFRAME_SRC_URL" %}` instead, which requires an `addShortcode("video", …)` in `eleventy.config.js` — see Step 6 of `references/eleventy-setup.md` for the definition.

**Astro** has no shortcode mechanism in plain Markdown, so the script emits the rendered responsive `<iframe>` HTML inline (`<div class="video-embed"><iframe src="IFRAME_SRC_URL" …></iframe></div>`). Astro passes raw HTML through, so nothing extra is required — see Step 6 of `references/astro-setup.md`.

### Step 5 — Handle internal cross-links

If any post links to another post using its old Medium URL (e.g. `https://yourdomain.com/post-title-a1b2c3d4`), these will continue to work after migration because the `aliases` field creates redirect pages at those paths. No manual link-fixing is required.

> **Publication that lost its Medium custom domain?** The same mechanism still applies. Each post's `aliases` carries its original slug (`/post-title-a1b2c3d4`), so pointing that domain's DNS at the new site during cutover makes every old link resolve again — even if Medium disconnected the domain first (the publication stays at `medium.com/<pub>`). The slug is identical whether the `medium-publication-export` skill scraped the live custom domain or the `medium.com/<pub>` home, so no extra work is needed here.

### Step 6 — Confirm and update status

Show the user a summary of all converted posts. Confirm each converted file looks correct. Mark Phase 2 complete in `migration-status.md` and list all created files.
