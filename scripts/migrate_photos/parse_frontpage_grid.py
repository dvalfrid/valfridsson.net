"""Parse ivan-old's older FrontPage-era HTML into Hugo page bundles under
content/ivan-old/.

ivan-old/ predates the Sandvox site (ivan/) handled by the other parsers
in this directory and has a completely different DOM shape: hand-written
FrontPage `<table>` grids, not Sandvox RichTextElement divs. Two distinct
source shapes are handled here:

- `album.htm` + `foto01.htm`-`foto72.htm`: `album.htm` is a master index,
  one `<tr>` per foto page, whose link text doubles as an anchor-linked
  *topic* list for that page (e.g. `foto72.htm#3` = "Ivan firar 75 år").
  Each `fotoNN.htm` is a `<table>` grid of cells shaped
  `<img src="X.jpg">Y.jpg<br>caption text, maybe with an embedded date`.
  `parse_album()` builds a `{foto-filename: {anchor: topic title}}` map
  from album.htm; `parse_foto_page()` then walks a given foto page's
  `<td>` cells in document order, using `<a name="N">` anchors that
  appear in that map as topic-section boundaries (anchors present in the
  HTML but *not* in album.htm's map -- e.g. foto57.htm's unused 8-19
  anchor cluster -- are treated as non-boundaries and folded into
  whichever topic is currently open, since album.htm's curator evidently
  didn't consider them separate sections either). A page with *zero*
  album.htm-mapped anchors (whether because it truly has no `<a name>`
  tags, like foto50.htm, or because album.htm just never linked any of
  its internal anchors individually, like foto57.htm) is treated as one
  single topic covering the whole page. One gallery bundle is emitted per
  resulting topic, flattened directly under `content/ivan-old/album/`
  (not nested per source page) -- see module docstring in the migration
  plan for why: the anchors already encode the meaningful editorial
  grouping, better than 72 generic `foto01`...`foto72` page bundles
  would.

  A caption occasionally embeds an inline link to a non-image local
  attachment (a `.pdf` or `.mp3`, e.g. foto57.htm's `MOR0104a.pdf`,
  `Odesbacka.pdf` and `Mor.mp3`) -- these are detected while converting
  the caption HTML to markdown and copied into the topic's bundle
  directory alongside the images, same pattern already used (by hand)
  for the Christmas-letter PDFs on content/ivan/ivan-valfridsson/. The
  markdown link text is left as-is (a bare relative filename), which
  resolves correctly once the file is a sibling page resource.

  Unlike ivan/'s _Media library, ivan-old's photos live flat at the top
  level of ivan-old/ with no pre-generated resolution variants -- so
  resolution here is a plain case-insensitive exact filename lookup
  (`resolve_exact`/`build_media_index`), not common.find_media's
  variant-priority matching.

  A run of the earliest pages (foto01.htm-foto09.htm, foto13.htm, plus
  scattered individual rows on some later, otherwise-mainstream pages --
  e.g. foto10.htm's Urskogsstigen row, foto12.htm's California-trip
  photos) use a *reversed* two-column row shape instead: a caption
  (+ optional date paragraph) in one `<td>`, the bare `<img>` with no
  caption of its own in the next `<td>`. `parse_foto_page()` handles
  this at row level (`tr.find_all("td", recursive=False)`, a per-row
  `row_pending_caption` buffer), not as a whole-page shape dispatch --
  several pages genuinely mix both row shapes (foto08.htm, foto12.htm),
  so a page-level "is this page reversed?" flag can't work. An
  image-less `<td>` is treated as the caption half of a reversed pair
  and deferred for the next `<img>` td in the same row unless
  `_is_intro_not_caption()` flags it as genuine topic-intro/heading prose
  instead (an embedded `<object>`/`<embed>` video, a nested `<table>`, or
  large `<font size>` styling -- see that function's docstring for the
  foto52.htm/foto56.htm examples that motivated it). If no image follows
  in the row, a deferred caption falls back to topic-intro prose, same as
  before.

- `bilder/Haraldsfoto.htm`: a flat list of `<p><a href="X.jpg">X.jpg</a></p>`
  links (not `<img>` tags -- these are plain link-per-photo lists, the
  photo's own filename doubling as its caption), for the Lindberg family
  genealogy photos. `process_bilder_gallery()` turns this into one
  undated gallery bundle at content/ivan-old/bilder/.

- `Shalom/bild0610.htm`: a flat list of `<a href="X.jpg">X.jpg</a>: real
  caption<br>` lines (one `<p>`, not one-per-photo like Haraldsfoto.htm)
  for a 2006 Shalom board-meeting photo set -- `process_shalom_gallery()`
  turns this into one dated gallery bundle at content/ivan-old/shalom/,
  with the folder's uncaptioned/unreferenced `jesajadel*.mp3` sermon
  recordings attached as downloadable resources (see README.md).

- Top-level `.jpg`/`.JPG` files in ivan-old/ not consumed by any
  foto*.htm topic bundle above are genuinely caption-less/undated --
  `build_ovriga_bilder()` collects them into one big undated gallery
  bundle at content/ivan-old/ovriga-bilder/, per the migration plan's
  "nothing that was previously viewable disappears" decision (see
  CLAUDE.md).

One-off migration tool, not part of the `hugo --minify` build. See
README.md in this directory. Safe to re-run (idempotent): re-running
overwrites the generated index.sv.md files and re-copies images.

Usage:
    python scripts/migrate_photos/parse_frontpage_grid.py [--dry-run] [--pages foto72.htm foto50.htm ...]
    python scripts/migrate_photos/parse_frontpage_grid.py --all   # full run: all foto*.htm + bilder + Shalom + ovriga-bilder
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import OrderedDict
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).parent))
from common import (  # noqa: E402
    ImageResource,
    PageBundle,
    parse_filename_date,
    parse_sv_caption_date,
    slugify,
    write_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "ivan-old"
SRC_BILDER = SRC / "bilder"
SRC_SHALOM = SRC / "Shalom"
OUT_ALBUM = ROOT / "content" / "ivan-old" / "album"
OUT_BILDER = ROOT / "content" / "ivan-old" / "bilder"
OUT_SHALOM = ROOT / "content" / "ivan-old" / "shalom"
OUT_OVRIGA = ROOT / "content" / "ivan-old" / "ovriga-bilder"

# Representative partial-run sample (see the migration plan's "Phase 5
# (ivan-old, partial)" scoping note) -- picked from album.htm's own
# anchor list to exercise: a large multi-topic page (foto72, 22 topics),
# a multi-topic page where album.htm skips some of the page's own
# in-page anchor numbers (foto61, anchors 5/6/8 unmapped -> folded
# forward), a single-topic page (foto65), two zero-topic/whole-page
# pages of different messiness (foto50 has no internal anchors at all;
# foto57 has internal anchors 1-19 but album.htm maps none of them, and
# also exercises the PDF/mp3 attachment case), and an early-2000s page
# still using the "mainstream" same-cell img+caption shape (foto10,
# alongside the reversed-column shape some pages before it use -- foto10
# also has one stray reversed-shape row itself, see the module docstring).
DEFAULT_PAGES = [
    "foto10.htm",
    "foto50.htm",
    "foto57.htm",
    "foto61.htm",
    "foto65.htm",
    "foto72.htm",
]

# Full run: foto01.htm-foto72.htm plus the two genuine continuation pages
# (foto37b.htm, foto56b.htm -- distinct, non-overlapping photo sets with
# their own album.htm-mapped topics, see CLAUDE.md/README.md) found on
# disk beyond the plain numeric sequence. foto57x.htm, the third
# suffixed file found on disk, is deliberately *excluded*: it's a stale
# prior FrontPage revision of foto57.htm itself (same title, same 40
# photos, same captions -- only the family-photo <map> area coordinates
# and a footer nav link pointing at the pre-move crossnet.se domain
# differ), not referenced anywhere in album.htm, and not a distinct
# topic -- processing it would duplicate the already-migrated
# 2009-slakttraff-pa-odesbacka bundle's photos into a second bundle for
# no benefit.
ALL_PAGES = [f"foto{n:02d}.htm" for n in range(1, 38)] + ["foto37b.htm"] + [
    f"foto{n:02d}.htm" for n in range(38, 57)
] + ["foto56b.htm"] + [f"foto{n:02d}.htm" for n in range(57, 73)]

_FOTO_HREF_RE = re.compile(r"(foto\d+[a-z]?)\.htm(?:#(\d+))?", re.IGNORECASE)

# Decorative page furniture, not content -- the down-arrow icon reused in
# every foto*.htm's footer row ahead of the "Föregående sida!"/"Hemsidan!"
# nav links. That footer row otherwise looks exactly like an ordinary
# multi-image content cell (two <img>s with trailing text after each), so
# without this filter it gets misread as two bogus "photos" whose
# "captions" are really the nav-link text and the copyright notice.
_FURNITURE_IMAGES = {"pil_v.gif"}
_ATTACHMENT_EXT = {".pdf", ".mp3"}


def _read_html(path: Path) -> BeautifulSoup:
    # ivan-old is older FrontPage-era HTML, windows-1252 (explicit on the
    # pages that bother to declare a charset, e.g. bilder.htm,
    # bilder/Haraldsfoto.htm; the foto*.htm/album.htm pages don't declare
    # one at all but are the same encoding, era and authoring tool).
    return BeautifulSoup(path.read_bytes().decode("cp1252", errors="replace"), "html.parser")


def build_media_index(directory: Path) -> dict[str, Path]:
    return {p.name.lower(): p for p in directory.iterdir() if p.is_file()}


def resolve_exact(index: dict[str, Path], filename: str) -> Path | None:
    return index.get(filename.lower())


# ---------------------------------------------------------------------------
# HTML -> markdown (shared by caption and intro-paragraph extraction)
# ---------------------------------------------------------------------------


def node_to_md(node, attachments: list[str], plain: bool = False) -> str:
    """Convert a cell's inner HTML to markdown for use as page *body*
    prose (intro paragraphs). Also used, with `plain=True`, for
    *captions*: `resources:` front matter's `params.caption` is rendered
    by layouts/_default/gallery.html as a raw string (`{{ . }}`), not
    piped through `markdownify` -- unlike a real markdown link, `**bold**`
    markers embedded there would show up as literal, unrendered asterisks
    to a visitor. So `plain=True` drops markdown emphasis/link syntax and
    keeps only the inner text, while still recording any local PDF/mp3
    attachment found along the way so the caller can surface it as a real,
    clickable markdown link in the topic's body prose instead (which *is*
    rendered normally through .Content)."""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name in ("strong", "b"):
        inner = "".join(node_to_md(c, attachments, plain) for c in node.children).strip()
        if not inner:
            return ""
        return inner if plain else f"**{inner}**"
    if node.name in ("em", "i"):
        inner = "".join(node_to_md(c, attachments, plain) for c in node.children).strip()
        if not inner:
            return ""
        return inner if plain else f"*{inner}*"
    if node.name == "a" and node.get("href"):
        href = node["href"]
        inner = "".join(node_to_md(c, attachments, plain) for c in node.children).strip()
        if not href.lower().startswith(("http://", "https://", "mailto:")):
            # A relative link inside a caption/intro is a local attachment
            # (the PDF/mp3 edge case) -- record it so the caller can copy
            # the file into the bundle and add a real markdown link to it
            # somewhere it will actually render (the page body, not a
            # caption -- see the plain=True note above).
            name = unquote(Path(href).name)
            if Path(name).suffix.lower() in _ATTACHMENT_EXT:
                attachments.append(name)
            return inner or name
        return (inner or href) if plain else f"[{inner or href}]({href})"
    if node.name == "br":
        return " " if plain else "  \n"
    if node.name in ("img", "map", "area"):
        return ""
    if node.name == "p":
        inner = "".join(node_to_md(c, attachments, plain) for c in node.children).strip()
        if not inner:
            return ""
        return f" {inner} " if plain else f"\n\n{inner}\n\n"
    return "".join(node_to_md(c, attachments, plain) for c in node.children)


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_plain(text: str) -> str:
    """For caption text (params.caption, single-line, never markdown):
    collapse ALL whitespace including literal newlines to a single space.
    FrontPage-era source HTML often has manually soft-wrapped lines inside
    a <td> cell's raw text nodes -- those are source formatting, not
    intentional line breaks, and must not survive into the caption."""
    return re.sub(r"\s+", " ", text).strip()


def extract_caption_after(img: Tag, attachments: list[str]) -> str:
    """Everything after `img` within its own <td>, up to (not including)
    the next <img> sibling, if any -- a cell's caption/date text. Rendered
    plain (no markdown emphasis/link syntax -- see node_to_md's plain=True
    docstring): this text goes straight into `params.caption`, which the
    gallery template does not markdownify."""
    parts = []
    for sib in img.next_siblings:
        if isinstance(sib, Tag) and sib.name == "img":
            break
        parts.append(node_to_md(sib, attachments, plain=True))
    return _clean_plain("".join(parts))


def extract_caption_plain(td: Tag, attachments: list[str]) -> str:
    """Full text of an image-less <td>, rendered plain like
    extract_caption_after -- used for the *reversed* two-column layout
    (caption <td> first, bare <img> in the next <td>, no caption at all)
    that a run of the earliest foto*.htm pages use (and a handful of
    stray same-shaped rows scattered through otherwise-mainstream later
    pages, e.g. foto10.htm's Urskogsstigen row), see parse_foto_page's
    row loop."""
    parts = [node_to_md(c, attachments, plain=True) for c in td.children]
    return _clean_plain("".join(parts))


def _is_intro_not_caption(td: Tag) -> bool:
    """An image-less <td> that is genuine topic-intro/heading prose
    rather than the *caption* half of a reversed caption-td-then-image-td
    pair (see extract_caption_plain). FrontPage authors reached for an
    <object>/<embed> (an embedded video, e.g. foto52.htm's YouTube
    embed), a nested <table>, or large <font size> styling (e.g.
    foto56.htm's 70th-birthday announcement paragraph) for these -- all
    structurally distinct from the plain, optionally <br>-separated or
    <p>-wrapped text used throughout the genuine reversed-layout caption
    cells (foto01.htm-foto09.htm, foto13.htm, and the stray rows noted
    above), including some *long* ones (foto07.htm/foto08.htm/foto09.htm's
    funeral-memorial pages have 250-450 character tribute captions, so
    text length alone is not a reliable signal here)."""
    if td.find(["object", "embed", "table"]):
        return True
    font = td.find("font", size=True)
    if font is not None:
        try:
            size = int(str(font.get("size")).lstrip("+"))
        except ValueError:
            size = 0
        if size >= 4:
            return True
    return False


def td_text(td: Tag, attachments: list[str]) -> str:
    """An anchor-only <td>'s intro/prose text -- becomes page *body*
    markdown (rendered through .Content), so full markdown (bold/links)
    is kept."""
    parts = [node_to_md(c, attachments, plain=False) for c in td.children]
    return _clean("".join(parts))


# ---------------------------------------------------------------------------
# album.htm: {foto-filename: {anchor: topic title}} + page-level fallback titles
# ---------------------------------------------------------------------------


def parse_album(album_path: Path) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    soup = _read_html(album_path)
    topic_map: dict[str, dict[str, str]] = {}
    page_title_map: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        if not text:
            continue  # the framat.gif "next page" icon link
        m = _FOTO_HREF_RE.search(a["href"])
        if not m:
            continue
        page = m.group(1).lower() + ".htm"
        frag = m.group(2)
        if frag:
            topic_map.setdefault(page, {})[frag] = text
        else:
            page_title_map.setdefault(page, text)

    # Many rows -- every foto01.htm-foto13.htm-ish single-story early page
    # -- never wrap their descriptive text in an <a> at all: the row's
    # only <a href="fotoNN.htm"> wraps just the framat.gif "next page"
    # arrow icon (empty link text, skipped above), and the real title
    # sits as plain sibling <td> text instead, e.g. foto01.htm's row is
    # <td><a href="foto01.htm"><img src="framat.gif"></a></td><td>Vår
    # dotter Åsa med familj strax före resan till Kalifornien - mars
    # 1999.</td>. Recover that as a second-priority page title (only
    # fills gaps -- setdefault -- so it never overrides a real
    # album.htm-anchor-derived title like foto72.htm's "2014").
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 2:
            continue
        icon_link = tds[0].find("a", href=True)
        if icon_link is None or icon_link.get_text(strip=True):
            continue  # not an icon-only cell
        m = _FOTO_HREF_RE.search(icon_link["href"])
        if not m or m.group(2):
            continue
        page = m.group(1).lower() + ".htm"
        row_text = " ".join(tds[1].get_text(" ", strip=True).split()).rstrip(".").strip()
        if row_text:
            page_title_map.setdefault(page, row_text)
    return topic_map, page_title_map


# ---------------------------------------------------------------------------
# fotoNN.htm -> {topic-key: {title, intro, images, attachments}}
# ---------------------------------------------------------------------------


def _is_footer_td(td: Tag) -> bool:
    """Every foto*.htm ends with one boilerplate cell: a "Foto: <credit>"
    line, a mailto: link, "Föregående sida!"/"Hemsidan!" nav links (via
    the pil_v.gif icon, see _FURNITURE_IMAGES) and a copyright notice --
    page furniture, not photos or real prose, on every single page."""
    if td.find("a", href=lambda h: bool(h) and h.lower().startswith("mailto:")):
        return True
    text = td.get_text(" ", strip=True).lower()
    return "föregående sida" in text or "all rights reserved" in text


def parse_foto_page(
    html_path: Path, topic_map: dict[str, dict[str, str]], page_title_map: dict[str, str]
) -> "OrderedDict[str, dict]":
    page_key = html_path.name.lower()
    soup = _read_html(html_path)
    table = soup.find("table")
    if table is None:
        return OrderedDict()

    mapped = topic_map.get(page_key, {})
    whole_page = not mapped

    fallback_title = page_title_map.get(page_key)
    if not fallback_title:
        title_tag = soup.find("title")
        fallback_title = title_tag.get_text(strip=True) if title_tag else page_key
        fallback_title = re.sub(r"\s*-\s*fotografier\s*$", "", fallback_title, flags=re.IGNORECASE).strip()

    topics: "OrderedDict[str, dict]" = OrderedDict()

    def ensure(key: str, title: str) -> dict:
        if key not in topics:
            topics[key] = {"title": title, "intro": [], "images": [], "attachments": []}
        return topics[key]

    current_key: str | None = None
    if whole_page:
        current_key = "_page"
        ensure(current_key, fallback_title)

    pending_images: list[ImageResource] = []
    pending_attach: list[str] = []

    # Walk row by row (not a flat table.find_all("td")) so a caption-only
    # <td> can be paired with the *next* image-bearing <td> in the same
    # row -- the reversed early-page layout, and stray same-shaped rows
    # on later, otherwise-mainstream pages -- without a whole-page shape
    # dispatch (several pages genuinely mix both row shapes; see the
    # module docstring and _is_intro_not_caption).
    for tr in table.find_all("tr", recursive=False):
        # recursive=False: only the outer table's own rows, not a nested
        # <table>'s (foto56.htm's 70th-birthday "tack" message uses one
        # for layout -- no real photo content ever lives in a nested
        # table, confirmed by scanning all 74 pages). td_text() already
        # walks a td's *entire* subtree (including any nested table)
        # when that td is classified as intro prose, so also visiting
        # the nested table's own <tr> as a separate top-level row here
        # would double-emit that text.
        if tr.find("h1"):
            continue  # the page's own header row (title + anchor-list), not content

        row_tds = [td for td in tr.find_all("td", recursive=False) if not _is_footer_td(td)]
        if not row_tds:
            continue

        row_pending_caption: list[str] = []
        row_pending_attach: list[str] = []
        row_deferred_intro: list[str] = []
        row_deferred_intro_attach: list[str] = []

        for td in row_tds:
            if not whole_page:
                for a in td.find_all("a"):
                    name = a.get("name")
                    if name and name in mapped:
                        current_key = name
                        ensure(current_key, mapped[name])

            imgs = [
                i for i in td.find_all("img")
                if unquote(Path(i.get("src", "")).name).lower() not in _FURNITURE_IMAGES
            ]
            if not imgs:
                if len(row_tds) == 1 or _is_intro_not_caption(td):
                    # A lone <td> spanning the whole row (colspan="2" or
                    # width="100%") can never be paired with "the next
                    # image <td> in this row" -- there isn't one -- so
                    # it's unambiguously intro/heading prose, not a
                    # reversed-layout caption candidate (e.g. foto65.htm's
                    # "<b>Släktbilden</b>" section-label row, or
                    # foto72.htm's "<b>Julen 2014</b>" one). Routing these
                    # through td_text (markdown-preserving) rather than
                    # the caption path keeps their <b>/<strong> emphasis
                    # intact instead of losing it to extract_caption_plain
                    # or the row_pending_caption plain-text fallback.
                    #
                    # Otherwise: genuine topic-intro/heading prose (embedded video,
                    # nested table, large <font size>). Deferred to the
                    # end of the row rather than committed to
                    # topic["intro"] immediately: a topic-boundary
                    # `<a name="N">` sometimes sits inside a *later* <td>
                    # in this same row (e.g. foto56.htm#5's "Ivan firar
                    # sin 70-årsdag" intro paragraph is in the row's
                    # first <td>, but the <a name="5"> anchor is inside
                    # the *second* <td>, alongside that topic's photo) --
                    # committing immediately would attach it to whatever
                    # topic was still open before this row started, one
                    # td too early. Waiting until the row (including any
                    # later anchor in it) is fully processed gets this
                    # right without a whole-row anchor pre-scan, which
                    # would instead break rows where *each* <td> has its
                    # own independent anchor+image pair (e.g. foto68.htm,
                    # two different flower photos side by side).
                    attach: list[str] = []
                    text = td_text(td, attach)
                    if text:
                        row_deferred_intro.append(text)
                    row_deferred_intro_attach.extend(attach)
                else:
                    # Might be the caption half of a reversed
                    # caption-td-then-image-td pair -- buffer it for
                    # whichever image <td> comes next in this row. If
                    # none does, it falls through to topic-intro prose
                    # after the row loop, below.
                    attach = []
                    text = extract_caption_plain(td, attach)
                    if text or attach:
                        row_pending_caption.append(text)
                        row_pending_attach.extend(attach)
                continue

            for idx, img in enumerate(imgs):
                src_raw = img.get("src")
                if not src_raw:
                    continue
                src = unquote(Path(src_raw).name)
                attach = []
                own_caption = extract_caption_after(img, attach) or None
                if idx == 0 and row_pending_caption:
                    combined = row_pending_caption + ([own_caption] if own_caption else [])
                    caption = _clean_plain(" ".join(combined)) or None
                    attach = row_pending_attach + attach
                    row_pending_caption, row_pending_attach = [], []
                else:
                    caption = own_caption
                image = ImageResource(src=src, caption=caption)
                if current_key is None:
                    # Images before the page's first *mapped* anchor -- not
                    # seen in practice across the sample pages, but handled
                    # defensively rather than silently dropped.
                    pending_images.append(image)
                    pending_attach.extend(attach)
                    continue
                topic = ensure(current_key, mapped.get(current_key, fallback_title))
                if pending_images:
                    topic["images"] = pending_images + topic["images"]
                    topic["attachments"] = pending_attach + topic["attachments"]
                    pending_images, pending_attach = [], []
                topic["images"].append(image)
                topic["attachments"].extend(attach)

        if row_deferred_intro and current_key is not None:
            # Commit using the row's *final* current_key -- picks up any
            # anchor found later in this same row, see the comment above.
            topic = ensure(current_key, mapped.get(current_key, fallback_title))
            topic["intro"].append(_clean("\n\n".join(row_deferred_intro)))
            topic["attachments"].extend(row_deferred_intro_attach)

        if row_pending_caption:
            # No image followed the caption-shaped text anywhere else in
            # this row -- treat it as topic-intro prose instead of
            # silently dropping it (rare: not seen to actually occur
            # across all 74 processed pages, but handled defensively).
            text = _clean_plain(" ".join(p for p in row_pending_caption if p))
            if text and current_key is not None:
                topic = ensure(current_key, mapped.get(current_key, fallback_title))
                topic["intro"].append(text)
                topic["attachments"].extend(row_pending_attach)

    if pending_images:
        if topics:
            first_key = next(iter(topics))
            topics[first_key]["images"] = pending_images + topics[first_key]["images"]
            topics[first_key]["attachments"] = pending_attach + topics[first_key]["attachments"]
        else:
            t = ensure("_page", fallback_title)
            t["images"] = pending_images
            t["attachments"] = pending_attach

    return topics


def compute_date(intro_text: str, images: list[ImageResource]) -> str | None:
    date = parse_sv_caption_date(intro_text) if intro_text else None
    if date:
        return date
    for img in images:
        date = parse_filename_date(Path(img.src).stem)
        if date:
            return date
    return None


def topic_slug(title: str, date: str | None, used_slugs: set[str]) -> str:
    """`used_slugs` tracks every *final* slug this run has already
    returned (not the pre-suffix base) -- two topics with genuinely
    different titles can still collide on the same final string (e.g.
    foto37.htm's own "TYFRI MC 2" topic and foto41.htm's *second*
    "TYFRI MC" topic, whose auto-appended "-2" collision suffix lands on
    that exact same string). Keying collision-tracking on the pre-suffix
    base alone (as an earlier version of this function did) misses that
    second-order collision -- the two topics silently overwrite each
    other's bundle directory instead of getting distinct slugs."""
    base = slugify(title) if title else "avsnitt"
    year = date[:4] if date else None
    if not year:
        m = re.search(r"(19|20)\d{2}", title or "")
        year = m.group(0) if m else None
    slug = f"{year}-{base}" if year else base
    candidate = slug
    n = 1
    while candidate in used_slugs:
        n += 1
        candidate = f"{slug}-{n}"
    used_slugs.add(candidate)
    return candidate


def resolve_attachments(media_index: dict[str, Path], names: list[str]) -> list[Path]:
    resolved: list[Path] = []
    seen: set[str] = set()
    for name in names:
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        path = resolve_exact(media_index, name)
        if path is None:
            print(f"    WARNING: attachment not found: {name!r}")
            continue
        resolved.append(path)
    return resolved


def process_foto_pages(pages: list[str], dry_run: bool) -> tuple[int, int, set[str]]:
    """Returns (n_topics, n_images, consumed_filenames) -- the third
    element is every top-level ivan-old/ filename (images + attachments,
    lowercased) that ended up copied into an album/ bundle, used by
    build_ovriga_bilder() to diff against the full top-level *.jpg/.JPG
    listing and find the genuinely orphaned/caption-less set."""
    topic_map, page_title_map = parse_album(SRC / "album.htm")
    media_index = build_media_index(SRC)
    used_slugs: set[str] = set()
    n_topics = 0
    n_images = 0
    consumed: set[str] = set()

    for page_name in pages:
        html_path = SRC / page_name
        if not html_path.exists():
            print(f"WARNING: {page_name} not found in {SRC}, skipping")
            continue
        topics = parse_foto_page(html_path, topic_map, page_title_map)
        if not topics:
            print(
                f"WARNING: no topics/images extracted from {page_name} -- possibly an "
                "unsupported page layout (e.g. the older caption-before-image reversed "
                "column layout used by some early foto*.htm pages, see README.md)"
            )
            continue
        print(f"== {page_name} ({len(topics)} topic(s)) ==")

        for key, data in topics.items():
            if not data["images"]:
                print(f"  (skipping empty topic {data['title']!r}, anchor #{key} has no photos)")
                continue

            resolved_images: list[ImageResource] = []
            media_paths: dict[str, Path] = {}
            for img in data["images"]:
                path = resolve_exact(media_index, img.src)
                if path is None:
                    print(f"  WARNING: image not found: {img.src!r} ({page_name}, topic {data['title']!r})")
                    continue
                resolved_images.append(ImageResource(src=path.name, caption=img.caption))
                media_paths[path.name] = path
                consumed.add(path.name.lower())
            if not resolved_images:
                continue

            intro = "\n\n".join(data["intro"])
            date = compute_date(intro, resolved_images)
            slug = topic_slug(data["title"], date, used_slugs)
            attachments = resolve_attachments(media_index, data["attachments"])
            for att_path in attachments:
                consumed.add(att_path.name.lower())
            if attachments:
                # The captions that referenced these (see node_to_md's
                # plain=True note) only kept the link *text*, not a
                # markdown link -- resources: captions aren't
                # markdownified by the gallery template. Surface a real,
                # clickable link in the body instead, which is.
                links = ", ".join(f"[{p.name}]({p.name})" for p in attachments)
                intro = f"{intro}\n\n**Bilagor:** {links}" if intro else f"**Bilagor:** {links}"

            bundle = PageBundle(
                slug_path=OUT_ALBUM / slug,
                title=data["title"],
                date=date,
                draft=False,
                layout="gallery",
                body=intro,
                images=resolved_images,
            )

            if dry_run:
                att_note = f", attachments={[p.name for p in attachments]}" if attachments else ""
                print(
                    f"  [dry-run] album/{slug} <- {page_name}#{key} "
                    f"(title={data['title']!r}, images={len(resolved_images)}, date={date}{att_note})"
                )
            else:
                path = write_bundle(bundle, media_paths)
                for att_path in attachments:
                    dest = bundle.slug_path / att_path.name
                    if not dest.exists() or dest.stat().st_size != att_path.stat().st_size:
                        shutil.copyfile(att_path, dest)
                att_note = f", {len(attachments)} attachment(s)" if attachments else ""
                print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s){att_note})")

            n_topics += 1
            n_images += len(resolved_images)

    return n_topics, n_images, consumed


