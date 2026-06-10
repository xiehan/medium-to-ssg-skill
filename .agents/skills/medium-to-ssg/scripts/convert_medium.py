"""
convert_medium.py — Convert Medium HTML export files to Hugo Markdown.

Usage:
    1. Edit the `posts` list below to include only the posts you want to migrate.
       Map each HTML filename (from the Medium export's posts/ directory) to
       the clean slug you want for the canonical URL (title without the hash).
    2. Set INPUT_DIR to the directory containing the extracted HTML files.
    3. Set OUTPUT_DIR to where you want the Markdown files written.
    4. Run: python3 convert_medium.py

Images: by default, remote images (Medium's CDN and any other external image
URLs) are downloaded into the Hugo static directory and the Markdown is
rewritten to reference the local copy (e.g. /images/<file>), so the migrated
site is self-contained and won't break when Medium's CDN goes away. Set
DOWNLOAD_IMAGES = False to keep the original remote URLs instead. If an
individual download fails, the original remote URL is kept so nothing is lost.

Promo CTAs: Medium's inline subscribe / membership call-to-action blocks
("Get <author>'s stories in your inbox", "Join Medium for free", etc.) are
detected by their text and stripped from the body so they don't leak into the
Markdown. This is most common with content captured via the
medium-publication-export skill, but applies to any source.

Byline chrome: scraped pages also prepend the on-page byline (author, "N min
read", date) to the body; that leading block is detected and stripped too.
Personal exports don't include it, so this is a no-op for them.

Tags: Medium's personal "Download your information" export does not include a
post's topic tags, but the medium-publication-export skill captures them into
the export HTML as <a class="p-category"> entries. When present, they are
written to the Hugo front matter's `tags:` list. Set EXTRACT_TAGS = False to
omit them.

Requires: beautifulsoup4 (pip install beautifulsoup4)
          (image downloading uses only the Python standard library)
"""

import hashlib
import mimetypes
import os
import re
import urllib.request
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse


# ── Configuration ────────────────────────────────────────────────────────────

INPUT_DIR = "work/medium-posts"    # Directory containing extracted HTML files
OUTPUT_DIR = "hugo-site/content/posts"  # Where to write .md files

# Image self-hosting. When True, remote images are downloaded into
# STATIC_DIR/IMAGE_DIR_NAME and references are rewritten to /<IMAGE_DIR_NAME>/...
DOWNLOAD_IMAGES = True
STATIC_DIR = "hugo-site/static"    # Hugo static root (served at the site root)
IMAGE_DIR_NAME = "images"          # Subfolder under static/ for downloaded images

# Preserve topic tags. When True, tags captured by the medium-publication-export
# skill (<a class="p-category"> entries) are written to the front matter's
# `tags:` list. Personal Medium exports contain no tags, so this is a no-op for
# them. Set to False to omit tags entirely.
EXTRACT_TAGS = True

# Map each HTML filename to its intended clean slug.
# The clean slug becomes the canonical URL: /posts/<slug>/
# The Medium-style slug (title + hash) is extracted automatically and used
# as the alias for redirects.
#
# Example:
# posts = [
#     ("2024-01-15_My-Post-Title-abc123def456.html", "my-post-title"),
#     ("2023-06-01_Another-Post-b1c2d3e4f5a6.html", "another-post"),
# ]
posts = [
    # ("FILENAME.html", "clean-slug"),
]


# ── Image localization ────────────────────────────────────────────────

_IMAGE_CACHE = {}   # remote URL -> local reference (e.g. /images/<file>)
_IMAGE_STATS = {"localized": 0, "reused": 0, "failed": 0}
_FETCH_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; medium-to-ssg/1.0)"}


def _sanitize_stem(name):
    stem = os.path.splitext(name)[0]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-_.")
    return stem[:60] or "image"


def _url_extension(url):
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if re.match(r"^\.[a-z0-9]{1,5}$", ext) else ""


