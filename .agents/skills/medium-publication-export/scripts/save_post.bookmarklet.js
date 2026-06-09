/*
 * save_post.bookmarklet.js
 *
 * Save a single Medium post's fully-rendered HTML from the logged-in browser.
 * Use this for posts the automated fetcher can't get (403/429) or that are
 * member-only: open the post, run the bookmarklet, and it downloads an HTML
 * file you drop into medium-export-out/inbox/ for the scraper to normalize
 * (python3 scripts/scrape_publication.py --inbox medium-export-out/inbox).
 *
 * It captures the rendered <article> plus the page's structured-data and meta
 * tags (which live in <head>, not in <article>) so the scraper can still read
 * the title, publish date, author, and canonical URL.
 *
 * This is the readable source. The bookmarklet is the same code wrapped in
 * "javascript:(()=>{ ... })();" and URL-encoded (see references/bookmarklets.md).
 */
(() => {
  const article = document.querySelector("article") || document.body;

  // Pull the metadata-bearing head elements so the saved file is self-contained.
  const head = [];
  document
    .querySelectorAll('script[type="application/ld+json"]')
    .forEach((s) => head.push(s.outerHTML));
  document
    .querySelectorAll(
      'meta[property^="article:"], meta[property^="og:"], meta[name="author"], link[rel="canonical"]'
    )
    .forEach((m) => head.push(m.outerHTML));

  const canonical = location.origin + location.pathname.replace(/\/$/, "");
  const slug = canonical.split("/").pop() || "post";

  const doc =
    "<!DOCTYPE html><html><head><meta charset=\"utf-8\">" +
    "<title>" +
    document.title +
    "</title>" +
    '<link rel="canonical" href="' +
    canonical +
    '">' +
    head.join("") +
    "</head><body>" +
    article.outerHTML +
    "</body></html>";

  const blob = new Blob([doc], { type: "text/html" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = slug + ".html";
  document.body.appendChild(a);
  a.click();
  a.remove();
})();
