# migrate_photos

One-off scripts used to migrate the legacy Sandvox/FrontPage photo
galleries into Hugo page bundles under `content/`. **Not** part of the
`hugo --minify` build — nothing here runs in CI. Kept in the repo as
a record of how the generated content was produced, and so they can be
re-run if a generated bundle needs regenerating (they're idempotent).

## Requirements

Python 3 + `beautifulsoup4`:

```
python -m pip install beautifulsoup4
```

## Layout

- `common.py` — shared helpers: `slugify`, Swedish timestamp parsing
  (`parse_sv_timestamp` for masten's 3-letter-month `<div
  class="timestamp">` style, `parse_sv_caption_date` for ivan's
  hand-typed full-month-name and D/M -YY caption styles,
  `parse_filename_date` for `YYYYMMDD`/`YYYY-MM-DD`-prefixed legacy
  filenames), legacy image-variant selection (`find_media`, preferring
  `_med_hr` > unsuffixed > `_360` > `_med` > any other match for that
  photo's stem), `extract_img_src` (prefers the JS hi-res-swap
  `data-img-src-hr` attribute over `data-img-src`/`src`), and the
  page-bundle writer (`write_bundle`) that emits `index.sv.md` with a
  Hugo `resources:` front matter block plus copies the chosen image
  file(s) into the bundle directory.
- `parse_sandvox_grid.py` — parses ivan's bare Sandvox "PhotoGridIndex"
  one-page-per-photo galleries: `ivan/bilder/2015/{januari,februari}/*.html`
  (one gallery bundle per month, no captions -- these never had any) and
  `ivan/till-marita/*.html` (one gallery bundle per date, parsed from
  each page's `YYYYMMDD-NNNN` filename; all 71 happen to land on one
  date, 2018-08-15, but the grouping is computed, not hardcoded). Also
  exposes `get_orphan_thumbnail()`, used by `parse_sandvox_flatyear.py`
  to fold in the one salvageable image from the orphaned
  `ivan/20200725-ah-3045.html` page (see "Known exclusions (ivan)"
  below). Run with `--dry-run` to preview.
- `parse_sandvox_flatyear.py` — parses ivan's flat "one page per year"
  photo-diary pages (`ivan/bilder/untitled.html` for 2015,
  `ivan/bilder/2016.html`-`2020.html`), walking the DOM structurally
  (an ImageElement, or hi-res-swap span, followed by its caption `<p>`;
  divider-only paragraphs of `*`/`-`/`<`/`>` are discarded) and grouping
  the results by the real calendar date embedded in each caption (with
  filename-embedded-date and last-known-date fallbacks) into one gallery
  bundle per date under `content/ivan/bilder/<year>/<date>/`. A handful
  of standalone "intro" paragraphs that aren't a direct caption (e.g.
  "Förberedelse för fiberinstallation på Danhäll...", "Under dessa
  coronatider...") are prepended to the very next photo's caption rather
  than dropped. Also parses `ivan/bilder/micke.html` (`process_micke`)
  into one undated gallery bundle at `content/ivan/bilder/micke/`,
  captions dropped since they're just the image filename echoed back.
  Run with `--dry-run` to preview.
- `parse_masten_gallery.py` — parses `masten/second-hand/fotografier/*.html`
  (real `<div class="timestamp in">` per entry -> `date` front matter,
  folder name) and `masten/second-hand/resultat/*.html` (no date, just a
  short title -> slugified folder name). Run with `--dry-run` to preview
  without writing anything.
- `parse_frontpage_grid.py` — parses ivan-old's older FrontPage-era
  `<table>`-grid HTML (a completely different DOM shape from the Sandvox
  RichTextElement pages the other parsers handle). `parse_album()` reads
  `album.htm`'s anchor-linked topic list into a `{foto-filename: {anchor:
  topic title}}` map; `parse_foto_page()` walks a given `fotoNN.htm`'s
  `<tr>`→`<td>` rows in document order (not a flat `table.find_all("td")`
  — needed so a caption-only `<td>` can be paired with the image-bearing
  `<td>` that follows it in the *same row*, see the reversed-layout note
  below), using the album.htm-mapped `<a name="N">` anchors found in the
  page as topic-section boundaries (an in-page anchor *not* in
  album.htm's map is a non-boundary, folded into whichever topic is
  currently open — see the foto61.htm example in CLAUDE.md's decisions
  log). A page with zero album.htm-mapped anchors is one single topic
  covering the whole page. One gallery bundle per resulting topic is
  written flat under `content/ivan-old/album/<slug>/` (year-prefixed
  where derivable, globally unique via a `set[str]` of every final slug
  already returned this run — not a `{base: count}` dict, which missed a
  real second-order collision, see CLAUDE.md). A caption that embeds a
  local `.pdf`/`.mp3` link (e.g. foto57.htm's `MOR0104a.pdf`,
  `Odesbacka.pdf`, `Mor.mp3`) gets that file copied into the topic's
  bundle and a real markdown link added to the topic's body prose instead
  of the caption (`resources:` captions aren't markdownified — see
  CLAUDE.md). A run of the earliest pages (foto01.htm-foto09.htm,
  foto13.htm) plus scattered individual rows on some later,
  otherwise-mainstream pages use a *reversed* two-column row shape —
  caption in one `<td>`, the bare `<img>` in the next — handled at row
  level, not as a whole-page shape switch (see CLAUDE.md for why a
  page-level dispatch doesn't work here). `process_bilder_gallery()`
  separately parses `bilder/Haraldsfoto.htm` (a flat
  `<p><a href="X.jpg">X.jpg</a></p>` link list, not `<img>` tags -- the
  Lindberg family genealogy photos) into one undated gallery at
  `content/ivan-old/bilder/`, and `process_shalom_gallery()` parses
  `Shalom/bild0610.htm` (one `<p>` of `<a href="X.jpg">X.jpg</a>:
  caption<br>` lines) into one dated gallery at `content/ivan-old/shalom/`
  with its folder's orphaned `jesajadel*.mp3` recordings attached as
  downloadable resources. `build_ovriga_bilder()` diffs every top-level
  `.jpg` filename against everything `process_foto_pages()` actually
  consumed and writes whatever's left as one big undated, caption-less
  gallery at `content/ivan-old/ovriga-bilder/`. Takes `--pages foto10.htm
  foto50.htm ...` to select a specific set of `foto*.htm` files (default:
  a small representative sample, see `DEFAULT_PAGES`), or `--all` for the
  full run (`ALL_PAGES` — all of foto01.htm-foto72.htm plus
  foto37b.htm/foto56b.htm, **not** foto57x.htm, see "Known
  exclusions/decisions (ivan-old)" below — plus bilder/, Shalom/ and
  ovriga-bilder). Run with `--dry-run` to preview.
- `parse_cina_captions.py` — parses `cina/aktuella-tavlor.html` and
  `cina/tidigare-produktion.html` (one painting page bundle per
  image+caption pair, `layout: painting`) and `cina/fotoalbum/*.html`
  (13 flat pages + the 2 already-nested `8-utstallning-i-tyreso/`,
  `9-utstallning-i-tyreso/` albums; one gallery bundle per page,
  `layout: gallery`). Painting captions get a best-effort regex pass
  extracting `params.motif`/`size`/`owner`/`medium` when they cleanly
  match `[<medium> -] Motiv: <subject> - Storlek: <dims> cm[ - Ägare:
  <owner>]`; the raw caption is always kept verbatim in the page-level
  `caption` front matter field regardless (the caption-hybrid decision —
  never force-fit, never lose data). Run with `--dry-run` to preview.

## Running

From the repo root:

```
python scripts/migrate_photos/parse_masten_gallery.py --dry-run
python scripts/migrate_photos/parse_masten_gallery.py

python scripts/migrate_photos/parse_cina_captions.py --dry-run
python scripts/migrate_photos/parse_cina_captions.py

python scripts/migrate_photos/parse_sandvox_grid.py --dry-run
python scripts/migrate_photos/parse_sandvox_grid.py

python scripts/migrate_photos/parse_sandvox_flatyear.py --dry-run
python scripts/migrate_photos/parse_sandvox_flatyear.py

python scripts/migrate_photos/parse_frontpage_grid.py --dry-run
python scripts/migrate_photos/parse_frontpage_grid.py
# process a specific set of foto*.htm pages instead of the default sample:
python scripts/migrate_photos/parse_frontpage_grid.py --pages foto01.htm foto02.htm ... foto72.htm
# full run: all of ALL_PAGES, plus bilder/, Shalom/ and the ovriga-bilder orphan gallery:
python scripts/migrate_photos/parse_frontpage_grid.py --all
```

`parse_sandvox_flatyear.py` imports `get_orphan_thumbnail` from
`parse_sandvox_grid.py`, but each script is otherwise independently
runnable/re-runnable; order between the two doesn't matter for anything
except that one warm re-run of `parse_sandvox_flatyear.py` after
`parse_sandvox_grid.py`'s bundles already exist will still correctly
re-fold the orphan thumbnail into `bilder/2020/2020-07-25/` (both
scripts only read from the legacy `ivan/` source tree, never from each
other's `content/` output).

Output goes to `content/masten/second-hand/fotografier/<date>/` and
`content/masten/second-hand/resultat/<slug>/`,
`content/cina/aktuella-tavlor/<motif-slug-or-malning-N>/`,
`content/cina/tidigare-produktion/<motif-slug-or-malning-N>/`,
`content/cina/fotoalbum/<album-slug>/`,
`content/ivan/bilder/2015/{januari,februari}/`,
`content/ivan/bilder/<year>/<date>/` (2015-2020),
`content/ivan/bilder/micke/` and `content/ivan/till-marita/<date>/`
respectively.

The bio pages (`ivan-valfridsson`, `elsie-valfridsson`,
`susanne-hilliges-valfridsson`), the `ivan` home landing page, and the
Susanne diary bundle (`susanne-hilliges-valfridsson/dagbok/`) are
hand-authored directly in `content/`, not script-generated — they're
long-form prose, not repeating gallery shapes, and the diary in
particular needed careful line-by-line fidelity rather than a generic
parser.

## Known exclusions (masten)

- `second-hand/fotografier/bilder-fran-middag.html` is skipped: it's an
  orphaned leftover revision (not linked from `fotografier/index.html`'s
  nav list) with the same empty body as `2015-06-03-bilder-fran.html`,
  just a stale timestamp — a duplicate, not distinct content.
- `masten/_Media/konsert150606w1_*.png`, `konsert150606w940x300_med_hr.jpeg`,
  `logo_secondhand_orgs_med_hr.jpeg` and `20121207-02_med_hr.jpeg` are not
  referenced by any `masten/**/*.html` page (checked via grep across the
  whole `masten/` tree) — orphaned media library uploads that were never
  placed on a page. Not migrated.
- Two fotografier entries with substantial embedded prose+photos
  (`2012-12-07---second-hand.html`, the Second Hand julbord 2012 writeup,
  and `2013-01-05-ett-stort-tacksa.html`, the Ingvar Hellberg diploma
  story) were regenerated by this script like any other entry, then
  hand-finished afterwards for better prose flow — the script's
  image/caption extraction handles them adequately but not as cleanly as
  a human edit for genuinely long-form articles.

## Known exclusions/decisions (ivan)

- `ivan/untitled.html` (top-level) is a stale, truncated duplicate of
  `ivan/bilder/untitled.html` (both titled "2015", not byte-identical):
  the top-level one only has entries from 13/11 back to 1/1, missing
  everything from 23/12 down to 23/11, and is never linked from any
  page's nav (every page links `bilder/untitled.html` instead, confirmed
  via grep). Dropped entirely, not migrated, no alias. `bilder/untitled.html`
  is treated as the canonical, complete 2015 flat-year page and processed
  by `parse_sandvox_flatyear.py` exactly like `bilder/2016.html`-`2020.html`,
  alongside (not instead of) the separate `bilder/2015/{januari,februari}/`
  PhotoGridIndex folder handled by `parse_sandvox_grid.py` — the two
  turned out to be two distinct, non-overlapping photo sets for the same
  year (camera-native filenames vs. date-encoded filenames), so both are
  kept as sibling entries under `content/ivan/bilder/2015/`.
- `ivan/micke.html` (top-level, 5 photos, all circa 1970) vs.
  `ivan/bilder/micke.html` (75 photos spanning 1970-2019): the top-level
  one's 5 photos are exactly the oldest tail of the bilder/ version's
  full chronological list. Neither is linked from any page's nav
  (checked via grep), so both are effectively orphaned from in-site
  navigation — but `bilder/micke.html` is clearly the complete, canonical
  album and is migrated to `content/ivan/bilder/micke/`; the top-level
  stub is dropped as a redundant subset.
- `ivan/20200725-ah-3045.html` — an orphan page (no inbound links from
  any other page) shaped like a bare PhotoGridIndex entry, but its
  RichTextElement contains a broken Sandvox VideoElement
  (`20200725-ah-3045.mov`, no playable embed survives static export)
  rather than a real ImageElement. The one still-image asset that does
  exist for it, `20200725-ah-3045-2.jpeg` (the video's poster frame), is
  folded into the `content/ivan/bilder/2020/2020-07-25/` gallery bundle
  (same real-world date, already generated from `bilder/2020.html`) via
  `parse_sandvox_grid.get_orphan_thumbnail()` rather than given its own
  near-empty gallery.
- `ivan/iva1912.pdf` exists in `ivan/` alongside `iva1912-2.pdf`, but
  only `iva1912-2.pdf` is actually
  linked from `ivan-valfridsson.html`'s Christmas-letter list (checked by
  grepping the full source page). `iva1912.pdf` was already an invisible,
  unlinked file on the live legacy site, not a migration regression — not
  copied into the `ivan-valfridsson` bundle.
- `ivan/iva1712pdf.html` — not a real PDF (no `iva1712.pdf` exists); it's
  an HTML wrapper around `iva1712_med_hr.png`. The 2017 entry in the
  Christmas-letter list on `content/ivan/ivan-valfridsson/index.sv.md`
  links to an in-page `#julbrev-2017` anchor (a heading + inline image)
  instead of a fabricated `.pdf` link. (A separate `julbrev-2017/`
  sub-bundle was tried first but doesn't work: `ivan-valfridsson` is a
  leaf bundle — `index.sv.md`, not `_index.sv.md` — and Hugo leaf bundles
  cannot contain nested content pages, only page resources; a
  subdirectory with its own `index.sv.md` inside one is silently dropped
  from the build. Kept as one inline image on the parent page instead.)
- Years ≤2014 in that same Christmas-letter list still point to
  `http://valfridsson.net/ivan-old/ivaXXXX.pdf` (unmigrated `ivan-old`
  content, expected to 404 until a future phase migrates it — same
  pattern as `bilder/aldre-fotoalbum.html`'s `/ivan-old/album/` link).
- `ivan/susanne-hilliges-valfridsso/index.html` turned out to be a real,
  substantial autobiography (portrait + ~10 paragraphs) for Susanne, not
  the "small landing/contact page" it looked like from the filename
  alone — same shape and quality as `ivan-valfridsson.html` and
  `elsie-valfridsson.html`. To preserve it without colliding with the
  content-model's fixed path for the (unsplit, see main CLAUDE.md)
  diary, `content/ivan/susanne-hilliges-valfridsson/` is a *branch*
  bundle (`_index.sv.md`, the bio) with the diary as its child leaf
  bundle at `content/ivan/susanne-hilliges-valfridsson/dagbok/` — this
  mirrors the legacy site's own structure exactly (`index.html` +
  `dagbok---susanne.html` as a subpage under it, with "DAGBOK - Susanne"
  literally a submenu entry under "Susanne Hilliges-Valfridsson" in
  every page's nav).
- `ivan/bilder/index.html`, `ivan/bilder/2015/{januari,februari}/index.html`,
  `ivan/till-marita/index.html` and the flat year pages' own nav/sidebar
  chrome (list-of-links, thumbnail grids) aren't migrated as content —
  Hugo's own section list pages (`_index.sv.md` + `layouts/_default/list.html`)
  replace them structurally. `ivan/index.html`'s and `ivan/micke.html`'s
  sidebar widgets (a third-party "Dagens bibelord" verse-of-the-day JS
  embed, and an already-disabled guestbook notice) are dropped as
  non-portable legacy chrome; the "Länkar" list from that same sidebar
  (Masten, Cina Jeppsson, Shalom, Darash, Pingstkyrkan Tyresö) is real,
  useful cross-site navigation content and was folded into
  `content/ivan/_index.sv.md`'s body instead of being dropped with the
  rest of the sidebar.

## Known exclusions/decisions (ivan-old)

- **Full run complete.** `parse_frontpage_grid.py --all` processes
  `foto01.htm`-`foto72.htm` plus `foto37b.htm`/`foto56b.htm` (74 of the
  75 `foto*.htm` files found on disk — `foto57x.htm` is deliberately
  excluded, see below), `bilder/Haraldsfoto.htm`, `Shalom/bild0610.htm`,
  and the `ovriga-bilder/` orphan gallery, in one run: 442 album topic
  bundles (3188 images), 1 bilder gallery (80 images), 1 shalom gallery
  (15 images + 5 mp3 attachments), 1 ovriga-bilder gallery (119 images).
  `content/ivan-old/` totals ~418MB. See CLAUDE.md's decisions log for
  the full account of what changed since the earlier 6-page partial-run
  validation, including two real bugs the full run's row-level rework
  surfaced and fixed (an anchor-in-a-later-`<td>` topic misattribution,
  and a `topic_slug()` collision that let one topic's bundle silently
  overwrite another's).
- `ivan-old/index.html` (an older, shorter FrontPage duplicate of
  `ivan/index.html`'s content) was not ported — `content/ivan-old/_index.sv.md`
  is a short, freshly-written landing page instead, linking to
  `/ivan-old/album/`, `/ivan-old/bilder/`, `/ivan-old/shalom/` and
  `/ivan-old/ovriga-bilder/`.
- `ivan-old/dagbok.html`/`.htm` (confirmed duplicate of the already-migrated
  diary) was not migrated as content; `content/ivan/susanne-hilliges-valfridsson/dagbok/index.sv.md`
  got `aliases: ["/ivan-old/dagbok.html", "/ivan-old/dagbok.htm"]` added
  so the old URLs redirect instead of 404ing.
- `ivan-old/bilder.htm` (a *different* file from the `ivan-old/bilder/`
  *directory* migrated here) is a short "Oredigerade bilder" page whose
  links point at `ivan/foto/*.jpg` — a path that doesn't exist anywhere
  in this repo (dead links on the live legacy site already, not a
  migration regression). Not migrated.
- `ivan-old/video/` (six `.avi` clips, ~51MB) — checked via grep across
  every `.htm` page in `ivan-old/`, zero references anywhere. Dropped:
  orphaned *and* old low-resolution `.avi` clips are unlikely to be
  playable in a modern browser without transcoding, unlike `Shalom/`'s
  small, still-playable orphaned mp3s (kept) or `ovriga-bilder`'s
  ordinary, still-viewable orphaned JPEGs (also kept).
- Top-level `ivaXXXX.pdf` Christmas-letter PDFs (pre-2015 continuation of
  the ones already migrated to `content/ivan/ivan-valfridsson/`) are
  **not** migrated by this pass — wiring them up requires editing
  `content/ivan/ivan-valfridsson/index.sv.md`, which is explicitly out of
  scope for an ivan-old-only pass. Those Christmas-letter list entries
  remain 404 until a future pass touches that file specifically.
- ivan-old's `foto*.htm`/`album.htm`/`bilder/Haraldsfoto.htm`/
  `Shalom/bild0610.htm` pages are windows-1252-encoded (explicit on the
  pages that declare a charset; the rest are undeclared but same
  era/tool/encoding) — `_read_html()` decodes as `cp1252`, not UTF-8.
- See CLAUDE.md's decisions log for the footer-boilerplate-cell filter
  (`_is_footer_td`/`_FURNITURE_IMAGES`), the unmapped-in-page-anchor
  fold-forward rule, the `params.caption`-isn't-markdownified caption/body
  split, the row-level (not page-level) reversed-caption-layout handling,
  the `foto57x.htm` exclusion, and the `ovriga-bilder`/`Shalom`/`video`
  scoping decisions in full detail.