def localize_image_src(src):
    """Download a remote image into the Hugo static dir; return a local ref.

    Returns a site-root path like /images/<file>. Non-remote srcs (data:,
    relative, or already-local) are returned unchanged. If the download fails,
    the original remote URL is returned so the post still references the image.
    """
    if not DOWNLOAD_IMAGES or not src:
        return src
    if src.startswith("//"):
        src = "https:" + src
    if not src.startswith(("http://", "https://")):
        return src  # data:, relative, or already local
    if src in _IMAGE_CACHE:
        _IMAGE_STATS["reused"] += 1
        return _IMAGE_CACHE[src]

    digest = hashlib.sha1(src.encode("utf-8")).hexdigest()[:8]
    stem = _sanitize_stem(os.path.basename(urlparse(src).path))
    image_dir = os.path.join(STATIC_DIR, IMAGE_DIR_NAME)
    ext = _url_extension(src)

    # If the extension is known from the URL, reuse an existing download.
    if ext:
        filename = f"{digest}-{stem}{ext}"
        if os.path.exists(os.path.join(image_dir, filename)):
            ref = f"/{IMAGE_DIR_NAME}/{filename}"
            _IMAGE_CACHE[src] = ref
            _IMAGE_STATS["reused"] += 1
            return ref

    try:
        req = urllib.request.Request(src, headers=_FETCH_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if not ext:
                ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
                guessed = mimetypes.guess_extension(ctype) if ctype else ""
                ext = ".jpg" if guessed in (".jpe", ".jpeg") else (guessed or ".img")
        filename = f"{digest}-{stem}{ext}"
        os.makedirs(image_dir, exist_ok=True)
        with open(os.path.join(image_dir, filename), "wb") as f:
            f.write(data)
        ref = f"/{IMAGE_DIR_NAME}/{filename}"
        _IMAGE_CACHE[src] = ref
        _IMAGE_STATS["localized"] += 1
        return ref
    except Exception as e:
        print(f"   ! image download failed ({src}): {e}; keeping remote URL")
        _IMAGE_STATS["failed"] += 1
        return src


# ── Medium promo CTA stripping ────────────────────────────────────────────────

# Medium injects subscribe / membership call-to-action widgets into the rendered
# article — e.g. "Get <author>'s stories in your inbox" or "Join Medium for
# free". These are not part of the post and must not leak into the Markdown.
# They most often appear when content was captured by the medium-publication-
# export skill (scraped from the rendered page), but a personal export can carry
# them too, so we strip them here regardless of source.
#
# The scraper normalizes away class names, so detection is by text content: each
# CTA is a short, self-contained block whose text is dominated by one of these
# phrases. Patterns are deliberately specific (they require the word "Medium" or
# an unmistakable Medium phrase) to avoid removing legitimate article prose.
_CTA_PATTERNS = [
    re.compile(r"stories in your inbox", re.IGNORECASE),
    re.compile(r"join medium for free", re.IGNORECASE),
    re.compile(r"get the medium app", re.IGNORECASE),
    re.compile(r"sign up\b.{0,40}\bmedium\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"by signing up,?\s+you will create a medium account", re.IGNORECASE),
]
_CTA_STATS = {"removed": 0}

# Block-level tags a CTA widget is typically wrapped in.
_CTA_BLOCK_TAGS = {
    "p", "div", "section", "figure", "aside", "blockquote",
    "h1", "h2", "h3", "h4", "a", "li", "ul",
}
# CTAs are short. Only blocks at or below this text length are eligible for
# removal, so the patterns can never match a long content paragraph (or the
# whole article body) by accident.
_CTA_MAX_LEN = 400


def _is_cta_text(text):
    return bool(text) and len(text) <= _CTA_MAX_LEN and any(
        p.search(text) for p in _CTA_PATTERNS
    )


def _still_attached(node, root):
    """True if node is still within root (not already removed via an ancestor)."""
    cur = node
    while cur is not None:
        if cur is root:
            return True
        cur = cur.parent
    return False


def strip_medium_ctas(body_section):
    """Remove Medium subscribe / membership promo CTA blocks from the body.

    Returns the number of CTA blocks removed.
    """
    removed = 0
    candidates = body_section.find_all(_CTA_BLOCK_TAGS)
    for el in candidates:
        if not _still_attached(el, body_section):
            continue  # was inside a CTA block already decomposed
        if not _is_cta_text(el.get_text(" ", strip=True)):
            continue
        # Expand to the outermost still-CTA-sized block so the whole widget
        # (heading + body + button text) is removed, not just one inner line.
        target = el
        parent = el.parent
        while (
            parent is not None
            and parent is not body_section
            and parent.name in _CTA_BLOCK_TAGS
            and _is_cta_text(parent.get_text(" ", strip=True))
        ):
            target = parent
            parent = parent.parent
        target.decompose()
        removed += 1
    _CTA_STATS["removed"] += removed
    return removed


# ── Medium byline-chrome stripping ────────────────────────────────────────────

# Scraped Medium pages prepend the article's on-page byline chrome to the body:
# the author's avatar, a (duplicated) author link, an "N min read" estimate, and
# the publish date — often followed by a "--" separator. Personal "Download your
# information" exports don't include this (their body starts at the real first
# paragraph), but content captured by the medium-publication-export skill does,
# so we strip the leading byline block here.
#
# Anchor: "N min read". That token is part of every Medium byline and effectively
# never appears in article prose, which makes it a precise, source-agnostic
# signal. We only remove a block whose *entire* text is the byline
# ("<author> N min read <date> --"); any real prose after the separator breaks
# the full match, so a short post's content can never be mistaken for byline.
_BYLINE_STATS = {"removed": 0}

# Full-match for a byline-only block: an optional author, the "N min read"
# estimate, an optional "Mon D, YYYY" date, and an optional trailing separator —
# and nothing else.
_BYLINE_FULL_RE = re.compile(
    r"^\s*.{0,120}?\b\d+\s+min read\b"            # optional author + "N min read"
    r"(?:\s+[A-Za-z]{3,9}\.?\s+\d{1,2}\s*,?\s*\d{4})?"  # optional "Mon D, YYYY"
    r"\s*(?:--|—|–|·)?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# Block tags the byline cluster is wrapped in (Medium uses nested <div>s).
_BYLINE_BLOCK_TAGS = {"p", "div", "section", "span", "a", "figure", "header"}
# A bare separator Medium sometimes leaves between the byline and the body.
_SEPARATOR_TEXTS = {"--", "—", "–", "·"}


def strip_medium_byline(body_section):
    """Remove the leading author/read-time/date byline chrome from the body.

    Returns the number of byline blocks removed (0 or 1).
    """
    removed = 0
    # In document order the first element whose *entire* text matches the byline
    # signature is the outermost byline-only block (ancestors also contain real
    # content, so they fail the full match). Remove it and stop.
    for el in body_section.find_all(_BYLINE_BLOCK_TAGS):
        if not _still_attached(el, body_section):
            continue
        if _BYLINE_FULL_RE.match(el.get_text(" ", strip=True)):
            el.decompose()
            removed = 1
            break

    # Drop a now-leading bare separator left behind by the byline (e.g. "--").
    if removed:
        for el in body_section.find_all(_BYLINE_BLOCK_TAGS):
            text = el.get_text(" ", strip=True)
            if text == "":
                continue
            if text in _SEPARATOR_TEXTS and not el.find("img"):
                el.decompose()
            break  # only inspect the first non-empty block

    _BYLINE_STATS["removed"] += removed
    return removed


# ── Conversion logic ─────────────────────────────────────────────────────────

def _split_edge_ws(text):
    """Split leading/trailing whitespace from text.

    Returns (leading_ws, core, trailing_ws). Markdown emphasis and link
    markers cannot sit directly against whitespace (``* text *`` is not valid
    emphasis), so boundary whitespace that lived inside an inline tag has to be
    re-emitted outside the markers instead of being dropped.
    """
    stripped = text.strip()
    if not stripped:
        return "", "", ""
    start = text.index(stripped[0])
    end = start + len(stripped)
    lead = " " if text[:start] else ""
    trail = " " if text[end:] else ""
    return lead, stripped, trail


def _wrap_inline(inner, prefix, suffix):
    """Wrap inner content in inline markers, preserving boundary whitespace."""
    lead, core, trail = _split_edge_ws(inner)
    if not core:
        return ""
    return f"{lead}{prefix}{core}{suffix}{trail}"


def node_to_md(node):
    """Recursively convert a BeautifulSoup node to Markdown text."""
    if isinstance(node, str):
        return node

    tag = node.name

    # Inline elements
    if tag in ("strong", "b"):
        inner = "".join(node_to_md(c) for c in node.children)
        return _wrap_inline(inner, "**", "**")
    if tag in ("em", "i"):
        inner = "".join(node_to_md(c) for c in node.children)
        return _wrap_inline(inner, "*", "*")
    if tag == "a":
        inner = "".join(node_to_md(c) for c in node.children)
        href = node.get("href", "")
        if not inner.strip():
            return ""
        lead, core, trail = _split_edge_ws(inner)
        return f"{lead}[{core}]({href}){trail}"
    if tag == "br":
        return "\n"
    if tag == "code":
        inner = "".join(node_to_md(c) for c in node.children)
        return _wrap_inline(inner, "`", "`")
    if tag == "img":
        src = node.get("src") or node.get("data-src") or ""
        alt = node.get("alt", "").strip()
        return f"![{alt}]({localize_image_src(src)})" if src else ""

    # Block elements
    if tag == "p":
        inner = "".join(node_to_md(c) for c in node.children).strip()
        return f"\n\n{inner}\n\n" if inner else ""
    if tag in ("h1", "h2", "h3", "h4"):
        level = int(tag[1])
        inner = "".join(node_to_md(c) for c in node.children).strip()
        return f"\n\n{'#' * level} {inner}\n\n" if inner else ""
    if tag in ("ul", "ol"):
        items = []
        for li in node.find_all("li", recursive=False):
            inner = "".join(node_to_md(c) for c in li.children).strip()
            prefix = "-" if tag == "ul" else "1."
            items.append(f"{prefix} {inner}")
        return "\n\n" + "\n".join(items) + "\n\n" if items else ""
    if tag == "blockquote":
        inner = "".join(node_to_md(c) for c in node.children).strip()
        lines = inner.split("\n")
        return "\n\n" + "\n".join(f"> {line}" for line in lines) + "\n\n"
    if tag == "pre":
        inner = node.get_text()
        return f"\n\n```\n{inner}\n```\n\n"
    if tag == "hr":
        return "\n\n---\n\n"

    # Embedded media (iframe inside a figure element)
    # Converted to a Hugo shortcode: {{< video src="..." >}}
    # Requires layouts/shortcodes/video.html to be created in the Hugo project.
    if tag == "figure":
        iframe = node.find("iframe")
        if iframe:
            src = iframe.get("src", "")
            return f'\n\n{{{{< video src="{src}" >}}}}\n\n'
        img = node.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or ""
            alt = img.get("alt", "").strip()
            if not src:
                return ""
            src = localize_image_src(src)
            caption = node.find("figcaption")
            md = f"\n\n![{alt}]({src})\n\n"
            if caption:
                caption_text = caption.get_text(strip=True)
                if caption_text:
                    md += f"*{caption_text}*\n\n"
            return md
        return ""

    # Generic: recurse into children
    return "".join(node_to_md(c) for c in node.children)


def convert_post(html_filename, clean_slug):
    """Convert a single Medium HTML export file to Hugo Markdown."""
    input_path = os.path.join(INPUT_DIR, html_filename)

    with open(input_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # ── Extract metadata ──────────────────────────────────────────────────

    title = soup.find("title").get_text(strip=True)

    time_tag = soup.find("time", class_="dt-published")
    if not time_tag:
        raise ValueError(f"No dt-published time tag found in {html_filename}")
    raw_date = time_tag["datetime"]  # e.g. "2024-01-15T10:30:00.000Z"
    date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).strftime("%Y-%m-%d")

    canonical_tag = soup.find("a", class_="p-canonical")
    if not canonical_tag:
        raise ValueError(f"No p-canonical link found in {html_filename}")
    # Extract the path slug from the canonical URL (title + Medium hash)
    medium_slug = canonical_tag["href"].rstrip("/").split("/")[-1]

    # Author attribution (present in personal exports and added by the
    # medium-publication-export skill for multi-author publications). Optional.
    author_tag = soup.find("a", class_="p-author") or soup.find(class_="p-author")
    author = author_tag.get_text(strip=True) if author_tag else ""
    author = re.sub(r"^by\s+", "", author, flags=re.IGNORECASE).strip()

    # ── Extract and clean body content ───────────────────────────────────

    body_section = soup.find("section", {"data-field": "body"})
    if not body_section:
        raise ValueError(f"No body section found in {html_filename}")

    # Remove the repeated title heading at the top of the body
    title_heading = body_section.find(class_="graf--title")
    if title_heading:
        title_heading.decompose()

    # Remove Medium's decorative horizontal rule dividers
    for divider in body_section.find_all(class_="section-divider"):
        divider.decompose()

    # Remove the leading author / "N min read" / date byline chrome that scraped
    # pages prepend to the body. See strip_medium_byline above.
    strip_medium_byline(body_section)

    # Remove Medium subscribe / membership promo CTAs ("Get <author>'s stories
    # in your inbox", "Join Medium for free", etc.) that can leak into scraped
    # content. See strip_medium_ctas above.
    strip_medium_ctas(body_section)

    md_body = node_to_md(body_section)

    # Collapse more than two consecutive newlines
    md_body = re.sub(r"\n{3,}", "\n\n", md_body).strip()

    # ── Assemble front matter ─────────────────────────────────────────────

    # Escape any double quotes in the title for YAML safety
    safe_title = title.replace('"', '\\"')

    author_line = ""
    if author:
        safe_author = author.replace('"', '\\"')
        author_line = f'author: "{safe_author}"\n'

    # Topic tags (present only when captured by medium-publication-export, as
    # <a class="p-category"> entries outside the body). Personal exports have none.
    tags_block = ""
    if EXTRACT_TAGS:
        seen = set()
        tags = []
        for el in soup.find_all(class_="p-category"):
            tag_text = el.get_text(strip=True)
            key = tag_text.lower()
            if tag_text and key not in seen:
                seen.add(key)
                tags.append(tag_text)
        if tags:
            items = "".join(
                f'  - "{t.replace(chr(34), chr(92) + chr(34))}"\n' for t in tags
            )
            tags_block = f"tags:\n{items}"

    front_matter = (
        f'---\n'
        f'title: "{safe_title}"\n'
        f'date: {date}\n'
        f'{author_line}'
        f'slug: "{clean_slug}"\n'
        f'aliases:\n'
        f'  - /{medium_slug}\n'
        f'{tags_block}'
        f'---'
    )

    return front_matter + "\n\n" + md_body + "\n"


def main():
    if not posts:
        print("ERROR: The `posts` list is empty. Edit convert_medium.py to add your posts.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    success = 0
    errors = []

    for html_filename, clean_slug in posts:
        try:
            result = convert_post(html_filename, clean_slug)
            output_path = os.path.join(OUTPUT_DIR, f"{clean_slug}.md")
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"✓  {clean_slug}.md")
            success += 1
        except Exception as e:
            print(f"✗  {html_filename}: {e}")
            errors.append((html_filename, str(e)))

    print(f"\n{success}/{len(posts)} posts converted successfully.")
    if _BYLINE_STATS["removed"]:
        print(f"Removed {_BYLINE_STATS['removed']} leading Medium byline "
              f"block(s) (author / read time / date).")
    if _CTA_STATS["removed"]:
        print(f"Removed {_CTA_STATS['removed']} Medium promo CTA block(s) "
              f"(subscribe / \"Join Medium for free\").")
    if DOWNLOAD_IMAGES:
        s = _IMAGE_STATS
        print(
            f"Images: {s['localized']} downloaded, {s['reused']} reused, "
            f"{s['failed']} failed (kept remote). "
            f"Saved to {os.path.join(STATIC_DIR, IMAGE_DIR_NAME)}/."
        )
        if s["failed"]:
            print("  Some images could not be downloaded and still point at "
                  "remote URLs; re-run to retry, or self-host them manually.")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for filename, msg in errors:
            print(f"  {filename}: {msg}")


if __name__ == "__main__":
    main()
