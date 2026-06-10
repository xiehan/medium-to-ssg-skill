#!/usr/bin/env python3
"""
scrape_publication.py — Export every post from a Medium publication into a
Medium-export-compatible ZIP that the `medium-to-ssg` skill can consume.

Medium has no "export this publication" feature, so multi-author publications
(e.g. a company engineering blog) cannot use Settings -> Download your
information, which is per-account. This script rebuilds that export by
collecting each post and writing it as an HTML file in the same shape
`convert_medium.py` expects: a <title>, a <time class="dt-published">, an
<a class="p-canonical">, and a <section data-field="body">. See
references/export-format.md for the full contract.

Three ways to supply posts (pick whichever works for your publication):

  1. Sitemap (fully automated, no login):
       python3 scrape_publication.py --site https://mycompany.blog
     Add --enumerate-only to just write urls.txt without fetching.

  2. A list of post URLs, one per line (e.g. from the enumeration bookmarklet):
       python3 scrape_publication.py --urls urls.txt

  3. Raw post HTML saved from the logged-in browser with the save-post
     bookmarklet (most reliable when fetching is blocked); drop the files in a
     folder and normalize them:
       python3 scrape_publication.py --inbox medium-export-out/inbox

Preserving old URLs when the custom domain is gone:
  Medium now requires a paid plan to serve a publication at a custom domain.
  After the deadline it disconnects the custom domain, but the publication
  stays available at medium.com/<pub>. Scraping still works from those URLs,
  and old links are preserved automatically: the Hugo alias medium-to-ssg
  generates is the post SLUG (the last path segment, e.g. my-post-abc123), which
  is identical on the custom domain and on medium.com/<pub>. Pass --canonical-base
  with the original domain to additionally re-home each exported canonical URL to
  it, so the export and manifest faithfully record the real public links:
       python3 scrape_publication.py --urls urls.txt \
           --canonical-base https://mycompany.blog
  Note: a few Medium URLs use the bare-hash form medium.com/p/<hash> (no title
  slug); --canonical-base can't recover the title, so capture those with the
  save-post bookmarklet instead. See references/scraping-strategy.md
  ("The custom-domain deadline").

Package the ZIP once posts/ is complete:
       python3 scrape_publication.py --package

Review and prune topic tags before packaging (tags come from the live page;
see references/export-format.md):
       python3 scrape_publication.py --tags-report          # list tags + counts
       python3 scrape_publication.py --prune-tags "NPR,Misc" # drop named tags
       python3 scrape_publication.py --min-tag-count 2       # drop one-off tags

Output (under --out, default ./medium-export-out):
  urls.txt                          enumerated post URLs
  posts/<YYYY-MM-DD>_<slug>.html    one per post, export format
  manifest.csv                      inventory (date, author, url, file)
  tags.csv                          tag inventory with post counts (--tags-report)
  medium-publication-export.zip     zipped posts/ -- feed this to medium-to-ssg

Resumable: posts already written to posts/ are skipped.

Requires: beautifulsoup4  (pip install beautifulsoup4)
          requests        (only for --site / --urls fetching)
"""

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

try:
    import requests
except ImportError:  # requests is only needed for the fetching paths
    requests = None


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ZIP_NAME = "medium-publication-export.zip"

# Tags that never carry post content and should be dropped from the body.
JUNK_TAGS = ["script", "style", "noscript", "svg", "button", "form", "nav", "aside"]

# Attributes worth keeping on body elements; everything else is stripped to
# keep the normalized HTML small and predictable for the converter.
KEEP_ATTRS = {"href", "src", "alt", "datetime"}

# ── Medium UI chrome that leaks into scraped article bodies ───────────────────
# A live Medium page renders the on-page byline (author, "N min read", date) and
# inline subscribe / membership promos inside the article. These are not part of
# the post, so we strip them here — before the export is written — so the ZIP
# matches a clean personal "Download your information" export. medium-to-ssg's
# convert_medium.py strips the same things again as a backstop for other sources.

