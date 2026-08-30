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
  `content/ivan/susanne-hilliges-valfridsson/dagbok/index.sv.md` — not
  migrated as content. That page should carry `aliases:` for both old
  URLs so they redirect instead of 404ing (path corrected from the
  originally-planned `.../susanne-hilliges-valfridsson/index.sv.md` — see
  the branch/leaf bundle split noted further below; the diary itself is
  unaffected, still one unsplit page, just one path segment deeper).
- Sandvox "PhotoGridIndex" one-photo-per-page galleries (`ivan/bilder/2015/**`,
  `ivan/till-marita/**` in the legacy tree) were collapsed into one
  gallery page per month/date rather than ported as one page per photo.
- Susanne's diary (`content/ivan/susanne-hilliges-valfridsson/dagbok/`) is
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
- `ivan/untitled.html` (top-level) is a stale, truncated duplicate of
  `ivan/bilder/untitled.html` — the latter is the real, linked-from-nav
  "2015" flat-year page (same repeating-image-and-caption shape as
  `bilder/2016.html`-`2020.html`) and is processed accordingly by
  `scripts/migrate_photos/parse_sandvox_flatyear.py`; the top-level
  duplicate is dropped, unreferenced from any real nav. It turned out to
  be a *different* photo set from the separate `ivan/bilder/2015/`
  PhotoGridIndex folder (camera-native filenames, no captions) rather
  than the same one twice, so both now live side by side under
  `content/ivan/bilder/2015/` — dated entries from the flat page, plus
  `januari/`/`februari/` month galleries from the PhotoGridIndex folder.
- `ivan/micke.html` (top-level, 5 photos) is a redundant subset of
  `ivan/bilder/micke.html` (75 photos, the complete album) — only the
  latter is migrated, to `content/ivan/bilder/micke/`, as one undated
  gallery bundle (captions dropped: every one was just the image's own
  filename echoed back, not a real caption).
