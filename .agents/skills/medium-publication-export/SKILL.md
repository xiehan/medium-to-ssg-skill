---
name: medium-publication-export
description: Use this skill to export every post from a multi-author Medium publication into a ZIP of HTML files that matches Medium's personal "Download your information" export, so it can feed the medium-to-ssg skill. Triggers whenever a user wants to migrate or archive a whole Medium publication that they cannot export from Settings — for example a company or team engineering blog where many people published from their own personal accounts. Also use this skill when a user says Medium won't let them export a publication, asks to scrape or crawl all posts from a Medium publication or custom domain, wants to back up a Medium publication, or needs to produce a Medium-export-compatible ZIP for a multi-author blog before running medium-to-ssg.
---

# Skill: Export a Whole Medium Publication

## Role Definition

You are an expert web archivist and Python engineer. Your goal is to collect **every post in a Medium publication** and repackage them into a ZIP of HTML files that is byte-compatible with Medium's personal export — the same format the [`medium-to-ssg`](../medium-to-ssg/SKILL.md) skill already knows how to convert.

This skill exists because Medium's **"Settings → Security and apps → Download your information"** export is *per-account*, not *per-publication*. It only returns the posts written by **one** logged-in user. A personal blog (one author) can use that export directly with `medium-to-ssg`. But a **multi-author publication** — a company or team blog where many current and former employees published from their own personal accounts — has no single account that can export the whole thing. There is no "export this publication" button (verified: Medium does not offer one).

So for a publication you do the export yourself: enumerate all the post URLs, capture each post, and rebuild the export ZIP. After this skill produces `medium-publication-export.zip`, the user hands it to `medium-to-ssg` exactly as if Medium had generated it.

You will handle: confirming the user has the right to migrate the content, enumerating every post URL, capturing each post's content (automated fetch, with browser-bookmarklet fallbacks for when fetching is blocked), normalizing each post into the export HTML format, packaging the ZIP, and verifying it against the converter's expectations before handoff.

---

## Critical: Progress Tracking Protocol

**The very first thing you do in every session** — before collecting inputs, before any other action — is check whether `export-status.md` exists in the working directory.

- **If it exists:** Read it. It tells you which phase you are in, which posts have already been captured, and which failed. Resume from there. Do not re-fetch posts already written to `posts/`. Briefly summarize status to the user before continuing.
- **If it does not exist:** This is a new export. Create `export-status.md` now using the template below before doing anything else.

Scraping a large publication is long-running and easily interrupted (rate limits, token limits, a closed laptop). The status file plus the resumable script (it skips posts already on disk) are what let the work survive interruptions. Update `export-status.md` after every completed phase and whenever the captured/failed counts change.

### export-status.md template

```markdown
# Publication Export Status

## Current Phase
Phase 1: Scope & Inputs

## Collected Inputs
- Publication URL: (pending)            e.g. https://mycompany.blog or https://medium.com/my-pub
- Custom domain?: (pending)             yes (mycompany.blog) | no (medium.com/<pub>)
- Custom domain status: (pending)       live | disconnected (now at medium.com/<pub>) | n/a
- Original custom domain: (pending)     e.g. https://mycompany.blog (pin canonical to this)
- Rights confirmed: (pending)           user owns / is authorized to migrate this content
- Enumeration method: (pending)         sitemap | bookmarklet-urls | archive-crawl
- Capture method: (pending)             fetch (automated) | saved-html (save-post bookmarklet)
- Output directory: medium-export-out

## Counts
- Post URLs enumerated: 0
- Posts captured: 0
- Posts failed / needs manual capture: 0

## Phase Checklist
- [ ] Phase 1: Scope & Inputs
- [ ] Phase 2: Enumerate all post URLs
- [ ] Phase 3: Capture post content
- [ ] Phase 4: Normalize & package the ZIP
- [ ] Phase 5: Verify & hand off to medium-to-ssg

## Failed / manual-capture posts
(none yet)
```

---

## Required Inputs

Collect these before Phase 2. Record them in `export-status.md`.

| Input | Notes |
|---|---|
| **Publication URL** | The public home of the publication. Either a custom domain (`https://mycompany.blog`) or a Medium-hosted path (`https://medium.com/<publication>`). |
| **Original custom domain** | If the publication ever had a custom domain (e.g. `https://mycompany.blog`), record it even if it no longer resolves. The migration's goal is to keep serving that domain's old URLs, so it pins every post's canonical URL (see "Preserving the publication's URLs" below). Skip if the publication only ever lived at `medium.com/<pub>`. |
| **Rights to the content** | Confirm the user owns the content or is authorized by the publication/authors to migrate it. This skill is for migrating **your own** publication, not for copying someone else's. Do not proceed without this. |
| **Output directory** | Where the working files and the final ZIP go. Default `medium-export-out/` in the working directory. |

You do **not** need the user's Medium login for the automated path. Some fallbacks (the bookmarklets) run in the user's already-logged-in browser; that is the user's own session and is fine.

---

## Background Context