# A byline-only block: optional author, "N min read", optional "Mon D, YYYY"
# date, optional trailing separator, and nothing else (real prose after the
# separator breaks the match, so post content is never removed).
_BYLINE_FULL_RE = re.compile(
    r"^\s*.{0,120}?\b\d+\s+min read\b"
    r"(?:\s+[A-Za-z]{3,9}\.?\s+\d{1,2}\s*,?\s*\d{4})?"
    r"\s*(?:--|—|–|·)?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_SEPARATOR_TEXTS = {"--", "—", "–", "·"}

# Inline subscribe / membership CTA phrases (short blocks only).
_CTA_PATTERNS = [
    re.compile(r"stories in your inbox", re.IGNORECASE),
    re.compile(r"join medium for free", re.IGNORECASE),
    re.compile(r"get the medium app", re.IGNORECASE),
    re.compile(r"sign up\b.{0,40}\bmedium\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"by signing up,?\s+you will create a medium account", re.IGNORECASE),
]
_CTA_BLOCK_TAGS = {
    "p", "div", "section", "figure", "aside", "blockquote",
    "h1", "h2", "h3", "h4", "a", "li", "ul",
}
_CTA_MAX_LEN = 400


def _node_attached(node, root):
    cur = node
    while cur is not None:
        if cur is root:
            return True
        cur = cur.parent
    return False


def _is_cta_text(text):
    return bool(text) and len(text) <= _CTA_MAX_LEN and any(
        p.search(text) for p in _CTA_PATTERNS
    )


def strip_medium_chrome(soup):
    """Remove the leading byline block and inline subscribe/membership CTAs."""
    # Leading byline: the first block in document order whose entire text is the
    # byline signature is the outermost byline-only block; remove it once.
    for el in soup.find_all(True):
        if not _node_attached(el, soup):
            continue
        if _BYLINE_FULL_RE.match(el.get_text(" ", strip=True)):
            el.decompose()
            break
    # A bare separator left behind at the top (e.g. "--").
    for el in soup.find_all(True):
        text = el.get_text(" ", strip=True)
        if text == "":
            continue
        if text in _SEPARATOR_TEXTS and not el.find("img"):
            el.decompose()
        break

    # Inline promo CTAs anywhere in the body.
    for el in soup.find_all(_CTA_BLOCK_TAGS):
        if not _node_attached(el, soup):
            continue
        if not _is_cta_text(el.get_text(" ", strip=True)):
            continue
        target = el
        parent = el.parent
        while (
            parent is not None
            and parent is not soup
            and parent.name in _CTA_BLOCK_TAGS
            and _is_cta_text(parent.get_text(" ", strip=True))
        ):
            target = parent
            parent = parent.parent
        target.decompose()


# ── URL helpers ──────────────────────────────────────────────────────────────

def normalize_url(url):
    """Drop query/fragment and trailing slash so duplicates collapse."""
    p = urlparse(url)
    path = p.path.rstrip("/")
    return f"{p.scheme}://{p.netloc}{path}"


def is_probable_post_url(url, host):
    """A post URL is same-host and ends in a hyphen + short hash."""
    p = urlparse(url)
    if p.netloc != host:
        return False
    path = p.path.rstrip("/")
    if not path or path == "":
        return False
    first = path.split("/")[1] if len(path.split("/")) > 1 else ""
    if first in ("tag", "archive", "search", "m", "me", "membership", "about", "feed"):
        return False
    if path.startswith("/@"):
        return False
    return bool(re.search(r"-[0-9a-z]{6,}$", path, re.IGNORECASE))


def slug_from_url(url):
    """Last path segment of the canonical URL (title + Medium hash)."""
    return urlparse(url).path.rstrip("/").split("/")[-1] or "post"


def rehome_canonical(canonical, canonical_base):
    """Re-home a post's canonical URL under the original custom domain.

    Used when scraping from medium.com/<pub> (because the custom domain has
    lapsed) but the migrated site must keep serving the original links. Keeps
    the post slug and swaps the domain/path prefix, so the Hugo alias that
    medium-to-ssg derives from the last path segment stays correct.
    """
    if not canonical_base:
        return canonical
    return canonical_base.rstrip("/") + "/" + slug_from_url(canonical)


# ── Fetching ─────────────────────────────────────────────────────────────────

def make_session():
    if requests is None:
        sys.exit(
            "The 'requests' package is required for fetching. "
            "Install it with: pip install requests\n"
            "(Or use --inbox to normalize HTML saved via the save-post bookmarklet.)"
        )
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def fetch(session, url, delay, retries=3):
    """Fetch a URL politely. Returns text or None on hard failure."""
    backoff = max(delay, 1.0)
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
        except Exception as e:  # network error
            print(f"   ! network error ({e}); retry {attempt}/{retries}")
            time.sleep(backoff)
            backoff *= 2
            continue
        if resp.status_code == 200:
            time.sleep(delay)
            return resp.text
        if resp.status_code in (403, 429, 503):
            print(f"   ! HTTP {resp.status_code}; backing off ({attempt}/{retries})")
            time.sleep(backoff)
            backoff *= 2
            continue
        print(f"   ! HTTP {resp.status_code}")
        return None
    return None


# ── Enumeration via sitemap ──────────────────────────────────────────────────

def discover_urls_from_sitemap(session, site, delay):
    """Walk the publication sitemap(s) and return probable post URLs."""
    host = urlparse(site).netloc
    candidates = [
        urljoin(site, "/sitemap/sitemap.xml"),
        urljoin(site, "/sitemap.xml"),
    ]
    to_visit = []
    for c in candidates:
        xml = fetch(session, c, delay)
        if xml:
            to_visit.append((c, xml))
            break
    if not to_visit:
        print("No sitemap found. Use the enumeration bookmarklet instead.")
        return []

    found = set()
    seen_sitemaps = set()
    while to_visit:
        loc, xml = to_visit.pop()
        if loc in seen_sitemaps:
            continue
        seen_sitemaps.add(loc)
        soup = BeautifulSoup(xml, "xml")
        locs = [l.get_text(strip=True) for l in soup.find_all("loc")]
        for u in locs:
            if u.endswith(".xml"):
                if u not in seen_sitemaps:
                    child = fetch(session, u, delay)
                    if child:
                        to_visit.append((u, child))
            elif is_probable_post_url(u, host):
                found.add(normalize_url(u))
    return sorted(found)


# ── Metadata + body extraction ───────────────────────────────────────────────

def _ld_json_article(soup):
    """Find the Article-like JSON-LD block, if present.

    Medium tags its post JSON-LD with ``@type: "SocialMediaPosting"`` (schema.org
    parlance for a published story), so that type must be recognized too — without
    it the block is skipped and date/author extraction silently falls back to the
    ``article:published_time`` meta, which Medium sets to the *latest* publish time
    (i.e. the last-edited date), not the original ``datePublished``.
    """
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict) and obj.get("@type") in (
                "Article", "NewsArticle", "BlogPosting", "SocialMediaPosting",
            ):
                return obj
    return None


def _meta(soup, **attrs):
    tag = soup.find("meta", attrs=attrs)
    return tag.get("content", "").strip() if tag else ""


def extract_tags(soup):
    """Return the post's topic tags in display form (best-effort, ordered).

    Live Medium pages expose tags two ways: as "Topic:" pill buttons at the
    foot of the article (an ``aria-label="Topic: <name>"`` on each) and inside
    the embedded Apollo cache (``"Tag:<slug>"`` objects carrying a
    ``displayTitle``). The pill buttons belong specifically to this post, so we
    prefer them; the Apollo cache is a reliable fallback (and is what bookmarklet
    captures or fetches without rendered pills still contain), followed by
    ld+json / ``<meta>`` keywords. Personal "Download your information" exports
    carry no tags, so this returns ``[]`` for them.
    """
    seen = set()
    tags = []

    def add(name):
        name = re.sub(r"\s+", " ", html.unescape(name or "")).strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            tags.append(name)

    # 1) Topic pill buttons (most precise — specific to this post).
    topic_re = re.compile(r"^\s*Topic:\s*", re.IGNORECASE)
    for el in soup.find_all(attrs={"aria-label": topic_re}):
        add(topic_re.sub("", el.get("aria-label", "")))

    # 2) Apollo cache Tag objects ("Tag:<slug>": { ... "displayTitle": "..." }).
    if not tags:
        for script in soup.find_all("script"):
            text = script.get_text() or ""
            if '"Tag:' not in text:
                continue
            for m in re.finditer(
                r'"Tag:[^"]+":\{[\s\S]{0,500}?"displayTitle":"([^"\\]+)"',
                text,
            ):
                add(m.group(1))
            if tags:
                break

    # 3) ld+json / <meta> keywords (comma-separated).
    if not tags:
        ld = _ld_json_article(soup) or {}
        kw = ld.get("keywords")
        if isinstance(kw, list):
            for k in kw:
                add(str(k))
        elif isinstance(kw, str):
            for k in kw.split(","):
                add(k)
        if not tags:
            for k in _meta(soup, name="keywords").split(","):
                add(k)

    return tags


def extract_metadata(soup, source_url):
    """Pull title, ISO date, author, and canonical URL from a post page."""
    ld = _ld_json_article(soup) or {}

    title = ld.get("headline") or _meta(soup, property="og:title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)
        # Strip a trailing " | Publication" / " - Medium" if present.
        title = re.sub(r"\s*[|\u2013\u2014-]\s*[^|]+$", "", title) if " " in title else title
    title = (title or "Untitled").strip()

    date_iso = ld.get("datePublished") or _meta(soup, property="article:published_time")
    if not date_iso:
        t = soup.find("time")
        date_iso = t.get("datetime", "") if t else ""
    date_iso = date_iso.strip() or _now_iso()

    author = ""
    a = ld.get("author")
    if isinstance(a, dict):
        author = a.get("name", "")
    elif isinstance(a, list) and a:
        author = ", ".join(x.get("name", "") for x in a if isinstance(x, dict)).strip(", ")
    elif isinstance(a, str):
        author = a
    if not author:
        author = _meta(soup, name="author")
    author = (author or "").strip()

    canonical = ""
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        canonical = link["href"].strip()
    if not canonical:
        canonical = ld.get("mainEntityOfPage", "") if isinstance(ld.get("mainEntityOfPage"), str) else ""
    host = urlparse(source_url).netloc
    if not canonical or urlparse(canonical).netloc != host:
        # Prefer the public publication URL we actually scraped from.
        canonical = source_url
    canonical = normalize_url(canonical)

    return {
        "title": title,
        "date_iso": date_iso,
        "author": author,
        "canonical": canonical,
        "tags": extract_tags(soup),
    }


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _date_only(date_iso):
    try:
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _human_date(date_iso):
    try:
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        return dt.strftime("%B %d, %Y")
    except ValueError:
        return ""


def find_body_container(soup):
    """Pick the article body element.

    Prefer an explicit <section data-field="body"> (present in saved exports and
    bookmarklet captures); otherwise fall back to the element with the most <p>
    descendants under <article> (live Medium pages use obfuscated markup).
    """
    explicit = soup.find("section", {"data-field": "body"})
    if explicit:
        return explicit
    article = soup.find("article") or soup.body or soup
    best = article
    best_count = len(article.find_all("p"))
    for el in article.find_all(["section", "div"]):
        n = len(el.find_all("p", recursive=True))
        if n > best_count:
            best_count = n
            best = el
    return best


def _best_img_src(img):
    """Choose the highest-quality image URL for an <img>, handling lazy loads."""
    for attr in ("src", "data-src", "data-srcset", "srcset"):
        val = img.get(attr)
        if val:
            # srcset is "url1 1x, url2 2x"; take the last (largest) URL.
            return val.split(",")[-1].strip().split(" ")[0]
    parent = img.find_parent("picture")
    if parent:
        source = parent.find("source")
        if source and source.get("srcset"):
            return source["srcset"].split(",")[-1].strip().split(" ")[0]
    return ""


def normalize_body(container, title):
    """Strip non-content cruft and reduce to the converter's HTML subset."""
    soup = BeautifulSoup(str(container), "html.parser")

    for tag in soup.find_all(JUNK_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"aria-hidden": "true"}):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": "button"}):
        tag.decompose()

    # Remove a duplicated title heading at the top of the body.
    for h in soup.find_all(["h1", "h2", "h3"]):
        if h.get_text(strip=True) == title.strip():
            h.decompose()
            break

    # Remove Medium UI chrome (leading byline + inline subscribe/membership CTAs)
    # so the export body starts at the real first paragraph.
    strip_medium_chrome(soup)

    # Normalize images to a clean <img src> the converter understands.
    for img in soup.find_all("img"):
        src = _best_img_src(img)
        if not src:
            img.decompose()
            continue
        alt = img.get("alt", "")
        img.attrs = {"src": src, "alt": alt}

    # Strip unrelated attributes from everything else.
    for tag in soup.find_all(True):
        if tag.name == "img":
            continue
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in KEEP_ATTRS}

    return soup.decode_contents().strip()


