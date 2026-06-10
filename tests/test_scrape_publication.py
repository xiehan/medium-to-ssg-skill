"""Regression tests for scrape_publication.py (medium-publication-export skill).

Focus: the pure parsing/transformation layer. Network fetching, the sitemap
crawl, and file output are intentionally out of scope. Each test pins a piece of
behavior that was the subject of a past bug fix or is load-bearing for the
export format the medium-to-ssg converter consumes.
"""
import unittest

from bs4 import BeautifulSoup

from _loader import SCRAPE_PUBLICATION_PATH, load_module

sp = load_module("scrape_publication", SCRAPE_PUBLICATION_PATH)


def soup(html):
    return BeautifulSoup(html, "html.parser")


class LdJsonArticleTypeTests(unittest.TestCase):
    """Medium tags post JSON-LD as ``SocialMediaPosting`` (the date-bug fix)."""

    def test_recognizes_social_media_posting(self):
        page = soup(
            '<script type="application/ld+json">'
            '{"@type": "SocialMediaPosting", "datePublished": "2019-09-04T12:00:00.000Z"}'
            "</script>"
        )
        obj = sp._ld_json_article(page)
        self.assertIsNotNone(obj)
        self.assertEqual(obj["datePublished"], "2019-09-04T12:00:00.000Z")

    def test_recognizes_classic_article_types(self):
        for typ in ("Article", "NewsArticle", "BlogPosting"):
            page = soup(
                '<script type="application/ld+json">'
                f'{{"@type": "{typ}", "headline": "x"}}'
                "</script>"
            )
            self.assertIsNotNone(sp._ld_json_article(page), typ)

    def test_finds_article_inside_json_ld_list(self):
        page = soup(
            '<script type="application/ld+json">'
            '[{"@type": "WebPage"}, {"@type": "SocialMediaPosting", "headline": "y"}]'
            "</script>"
        )
        obj = sp._ld_json_article(page)
        self.assertEqual(obj["headline"], "y")

    def test_ignores_unrelated_and_malformed_blocks(self):
        page = soup(
            '<script type="application/ld+json">{"@type": "WebSite"}</script>'
            '<script type="application/ld+json">not json</script>'
        )
        self.assertIsNone(sp._ld_json_article(page))


class ExtractMetadataDateTests(unittest.TestCase):
    """The original publish date must win over the last-edited meta tag."""

    def test_prefers_datepublished_over_article_published_time(self):
        # The exact bug: JSON-LD carries the real first-publish date while the
        # meta tag carries Medium's latest (last-edited) publish time.
        page = soup(
            '<script type="application/ld+json">'
            '{"@type": "SocialMediaPosting",'
            ' "datePublished": "2019-09-04T08:00:00.000Z"}'
            "</script>"
            '<meta property="article:published_time" content="2020-10-01T00:00:00.000Z">'
            "<title>A glimpse under the hood</title>"
        )
        meta = sp.extract_metadata(page, "https://blog.example.com/a-glimpse-abc123")
        self.assertEqual(meta["date_iso"], "2019-09-04T08:00:00.000Z")

    def test_falls_back_to_meta_when_no_json_ld(self):
        page = soup(
            '<meta property="article:published_time" content="2021-02-03T00:00:00.000Z">'
            "<title>No JSON-LD here</title>"
        )
        meta = sp.extract_metadata(page, "https://blog.example.com/no-json-ld-abc123")
        self.assertEqual(meta["date_iso"], "2021-02-03T00:00:00.000Z")


class ExtractMetadataAuthorTitleTests(unittest.TestCase):
    def test_author_from_json_ld_dict(self):
        page = soup(
            '<script type="application/ld+json">'
            '{"@type": "SocialMediaPosting", "headline": "Hi",'
            ' "datePublished": "2019-10-15T00:00:00.000Z",'
            ' "author": {"@type": "Person", "name": "Greg Sauer"}}'
            "</script>"
        )
        meta = sp.extract_metadata(page, "https://blog.example.com/profile-greg-abc123")
        self.assertEqual(meta["author"], "Greg Sauer")
        self.assertEqual(meta["title"], "Hi")

    def test_author_from_json_ld_list(self):
        page = soup(
            '<script type="application/ld+json">'
            '{"@type": "Article", "author":'
            ' [{"name": "Ann"}, {"name": "Bob"}]}'
            "</script><title>t</title>"
        )
        meta = sp.extract_metadata(page, "https://blog.example.com/co-authored-abc123")
        self.assertEqual(meta["author"], "Ann, Bob")

    def test_title_strips_publication_suffix(self):
        page = soup("<title>My Great Post | Some Publication</title>")
        meta = sp.extract_metadata(page, "https://blog.example.com/my-great-post-abc123")
        self.assertEqual(meta["title"], "My Great Post")


