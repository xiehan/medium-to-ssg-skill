# Bookmarklets Reference

Two browser bookmarklets back up the automated scraper for the parts Medium makes hard:

- **Enumerate URLs** — collect every post URL from the publication's archive when the sitemap is missing or incomplete.
- **Save post** — capture a single post's fully-rendered HTML when the automated fetch is blocked (403/429) or the post is member-only.

Both run in your own logged-in browser, so they see what you see. The readable source for each lives next to this file in `scripts/` (`enumerate_urls.bookmarklet.js`, `save_post.bookmarklet.js`); the pasteable minified versions are below.

## How to install a bookmarklet (Chrome)

1. Show the bookmarks bar: **View → Always Show Bookmarks Bar** (or ⌘⇧B).
2. Right-click the bookmarks bar → **Add page…** (or **Add bookmark…**).
3. Put any name in **Name** (e.g. "Medium: enumerate URLs").
4. Paste the entire `javascript:…` line below into the **URL** field.
5. Save. Click the bookmark while on the right Medium page to run it.

Some browsers strip a leading `javascript:` when you paste — re-type those 11 characters if so.

## Bookmarklet 1 — Enumerate post URLs

**Run it on:** the publication's archive page, e.g. `https://mycompany.blog/archive`, while logged in.

It auto-scrolls and expands "show more" until the whole archive is loaded, collects every post link, deduplicates, and downloads `urls.txt`. Move that file into your output directory and run `python3 scripts/scrape_publication.py --urls urls.txt`.

```text
javascript:(async()=>{const s=new Set();const p=u=>{if(u.host!==location.host)return false;const x=u.pathname.replace(/\/$/,"");if(/^\/(tag|archive|search|m|me|membership)\b/.test(x))return false;if(x.startsWith("/@"))return false;return /-[0-9a-z]{6,}$/i.test(x);};const c=()=>{document.querySelectorAll("a[href]").forEach(a=>{try{const u=new URL(a.href,location.origin);if(p(u))s.add(u.origin+u.pathname.replace(/\/$/,""));}catch(e){}});};let l=-1,k=0;while(k<5){c();window.scrollTo(0,document.body.scrollHeight);document.querySelectorAll("button,a").forEach(e=>{if(/\b(show|load)\s+more\b/i.test(e.textContent||""))e.click();});await new Promise(r=>setTimeout(r,1500));if(s.size===l){k++;}else{k=0;l=s.size;}}c();const t=[...s].sort().join("\n")+"\n";const b=new Blob([t],{type:"text/plain"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="urls.txt";document.body.appendChild(a);a.click();a.remove();alert("Collected "+s.size+" post URLs -> urls.txt");})();
```

### Tips for enumerating URLs

- It can take a minute or two on a large publication — it waits for the archive to stop growing. Leave the tab focused.
- When it finishes it pops an alert with the count. Sanity-check that the number is in the ballpark you expect.
- If it collects too few, scroll the archive manually once to kick off loading, then re-run.

## Bookmarklet 2 — Save a single post

**Run it on:** an individual post page you couldn't fetch automatically (or a member-only post), while logged in.

It saves the rendered article plus the page's structured-data/meta tags as an HTML file. Put the saved files in `medium-export-out/inbox/` and run `python3 scripts/scrape_publication.py --inbox medium-export-out/inbox` to normalize them into the export format.

```text
javascript:(()=>{const art=document.querySelector("article")||document.body;const h=[];document.querySelectorAll('script[type="application/ld+json"]').forEach(s=>h.push(s.outerHTML));document.querySelectorAll('meta[property^="article:"],meta[property^="og:"],meta[name="author"],link[rel="canonical"]').forEach(m=>h.push(m.outerHTML));const can=location.origin+location.pathname.replace(/\/$/,"");const slug=can.split("/").pop()||"post";const doc='<!DOCTYPE html><html><head><meta charset="utf-8"><title>'+document.title+'</title><link rel="canonical" href="'+can+'">'+h.join("")+"</head><body>"+art.outerHTML+"</body></html>";const b=new Blob([doc],{type:"text/html"});const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download=slug+".html";document.body.appendChild(a);a.click();a.remove();})();
```

### Tips for saving a post

- Scroll the post to the bottom once before running it so any lazy-loaded images are in the DOM.
- One file is saved per post, named after the post's URL slug. Collect as many as you need, then normalize the whole `inbox/` folder in one run.