# ---------------------------------------------------------------------------
# bilder/Haraldsfoto.htm: flat link list -> one undated gallery bundle
# ---------------------------------------------------------------------------


def process_bilder_gallery(dry_run: bool) -> int:
    html_path = SRC_BILDER / "Haraldsfoto.htm"
    soup = _read_html(html_path)
    media_index = build_media_index(SRC_BILDER)

    title_tag = soup.find("h1")
    title = title_tag.get_text(" ", strip=True) if title_tag else "Bilder"
    title = " ".join(title.split())

    images: list[ImageResource] = []
    pending_section: str | None = None
    for p in soup.find_all("p"):
        a = p.find("a", href=True)
        if a is None:
            text = p.get_text(strip=True)
            if text:
                pending_section = text.rstrip(":").strip()
            continue
        filename = unquote(Path(a["href"]).name)
        link_text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
        full_text = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
        note = full_text[len(link_text):].strip() if full_text.startswith(link_text) else ""
        caption = Path(filename).stem
        if pending_section:
            caption = f"{pending_section}: {caption}"
            pending_section = None
        if note:
            caption = f"{caption} {note}"
        images.append(ImageResource(src=filename, caption=caption))

    resolved_images: list[ImageResource] = []
    media_paths: dict[str, Path] = {}
    for img in images:
        path = resolve_exact(media_index, img.src)
        if path is None:
            print(f"  WARNING: image not found: {img.src!r} (bilder/Haraldsfoto.htm)")
            continue
        resolved_images.append(ImageResource(src=path.name, caption=img.caption))
        media_paths[path.name] = path

    bundle = PageBundle(
        slug_path=OUT_BILDER,
        title=title,
        date=None,
        draft=False,
        layout="gallery",
        images=resolved_images,
    )
    if dry_run:
        print(f"[dry-run] bilder/Haraldsfoto.htm -> content/ivan-old/bilder/ ({len(resolved_images)} image(s))")
    else:
        path = write_bundle(bundle, media_paths)
        print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
    return len(resolved_images)


