/*
 * enumerate_urls.bookmarklet.js
 *
 * Collect every post URL from a Medium publication's archive page.
 *
 * Usage: open https://<publication>/archive while logged in (Chrome), then run
 * this as a bookmarklet (see references/bookmarklets.md for the minified,
 * pasteable version and step-by-step instructions). It auto-scrolls and clicks
 * any "show more" buttons until the whole archive is loaded, collects the post
 * links, deduplicates them, and downloads a urls.txt.
 *
 * This is the readable source. The bookmarklet is the same code wrapped in
 * "javascript:(async()=>{ ... })();" and URL-encoded.
 */
(async () => {
  const seen = new Set();

  // A post URL on this publication is same-origin and its last path segment
  // ends in a hyphen + short hash, e.g. /the-title-1a2b3c4d5e6f. Tag pages,
  // author pages (/@user), and the archive are excluded.
  const isPost = (u) => {
    if (u.host !== location.host) return false;
    const path = u.pathname.replace(/\/$/, "");
    if (/^\/(tag|archive|search|m|me|membership)\b/.test(path)) return false;
    if (path.startsWith("/@")) return false;
    return /-[0-9a-z]{6,}$/i.test(path);
  };

  const collect = () => {
    document.querySelectorAll("a[href]").forEach((a) => {
      try {
        const u = new URL(a.href, location.origin);
        if (isPost(u)) seen.add(u.origin + u.pathname.replace(/\/$/, ""));
      } catch (e) {
        /* ignore malformed hrefs */
      }
    });
  };

  // Scroll to the bottom and expand "more" buttons until the count stops
  // growing for several consecutive passes.
  let lastCount = -1;
  let stablePasses = 0;
  while (stablePasses < 5) {
    collect();
    window.scrollTo(0, document.body.scrollHeight);
    document.querySelectorAll("button, a").forEach((el) => {
      if (/\b(show|load)\s+more\b/i.test(el.textContent || "")) el.click();
    });
    await new Promise((r) => setTimeout(r, 1500));
    if (seen.size === lastCount) {
      stablePasses += 1;
    } else {
      stablePasses = 0;
      lastCount = seen.size;
    }
  }
  collect();

  const text = [...seen].sort().join("\n") + "\n";
  const blob = new Blob([text], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "urls.txt";
  document.body.appendChild(a);
  a.click();
  a.remove();
  alert("Collected " + seen.size + " post URLs -> urls.txt");
})();