# ── Export HTML assembly ─────────────────────────────────────────────────────

def build_export_html(meta, body_html):
    title = html.escape(meta["title"])
    author = html.escape(meta["author"])
    author_block = ""
    if meta["author"]:
        author_block = (
            f'  <p class="p-author">By '
            f'<a class="p-author h-card" href="">{author}</a></p>\n'
        )
    tags_block = ""
    if meta.get("tags"):
        # h-entry microformat: one <a class="p-category"> per tag. The
        # converter reads these into the Hugo front matter's `tags:` list.
        links = "".join(
            f'<a class="p-category" href="">{html.escape(t)}</a>'
            for t in meta["tags"]
        )
        tags_block = f'    <p class="tags">{links}</p>\n'
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{title}</title>\n"
        "</head>\n<body>\n"
        '<article class="h-entry">\n'
        f'  <header><h1 class="p-name">{title}</h1></header>\n'
        f"{author_block}"
        '  <section data-field="body" class="e-content">\n'
        f"{body_html}\n"
        "  </section>\n"
        "  <footer>\n"
        f'    <time class="dt-published" datetime="{html.escape(meta["date_iso"])}">'
        f'{html.escape(_human_date(meta["date_iso"]))}</time>\n'
        f'    <a class="p-canonical" href="{html.escape(meta["canonical"])}"></a>\n'
        f"{tags_block}"
        "  </footer>\n"
        "</article>\n</body>\n</html>\n"
    )


