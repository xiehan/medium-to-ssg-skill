# Export Format Reference (the compatibility contract)

This skill rebuilds Medium's personal export format so the [`medium-to-ssg`](../../medium-to-ssg/SKILL.md) converter can consume the result unchanged.
Read this before writing or normalizing any HTML.

## What the converter actually reads

`medium-to-ssg/scripts/convert_medium.py` is intentionally minimal.
For each HTML file it pulls out exactly these elements and ignores everything else (scripts, styles, nav, headers, classes other than the two noted below):

| Data | How it's found | Used for |
|---|---|---|
| Title | `<title>` tag text | `title:` front matter |
| Publish date | `<time class="dt-published" datetime="…">` (ISO 8601) | `date:` front matter |
| Canonical URL | `<a class="p-canonical" href="…">` | the last path segment becomes the Hugo `alias` that preserves the old link |
| Body | `<section data-field="body">…</section>` | the post content, converted to Markdown |

Two classes inside the body get special treatment by the converter:

- An element with class `graf--title` is removed (Medium's duplicated title heading at the top of the body).
- Elements with class `section-divider` are removed (decorative dividers).

You don't need to add those classes — but if your normalized body still contains a duplicated title heading or divider, tag them with these classes (or remove them yourself) so they don't leak into the Markdown.

## The HTML file this skill emits

Each post becomes a standalone HTML document with this shape.
The four required elements are marked. The `p-author` block is **optional but recommended** — it's how multi-author attribution survives the migration (the converter emits an `author:` field when it's present).

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Post Title</title>                                   <!-- REQUIRED -->
</head>
<body>
<article class="h-entry">
  <header>
    <h1 class="p-name">Post Title</h1>
  </header>

  <p class="p-author">By
    <a class="p-author h-card" href="https://medium.com/@author">Author Name</a>
  </p>

  <section data-field="body" class="e-content">             <!-- REQUIRED -->
    <p>First paragraph…</p>
    <h2>A heading</h2>
    <p>More text with <a href="…">a link</a> and <strong>bold</strong>.</p>
    <figure><img src="https://cdn-images-1.medium.com/…" alt="…"></figure>
    <pre><code>code block</code></pre>
    <blockquote>A quote.</blockquote>
  </section>

  <footer>
    <time class="dt-published" datetime="2020-03-11T14:05:00.000Z">
      March 11, 2020
    </time>                                                   <!-- REQUIRED -->
    <a class="p-canonical" href="https://mycompany.blog/post-title-abc123"></a>  <!-- REQUIRED -->
  </footer>
</article>
</body>
</html>
```

### Notes

- **Canonical URL = public post URL.** Set `p-canonical`'s `href` to the URL the post lives at today on the publication (e.g. `https://mycompany.blog/post-title-abc123`), **not** a `medium.com/...` mirror. The converter takes its last path segment (`post-title-abc123`) and creates a Hugo `alias` of `/post-title-abc123`, which is what keeps the old live link working after migration. Because only the last segment (the slug) is used, scraping from `medium.com/<pub>` preserves the link just as well — the slug is identical there. If you scraped from `medium.com/<pub>` because the custom domain lapsed, the `--canonical-base` flag re-homes each recorded canonical to the original domain for fidelity (see `references/scraping-strategy.md`, "The custom-domain deadline").
- **Body uses a plain HTML subset.** The converter understands `p`, `h1`–`h4`, `ul`/`ol`/`li`, `blockquote`, `pre`/`code`, `a`, `strong`/`b`, `em`/`i`, `code`, `br`, `hr`, `img`, `figure>img` (image), and `figure>iframe` (turned into a Hugo `video` shortcode). It recurses through unknown wrapper tags (e.g. `div`, `span`), extracting their text and inline formatting. Normalize Medium's obfuscated markup down toward this subset so conversion is clean.
- **Images stay as remote URLs.** Like Medium's real export, leave `<img src="https://cdn-images-1.medium.com/…">` pointing at Medium's CDN. `medium-to-ssg`'s converter (`convert_medium.py`) automatically downloads and self-hosts those images during conversion. Don't rewrite them here.
- **Filename.** Save each file as `<YYYY-MM-DD>_<slug>.html` inside a `posts/` directory, matching Medium's `YYYY-MM-DD_Post-Title-Slug-{hash}.html` convention. The converter doesn't parse the filename for data — it's for human inventory and uniqueness — but matching the convention keeps the ZIP indistinguishable from a real export.

## ZIP layout

The final `medium-publication-export.zip` contains a single top-level `posts/` directory of these HTML files — the same layout a personal Medium export uses, so `medium-to-ssg` treats it identically:

```
medium-publication-export.zip
└── posts/
    ├── 2020-03-11_Some-Post-abc123.html
    ├── 2019-07-02_Another-Post-def456.html
    └── ...
```
