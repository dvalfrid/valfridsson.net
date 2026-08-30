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

  NOTE: a handful of the very earliest pages (circa foto01-foto09,
  1999-2000) use a different, *reversed* column layout -- caption+date in
  one `<td>`, the bare `<img>` with no caption at all in the next `<td>`
  -- which this parser does not (yet) handle; see README.md. None of
  those pages are included in the default --pages sample.

- `bilder/Haraldsfoto.htm`: a flat list of `<p><a href="X.jpg">X.jpg</a></p>`
  links (not `<img>` tags -- these are plain link-per-photo lists, the
  photo's own filename doubling as its caption), for the Lindberg family
  genealogy photos. `process_bilder_gallery()` turns this into one
  undated gallery bundle at content/ivan-old/bilder/.

One-off migration tool, not part of the `hugo --minify` build. See
README.md in this directory. Safe to re-run (idempotent): re-running
overwrites the generated index.sv.md files and re-copies images.

Usage:
    python scripts/migrate_photos/parse_frontpage_grid.py [--dry-run] [--pages foto72.htm foto50.htm ...]
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
OUT_ALBUM = ROOT / "content" / "ivan-old" / "album"
OUT_BILDER = ROOT / "content" / "ivan-old" / "bilder"

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
# rather than the older reversed-column shape some pages before it use).
DEFAULT_PAGES = [
    "foto10.htm",
    "foto50.htm",
    "foto57.htm",
    "foto61.htm",
    "foto65.htm",
    "foto72.htm",
]

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

    for td in table.find_all("td"):
        if td.find("h1"):
            continue  # the page's own header cell (title + anchor-list), not content
        if _is_footer_td(td):
            continue  # the page furniture: "Foto: X", mailto, nav links, copyright

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
            if current_key is not None:
                attach: list[str] = []
                text = td_text(td, attach)
                topic = ensure(current_key, mapped.get(current_key, fallback_title))
                if text:
                    topic["intro"].append(text)
                topic["attachments"].extend(attach)
            continue

        for img in imgs:
            src_raw = img.get("src")
            if not src_raw:
                continue
            src = unquote(Path(src_raw).name)
            attach = []
            caption = extract_caption_after(img, attach) or None
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


def topic_slug(title: str, date: str | None, used_slugs: dict[str, int]) -> str:
    base = slugify(title) if title else "avsnitt"
    year = date[:4] if date else None
    if not year:
        m = re.search(r"(19|20)\d{2}", title or "")
        year = m.group(0) if m else None
    slug = f"{year}-{base}" if year else base
    n = used_slugs.get(slug, 0) + 1
    used_slugs[slug] = n
    return slug if n == 1 else f"{slug}-{n}"


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


def process_foto_pages(pages: list[str], dry_run: bool) -> tuple[int, int]:
    topic_map, page_title_map = parse_album(SRC / "album.htm")
    media_index = build_media_index(SRC)
    used_slugs: dict[str, int] = {}
    n_topics = 0
    n_images = 0

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
            if not resolved_images:
                continue

            intro = "\n\n".join(data["intro"])
            date = compute_date(intro, resolved_images)
            slug = topic_slug(data["title"], date, used_slugs)
            attachments = resolve_attachments(media_index, data["attachments"])
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

    return n_topics, n_images


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
    args = parser.parse_args()

    print(f"== album ({len(args.pages)} foto page(s): {', '.join(args.pages)}) ==")
    n_topics, n_images = process_foto_pages(args.pages, args.dry_run)

    print()
    print("== bilder/Haraldsfoto.htm ==")
    n_bilder = process_bilder_gallery(args.dry_run)

    print()
    print(
        f"{n_topics} album topic bundle(s) ({n_images} images total) + "
        f"1 bilder gallery ({n_bilder} images)"
        f"{' (dry run, nothing written)' if args.dry_run else ''}"
    )


if __name__ == "__main__":
    main()
