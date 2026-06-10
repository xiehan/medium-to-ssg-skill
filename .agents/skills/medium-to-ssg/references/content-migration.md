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

### Step 3 — Build the post inventory

Create a table with these columns and confirm it with the user before proceeding to Part 2:

| Title | Date | Medium URL | Has embeds? |
|---|---|---|---|

To get the canonical Medium URL for each post, look for:
```html
<a class="p-canonical" href="https://...">
```

Note any posts that contain `<iframe>` elements (these need a video shortcode). You do not need to track `<img>` tags by hand — the conversion script in Part 2 downloads remote images and rewrites their references automatically.

### Step 4 — Embedded images (handled automatically)

Images hosted on Medium's CDN (`miro.medium.com`, `cdn-images-*.medium.com`) or any other external URL are self-hosted automatically by `scripts/convert_medium.py` in Part 2: each remote image is downloaded into `hugo-site/static/images/` and its Markdown reference is rewritten to a local `/images/<file>` path, so the migrated site keeps working even after Medium's CDN stops serving them. No manual downloading or reference-fixing is required.

The converter prints an image summary when it finishes (e.g. `Images: 12 downloaded, 0 reused, 0 failed`). If a download fails (network issue, deleted asset), that image keeps its original remote URL so nothing is lost, the failure is counted, and you can re-run the script to retry. To skip self-hosting entirely and keep all remote URLs, set `DOWNLOAD_IMAGES = False` at the top of the script.

---

## Part 2: Content Migration (HTML → Markdown)

### Step 1 — Run the conversion script

Use `scripts/convert_medium.py`. Before running it, edit the `posts` list at the top of the script to include only the confirmed posts from your inventory, mapping each HTML filename to its intended clean slug (title without the Medium hash suffix).

```bash
python3 scripts/convert_medium.py
```

Output files are written to `hugo-site/content/posts/`.

### Step 2 — Understand the front matter format

The script generates front matter in this format:

```yaml
---
title: "Post Title Here"
date: 2024-01-15
slug: "post-title-here"
aliases:
  - /post-title-here-a1b2c3d4e5f6
---
```

The `slug` is the clean URL path under `/posts/`. The `aliases` value is the full Medium-style slug (title + hash), which Hugo will create a redirect page for automatically.

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

If a post contains an `<iframe>` (e.g. a YouTube or Vimeo embed), the script converts it to:

```
{{< video src="IFRAME_SRC_URL" >}}
```

This requires a custom Hugo shortcode. Create `hugo-site/layouts/shortcodes/video.html`:

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

### Step 5 — Handle internal cross-links

If any post links to another post using its old Medium URL (e.g. `https://yourdomain.com/post-title-a1b2c3d4`), these will continue to work after migration because the `aliases` field creates redirect pages at those paths. No manual link-fixing is required.

> **Publication that lost its Medium custom domain?** The same mechanism still applies. Each post's `aliases` carries its original slug (`/post-title-a1b2c3d4`), so pointing that domain's DNS at the new site during cutover makes every old link resolve again — even if Medium disconnected the domain first (the publication stays at `medium.com/<pub>`). The slug is identical whether the `medium-publication-export` skill scraped the live custom domain or the `medium.com/<pub>` home, so no extra work is needed here.

### Step 6 — Confirm and update status

Show the user a summary of all converted posts. Confirm each converted file looks correct. Mark Phase 2 complete in `migration-status.md` and list all created files.