### What the output must look like

The whole point is compatibility. `medium-to-ssg`'s converter (`convert_medium.py`) reads four things out of each HTML file and ignores everything else:

1. `<title>…</title>` — the post title
2. `<time class="dt-published" datetime="…ISO 8601…">` — the publish date
3. `<a class="p-canonical" href="…">` — the **public** post URL (its last path segment becomes the Hugo alias that preserves the old link)
4. `<section data-field="body">…</section>` — the article body

Every file this skill emits **must** contain those four elements. The exact required structure, plus the optional `p-author` element this skill adds for multi-author attribution, is documented in `references/export-format.md`. Read it before writing or normalizing any HTML.

The canonical URL matters: set it to the **public publication URL** the post lives at today (e.g. `https://mycompany.blog/some-title-abc123`). That last path segment is what `medium-to-ssg` turns into a redirect alias, so the old live links keep working after migration.

### Preserving the publication's URLs (custom-domain deadline)

Medium used to serve publication custom domains for free, but now requires a paid membership to keep one — with a hard cutoff (June 11, 2026) and **no grandfathering**. Per Medium's own notice, if you don't migrate by the deadline they **disconnect the custom domain** and the publication **stays available at `https://medium.com/<pub>`**. So the content never disappears — after the cutoff the custom domain simply stops resolving and the canonical home becomes `medium.com/<pub>`.

That means the content is always reachable, so **scraping still succeeds** — from the custom domain before the cutoff, or from `medium.com/<pub>` after it. The user's real goal is unchanged: the new static site must keep serving the **original** links like `https://mycompany.blog/some-title-abc123`.

The good news is that this is preserved **automatically**. `medium-to-ssg` builds each redirect alias from the **post slug** — the last path segment of `p-canonical` (`some-title-abc123`), not the domain — and that slug is **identical** on the custom domain and on `medium.com/<pub>`. So scraping from `medium.com/<pub>` yields the same `/some-title-abc123` alias, and once the new site is served at the original domain (via DNS cutover in `medium-to-ssg`), the old link resolves.

Use `--canonical-base` to additionally re-home each exported `p-canonical` to the original domain, so the export and its `manifest.csv` faithfully record the real public URLs:

```bash
python3 scripts/scrape_publication.py --urls urls.txt --canonical-base https://mycompany.blog
```

The one case that genuinely breaks slug preservation is the bare-hash URL form `medium.com/p/<hash>` (no title slug) — its last segment is just `<hash>`, so the alias would be `/<hash>` instead of `/some-title-<hash>`, and `--canonical-base` can't recover the missing title. Flag any `/p/<hash>` entries during the urls.txt review and have the user capture those posts with the **save-post bookmarklet**, which runs on the rendered post and records its real title slug.

**Best practice:** if the custom domain is still live, scrape it **now**, before the deadline — then the canonicals are already correct and no `--canonical-base` is needed.

### How you get the posts (three tiers)

Medium actively discourages scraping, so lead with the lowest-friction method and fall back as needed. All three tiers feed the *same* normalize-and-package pipeline.

1. **Sitemap enumeration (automated, no login).** Most Medium publications expose a sitemap (e.g. `https://mycompany.blog/sitemap/sitemap.xml`) listing every post URL. The script reads it, fetches each post, and normalizes it. Try this first.
2. **Bookmarklet URL enumeration.** When the sitemap is missing or incomplete, the user runs the enumeration bookmarklet on the publication's archive page (logged in, in Chrome). It auto-paginates and downloads a `urls.txt`. Feed that to the script.
3. **Save-post bookmarklet (most reliable content capture).** When fetching individual posts is blocked or renders poorly, the user opens each post and runs the save-post bookmarklet, which saves the fully-rendered article HTML. Drop those files in an `inbox/` folder and the script normalizes them into the export format.

The bookmarklets are the user's trusted manual escape hatch; the script automates everything around them. See `references/bookmarklets.md` and `references/scraping-strategy.md`.

### Be a polite, ethical scraper

- Only migrate content the user owns or is authorized to migrate.
- Rate-limit requests (the script defaults to a delay between fetches) and identify with a real User-Agent.
- Do not attempt to bypass paywalls, member-only gating, or authentication. If a post is member-only and the user has rights to it, capture it via the logged-in save-post bookmarklet instead of trying to defeat access controls.
- Respect `robots.txt` intent and back off on HTTP 429/403 rather than hammering.

---

## Execution

Work through the phases in order. Update `export-status.md` after each.

### Phase 1 — Scope & Inputs

1. Confirm the **publication URL** and whether it is a custom domain or `medium.com/<pub>`.
2. **Check the custom domain's status.** Open it: does it still serve the publication, or has Medium disconnected it (the publication is now only at `medium.com/<pub>`)? Medium now requires a paid plan to keep a custom domain (deadline June 11, 2026, no grandfathering); after the cutoff the domain is disconnected but the publication stays at `medium.com/<pub>`. Record the **original custom domain** regardless — it's what the migrated site must keep serving. If the domain is still live, prefer scraping it now; if it's already disconnected, scrape from `medium.com/<pub>` and pin the old domain with `--canonical-base` (see "Preserving the publication's URLs").
3. Confirm the user has the **right** to migrate the content. Do not continue otherwise.
4. Pick the **output directory** (default `medium-export-out/`).
5. Make sure Python 3 with `beautifulsoup4` and `requests` is available (`pip install beautifulsoup4 requests`). `requests` is only needed for the automated fetch path.