class UrlHelperTests(unittest.TestCase):
    def test_normalize_url_drops_query_fragment_and_trailing_slash(self):
        self.assertEqual(
            sp.normalize_url("https://blog.example.com/my-post-abc123/?ref=x#section"),
            "https://blog.example.com/my-post-abc123",
        )

    def test_is_probable_post_url_accepts_hashed_slug(self):
        self.assertTrue(
            sp.is_probable_post_url(
                "https://blog.example.com/my-post-a1b2c3d4e5f6", "blog.example.com"
            )
        )

    def test_is_probable_post_url_rejects_other_host(self):
        self.assertFalse(
            sp.is_probable_post_url(
                "https://other.example.com/my-post-a1b2c3", "blog.example.com"
            )
        )

    def test_is_probable_post_url_rejects_section_and_profile_paths(self):
        host = "blog.example.com"
        self.assertFalse(sp.is_probable_post_url("https://blog.example.com/tag/python", host))
        self.assertFalse(sp.is_probable_post_url("https://blog.example.com/@someone", host))
        self.assertFalse(sp.is_probable_post_url("https://blog.example.com/about", host))

    def test_is_probable_post_url_rejects_unhashed_path(self):
        self.assertFalse(
            sp.is_probable_post_url("https://blog.example.com/plain-page", "blog.example.com")
        )

    def test_slug_from_url(self):
        self.assertEqual(
            sp.slug_from_url("https://blog.example.com/some-title-abc123/"),
            "some-title-abc123",
        )

    def test_rehome_canonical_swaps_domain_keeps_slug(self):
        rehomed = sp.rehome_canonical(
            "https://medium.com/the-pub/some-title-abc123", "https://blog.example.com"
        )
        self.assertEqual(rehomed, "https://blog.example.com/some-title-abc123")

    def test_rehome_canonical_noop_without_base(self):
        url = "https://medium.com/the-pub/some-title-abc123"
        self.assertEqual(sp.rehome_canonical(url, None), url)


class DateFormattingTests(unittest.TestCase):
    def test_date_only(self):
        self.assertEqual(sp._date_only("2019-09-04T08:00:00.000Z"), "2019-09-04")

    def test_human_date(self):
        self.assertEqual(sp._human_date("2019-09-04T08:00:00.000Z"), "September 04, 2019")

    def test_date_only_falls_back_on_garbage(self):
        # Invalid input must not raise; it returns today's date (length 10).
        self.assertEqual(len(sp._date_only("not-a-date")), 10)

    def test_human_date_empty_on_garbage(self):
        self.assertEqual(sp._human_date("not-a-date"), "")


class ExtractTagsTests(unittest.TestCase):
    def test_topic_pills_are_preferred(self):
        page = soup(
            '<a aria-label="Topic: Web Development">x</a>'
            '<a aria-label="Topic: Accessibility">y</a>'
        )
        self.assertEqual(sp.extract_tags(page), ["Web Development", "Accessibility"])

    def test_dedupes_case_insensitively(self):
        page = soup(
            '<a aria-label="Topic: Python">a</a>'
            '<a aria-label="Topic: python">b</a>'
        )
        self.assertEqual(sp.extract_tags(page), ["Python"])

    def test_no_tags_returns_empty_list(self):
        self.assertEqual(sp.extract_tags(soup("<p>no tags here</p>")), [])


class BuildExportHtmlTests(unittest.TestCase):
    """The export HTML must carry the markers convert_medium.py reads back."""

    def _meta(self, **over):
        base = {
            "title": "My Post",
            "date_iso": "2019-09-04T08:00:00.000Z",
            "author": "Greg Sauer",
            "canonical": "https://blog.example.com/my-post-abc123",
            "tags": ["Web Development", "Accessibility"],
        }
        base.update(over)
        return base

    def test_includes_dt_published_with_iso_datetime(self):
        out = sp.build_export_html(self._meta(), "<p>Body.</p>")
        page = soup(out)
        t = page.find("time", class_="dt-published")
        self.assertIsNotNone(t)
        self.assertEqual(t["datetime"], "2019-09-04T08:00:00.000Z")

    def test_includes_body_section_canonical_and_author(self):
        out = sp.build_export_html(self._meta(), "<p>Body.</p>")
        page = soup(out)
        self.assertIsNotNone(page.find("section", {"data-field": "body"}))
        self.assertIsNotNone(page.find("a", class_="p-canonical"))
        self.assertIsNotNone(page.find("a", class_="p-author"))

    def test_tags_render_as_p_category_links(self):
        out = sp.build_export_html(self._meta(), "<p>Body.</p>")
        cats = soup(out).find_all("a", class_="p-category")
        self.assertEqual([c.get_text() for c in cats], ["Web Development", "Accessibility"])

    def test_no_author_block_when_author_missing(self):
        out = sp.build_export_html(self._meta(author=""), "<p>Body.</p>")
        self.assertIsNone(soup(out).find("a", class_="p-author"))

    def test_title_is_escaped(self):
        out = sp.build_export_html(self._meta(title='A & B <c>'), "<p>Body.</p>")
        self.assertIn("A &amp; B &lt;c&gt;", out)


if __name__ == "__main__":
    unittest.main()