def post_from_html(page_html, source_url, canonical_base=None):
    """Parse a fetched/saved post page into (meta, export_html, filename)."""
    soup = BeautifulSoup(page_html, "html.parser")
    meta = extract_metadata(soup, source_url)
    meta["canonical"] = rehome_canonical(meta["canonical"], canonical_base)
    container = find_body_container(soup)
    body_html = normalize_body(container, meta["title"])
    if not body_html or len(BeautifulSoup(body_html, "html.parser").get_text(strip=True)) < 40:
        return meta, None, None  # nothing meaningful captured
    export_html = build_export_html(meta, body_html)
    filename = f'{_date_only(meta["date_iso"])}_{slug_from_url(meta["canonical"])}.html'
    return meta, export_html, filename


# ── Output management ────────────────────────────────────────────────────────

def ensure_dirs(out):
    os.makedirs(os.path.join(out, "posts"), exist_ok=True)


def already_have(out, filename):
    return filename and os.path.exists(os.path.join(out, "posts", filename))


def write_post(out, filename, export_html):
    path = os.path.join(out, "posts", filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(export_html)
    return path


def append_manifest(out, meta, filename):
    path = os.path.join(out, "manifest.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "title", "author", "canonical_url", "file"])
        w.writerow([
            _date_only(meta["date_iso"]), meta["title"],
            meta["author"], meta["canonical"], filename,
        ])


# ── Tag inventory & pruning ──────────────────────────────────────────────────
# Live Medium posts carry topic tags (captured into the footer as
# <a class="p-category"> entries). Not every tag is worth keeping on a
# self-hosted site — e.g. a tag naming the publication itself ("NPR"), or a tag
# used on only one post out of hundreds. These helpers let the skill show the
# user a tag inventory (each tag + how many posts use it) and then drop the ones
# they don't want before the ZIP is packaged.

def _norm_tag(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def _footer_scope(soup):
    """Tags live in the footer; scope tag operations there to avoid the body."""
    return soup.find("footer") or soup


def _post_tag_names(scope):
    return [_norm_tag(a.get_text()) for a in scope.find_all("a", class_="p-category")]


def tag_inventory(out):
    """Scan posts/ and return [(display_name, post_count)] for every tag.

    Tags are grouped case-insensitively (the most common spelling is shown) and
    counted once per post. The list is sorted by count (desc) then name, so the
    publication-wide tags and the one-off tags are both easy to spot.
    """
    posts_dir = os.path.join(out, "posts")
    if not os.path.isdir(posts_dir):
        return []
    counts = {}      # key -> number of posts using it
    display = {}     # key -> {spelling: occurrences} to pick a canonical label
    for name in sorted(os.listdir(posts_dir)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(posts_dir, name), encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        seen = set()
        for tag in _post_tag_names(_footer_scope(soup)):
            key = tag.lower()
            if not tag or key in seen:
                continue          # count each tag at most once per post
            seen.add(key)
            counts[key] = counts.get(key, 0) + 1
            display.setdefault(key, {})
            display[key][tag] = display[key].get(tag, 0) + 1
    inventory = []
    for key, count in counts.items():
        label = max(display[key].items(), key=lambda kv: (kv[1], kv[0]))[0]
        inventory.append((label, count))
    inventory.sort(key=lambda kv: (-kv[1], kv[0].lower()))
    return inventory


def write_tags_report(out):
    """Print the tag inventory and write it to tags.csv for the user to review."""
    inventory = tag_inventory(out)
    posts_dir = os.path.join(out, "posts")
    if not inventory:
        print("No tags found in posts/. Tags come from the live Medium page, so "
              "personal exports have none and captures made before tag support "
              "won't either — re-capture to pick them up.")
        return inventory
    report_path = os.path.join(out, "tags.csv")
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["count", "tag"])
        for tag, count in inventory:
            w.writerow([count, tag])
    total = len([f for f in os.listdir(posts_dir) if f.endswith(".html")])
    print(f"\nTag inventory — {len(inventory)} distinct tag(s) across {total} post(s):")
    for tag, count in inventory:
        print(f"  {count:>4}  {tag}")
    print(f"\nWritten to {report_path}.")
    print("Review these with the user, then drop unwanted tags with")
    print('  --prune-tags "Tag One,Tag Two"   and/or   --min-tag-count N')
    print("and re-run --package.")
    return inventory


def prune_tags(out, drop_names=None, min_count=None):
    """Remove unwanted topic tags from every captured post, in place.

    drop_names: tag display names to remove (case-insensitive, comma list).
    min_count:  also remove any tag used by fewer than this many posts.
    Returns the set of tag display names actually removed.
    """
    posts_dir = os.path.join(out, "posts")
    if not os.path.isdir(posts_dir):
        print("No posts/ directory to prune.")
        return set()
    drop_keys = {_norm_tag(n).lower() for n in (drop_names or []) if _norm_tag(n)}
    if min_count:
        for tag, count in tag_inventory(out):
            if count < min_count:
                drop_keys.add(tag.lower())
    if not drop_keys:
        print("No tags selected to prune (nothing matched --prune-tags / --min-tag-count).")
        return set()

    removed = {}     # key -> display name actually removed
    changed = 0
    for name in sorted(f for f in os.listdir(posts_dir) if f.endswith(".html")):
        path = os.path.join(posts_dir, name)
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        scope = _footer_scope(soup)
        file_changed = False
        for a in scope.find_all("a", class_="p-category"):
            label = _norm_tag(a.get_text())
            if label.lower() in drop_keys:
                removed[label.lower()] = label
                a.decompose()
                file_changed = True
        if file_changed:
            # Drop the wrapping <p class="tags"> if it has no tags left.
            for p in scope.find_all("p", class_="tags"):
                if not p.find("a", class_="p-category"):
                    p.decompose()
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            changed += 1
    if removed:
        print(f"Pruned {len(removed)} tag(s) from {changed} post(s): "
              f"{', '.join(sorted(removed.values(), key=str.lower))}")
    else:
        print("No matching tags were present in any post.")
    print("Re-run --package to rebuild the ZIP with the updated tags.")
    return set(removed.values())


def package_zip(out):
    posts_dir = os.path.join(out, "posts")
    files = sorted(f for f in os.listdir(posts_dir) if f.endswith(".html"))
    if not files:
        print("No posts to package. Capture some first.")
        return
    zip_path = os.path.join(out, ZIP_NAME)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(os.path.join(posts_dir, name), arcname=os.path.join("posts", name))

    # Compatibility check on a sample file.
    sample = os.path.join(posts_dir, files[0])
    with open(sample, encoding="utf-8") as f:
        s = BeautifulSoup(f.read(), "html.parser")
    checks = {
        "<title>": bool(s.title),
        "time.dt-published": bool(s.find("time", class_="dt-published")),
        "a.p-canonical": bool(s.find("a", class_="p-canonical")),
        "section[data-field=body]": bool(s.find("section", {"data-field": "body"})),
    }
    print(f"\nPackaged {len(files)} posts -> {zip_path}")
    print("Compatibility check (sample: %s):" % files[0])
    for name, ok in checks.items():
        print(f"  {'OK ' if ok else 'MISSING'}  {name}")
    if all(checks.values()):
        print("\nReady. Hand this ZIP to the medium-to-ssg skill.")
    else:
        print("\nWARNING: sample is missing required elements; inspect before handoff.")


# ── Orchestration ────────────────────────────────────────────────────────────

def process_urls(urls, out, delay, canonical_base=None):
    ensure_dirs(out)
    session = make_session()
    captured = failed = skipped = 0
    failures = []
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {url}")
        page = fetch(session, url, delay)
        if not page:
            failed += 1
            failures.append(url)
            continue
        meta, export_html, filename = post_from_html(page, url, canonical_base)
        if already_have(out, filename):
            print(f"   = already have {filename}; skipping")
            skipped += 1
            continue
        if not export_html:
            print("   ! no body captured; needs manual save-post capture")
            failed += 1
            failures.append(url)
            continue
        write_post(out, filename, export_html)
        append_manifest(out, meta, filename)
        print(f"   + {filename}")
        captured += 1
    _summary(captured, skipped, failed, failures, out)


def process_inbox(inbox, out, delay, canonical_base=None):
    ensure_dirs(out)
    files = [f for f in sorted(os.listdir(inbox)) if f.endswith((".html", ".htm"))]
    captured = failed = skipped = 0
    failures = []
    for i, name in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {name}")
        with open(os.path.join(inbox, name), encoding="utf-8") as f:
            page = f.read()
        link = BeautifulSoup(page, "html.parser").find("link", rel="canonical")
        source_url = link["href"] if link and link.get("href") else name
        meta, export_html, filename = post_from_html(page, source_url, canonical_base)
        if already_have(out, filename):
            print(f"   = already have {filename}; skipping")
            skipped += 1
            continue
        if not export_html:
            print("   ! no body captured")
            failed += 1
            failures.append(name)
            continue
        write_post(out, filename, export_html)
        append_manifest(out, meta, filename)
        print(f"   + {filename}")
        captured += 1
    _summary(captured, skipped, failed, failures, out)


def _summary(captured, skipped, failed, failures, out):
    print(f"\nCaptured {captured}, skipped {skipped} (already had), failed {failed}.")
    if failures:
        fail_path = os.path.join(out, "failed-urls.txt")
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failures) + "\n")
        print(f"Failed items written to {fail_path}.")
        print("Capture these with the save-post bookmarklet into an inbox/ "
              "folder, then run with --inbox.")


def load_urls_file(path):
    with open(path, encoding="utf-8") as f:
        return [normalize_url(line.strip()) for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser(description="Export a Medium publication to a medium-to-ssg ZIP.")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--site", help="Publication base URL; enumerate via sitemap and fetch.")
    src.add_argument("--urls", help="File of post URLs (one per line) to fetch.")
    src.add_argument("--inbox", help="Folder of raw post HTML (save-post bookmarklet) to normalize.")
    ap.add_argument("--out", default="medium-export-out", help="Output directory.")
    ap.add_argument("--delay", type=float, default=1.0, help="Seconds between fetches.")
    ap.add_argument(
        "--canonical-base",
        help="Original publication domain (e.g. https://mycompany.blog) to re-home "
        "every exported post's canonical URL to. Use when scraping from "
        "medium.com/<pub> because the custom domain has lapsed, so the export "
        "faithfully records the original public links. (The alias slug is "
        "preserved either way; this fixes the recorded domain.)",
    )
    ap.add_argument("--enumerate-only", action="store_true", help="With --site: only write urls.txt.")
    ap.add_argument("--package", action="store_true", help="Build the ZIP from posts/ and exit.")
    ap.add_argument(
        "--tags-report",
        action="store_true",
        help="List every topic tag in posts/ with how many posts use it "
        "(writes tags.csv), then exit. Review before pruning.",
    )
    ap.add_argument(
        "--prune-tags",
        help="Comma-separated tag names to remove from every captured post "
        '(case-insensitive), e.g. --prune-tags "NPR,Misc". Then re-run --package.',
    )
    ap.add_argument(
        "--min-tag-count",
        type=int,
        help="Remove any tag used by fewer than N posts (drops one-off tags). "
        "Can be combined with --prune-tags.",
    )
    args = ap.parse_args()

    ensure_dirs(args.out)

    if args.tags_report:
        write_tags_report(args.out)
        return

    if args.prune_tags or args.min_tag_count:
        drop = args.prune_tags.split(",") if args.prune_tags else []
        prune_tags(args.out, drop_names=drop, min_count=args.min_tag_count)
        return

    if args.package:
        package_zip(args.out)
        return

    if args.canonical_base:
        print(f"Pinning canonical URLs to {args.canonical_base.rstrip('/')}/<slug>")

    if args.site:
        session = make_session()
        print(f"Enumerating posts from {args.site} ...")
        urls = discover_urls_from_sitemap(session, args.site, args.delay)
        urls_path = os.path.join(args.out, "urls.txt")
        with open(urls_path, "w", encoding="utf-8") as f:
            f.write("\n".join(urls) + ("\n" if urls else ""))
        print(f"Found {len(urls)} post URLs -> {urls_path}")
        if args.enumerate_only:
            return
        process_urls(urls, args.out, args.delay, args.canonical_base)
        package_zip(args.out)
    elif args.urls:
        urls = load_urls_file(args.urls)
        print(f"Loaded {len(urls)} URLs from {args.urls}")
        process_urls(urls, args.out, args.delay, args.canonical_base)
        package_zip(args.out)
    elif args.inbox:
        process_inbox(args.inbox, args.out, args.delay, args.canonical_base)
        package_zip(args.out)
    else:
        ap.error("Provide one of --site, --urls, --inbox, or --package.")


if __name__ == "__main__":
    main()
