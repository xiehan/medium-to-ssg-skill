# Scraping Strategy Reference

This document explains how to enumerate and capture every post in a Medium publication, and how to handle the ways Medium makes that hard.
The companion `scripts/scrape_publication.py` implements the automated paths; `references/bookmarklets.md` covers the manual fallbacks.

## The core problem

Medium's account export (**Settings → Security and apps → Download your information**) only returns the logged-in user's own posts.
A multi-author publication has no account that owns every post, and Medium offers no publication-level export.
So you reconstruct the export by (1) finding every post URL and (2) capturing each post's content, then (3) repackaging into the export format.

## The custom-domain deadline

Medium used to serve publication custom domains for free but now requires a paid membership to keep one, with a hard cutoff (June 11, 2026) and **no grandfathering** of existing domains.
Per Medium's notice, if you don't migrate by the deadline they **disconnect the custom domain** and the publication **stays available at `https://medium.com/<pub>`**. The content never disappears — after the cutoff the custom domain just stops resolving and `medium.com/<pub>` becomes the canonical home.

So the content is always reachable: scrape the custom domain while it's still live, or `medium.com/<pub>` once it's been disconnected. What changes is where you enumerate and fetch from, and how you keep the *original* links alive.

### Why the original links still survive

`medium-to-ssg` builds each Hugo redirect alias from the **last path segment** of a post's canonical URL — the slug, e.g. `the-title-1a2b3c4d5e6f`. The alias is a path (`/the-title-1a2b3c4d5e6f`), not a full URL, and the migrated site is served at the original domain. The publication slug is **identical** on the custom domain and on `medium.com/<pub>`, so scraping from `medium.com/<pub>` produces the same alias and `https://mycompany.blog/the-title-1a2b3c4d5e6f` keeps resolving — **regardless of which host you scraped it from**. In other words, URL preservation is automatic; the slug is what matters, not the domain.

### Pinning the original domain when scraping medium.com

Pass the original domain with `--canonical-base` to re-home every emitted post's `p-canonical` to `https://mycompany.blog/<slug>`. This isn't what makes the alias correct (the slug already does that) — it keeps the **export faithful**, so the exported canonical and the `manifest.csv` record the real public URLs rather than `medium.com` mirrors:

```bash
python3 scripts/scrape_publication.py --urls urls.txt --canonical-base https://mycompany.blog
```

The genuine edge case is the bare-hash URL form `https://medium.com/p/<hash>` (no title slug). Its last segment is just `<hash>`, so the alias comes out as `/<hash>` instead of `/<title>-<hash>` — and `--canonical-base` can't recover the missing title (it only swaps the domain, not the slug). Watch for `/p/<hash>` entries when reviewing `urls.txt`; have the user open those posts and capture them with the **save-post bookmarklet** (run on the rendered page, it records the real title slug) so the alias comes out right.

**Best practice:** if the custom domain is still live, scrape it now — before the deadline — and the canonicals are already correct without `--canonical-base`.

## Phase A — Enumerate every post URL

Try these in order. Stop when you have a complete, deduplicated list of post URLs.

### 1. Sitemap (preferred — automated, no login)

Most Medium publications publish an XML sitemap. For a custom domain it's usually:

```
https://<domain>/sitemap/sitemap.xml
```

…which is a *sitemap index* pointing at one or more child sitemaps (`posts`, `tags`, `users`, …).
The script fetches the index, follows the child sitemaps, and keeps only URLs that look like posts.

Run:

```bash
python3 scripts/scrape_publication.py --site https://mycompany.blog --enumerate-only
```

It writes `urls.txt` and prints a count. **Review it with the user**: post URLs on a Medium publication end in a hyphen + a short hash, e.g. `https://mycompany.blog/the-title-1a2b3c4d5e6f`. Tag pages (`/tag/...`), author pages (`/@user`), and the archive (`/archive/...`) are *not* posts and should not be in the list. The script filters these out, but eyeball the result.

If the sitemap 404s or is obviously incomplete (far fewer posts than the user expects), move to the bookmarklet.

### 2. Enumeration bookmarklet (when the sitemap fails)

