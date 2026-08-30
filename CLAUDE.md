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
`ErrorDoc/`) and the one-off migration scripts that converted it into
this Hugo content (`scripts/migrate_photos/`) have both been removed
from the working tree now that migration is complete and the Hugo site
is live — both are still recoverable from git history if a piece of
content ever needs re-deriving from the original source.

## Machine setup

- Hugo Extended required (image processing + SCSS-less pipelines use
  extended-only features in some templates). Locally: `hugo version`
  should report `+extended`. CI installs Hugo Extended 0.165.0 via the
  `.deb` release in `.github/workflows/hugo.yml` — keep that version in
  sync with what's installed locally.
- Node.js (for `npx pagefind`, the search-index build step; no other
  JS tooling is used).

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
  processing when shown at full display size on their own gallery/
  painting page. The one exception: `layouts/partials/preview-images.html`
  (a recursive partial — walks into child pages when a listing entry has
  no images of its own, e.g. a year folder whose actual photos live in
  its dated sub-galleries) collects up to 3 sample images per entry on
  `.page-list` renders (`layouts/_default/list.html`), and those *are*
  run through `.Fill "160x160 Center q70"` — embedding full-size
  originals as list-preview thumbnails would make large listings (e.g.
  `ivan-old/album/`, 442 entries) untenably heavy (~93MB vs ~5MB).
  Confirmed at ~1700 processed images site-wide this adds roughly 10-15s
  to a clean `hugo --minify` (no persistent build cache in CI, so this
  cost repeats every deploy).
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
- **Opt-in floated image**: for a portrait/decorative image with body
  text flowing around it (rather than sitting alone on its own line),
  use Hugo's built-in `figure` shortcode with `class="float-left"` or
  `class="float-right"` — e.g.
  `{{</* figure src="portrait.jpeg" alt="..." class="float-left" */>}}`
  — see `content/ivan/susanne-hilliges-valfridsson/_index.sv.md` for a
  real example. `main h2`/`h3`/`h4` clear the float automatically so a
  new section always starts at full width. Plain `![]()` markdown
  images remain the default (no float) everywhere else.
- **Strict relative linking** for anything a reader clicks
  (`relLangURL`, `.RelPermalink`) — the custom domain `valfridsson.net`
  makes this less load-bearing than on a `github.io` subpath, but it's
  still the convention. Absolute URLs (`.Permalink`/`absURL`) are
  reserved for SEO metadata (canonical, hreflang alternates, sitemap,
  RSS) in `layouts/partials/head.html`.