# ---------------------------------------------------------------------------
# Shalom/bild0610.htm: one <p> of <a href="X.jpg">X.jpg</a>: caption<br>
# lines -> one dated gallery bundle, + unreferenced jesajadel*.mp3 sermon
# recordings from the same folder attached as downloadable resources.
# ---------------------------------------------------------------------------


def process_shalom_gallery(dry_run: bool) -> tuple[int, int]:
    html_path = SRC_SHALOM / "bild0610.htm"
    soup = _read_html(html_path)
    media_index = build_media_index(SRC_SHALOM)

    ps = soup.find_all("p")
    intro_text = " ".join(ps[0].get_text(" ", strip=True).split()) if ps else ""
    # "Obehandlade och okomprimerade bilder från Shaloms arbets- och
    # styrelsemöte i Källered 14/10 -06:" -> "Shaloms arbets- och
    # styrelsemöte i Källered" (date dropped from the title -- it's
    # already `date` front matter; kept verbatim in the body sentence).
    title = re.sub(r"^Obehandlade och okomprimerade bilder från\s*", "", intro_text, flags=re.IGNORECASE)
    title = re.sub(r"\s*\d{1,2}/\d{1,2}\s*-\d{2}:?\s*$", "", title).strip()
    if not title:
        title = "Shalom"

    # The caption list itself is the *second* <p> -- a flat run of
    # <a href="X.jpg">X.jpg</a>: caption<br> lines all in one paragraph
    # (unlike bilder/Haraldsfoto.htm's one-<p>-per-link shape).
    images: list[ImageResource] = []
    caption_p = ps[1] if len(ps) > 1 else None
    if caption_p is not None:
        current_filename: str | None = None
        current_parts: list[str] = []

        def flush() -> None:
            nonlocal current_filename, current_parts
            if current_filename:
                caption = _clean_plain("".join(current_parts)).lstrip(":").strip()
                images.append(ImageResource(src=current_filename, caption=caption or None))
            current_filename, current_parts = None, []

        for node in caption_p.children:
            if isinstance(node, Tag) and node.name == "a" and node.get("href"):
                flush()
                current_filename = unquote(Path(node["href"]).name)
            elif isinstance(node, Tag) and node.name == "br":
                continue
            elif isinstance(node, NavigableString):
                current_parts.append(str(node))
            elif isinstance(node, Tag):
                current_parts.append(node.get_text())
        flush()

    resolved_images: list[ImageResource] = []
    media_paths: dict[str, Path] = {}
    for img in images:
        path = resolve_exact(media_index, img.src)
        if path is None:
            print(f"  WARNING: image not found: {img.src!r} (Shalom/bild0610.htm)")
            continue
        resolved_images.append(ImageResource(src=path.name, caption=img.caption))
        media_paths[path.name] = path

    date = None
    for img in resolved_images:
        date = parse_filename_date(Path(img.src).stem)
        if date:
            break

    # jesajadel1.mp3-jesajadel5.mp3 (Bible-study/sermon recordings) live
    # in the same folder but aren't linked from bild0610.htm or any other
    # ivan-old page (checked via grep across the whole tree) -- genuinely
    # orphaned audio, not reconstructible captions/context elsewhere.
    # Small enough (a handful of mp3s) to keep as downloadable
    # attachments on this page rather than drop, same judgment call as
    # foto57.htm's MOR0104a.pdf/Odesbacka.pdf/Mor.mp3 case.
    audio_files = sorted(SRC_SHALOM.glob("jesajadel*.mp3"))
    body = intro_text
    if audio_files:
        links = ", ".join(f"[{p.name}]({p.name})" for p in audio_files)
        note = (
            "Ljudinspelningar från samma mapp, utan egen bildtext eller känt "
            "sammanhang -- sparade som nedladdningsbara bilagor:"
        )
        body = f"{body}\n\n**{note}** {links}" if body else f"**{note}** {links}"

    bundle = PageBundle(
        slug_path=OUT_SHALOM,
        title=title,
        date=date,
        draft=False,
        layout="gallery",
        body=body,
        images=resolved_images,
    )
    if dry_run:
        print(
            f"[dry-run] Shalom/bild0610.htm -> content/ivan-old/shalom/ "
            f"({len(resolved_images)} image(s), {len(audio_files)} mp3 attachment(s))"
        )
    else:
        path = write_bundle(bundle, media_paths)
        for a in audio_files:
            dest = bundle.slug_path / a.name
            if not dest.exists() or dest.stat().st_size != a.stat().st_size:
                shutil.copyfile(a, dest)
        print(
            f"  wrote {path.relative_to(ROOT)} "
            f"({len(resolved_images)} image(s), {len(audio_files)} mp3 attachment(s))"
        )
    return len(resolved_images), len(audio_files)