The publication's **archive** page (`https://<domain>/archive`) lists every post, but it infinite-scrolls and is rendered by JavaScript, so a plain HTTP fetch sees almost nothing.
The enumeration bookmarklet runs *in the user's logged-in browser*: it auto-scrolls/expands the archive until everything is loaded, collects the post links, deduplicates them, and downloads a `urls.txt`.

See `references/bookmarklets.md` for the bookmarklet and step-by-step instructions.
Place the resulting `urls.txt` in the output directory and continue with `--urls`.

> **Custom domain disconnected?** If Medium has already disconnected the custom domain (the publication now lives only at `medium.com/<pub>`), run the enumeration bookmarklet on the **`medium.com/<pub>` archive** instead (e.g. `https://medium.com/my-pub/archive`). You'll collect `medium.com` URLs; capture them with `--canonical-base https://mycompany.blog` so the export records the original links (see "The custom-domain deadline" above).

### 3. Archive crawl (last resort)

If neither works, you can walk the date-based archive (`/archive/YYYY`, `/archive/YYYY/MM`, `/archive/YYYY/MM/DD`). This is slower and more fragile than the sitemap or bookmarklet, and is only worth it when both of those fail. Prefer the bookmarklet — it uses the real rendered page and the user's session.

The RSS feed (`https://<domain>/feed`) only returns roughly the latest 10 posts, so it's useful as a quick connectivity test but never as the full enumeration.

## Phase B — Capture each post

### Automated fetch (default)

```bash
python3 scripts/scrape_publication.py --urls urls.txt     # or --site for sitemap mode
```

For each URL the script:

1. Fetches the post HTML with a real User-Agent and a polite delay (default ~1s; tune with `--delay`).
2. Extracts metadata from the page's structured data (`<script type="application/ld+json">`) with `<meta>`/`<title>` fallbacks: title, publish date, author, canonical URL.
3. Finds the article body (the densest content container under `<article>`), strips non-content cruft (scripts, buttons, share widgets, the duplicated title), and normalizes images.
4. Writes an export-format HTML file to `posts/<date>_<slug>.html` (see `references/export-format.md`).
5. Records the result in `manifest.csv`.

It **skips posts already written**, so re-running after an interruption resumes where it left off.

### When fetching is blocked or renders badly

Medium may return 403/429 to automated requests, or a post may be member-only.
Don't fight the access controls. Instead, capture those posts from the logged-in browser with the **save-post bookmarklet**: open each problem post, run the bookmarklet, and it saves the fully-rendered article HTML (including the structured-data metadata) to your downloads.
Drop those files in `medium-export-out/inbox/` and normalize them with the same pipeline:

```bash
python3 scripts/scrape_publication.py --inbox medium-export-out/inbox
```

The inbox normalizer produces identical export-format output — it just reads already-saved HTML instead of fetching.

## Handling tricky content

- **Member-only / paywalled posts.** Only the logged-in browser can see the full content. Use the save-post bookmarklet. Never try to bypass the paywall programmatically.
- **Code blocks.** Medium wraps code in `<pre>`; the converter preserves it as a fenced block. Language hints are usually lost — acceptable, and easy to add later in Markdown.
- **Embeds (YouTube, gists, tweets).** Video `<iframe>`s inside a `<figure>` become a Hugo `video` shortcode downstream. Other embeds may flatten to a link; note them in the manifest so the user can revisit.
- **Images.** Left as remote `cdn-images-1.medium.com` / `miro.medium.com` URLs, matching the real export. `medium-to-ssg` downloads and self-hosts them later.
- **Duplicate URLs.** Posts can appear under multiple paths (with/without query strings, with a `?source=` suffix). The script normalizes and deduplicates by stripping queries and trailing slashes.

## Rate limiting & etiquette

- Keep the default delay between requests; raise it (`--delay 2`) if you see 429s.
- On repeated 403/429 the script backs off and then records the post as needing manual capture rather than hammering the server.
- Identify with a normal browser User-Agent; don't spoof Googlebot or other crawlers.
- Only run this against a publication the user owns or is authorized to migrate.
