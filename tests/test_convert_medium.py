"""Regression tests for convert_medium.py (medium-to-ssg skill).

Focus: the HTML->Markdown transform and the front-matter assembly, including the
Hugo-vs-Eleventy branching. Image downloading is disabled (``DOWNLOAD_IMAGES``)
so no network is touched; ``localize_image_src`` then returns the original URL.
Each test pins behavior that was a past bug fix or is load-bearing for the two
SSG output formats.
"""
import os
import tempfile
import unittest

from bs4 import BeautifulSoup

from _loader import CONVERT_MEDIUM_PATH, load_module

cm = load_module("convert_medium", CONVERT_MEDIUM_PATH)


def node(html):
    """Parse a fragment and return its first element node."""
    return BeautifulSoup(html, "html.parser").find()


def md(html, ssg="hugo"):
    """Convert an HTML fragment to Markdown under the given SSG, no network."""
    prev_ssg, prev_dl = cm.SSG, cm.DOWNLOAD_IMAGES
    cm.SSG, cm.DOWNLOAD_IMAGES = ssg, False
    try:
        return cm.node_to_md(node(html))
    finally:
        cm.SSG, cm.DOWNLOAD_IMAGES = prev_ssg, prev_dl


# Minimal export-format page that convert_post() knows how to read.
EXPORT_TEMPLATE = """<!DOCTYPE html>
<html><head><title>{title}</title></head><body>
<article class="h-entry">
  <header><h1 class="p-name">{title}</h1></header>
  {author}
  <section data-field="body" class="e-content">{body}</section>
  <footer>
    <time class="dt-published" datetime="{date_iso}">{date_h}</time>
    <a class="p-canonical" href="{canonical}"></a>
    {tags}
  </footer>
</article></body></html>
"""


