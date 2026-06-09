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


# ── Conversion logic ─────────────────────────────────────────────────────────

def node_to_md(node):
    """Recursively convert a BeautifulSoup node to Markdown text."""
    if isinstance(node, str):
        return node

    tag = node.name

    # Inline elements
    if tag in ("strong", "b"):
        inner = "".join(node_to_md(c) for c in node.children)
        return f"**{inner.strip()}**" if inner.strip() else ""
    if tag in ("em", "i"):
        inner = "".join(node_to_md(c) for c in node.children)
        return f"*{inner.strip()}*" if inner.strip() else ""
    if tag == "a":
        inner = "".join(node_to_md(c) for c in node.children).strip()
        href = node.get("href", "")
        return f"[{inner}]({href})" if inner else ""
    if tag == "br":
        return "\n"
    if tag == "code":
        inner = "".join(node_to_md(c) for c in node.children)
        return f"`{inner}`"
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

    front_matter = (
        f'---\n'
        f'title: "{safe_title}"\n'
        f'date: {date}\n'
        f'{author_line}'
        f'slug: "{clean_slug}"\n'
        f'aliases:\n'
        f'  - /{medium_slug}\n'
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
