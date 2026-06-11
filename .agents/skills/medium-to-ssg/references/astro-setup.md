# Astro Site Setup Reference

This is the Astro counterpart to `hugo-setup.md`. Read it instead of (not in addition to) `hugo-setup.md` or `eleventy-setup.md` when the chosen SSG is **Astro**. Hugo remains the default; only follow this file when the user explicitly chose Astro.

Astro is a Node.js static site generator. Like Eleventy — and unlike Hugo — there is **no installable theme system** and no single binary: a site is an npm project, and the closest equivalent to a "theme" is a **starter template** you scaffold once and own. Astro's official showcase is mostly *paid* themes; this skill standardizes on the free, first-party [`blog` starter](https://github.com/withastro/astro/tree/latest/examples/blog) (the one behind `npm create astro@latest -- --template blog`) as the default. The user may pick a different starter, but the steps below assume the blog starter's conventions and you must re-read the chosen starter's README and config if it differs.

The converter (`scripts/convert_medium.py`) must be run with `SSG = "astro"` for this path. That changes only the per-post front matter (`slug:` + `pubDate:` instead of Hugo's `slug:` + `date:` or Eleventy's `permalink:` + `date:`) and the video embed (a raw responsive `<iframe>` instead of a shortcode); everything else it produces is identical to the Hugo and Eleventy paths.

## Step 1 — Scaffold the starter into `astro-site/`

Create the Astro project from the official blog template into `astro-site/` (the Astro parallel to `hugo-site/` and `eleventy-site/`). Scaffold non-interactively, skipping the starter's own git history:

```bash
npm create astro@latest astro-site -- --template blog --no-git --skip-houston --yes
```

`--no-git` keeps the scaffold part of the user's own repository instead of starting a nested one; `--skip-houston` suppresses the interactive mascot animation; `--yes` accepts the defaults (including installing dependencies). If `--yes` skipped the install in your environment, run `cd astro-site && npm install` yourself (Step 2).

### Remove the starter's demo content

Unlike a cloned starter repo, a fresh `npm create astro` scaffold carries little foreign CI cruft — but it does ship **demo content** that must not survive into the user's blog: sample posts, a placeholder about page, and the starter's own README. Audit and remove what doesn't apply (`ls -a astro-site` and check `src/`):