def write_export(tmpdir, filename, *, title="My Post", body="<p>Hello world.</p>",
                 author="Greg Sauer", date_iso="2019-09-04T08:00:00.000Z",
                 canonical="https://blog.example.com/my-post-a1b2c3d4e5f6", tags=()):
    author_html = (
        f'<p class="p-author">By <a class="p-author h-card" href="">{author}</a></p>'
        if author else ""
    )
    tags_html = (
        '<p class="tags">'
        + "".join(f'<a class="p-category" href="">{t}</a>' for t in tags)
        + "</p>"
        if tags else ""
    )
    html = EXPORT_TEMPLATE.format(
        title=title, author=author_html, body=body, date_iso=date_iso,
        date_h="", canonical=canonical, tags=tags_html,
    )
    path = os.path.join(tmpdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return filename


class InlineFormattingTests(unittest.TestCase):
    def test_bold_and_italic(self):
        self.assertEqual(md("<strong>hi</strong>"), "**hi**")
        self.assertEqual(md("<em>hi</em>"), "*hi*")

    def test_boundary_whitespace_moves_outside_markers(self):
        # "* text *" is not valid emphasis; the space must move outside.
        self.assertEqual(md("<strong> hi </strong>"), " **hi** ")

    def test_link(self):
        self.assertEqual(
            md('<a href="https://example.com">text</a>'),
            "[text](https://example.com)",
        )

    def test_empty_link_is_dropped(self):
        self.assertEqual(md('<a href="https://example.com">   </a>'), "")


class MalformedLinkTests(unittest.TestCase):
    """Medium can mangle a paren-wrapped URL into ``scheme://%28<real-url>``."""

    def test_clean_href_unwraps_mangled_target(self):
        self.assertEqual(
            cm._clean_href("http://%28https://example.com%29"),
            "https://example.com",
        )

    def test_clean_href_leaves_normal_url_untouched(self):
        self.assertEqual(
            cm._clean_href("https://example.com/path"),
            "https://example.com/path",
        )

    def test_mangled_link_is_repaired_in_output(self):
        out = md('<a href="http://%28https://example.com%29">site</a>')
        self.assertEqual(out, "[site](https://example.com)")


class RawHtmlEscapingTests(unittest.TestCase):
    """Angle brackets in prose must be entity-escaped (Goldmark unsafe=false)."""

    def test_angle_brackets_in_text_are_escaped(self):
        out = md("<p>configure &lt;global-mapping&gt; here</p>")
        self.assertIn("configure &lt;global-mapping&gt; here", out)

    def test_inline_code_stays_literal(self):
        # Code spans read raw text and must NOT be entity-escaped.
        out = md("<p>use <code>&lt;tag&gt;</code> now</p>")
        self.assertIn("`<tag>`", out)


class CodeBlockTests(unittest.TestCase):
    def test_pre_preserves_line_breaks(self):
        out = md("<pre>line one<br>line two</pre>")
        self.assertIn("line one\nline two", out)
        self.assertIn("```", out)

    def test_fence_grows_when_content_has_backticks(self):
        # Content containing a triple backtick must be fenced with more.
        out = md("<pre>```<br>nested</pre>")
        self.assertIn("````", out)

    def test_pre_joins_span_line_groups(self):
        out = md("<pre><span>a<br>b</span><span>c</span></pre>")
        self.assertIn("a\nb\nc", out)


class BlockElementTests(unittest.TestCase):
    def test_heading_levels(self):
        self.assertIn("## Title", md("<h2>Title</h2>"))

    def test_unordered_list(self):
        out = md("<ul><li>one</li><li>two</li></ul>")
        self.assertIn("- one", out)
        self.assertIn("- two", out)

    def test_ordered_list(self):
        out = md("<ol><li>one</li><li>two</li></ol>")
        self.assertIn("1. one", out)

    def test_blockquote(self):
        out = md("<blockquote>quoted</blockquote>")
        self.assertIn("> quoted", out)

    def test_hr(self):
        self.assertIn("---", md("<hr>"))


class FigureAndImageTests(unittest.TestCase):
    def test_image_keeps_remote_src_when_download_disabled(self):
        out = md('<img src="https://img.example.com/x.png" alt="cat">')
        self.assertEqual(out, "![cat](https://img.example.com/x.png)")

    def test_figure_image_with_caption(self):
        out = md(
            '<figure><img src="https://img.example.com/x.png" alt="cat">'
            "<figcaption>A cat</figcaption></figure>"
        )
        self.assertIn("![cat](https://img.example.com/x.png)", out)
        self.assertIn("*A cat*", out)

    def test_figure_iframe_video_hugo_shortcode(self):
        out = md(
            '<figure><iframe src="https://youtube.com/embed/x"></iframe></figure>',
            ssg="hugo",
        )
        self.assertIn('{{< video src="https://youtube.com/embed/x" >}}', out)

    def test_figure_iframe_video_eleventy_shortcode(self):
        out = md(
            '<figure><iframe src="https://youtube.com/embed/x"></iframe></figure>',
            ssg="eleventy",
        )
        self.assertIn('{% video "https://youtube.com/embed/x" %}', out)


class ConvertPostFrontMatterTests(unittest.TestCase):
    """End-to-end front-matter assembly, including the SSG branch."""

    def setUp(self):
        self._prev = (cm.INPUT_DIR, cm.SSG, cm.DOWNLOAD_IMAGES,
                      cm.EXTRACT_TAGS, cm.PERMALINK_PREFIX)
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = self._tmpdir.name
        cm.INPUT_DIR = self.tmp
        cm.DOWNLOAD_IMAGES = False
        cm.EXTRACT_TAGS = True
        cm.PERMALINK_PREFIX = "/posts"

    def tearDown(self):
        (cm.INPUT_DIR, cm.SSG, cm.DOWNLOAD_IMAGES,
         cm.EXTRACT_TAGS, cm.PERMALINK_PREFIX) = self._prev
        self._tmpdir.cleanup()

    def test_hugo_front_matter_uses_slug(self):
        cm.SSG = "hugo"
        fn = write_export(self.tmp, "post.html")
        out = cm.convert_post(fn, "my-post")
        self.assertIn('slug: "my-post"', out)
        self.assertNotIn("permalink:", out)

    def test_eleventy_front_matter_uses_permalink(self):
        cm.SSG = "eleventy"
        fn = write_export(self.tmp, "post.html")
        out = cm.convert_post(fn, "my-post")
        self.assertIn('permalink: "/posts/my-post/"', out)
        self.assertNotIn("slug:", out)

    def test_date_comes_from_dt_published(self):
        cm.SSG = "hugo"
        fn = write_export(self.tmp, "post.html", date_iso="2019-09-04T08:00:00.000Z")
        out = cm.convert_post(fn, "my-post")
        self.assertIn("date: 2019-09-04", out)

    def test_draft_export_raises_clear_error(self):
        # Personal exports name unpublished drafts `draft_*.html`; they have no
        # dt-published date. convert_post must reject them with a message that
        # names the draft, not a cryptic parse error.
        fn = "draft_How-To-Do-X-f82aa957032e.html"
        with open(os.path.join(self.tmp, fn), "w", encoding="utf-8") as f:
            f.write("<html><head><title>Draft</title></head>"
                    "<body><section data-field=\"body\">x</section></body></html>")
        with self.assertRaises(ValueError) as ctx:
            cm.convert_post(fn, "how-to-do-x")
        self.assertIn(fn, str(ctx.exception))
        self.assertIn("draft", str(ctx.exception).lower())

    def test_alias_preserves_medium_slug_on_both_ssgs(self):
        for ssg in ("hugo", "eleventy"):
            cm.SSG = ssg
            fn = write_export(self.tmp, "post.html")
            out = cm.convert_post(fn, "my-post")
            self.assertIn("aliases:\n  - /my-post-a1b2c3d4e5f6", out, ssg)

    def test_author_line_present(self):
        cm.SSG = "hugo"
        fn = write_export(self.tmp, "post.html", author="Greg Sauer")
        out = cm.convert_post(fn, "my-post")
        self.assertIn('author: "Greg Sauer"', out)

    def test_tags_written_when_present(self):
        cm.SSG = "hugo"
        fn = write_export(self.tmp, "post.html", tags=("Web Development", "Java"))
        out = cm.convert_post(fn, "my-post")
        self.assertIn("tags:\n", out)
        self.assertIn('  - "Web Development"', out)
        self.assertIn('  - "Java"', out)

    def test_title_with_quotes_is_escaped(self):
        cm.SSG = "hugo"
        fn = write_export(self.tmp, "post.html", title='The "Best" Post')
        out = cm.convert_post(fn, "my-post")
        self.assertIn(r'title: "The \"Best\" Post"', out)


if __name__ == "__main__":
    unittest.main()