- **Pagefind search** — `npx --yes pagefind --site public` after the
  Hugo build, wired into CI. Worth keeping given the volume of photos
  and long-form prose (diaries, autobiographies, exhibition histories)
  across all four sites. A visible search box (Pagefind's Default UI,
  `pagefind-ui.js`/`.css`, referenced as plain static paths under
  `/pagefind/` in `layouts/partials/head.html`) sits in the header on
  every page (`#search` in `layouts/_default/baseof.html`, initialized
  via `new PagefindUI(...)`) — Pagefind confirms the Default UI
  "is supported and will continue to work" even though their docs now
  point new integrations at a newer Component UI instead; no reason to
  take on that extra complexity here. **Caveat**: `hugo server -D`
  does *not* run the Pagefind indexing step, so the search box 404s on
  its JS/CSS during normal local dev — to test it locally, run
  `hugo --minify && npx --yes pagefind --site public` and serve
  `public/` with a static file server instead.

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
- **ivan-old (Phase 5) full run**, completing the partial run described
  above. `parse_frontpage_grid.py --all` now processes `foto01.htm`
  through `foto72.htm` plus `foto37b.htm`/`foto56b.htm` (74 pages total),
  `bilder/Haraldsfoto.htm`, `Shalom/bild0610.htm`, and builds the
  `ovriga-bilder` orphan gallery, in one run. Result: 442 album topic
  bundles (3188 images), the existing 80-image `bilder/` gallery, a
  15-image/5-mp3-attachment `shalom/` gallery, and a 119-image
  `ovriga-bilder/` gallery — `content/ivan-old/` totals ~418MB (legacy
  source `ivan-old/` was 477MB; the difference is dropped system files,
  furniture GIFs, unreferenced top-level PDFs, and the excluded `.avi`
  clips, see below).
  - **Reversed early-page layout, solved at row level, not page level.**
    The originally-suspected "foto01–foto09 use a different whole-page
    shape" framing turned out to be wrong once all 74 pages were
    actually inspected: the caption-td-then-image-td shape is used
    *wholesale* on foto01.htm–foto09.htm and foto13.htm, but several
    later, otherwise-mainstream pages (foto10.htm, foto12.htm, foto35.htm,
    foto52.htm, foto56.htm) mix *individual* reversed-shape rows in among
    ordinary same-cell img+caption rows — foto12.htm in particular is
    genuinely ~56% reversed-shape rows. A whole-page shape dispatch can't
    handle that; `parse_foto_page()` was rewritten to walk `<tr>`→`<td>`
    (not a flat `table.find_all("td")`) and pair an image-less `<td>`
    with whichever image-bearing `<td>` comes *next in the same row*
    (`row_pending_caption`/`extract_caption_plain` in
    `parse_frontpage_grid.py`), falling back to topic-intro prose only if
    no image follows in that row. `_is_intro_not_caption()` excludes the
    genuine exceptions from this pairing — an embedded `<object>`/`<embed>`
    video (foto52.htm's YouTube embed), a nested `<table>` (foto56.htm's
    "tack" message), or large `<font size>` styling (foto56.htm's
    70th-birthday announcement) — since those are topic-intro/heading
    prose, not a caption-in-waiting; a lone `<td>` spanning the whole row
    (`colspan="2"`/`width="100%"`, e.g. foto65.htm's
    `<b>Släktbilden</b>` section-label row) is also unconditionally intro,
    since there's no "next `<td>` in this row" it could possibly pair
    with. Text length is *not* a usable signal here: foto07.htm/
    foto08.htm/foto09.htm are Susanne's funeral-memorial pages, where
    each photo's *real, legitimate* caption is a 250–450 character
    tribute quote from a named mourner.
  - **Fixed two real bugs surfaced by this row-level rework**, both of
    which also affected already-committed partial-run output (re-running
    the full page list regenerated and corrected them in place, verified
    byte-identical to the previously-approved content everywhere else):
    1. A caption-only `<td>` whose text visually belongs to a topic
       marked by an `<a name="N">` anchor that sits in a *later* `<td>`
       of the *same row* (not its own `<td>`) was previously attached to
       whatever topic was still open before that row started — one topic
       too early. Example: foto56.htm's "Söndagen den 22 februari fyllde
       Ivan 70 år…" intro paragraph shares a row with anchor `#5`, but
       the anchor tag itself sits in the row's *second* `<td>` (next to
       the photo), not the first (intro) `<td>`. Fixed by deferring an
       intro `<td>`'s commit to `topic["intro"]` until the whole row
       (including any anchor in a later cell) has been scanned, then
       committing with the row's *final* `current_key`
       (`row_deferred_intro` in `parse_foto_page()`) — rather than a
       whole-row anchor pre-scan, which was tried first and rejected: it
       broke rows where *each* `<td>` has its own independent
       anchor+image pair (foto68.htm's flower photos, `#1`/`#2` etc. one
       per cell in the same row).
    2. `topic_slug()`'s collision counter was keyed on the *pre-suffix*
       base string, so a topic whose auto-appended `-2`/`-3` disambiguator
       could still collide with a *different* topic's own, unsuffixed,
       naturally-identical slug without being detected — e.g. foto37.htm
       has its own topic literally titled "TYFRI MC 2" (slug
       `tyfri-mc-2`), and separately foto41.htm has a second `TYFRI MC`
       topic on the same page as its own "TYFRI MC 2" topic; the second
       `TYFRI MC` collided with foto38.htm's earlier one and produced
       `tyfri-mc-2` as its *output*, silently overwriting foto37.htm's
       real "TYFRI MC 2" bundle (title + `resources:` clobbered, its
       original images left as orphaned files no longer listed in that
       bundle's front matter). Fixed by tracking every *final* returned
       slug in a flat `set[str]` instead of a `{base: count}` dict, so
       collisions are always detected regardless of which topic's
       suffix-generation produced the clash.
  - **`parse_filename_date()` (`common.py`) gained a `1900 <= year` sanity
    check.** Some of ivan-old's older filenames use a *2-digit*-year
    `YYMMDDNN` convention (e.g. `05071005.jpg` for 2005-07-10) that the
    existing 4-digit-prefix regex still matched, misreading the first
    four digits as year 0507 and emitting a nonsense `date: 0508-02-01`
    front matter value (44 topics were affected before the fix). Nothing
    on this site predates 1900, so the guard can't reject any genuine
    date; ivan/masten/cina's own filenames are unaffected (their `_Media`
    libraries use real 4-digit years throughout).
  - **`parse_album()` gained a second-priority page-title source.**
    Every `foto01.htm`–`foto13.htm`-ish single-story early page's
    descriptive text in `album.htm` sits as plain sibling `<td>` text
    (`<td><a href="foto01.htm"><img src="framat.gif"></a></td><td>Vår
    dotter Åsa med familj strax före resan till Kalifornien - mars
    1999.</td>`), never wrapped in an `<a>` — the only `<a href>` in that
    row wraps just the "next page" arrow icon (empty link text, already
    skipped). Previously these pages fell back to their own `<title>`
    tag, which is sometimes a real title (foto10.htm: "Sommaren 2000 -
    några bilder") but sometimes a generic placeholder (foto01.htm:
    "Ivans foto01"). `parse_album()` now also scans for this
    icon-only-cell-plus-sibling-text row shape and fills `page_title_map`
    from it (`setdefault`, so it never overrides a real `album.htm`
    anchor-derived title). One side effect: foto10.htm's fallback title
    changed from the `<title>`-tag-derived "Sommaren 2000 - några bilder"
    to the `album.htm`-row-derived "Några foton från sommaren 2000" (a
    different slug) — the stale `content/ivan-old/album/2000-sommaren-2000-nagra-bilder/`
    directory from the earlier partial-run commit was deleted in favor of
    the new `2000-nagra-foton-fran-sommaren-2000/` (identical 39 photos,
    just the more authoritative album.htm-curated title).
  - **`foto57x.htm` deliberately excluded from the 75-file set found on
    disk** (72 numbered pages + `foto37b.htm`/`foto56b.htm`/`foto57x.htm`
    = 75; only 74 processed). Diffed byte-for-byte against `foto57.htm`:
    same title, same 40 photos, same captions — only the family-photo
    `<map>` `<area>` coordinates/labels and a footer nav link still
    pointing at the pre-move `crossnet.se` domain differ, confirming it's
    a stale prior FrontPage revision of foto57.htm itself, not a
    distinct topic. Not referenced anywhere in `album.htm` either.
    `foto37b.htm`/`foto56b.htm`, by contrast, are genuine continuation
    pages: distinct, non-overlapping photo sets (1 filename overlap out
    of 157+58 and 83+112 respectively — a shared furniture icon) with
    their own real `album.htm`-mapped topics, processed normally.
  - **`Shalom/bild0610.htm`** (15 dated photos from a 2006 Shalom
    board/work meeting in Källered) uses yet another shape — one `<p>` of
    `<a href="X.jpg">X.jpg</a>: caption<br>` lines, all in a single
    paragraph (unlike `bilder/Haraldsfoto.htm`'s one-`<p>`-per-link
    shape) — handled by a small dedicated `process_shalom_gallery()`
    rather than shoehorned into `parse_foto_page()`. Real per-photo
    captions exist (names/event labels: "Jonas", "Stefan", "Gruppfoto:
    …", "Styrelsemöte"), so this is a genuine dated gallery, not an
    undated one. The folder's 5 `jesajadel1.mp3`–`jesajadel5.mp3`
    recordings (Isaiah Bible-study/sermon audio; the plan's own
    description guessed 4, disk has 5) aren't linked from `bild0610.htm`
    or anywhere else in `ivan-old/` (checked via grep across the whole
    tree) — genuinely orphaned audio, kept as downloadable attachments on
    the `shalom/` page (same judgment call as foto57.htm's
    `MOR0104a.pdf`/`Odesbacka.pdf`/`Mor.mp3` case) rather than dropped,
    since there's no better home for them and they're small.
  - **`ivan-old/video/` (six `.avi` clips, ~51MB) dropped, not migrated.**
    Checked via grep across every `.htm` page in `ivan-old/` (including
    `album.htm`) for all six filenames — zero references anywhere, not
    even a dead link. Old, low-resolution `.avi` clips this old are also
    unlikely to play in a modern browser without transcoding. Given
    they're both orphaned *and* of doubtful standalone playback value,
    the call here was to drop them rather than carry over 51MB of
    probably-unplayable video — different from the `Shalom` mp3s (small,
    definitely still playable, kept) and the `ovriga-bilder` photos
    (large in aggregate but each one is still a normal, viewable JPEG).
  - **`ovriga-bilder/` orphan-gallery scope is deliberately narrow: only
    top-level `.jpg` files.** ivan-old's top-level directory also has 20
    `.gif` files, but inspection showed these split cleanly into two
    unrelated categories — genuine early-page content photos already
    consumed by `foto01.htm`/`foto08.htm` (`henric01-03.gif`,
    `bengt01-03.gif`) and pure page furniture/decoration (advent-calendar
    icons `1adv_x.gif` etc., `framat.gif`/`pil_v.gif`/`pil_h.gif` nav
    arrows) that was never real photo content in the first place — so
    `.gif` was excluded from the orphan-diff entirely rather than risk
    surfacing decorative icons as if they were "missing photos." The
    top-level `iva9822b.pdf`/`iva9914.pdf`/`iva0029.pdf`/…/`iva1512.pdf`
    Christmas-letter PDFs (pre-2015 continuation of the ones already
    migrated to `content/ivan/ivan-valfridsson/`) are **also** left
    unmigrated here, on purpose: wiring them up means editing
    `content/ivan/ivan-valfridsson/index.sv.md`'s Christmas-letter list
    (currently pointing at these exact paths, expected-404 per that
    page's own migration note) — out of scope for this ivan-old-only
    pass, which was explicitly scoped to not touch already-migrated
    `ivan`/`masten`/`cina` Hugo content. Those links remain 404 until a
    future pass touches that file specifically.
  - `content/ivan-old/album/_index.sv.md` and `content/ivan-old/_index.sv.md`
    updated: the "this is a partial subset" disclaimer removed, and nav
    links to the new `shalom/` and `ovriga-bilder/` galleries added.
