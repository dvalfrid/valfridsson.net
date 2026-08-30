# valfridsson.net

Hugo site for valfridsson.net, deployed to GitHub Pages via GitHub
Actions. This repo bundles four historically separate sites under one
domain, migrated from an abandoned tool (Sandvox 2.10) plus older
FrontPage-era HTML:

- `/` — Daniel's own contact page
- `/cina/` — art portfolio for painter Cina Jeppsson
- `/ivan/` — family site for Ivan & Elsie Valfridsson
- `/ivan-old/` — superseded prior version of the ivan site (kept for its
  large photo archive, see `ivan-old/album/`)
- `/masten/` — MASTEN Socialt Center Tyresö (NGO/organization site)

The legacy static HTML export (root `index.html`, `cina/`, `ivan/`,
`ivan-old/`, `masten/`, `sandvox_*` theme dirs, `_Resources/`,
`ErrorDoc/`) still lives in the repo during migration as source material
for `scripts/migrate_photos/` — it is not served by Hugo and is removed
once migration is complete and verified.

## Machine setup

- Hugo Extended required (image processing + SCSS-less pipelines use
  extended-only features in some templates). Locally: `hugo version`
  should report `+extended`. CI installs Hugo Extended 0.165.0 via the
  `.deb` release in `.github/workflows/hugo.yml` — keep that version in
  sync with what's installed locally.
- Node.js (for `npx pagefind`, the search-index build step; no other
  JS tooling is used).
- Python 3 + `beautifulsoup4`/`lxml` only if re-running the one-off
  migration scripts in `scripts/migrate_photos/` — not needed for normal
  site work.

## Commands

- `hugo server -D` — local dev server, includes drafts.
- `hugo --minify` — production build into `public/`, excludes drafts.
  This is what CI runs; it's the correctness check for content/template
  changes (no test suite/linter exists).
- `npx --yes pagefind --site public` — build the search index, run after
  `hugo --minify` (matches the CI job order).
- Push to `main` → `.github/workflows/hugo.yml` builds and deploys via
  `actions/deploy-pages`. GitHub Pages source is set to "GitHub Actions"
  in repo settings (not "Deploy from a branch").

## Architecture

- No third-party Hugo theme. `layouts/`, `assets/`, `static/` live at
  repo root.
- **Page bundles** for any content with co-located media (galleries,
  bios with a portrait, painting entries). Templates read images via
  Hugo's native `resources:` frontmatter block (per-image `title`/
  `params.caption`), not by scraping filenames — see any migrated
  gallery's `index.sv.md` for the pattern. Gallery photos reuse the
  legacy pre-generated resolution variant (`_med_hr` etc.) as-is;
  they are **not** run through Hugo's `.Resize`/`.Fill` image
  processing.
- **Bilingual via `multiple_files` i18n**: `index.<lang>.md` /
  `_index.<lang>.md` side by side in the same bundle folder.
  `defaultContentLanguageInSubdir = false`, so Swedish (the only
  language with real content today) is at `/`, and English would be at
  `/en/` if/when it exists. Don't add a visible language switcher until
  real `.en.md` content exists — `i18n/en.toml` is a placeholder mirror
  of `i18n/sv.toml` for template chrome only.
- **`draft: true/false`** in frontmatter is the entire publish
  mechanism. `hugo --minify` (no `-D`) excludes drafts automatically.
- **CSS**: hand-written, no framework/npm build.
  `assets/css/{tokens,main,components}.css` are concatenated, minified,
  and fingerprinted via Hugo Pipes in `layouts/partials/head.html`,
  production-only (`hugo.IsProduction`). Colors/type live as CSS custom
  properties in `tokens.css`.
- **Strict relative linking** for anything a reader clicks
  (`relLangURL`, `.RelPermalink`) — the custom domain `valfridsson.net`
  makes this less load-bearing than on a `github.io` subpath, but it's
  still the convention. Absolute URLs (`.Permalink`/`absURL`) are
  reserved for SEO metadata (canonical, hreflang alternates, sitemap,
  RSS) in `layouts/partials/head.html`.
- **Pagefind search** — `npx --yes pagefind --site public` after the
  Hugo build, wired into CI. Worth keeping given the volume of photos
  and long-form prose (diaries, autobiographies, exhibition histories)
  across all four sites.

## Known migration decisions (don't reintroduce without re-checking)

- cina painting captions (`content/cina/aktuella-tavlor/`,
  `content/cina/tidigare-produktion/`) use a hybrid: the raw legacy
  caption is always kept verbatim in a page-level `caption` front matter
  field (100% fidelity, including the one freeform "Beskrivning av
  tavlan" outlier), and a best-effort regex additionally populates
  `params.motif`/`size`/`owner`/`medium` only when the caption cleanly
  matches `[<medium> -] Motiv: <subject> - Storlek: <dims> cm[ - Ägare:
  <owner>]` in full — never force-fit. `layouts/_default/painting.html`
  (selected via `layout: painting`) prefers the structured params when
  present, falling back to rendering the raw `caption` as prose
  otherwise. Paintings whose caption doesn't parse into a clean motif
  fall back to a generic `Målning N` title/slug rather than a
  mis-extracted one.
- `ivan-old/dagbok.html`/`.htm` was a confirmed duplicate of
  `content/ivan/susanne-hilliges-valfridsson/index.sv.md` — not
  migrated as content. That page carries `aliases:` for both old URLs
  so they redirect instead of 404ing.
- Sandvox "PhotoGridIndex" one-photo-per-page galleries (`ivan/bilder/2015/**`,
  `ivan/till-marita/**` in the legacy tree) were collapsed into one
  gallery page per month/date rather than ported as one page per photo.
- Susanne's diary (`content/ivan/susanne-hilliges-valfridsson/`) is
  intentionally **one continuous page**, not split into dated entries —
  it's a personal narrative (illness through Ivan's epilogue and funeral
  program), not a changelog. Don't restructure it to match the
  `revideringslista`/dated-gallery pattern used elsewhere.
- `ivan-old/ovriga-bilder/` is a deliberate undated, caption-less
  gallery of photos with no source caption/date — expected to index
  thin in Pagefind, that's fine.
- `ivan-old/temp/` (a guestbook spreadsheet) and Sandvox/FrontPage system
  files (theme CSS dirs, `_Resources` JS libs, `ErrorDoc/` beyond 404,
  `sitemap.xml.gz`, `index.xml`) were dropped entirely, not migrated.