- `ivan/20200725-ah-3045.html`, an orphaned page with no inbound links
  and a broken embedded video (no ImageElement), had its one salvageable
  still image (the video's poster-frame JPEG) folded into the
  `content/ivan/bilder/2020/2020-07-25/` gallery bundle — same real date
  already produced from `bilder/2020.html` — rather than given its own
  near-empty gallery.
- `ivan/iva1712pdf.html` wraps a PNG, not a real PDF (no `iva1712.pdf`
  exists in the source). The Christmas-letter list on
  `content/ivan/ivan-valfridsson/index.sv.md` links 2017 to an in-page
  `#julbrev-2017` anchor (heading + inline image) instead of a
  fabricated `.pdf` link — a sibling `julbrev-2017/` page bundle was
  tried first but doesn't work in Hugo: `ivan-valfridsson` is a *leaf*
  bundle (`index.sv.md`), and leaf bundles cannot contain nested content
  pages, only page resources (a subdirectory with its own `index.sv.md`
  inside one is silently dropped from the build, not an error).
- `ivan/susanne-hilliges-valfridsso/index.html` is a real autobiography
  for Susanne (portrait + prose), not just a landing page. Since the
  diary (`content/ivan/susanne-hilliges-valfridsson/`) needed to keep
  its established path per the decision above,
  `content/ivan/susanne-hilliges-valfridsson/` was made a *branch*
  bundle (`_index.sv.md`, the bio) with the diary moved one level down
  to its child leaf bundle `content/ivan/susanne-hilliges-valfridsson/dagbok/`
  — mirroring the legacy site's own nav structure exactly, where "DAGBOK
  - Susanne" was already a submenu entry under "Susanne
  Hilliges-Valfridsson". The diary itself is still fully unsplit, per
  the decision above — only its URL gained one path segment.
- `ivan/till-marita/`'s 71 photo pages (filenames `YYYYMMDD-NNNN.html`)
  all resolve to the same date, 2018-08-15 — grouping is computed from
  each filename rather than hardcoded, but happens to produce exactly
  one `content/ivan/till-marita/2018-08-15/` gallery bundle.
- Every `content/ivan/bilder/<year>/` and `content/ivan/till-marita/`
  needs its own hand-authored `_index.sv.md` for Hugo to render a
  section list page there — unlike some other frameworks, this
  particular Hugo build does not auto-generate a browsable `index.html`
  for a content directory that has child pages but no `_index.md` of its
  own (confirmed by the pre-existing `content/masten/second-hand/{fotografier,resultat}/_index.sv.md`
  files following the same pattern already).
- `ivan-old/` (Phase 5) is being migrated as a deliberate **partial run
  first**: `scripts/migrate_photos/parse_frontpage_grid.py` is the real,
  general-purpose parser (not a throwaway), but it has so far only been
  *run* against 6 of the 72 `foto*.htm` pages (`--pages foto10.htm
  foto50.htm foto57.htm foto61.htm foto65.htm foto72.htm`, its default)
  plus the small, self-contained `bilder/Haraldsfoto.htm` genealogy
  gallery — picked to exercise multi-topic grouping (foto72, 22 topics),
  a page where album.htm skips some of the page's own anchor numbers
  (foto61: anchors 5/6/8 present in the HTML but unmapped in album.htm,
  folded forward into whichever topic is currently open rather than
  starting bogus sub-sections), a single-topic page (foto65), two
  whole-page/no-topic pages of different messiness (foto50 has no
  internal anchors at all; foto57 has internal anchors 1-19 but
  album.htm maps none of them to a title), and the PDF/mp3 inline
  attachment case (foto57's `MOR0104a.pdf`, `Odesbacka.pdf`, `Mor.mp3`).
  **Not yet migrated in this pass:** the other 66 `foto*.htm` pages,
  `ovriga-bilder/` (the ~300MB orphaned/caption-less photo set),
  `Shalom/`, and `temp/` — a follow-up task re-runs the same script with
  the full `--pages foto01.htm..foto72.htm` list once this partial run's
  build size/time is verified. `ivan-old/index.html` (an older, shorter
  FrontPage duplicate of `ivan/index.html`) was not ported; `dagbok.html`/
  `.htm` (confirmed duplicate of the diary) got the alias redirect
  described above, already implemented on
  `content/ivan/susanne-hilliges-valfridsson/dagbok/index.sv.md`.
- ivan-old's photos live flat at the top level of `ivan-old/` with no
  pre-generated resolution variants (unlike `_Media/`-based masten/cina/
  ivan), so `parse_frontpage_grid.py` resolves images by plain
  case-insensitive exact filename match (`resolve_exact`/
  `build_media_index`), not `common.find_media`'s variant-priority
  matching.
- Every `foto*.htm` page ends in an identical boilerplate footer cell
  ("Foto: <credit>", a `mailto:` link, "Föregående sida!"/"Hemsidan!" nav
  links built from the reused `pil_v.gif` down-arrow icon, a copyright
  notice) that looks structurally identical to a real multi-image content
  cell and must be filtered out (`_is_footer_td`/`_FURNITURE_IMAGES` in
  `parse_frontpage_grid.py`) — otherwise the two `pil_v.gif` icons get
  misread as two bogus "photos" whose "captions" are the nav-link text
  and the copyright notice.
- `resources:` front matter's `params.caption` is rendered by
  `layouts/_default/gallery.html` as a raw string (`{{ . }}`), **not**
  piped through `markdownify` — a pre-existing constraint of the shared
  gallery template (also affects some already-migrated `ivan/bilder/`
  captions that embed literal, unrendered `**bold**` markers, e.g.
  `content/ivan/bilder/2017/2017-06-21/index.sv.md`; left as-is, out of
  scope for this pass since that content is already committed and the
  template is shared across every site). `parse_frontpage_grid.py`
  works around this for its *own* output rather than repeating the bug:
  `node_to_md(..., plain=True)` strips markdown emphasis/link syntax from
  caption text (keeping only the inner text), while a real PDF/mp3 link
  found inside a caption is recorded and re-emitted as an actual markdown
  link in the topic's *body* prose instead (a `**Bilagor:** [...]`
  line), which *is* rendered through `.Content` normally.
- A handful of the earliest `foto*.htm` pages (circa foto01-foto09,
  1999-2000) use a different, reversed two-column layout — caption+date
  text in one `<td>`, the bare `<img>` with no caption at all in the next
  `<td>` — instead of the mainstream same-cell img-then-caption shape
  every later page uses. `parse_frontpage_grid.py` does not (yet) handle
  this reversed shape; none of those pages are in the default `--pages`
  sample, and the follow-up full-migration task will need a small
  extension (or a hand-migrated exception) for them.