# ---------------------------------------------------------------------------
# Top-level *.jpg files not consumed by any album/ topic bundle -> one big
# undated, caption-less gallery bundle (the ~300MB+ "ovriga bilder"
# decision, see CLAUDE.md's known migration decisions).
# ---------------------------------------------------------------------------


def build_ovriga_bilder(consumed_lower: set[str], dry_run: bool) -> tuple[int, int]:
    """Diff every top-level .jpg/.JPG filename directly inside ivan-old/
    (NOT its bilder/, Shalom/, video/, temp/ subdirectories -- those are
    handled, or deliberately dropped, by their own dedicated code paths)
    against `consumed_lower` (everything process_foto_pages() already
    copied into an album/ bundle). Whatever's left is genuinely orphaned:
    no foto*.htm page ever referenced it. Returns (n_top_level,
    n_orphaned)."""
    all_top_level = sorted(
        (p for p in SRC.iterdir() if p.is_file() and p.suffix.lower() == ".jpg"),
        key=lambda p: p.name.lower(),
    )
    orphans = [p for p in all_top_level if p.name.lower() not in consumed_lower]

    images = [ImageResource(src=p.name, caption=None) for p in orphans]
    media_paths = {p.name: p for p in orphans}

    body = (
        "Bilder utan bildtext eller känt sammanhang -- de är inte länkade "
        "från någon av albumets sidor, men sparade här så att inget som "
        "tidigare gick att se på den gamla webbplatsen försvinner."
    )
    bundle = PageBundle(
        slug_path=OUT_OVRIGA,
        title="Övriga bilder",
        date=None,
        draft=False,
        layout="gallery",
        body=body,
        images=images,
    )
    if dry_run:
        print(
            f"[dry-run] {len(orphans)} orphaned image(s) of {len(all_top_level)} "
            "top-level .jpg file(s) -> content/ivan-old/ovriga-bilder/"
        )
    else:
        path = write_bundle(bundle, media_paths)
        print(f"  wrote {path.relative_to(ROOT)} ({len(orphans)} image(s))")
    return len(all_top_level), len(orphans)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--pages",
        nargs="+",
        default=DEFAULT_PAGES,
        help="foto*.htm filenames to process (default: the partial-run sample, see DEFAULT_PAGES)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="full run: all of ALL_PAGES (foto01.htm-foto72.htm + foto37b.htm/foto56b.htm) "
        "instead of --pages/DEFAULT_PAGES, plus bilder/, Shalom/ and the ovriga-bilder orphan gallery",
    )
    args = parser.parse_args()
    pages = ALL_PAGES if args.all else args.pages

    print(f"== album ({len(pages)} foto page(s): {', '.join(pages)}) ==")
    n_topics, n_images, consumed = process_foto_pages(pages, args.dry_run)

    print()
    print("== bilder/Haraldsfoto.htm ==")
    n_bilder = process_bilder_gallery(args.dry_run)

    summary = (
        f"{n_topics} album topic bundle(s) ({n_images} images total) + "
        f"1 bilder gallery ({n_bilder} images)"
    )

    if args.all:
        print()
        print("== Shalom/bild0610.htm ==")
        n_shalom_images, n_shalom_mp3 = process_shalom_gallery(args.dry_run)
        summary += f" + 1 shalom gallery ({n_shalom_images} images, {n_shalom_mp3} mp3 attachments)"

        print()
        print("== ovriga-bilder (orphaned top-level photos) ==")
        n_top_level, n_orphans = build_ovriga_bilder(consumed, args.dry_run)
        summary += (
            f" + 1 ovriga-bilder gallery ({n_orphans} orphaned of {n_top_level} "
            "top-level .jpg files)"
        )

    print()
    print(summary + (" (dry run, nothing written)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