### Phase 2 — Enumerate all post URLs

1. Try the sitemap first:

   ```bash
   python3 scripts/scrape_publication.py --site https://mycompany.blog --enumerate-only
   ```

   This writes `medium-export-out/urls.txt` with every post URL it found. Review it with the user — confirm the count looks right and that it contains posts (not tag/author/archive pages).
2. If the sitemap is missing, blocked, or clearly incomplete, have the user run the **enumeration bookmarklet** (`references/bookmarklets.md`) on the publication's `/archive` page and place the downloaded `urls.txt` in the output directory.
3. Record the enumerated count in `export-status.md`.

See `references/scraping-strategy.md` for enumeration details and troubleshooting.

### Phase 3 — Capture post content

1. Run the full capture from whichever URL source you have:

   ```bash
   # from a sitemap:
   python3 scripts/scrape_publication.py --site https://mycompany.blog
   # or from a URL list:
   python3 scripts/scrape_publication.py --urls medium-export-out/urls.txt
   ```

   The script fetches each post, normalizes it to the export HTML format, writes `medium-export-out/posts/<date>_<slug>.html`, and appends to `manifest.csv`. It skips posts already written, so it is safe to re-run.

   **If the custom domain has lapsed** and you're scraping from `medium.com/<pub>`, add `--canonical-base` with the original domain so the migrated site still serves the old links:

   ```bash
   python3 scripts/scrape_publication.py --urls medium-export-out/urls.txt \
       --canonical-base https://mycompany.blog
   ```
2. For any posts the script reports as **failed** (blocked, member-only, or poorly rendered), have the user capture them with the **save-post bookmarklet**, drop the saved files in `medium-export-out/inbox/`, then normalize them (pass `--canonical-base` here too if you used it above):

   ```bash
   python3 scripts/scrape_publication.py --inbox medium-export-out/inbox
   ```
3. Update the captured/failed counts and the failed-posts list in `export-status.md`.

### Phase 4 — Normalize & package the ZIP

1. Once `posts/` holds every post, build the ZIP:

   ```bash
   python3 scripts/scrape_publication.py --package
   ```

   This produces `medium-export-out/medium-publication-export.zip` containing a top-level `posts/` directory — the same layout Medium's personal export uses.
2. Spot-check a few HTML files: open them and confirm the title, date, canonical URL, author, and body all look right.

### Phase 5 — Verify & hand off to medium-to-ssg

1. Sanity-check compatibility before handoff: confirm a sample file contains all four required elements (`<title>`, `time.dt-published`, `a.p-canonical`, `section[data-field=body]`). The script's `--package` step prints a compatibility summary; review it.
2. Tell the user the ZIP is ready and that the next step is the **`medium-to-ssg`** skill: they unzip it (or point that skill's `convert_medium.py` at the extracted `posts/`) and proceed with the Hugo migration exactly as a personal-export user would.
3. Mark all phases complete in `export-status.md`.

---

## Output Structure

```
medium-export-out/
├── urls.txt                          # Enumerated post URLs
├── inbox/                            # (optional) raw HTML saved via save-post bookmarklet
├── posts/                           # Export-format HTML, one per post
│   ├── 2020-03-11_Some-Post-abc123.html
│   └── ...
├── manifest.csv                     # Inventory: title, date, author, url, file
├── medium-publication-export.zip    # ← hand this to medium-to-ssg
└── export-status.md                 # Progress tracker (resumable)
```

---

## Constraints

- **Only export content the user owns or is authorized to migrate.** Confirm this in Phase 1 and do not proceed without it.
- **Stay compatible.** Every emitted HTML file must contain the four required elements from `references/export-format.md`. Do not change `medium-to-ssg`'s converter to accommodate a different shape — produce the shape it already expects.
- **Set `p-canonical` to the public post URL** so the old live links survive as Hugo aliases. If the custom domain has lapsed and you're scraping from `medium.com/<pub>`, use `--canonical-base` to re-home every post to the original domain (see "Preserving the publication's URLs").
- **Scrape politely.** Keep the request delay, use a real User-Agent, back off on 429/403, and never try to bypass paywalls or authentication. Use the logged-in save-post bookmarklet for member-only posts the user is entitled to.
- **Be resumable.** Never wipe `posts/`; rely on the skip-existing behavior and keep `export-status.md` current so an interrupted export can continue in a fresh session.
- **This skill stops at the ZIP.** Converting to Markdown, scaffolding Hugo, and hosting are the `medium-to-ssg` skill's job. Hand off; don't duplicate it.