- `astro-site/src/content/blog/*.md` / `*.mdx` — the starter's sample posts. Delete them; the converter writes the user's real posts into this directory in Step 4.
- `astro-site/README.md` — documents the starter, not the user's blog. Replace it with a short README for the user's site, or remove it.
- `astro-site/src/pages/about.astro` — a lorem-ipsum **About page** (with a placeholder hero image). Hugo and Eleventy ship no About page by default, so don't ship this one either: an About page full of "Lorem ipsum" is worse than none. **Rename it to `about.astro.example`** rather than deleting it — Astro only builds routes from files with a page extension (`.astro`, `.md`, `.mdx`, …), so a `.astro.example` file is *not* routed and won't ship, yet it stays in the tree as a worked example showing the user how to add a custom page (and how to use the `BlogPost` layout for a standalone page). Tell the user to rename it back to `about.astro` and replace the lorem-ipsum once they've written real copy. **Also remove the `/about` link** from the header nav in `Header.astro` (and any other nav/footer reference) so the site has no dead link to the now-unrouted page; the user re-adds the link when they restore the page.
- `astro-site/src/pages/index.astro` — the starter's "Hello, Astronaut!" placeholder home page. Don't just delete it (the site needs a home page); **replace** it with a post listing in Step 4 ("Replace the placeholder homepage with the post list") so the front door is the user's blog, not template boilerplate.
- `astro-site/src/components/Header.astro` **and** `Footer.astro` — both ship a `.social-links` block that links to **Astro's own** Mastodon/Twitter/GitHub accounts (`@astro`, `astrodotbuild`, `withastro/astro`), not the user's. Shipping them would send the user's readers to Astro's socials. **Remove the `.social-links` `<div>` from both components** (and their now-orphaned CSS rules) by default. While you're in `Footer.astro`, also replace its `Your name here` copyright placeholder with the user's name (ask; don't invent it). Only keep social icons if the user explicitly asks — see "Restoring social links (pointed at the user's own accounts)" below — in which case repoint the `href`s and `sr-only` labels to the user's accounts.
  - **Re-center the header nav after removing the icons.** The starter's `<nav>` uses `display: flex; justify-content: space-between` and relies on *three* children (the title, the internal links, the social block) to land the nav links in the middle. Removing the social block leaves two children, so `space-between` shoves the nav links to the far right. Switch the `nav` rule in `Header.astro` to a centered three-column grid so the links stay centered with or without the social block:

    ```css
    nav {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
    }
    ```

    The title falls in the left `1fr`, the links in the centered `auto` column, and the right `1fr` stays empty (or holds the social block if it's later restored — give a restored `.social-links` `justify-self: end` so it sits at the right edge).

Two judgment calls rather than automatic deletions:

- **`LICENSE`** — if the scaffold ships one, it is the *starter's* license (the blog starter is based on Bear Blog). Keep any attribution a permissive license requires, or replace it with the user's own license while preserving required attribution. Confirm with the user.
- **`astro.config.mjs` extras** — the blog starter wires up `@astrojs/mdx`, `@astrojs/sitemap`, an RSS feed, and a bundled font. Keep these; they are useful and not cruft. You only edit the `site` value (Step 3) and add the `aliases` schema field (Step 7).

If the user supplied a different starter, scaffold/clone that instead and read its README before continuing — the directory names, schema, config, and routing below may all differ.

## Step 2 — Pin Node and install dependencies

Astro is Node software, so a compatible Node.js version is the first prerequisite (the analog of "Hugo Extended" on the Hugo path). Astro requires a fairly recent Node release and does not support odd-numbered Node majors, so its floor tends to climb as new Node LTS lines land. **Do not hard-code a version — read it from the starter.** The blog starter declares its requirement in `package.json` `engines` (at the time of writing `"node": ">=22.12.0"`, but treat that as an example, not a constant); also honor any `.nvmrc`/`volta` pin it ships. Pin exactly what the starter requires:

```bash
cd astro-site
# Use the version from the starter's package.json "engines" (or its .nvmrc):
node -p "require('./package.json').engines?.node"   # inspect the requirement
echo "22.12.0" > .nvmrc   # replace with the version the engines field requires
nvm use                    # install that version first with `nvm install` if needed
npm install
```

The same Node version must be used locally and in CI (Phase: Content Deployment wires `actions/setup-node` to match — see `references/cicd.md` / `references/github-pages.md`). A mismatch between local and CI Node is the most common cause of "builds for me, fails in CI" on this path — and on Astro a Node older than the starter's `engines` floor fails the build outright.

Because the site is an npm project, Phase 5 (Content Deployment) also adds a `package-ecosystem: npm` entry to `.github/dependabot.yml` so Astro and its integrations stay patched. This happens on **every** hosting platform and deployment method, including the manual AWS CLI path that generates no workflows — see "Node SSGs: also track npm dependencies" in `references/cicd.md`.

## Step 3 — Configure site metadata

The production URL lives in `astro.config.mjs` as `site` — it is what the sitemap, the RSS feed, and any absolute/canonical links use. Set it to the final custom domain:

```js
// astro.config.mjs
export default defineConfig({
  site: 'https://DOMAIN',
  // integrations: [mdx(), sitemap()],  // leave the starter's integrations as-is
  // ...
});
```

The blog starter also keeps the site title and description in a small constants file (`src/consts.ts` in the blog example: `SITE_TITLE`, `SITE_DESCRIPTION`) — read it and update those strings. Ask the user to confirm the site title and description before writing them; do not invent copy.

## Step 4 — Decide where posts live and which URL they get

Two settings must agree across the converter and the Astro project, or posts will 404 or land at the wrong URL:

| Concept | Converter setting | Astro side |
|---|---|---|
| Where the `.md` files are written | `OUTPUT_DIR` | the content collection directory (blog starter: `src/content/blog/`) |
| The canonical post URL prefix | *(none — Astro ignores `PERMALINK_PREFIX`)* | the route directory under `src/pages/` |

Set the converter's `OUTPUT_DIR = "astro-site/src/content/blog"` so converted posts land in the starter's `blog` content collection.

### How Astro derives the URL (filename → entry id → route)

Astro does **not** read a `permalink:` field. The blog starter loads the collection with a `glob` loader, which assigns each entry an **`id` from its filename** (a file named `my-post.md` gets `id: "my-post"`). The dynamic route then maps that id into the URL. So the converter controls the URL by **naming each file `<slug>.md`** — which it already does. The converter also writes a `slug:` field into the front matter for parity with the Hugo path; Astro's schema ignores unknown fields, so it is harmless.

The blog starter serves posts from `src/pages/blog/[...slug].astro`, which produces URLs under `/blog/`. To match this skill's canonical `/posts/<slug>/` (the Hugo/Eleventy default), **move that route directory to `posts/`** and repoint the starter's internal links:

```bash
cd astro-site
mv src/pages/blog src/pages/posts
grep -rl '/blog' src/        # find nav links, the listing page, and cards that hard-code /blog/
```

Update every `/blog` reference the `grep` finds (the header nav, the post listing page, and any "read more" link in a card/layout) to `/posts`. The dynamic route file itself needs no change — it already maps `params: { slug: post.id }`, so after the move it emits `/posts/<id>/`. If the user wants a different prefix (e.g. `/archive/`), name the route directory `src/pages/archive/` instead and update the redirect-route `target` in Step 7 to match (`/archive/<id>/`). The converter's `PERMALINK_PREFIX` has no effect on the Astro path — the route directory alone controls the prefix.

### Relax the content-collection schema

This is the step with no Hugo/Eleventy equivalent and the one most likely to **hard-fail the build** if skipped. Astro type-checks every post against the Zod schema in `src/content.config.ts`, and a **missing required field is a build error** (stricter than Eleventy, which only crashes if a template happens to use the field). The blog starter's schema requires `title`, `description`, and `pubDate`. Medium exports have a title and a date but **no description**, so the schema must be relaxed to make `description` (and the image-typed `heroImage`) optional. Own the schema — do **not** fabricate descriptions:

```ts
// src/content.config.ts — relax the starter's schema for migrated posts
schema: ({ image }) =>
  z.object({
    title: z.string(),
    description: z.string().optional(),        // Medium has no per-post description
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    heroImage: z.optional(image()),
    aliases: z.array(z.string()).optional(),   // old Medium URLs -> redirect stubs (Step 7)
  }),
```

Two consequences to handle:

- **Templates must tolerate the now-optional fields.** The starter's post layout and listing card may render `description`/`heroImage` unconditionally (e.g. `<meta name="description" content={description}>` or `<Image src={heroImage} />`), which breaks or emits empty tags when the field is absent. Guard them: render the `<meta description>`, the hero `<Image>`, and any card excerpt only `{description && ...}` / `{heroImage && ...}`.
- **`heroImage` uses `astro:assets` (`image()`), the converted posts don't set it.** That's fine — it's optional and the migrated posts omit it. The converter self-hosts inline body images a different way (Step 5), deliberately bypassing `astro:assets`.

### Tags

Each converted post may carry Medium topic tags in its front matter (`tags: [...]`). If the chosen starter renders or indexes tags, add `tags: z.array(z.string()).optional()` to the schema so they validate, and confirm the listing/tag pages read `post.data.tags`. The blog starter has no tag pages by default, so converted posts simply carry the field unused until the user builds tag pages — no build failure either way once the field is in the schema (or stripped as unknown if you leave it out).

### Replace the placeholder homepage with the post list

The blog starter's home page (`src/pages/index.astro`) is a **static "Hello, Astronaut!" welcome page** — Astro-template boilerplate that lists the starter's features and links to Astro's docs and Discord. Unlike the Hugo theme and the Eleventy starter, whose home pages list posts out of the box, the Astro starter keeps its post listing on a *separate* page (the route directory you moved to `src/pages/posts/` in the step above). If you leave `index.astro` alone, the user's front door is placeholder marketing copy, not their blog — **not** something they could deploy as-is. Replace it so the home page is the blog.

Reuse the listing the starter already wrote (the `getCollection('blog')` query and post-card markup in `src/pages/posts/index.astro`) rather than inventing a new layout — keep the starter's `Header`, `Footer`, `BaseHead`, and `FormattedDate` components and its CSS variables so it matches the rest of the site. Show the most recent posts (truncated, e.g. the latest 10) and link to the full archive at `/posts/`:

```astro
---
import { getCollection } from 'astro:content';
import BaseHead from '../components/BaseHead.astro';
import Footer from '../components/Footer.astro';
import FormattedDate from '../components/FormattedDate.astro';
import Header from '../components/Header.astro';
import { SITE_DESCRIPTION, SITE_TITLE } from '../consts';

const posts = (await getCollection('blog'))
  .sort((a, b) => b.data.pubDate.valueOf() - a.data.pubDate.valueOf())
  .slice(0, 10); // most recent; the full archive lives at /posts/
---
<!doctype html>
<html lang="en">
  <head>
    <BaseHead title={SITE_TITLE} description={SITE_DESCRIPTION} />
  </head>
  <body>
    <Header />
    <main>
      <section>
        <h1>{SITE_TITLE}</h1>
        <p>{SITE_DESCRIPTION}</p>
      </section>
      <section>
        <ul>
          {posts.map((post) => (
            <li>
              <a href={`/posts/${post.id}/`}>{post.data.title}</a>
              <FormattedDate date={post.data.pubDate} />
            </li>
          ))}
        </ul>
        <p><a href="/posts/">View all posts &rarr;</a></p>
      </section>
    </main>
    <Footer />
  </body>
</html>
```

Notes:

- This depends on the same content collection and route as everything else, so use the **actual collection name** (`blog` for this starter) and the **actual post URL prefix** (`/posts/` here; whatever you set in this step otherwise).
- A truncated list with an archive link is the minimal "feels like a blog" change; showing **all** posts on the home page is also fine (drop the `.slice`) — the starter's `/posts/` listing already does that, so truncating keeps the two pages distinct.
- If you prefer the home page *be* the full archive and don't want a duplicate listing, an alternative is to redirect `/` to `/posts/` (add `'/': '/posts/'` to the `redirects` map in `astro.config.mjs`); but a short curated home page reads better as a landing page. Pick one; don't ship both the placeholder and a redirect.
- Style is inherited from the starter's global stylesheet. Add a little scoped CSS if you want the date aligned or the list spaced, but it is not required for a clean, deployable page.

### Restoring social links (pointed at the user's own accounts)

By default the starter's social icons are removed (see Step 1) because they link to **Astro's** accounts, not the user's. If the user wants social links back — pointing at *their own* profiles — bring the block back and repoint it. Ask the user for the exact profile URLs (and which platforms); do **not** invent handles. Then, in `src/components/Header.astro` and/or `Footer.astro` (the starter puts the same `.social-links` block in both — restore it wherever the user wants the icons), restore a `.social-links` `<div>` and the small `.social-links` CSS rules (the header hides them under 720px with a media query — keep or drop that as the user prefers). For each platform the user has, point the `href` at their profile and rewrite the `sr-only` label to name them, e.g.:

```astro
<div class="social-links">
  <a href="https://github.com/USERNAME" target="_blank" rel="me">
    <span class="sr-only">USER on GitHub</span>
    <!-- reuse the starter's <svg> for this platform -->
  </a>
  <!-- repeat per platform the user actually has; drop the rest -->
</div>
```

Keep only the icons for platforms the user actually uses (delete the others rather than leaving them pointed at Astro), reuse the starter's existing SVG markup for each platform's icon, and add `rel="me"` for identity verification where the platform supports it (e.g. Mastodon, GitHub). If you restored the icons in the **header**, remember the nav was switched to a grid when the block was removed (see Step 1) — give the restored `.social-links` `justify-self: end` so it sits at the right edge of the nav.

If the user is on a platform the starter has no icon for, **don't fabricate an SVG** — pull it from [Simple Icons](https://simpleicons.org/) ([`simple-icons/simple-icons`](https://github.com/simple-icons/simple-icons)), the canonical, regularly-updated source of brand/social SVG icons (CC0-licensed). Match the starter's existing markup: set the `<svg>` to the same `width`/`height` (`32`) and `viewBox`, keep `aria-hidden="true"`, and use `fill="currentColor"` so the icon inherits the link color. Prefer Simple Icons over the starter's bundled set for any platform it doesn't already cover, and confirm the brand exists there before adding it rather than guessing a path.

## Step 5 — Self-hosted images

The converter downloads remote images into `STATIC_DIR/images` and rewrites references to site-root paths like `/images/<file>` (identical to the Hugo and Eleventy paths). Astro serves everything in the project's **`public/`** directory verbatim at the site root, so an image at `astro-site/public/images/foo.jpg` is served at `/images/foo.jpg`. Set the converter's `STATIC_DIR = "astro-site/public"` and keep `IMAGE_DIR_NAME = "images"`.

This **deliberately bypasses `astro:assets`** (the `<Image />` component and build-time optimization). `astro:assets` requires images to be *imported* as ES modules from `src/`, which is incompatible with the plain site-root image Markdown (`![alt]` pointing at `/images/<file>`) the converter generates. Keeping images in `public/` makes them unoptimized but Just Work with zero per-post wiring — the same trade-off the Eleventy path makes by scoping off image-transform plugins. (If the user later wants optimization, that's a manual, post-migration enhancement, not part of this skill.)

## Step 6 — Video embeds (raw iframe, no shortcode)

Plain Astro Markdown (`.md`) has **no shortcode mechanism** — shortcode-like component syntax requires MDX. So, unlike Hugo (`{{< video >}}`) and Eleventy (`{% video %}`), the converter emits the **rendered responsive `<iframe>` HTML inline** for Astro:

```html
<div class="video-embed"><iframe src="https://..." title="Embedded video" loading="lazy" allow="fullscreen" allowfullscreen></iframe></div>
```

This works because Astro's Markdown renderer **passes raw HTML through** by default (no `unsafe`/`html: true` toggle needed, unlike Hugo's Goldmark). Nothing to configure. Optionally add a little CSS for `.video-embed` to the starter's global stylesheet if you want responsive sizing; it is not required for the embed to work.

## Step 7 — Preserve old Medium URLs (aliases → redirect stubs)

This is the most important step on the Astro path, and the one with no built-in front-matter equivalent. On Hugo, the `aliases:` field automatically generates a `<meta http-equiv="refresh">` stub at each old URL; Eleventy reproduces it with a collection + template. Astro reproduces the **same behavior with a few lines of core Astro** — deliberately **without a community plugin**.

### Why a route instead of the `redirects` config

Astro *does* ship a built-in [`redirects`](https://docs.astro.build/en/guides/routing/#redirects) config option that, in a static build, emits exactly these meta-refresh stubs. This skill does **not** use it, because that option expects a **static map known at config-load time**, whereas each post's old URL lives in its own front matter (`aliases:`). Reading the content collection to build that map would mean parsing front matter inside `astro.config.mjs` (extra dependency, fragile) — so instead this skill emits the stubs from a **catch-all route that reads the collection through Astro's own content API**. This depends only on **core, long-stable Astro APIs** (`getCollection` + `getStaticPaths`), produces plain static HTML stubs that work on any host (S3 + CloudFront, GitHub Pages) with no server config, and keeps the fix — if a future Astro major ever changes these APIs — in one small file the user owns, not in an unmaintained dependency. (`aliases` must be in the schema from Step 4 for the route to read it.)

### 7a — Emit one redirect stub per alias (catch-all route)

Create `astro-site/src/pages/[...alias].astro`. Its `getStaticPaths` flattens every post's `aliases` into one build path each, and the page body is a refresh stub pointing at the post's canonical `/posts/<slug>/` URL:

```astro
---
import { getCollection } from 'astro:content';

export async function getStaticPaths() {
  const posts = await getCollection('blog');
  return posts.flatMap((post) =>
    (post.data.aliases ?? []).map((alias) => ({
      // strip leading/trailing slashes so the rest param matches the path segment
      params: { alias: alias.replace(/^\/+/, '').replace(/\/+$/, '') },
      props: { target: `/posts/${post.id}/` },
    }))
  );
}

const { target } = Astro.props;
---
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="refresh" content={`0; url=${target}`} />
    <link rel="canonical" href={target} />
    <meta name="robots" content="noindex" />
    <title>Redirecting…</title>
  </head>
  <body>
    <p>This page has moved to <a href={target}>{target}</a>.</p>
  </body>
</html>
```

How this maps to Hugo's aliases, stub for stub:

- The converter wrote `aliases: [ /post-title-a1b2c3d4e5f6 ]` into each post (leading slash, no trailing slash — the original Medium path). The route strips the slash to form the `alias` param.
- In a static build Astro builds **only** the paths returned by `getStaticPaths`, so this root catch-all never shadows real pages (`/posts/...`, the home page, the listing) — it materializes *only* the alias paths. With the default `build.format: 'directory'`, each becomes `dist/post-title-a1b2c3d4e5f6/index.html`. That directory-with-`index.html` shape serves the page for both `/post-title-…` and `/post-title-…/`, so it resolves on S3 + CloudFront (with the directory-rewrite function) and on GitHub Pages without extra config.
- The `<meta http-equiv="refresh">` plus `<link rel="canonical">` and `noindex` is byte-for-byte the behavior of a Hugo alias page: instant client-side redirect, canonical pointing at the real post, search engines consolidating on the canonical URL.

If you changed the post URL prefix in Step 4 (e.g. `/archive/`), change the `target` here to match (`/archive/${post.id}/`).

### 7b — Verify

After a build (Step 10), confirm a stub exists and points to the right place, e.g.:

```bash
cat dist/post-title-a1b2c3d4e5f6/index.html   # use a real alias from a converted post
```

It must contain the `meta refresh` to the post's `/posts/<slug>/` URL. Do this for at least one post before considering the path done — a broken alias is the highest-impact failure in the whole migration.

## Step 8 — Confirm the canonical base URL

Make sure `astro.config.mjs`'s `site` is the custom domain (Step 3) and that the post layout emits a `<link rel="canonical">` pointing at the post's own URL (the blog starter's `BlogPost` layout / `<BaseHead>` component already builds canonical and Open Graph URLs from `site` + the current path). A root-domain blog (the normal case here) needs no `base` path configuration — the apex domain is the base.

## Step 9 — `.gitignore`

Ensure the Astro build output and Node modules are ignored (the scaffold's `.gitignore` already lists these; confirm):

```gitignore
dist/
node_modules/
.astro/
```

## Step 10 — Build and test locally

Astro builds with Node, not a separate binary. Run the dev server to spot-check, then produce a one-shot production build (output goes to `dist/`):

```bash
cd astro-site
npm run dev      # local dev server at http://localhost:4321
npm run build    # production build -> dist/
npm run preview  # serve the built dist/ to verify the production output
```

Verify:

- The home page / listing shows the converted posts.
- At least one post renders correctly at its `/posts/<slug>/` URL.
- A redirect alias URL (e.g. `/post-title-a1b2c3d4e5f6`) redirects to the canonical post URL — test the built stub (Step 7b) and, ideally, the live redirect under `npm run preview`.
- Any video embed renders as an iframe, not as literal text.
- Images load from `/images/...` (i.e. they are served from `public/`).
- The build **completes** — an Astro build fails hard on a schema violation, so a green build confirms every post satisfies the relaxed schema.

If Node/Astro is not available in the current environment, document these steps for the user to run themselves, exactly as the Hugo path documents `hugo server`.

## Step 11 — Confirm and update status

Confirm the Astro site structure with the user. Mark the Site Setup phase complete in `migration-status.md` and list all created files. Record the build command (`npm run build`) and output directory (`dist/`) in `migration-status.md` — the hosting and deployment phases read those two values (the "SSG seam") instead of Hugo's `hugo --minify` / `public/`.

## Adapting to a different starter

The steps above assume the official `blog` starter's conventions. The converter's **output is starter-agnostic** — the front matter, raw `<iframe>` embed, and `/images/...` references it produces are correct regardless of starter — but a different starter wires up the schema, routing, and images differently, so the *integration* needs adjusting. If the user picked another starter, re-read its README, `astro.config.mjs`, and `src/content.config.ts` and watch for these differences:

- **A stricter or differently named schema.** This is the most common build-breaker on Astro. Starters routinely require fields Medium exports lack — `description`, an `image`/`cover`/`heroImage`, a `category`, or a `draft` boolean — and the build **fails hard** on any missing required field. Read the schema first and make every field the converter doesn't supply `.optional()` (do not fabricate values), and rename the date field if the starter calls it something other than `pubDate` (e.g. `date`, `publishDate`) — match the converter's `pubDate:` to the schema, or relax the schema to accept it.
- **Paid or non-MIT themes.** Astro's showcase is largely commercial. Confirm the user has a license to the chosen theme and that redistribution of the theme's code in their public repo is permitted before cloning it in.
- **A different content directory or collection name.** The blog starter uses `src/content/blog/` and a collection named `blog`. Others use `src/content/posts/` or `src/data/`, or a different collection name. Point `OUTPUT_DIR` at the actual content directory and use the actual collection name in the Step 7 `getCollection('...')` call.
- **The route lives elsewhere or uses a different param.** Step 4 assumes `src/pages/blog/[...slug].astro` mapping `params: { slug: post.id }`. Other starters use `[...id].astro`, `[slug].astro`, or nest the route under a locale. Read the actual route file to learn the param name and adjust the move/grep accordingly; the goal is unchanged — posts served at `/posts/<slug>/`.
- **`astro:assets` image optimization that collides with `/images/...`.** Some starters funnel every image through `<Image />`/`<Picture />` or a remark plugin that rewrites Markdown `![]()` into imports. That breaks the converter's already-self-hosted `public/images/...` references (and may try to re-fetch the original remote Medium images). Keep body images in `public/` and scope any such transform off the migrated posts.
- **A Node version below the starter's floor, or a wrapped build command.** Step 2 says to use the starter's pinned Node version; verify the installed Node actually satisfies the starter's `package.json` `engines` (Astro won't build on anything below it) and prefer a current even-major LTS. And read the starter's `package.json` `scripts.build`: if it is more than a bare `astro build` (e.g. it runs `astro check` first, or sets env vars), use the starter's own `npm run build` in both local testing (Step 10) and the CI workflow's build step — the deploy references assume `npm run build` → `dist/`.

None of these block a migration — they are one-time integration adjustments, not converter changes.

## Astro ⇄ Hugo quick reference

For cross-checking the paths when wiring later phases:

| Concern | Hugo | Astro (blog starter) |
|---|---|---|
| Project directory | `hugo-site/` | `astro-site/` |
| Config file | `hugo.toml` | `astro.config.mjs` |
| Posts directory | `content/posts/` | `src/content/blog/` |
| Build command | `hugo --minify` | `npm run build` |
| Build output directory | `public/` | `dist/` |
| Static/passthrough root | `static/` → `/` | `public/` → `/` |
| Canonical post URL | `slug:` + `[permalinks]` | filename → entry `id` + route dir (`src/pages/posts/`) |
| Publish-date field | `date:` | `pubDate:` |
| Old-URL preservation | `aliases:` (built in) | `aliases:` schema field + catch-all redirect route (Step 7) |
| Video embed | `{{< video >}}` shortcode | raw `<iframe>` HTML (no shortcodes in `.md`) |
| Raw HTML in Markdown | dropped unless `unsafe = true` | rendered by default |
| Schema strictness | none (extra fields ignored) | Zod schema — missing required field fails the build |
| Build toolchain | Hugo (Extended for SCSS) | Node.js (version per starter `engines`) |
