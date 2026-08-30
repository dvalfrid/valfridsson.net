"""Parse cina/aktuella-tavlor.html, cina/tidigare-produktion.html and
cina/fotoalbum/*.html into Hugo page bundles under
content/cina/{aktuella-tavlor,tidigare-produktion,fotoalbum}/.

All four source shapes are the same repeating "image, then a caption
<p>" DOM pattern (Sandvox RichTextElement), just used two different ways:

- aktuella-tavlor.html / tidigare-produktion.html: each image+caption is
  an independent painting -> its own page bundle. A caption occasionally
  spans more than one <p> (one entry has a long freeform "Beskrivning av
  tavlan" paragraph in addition to the usual short Motiv/Storlek/Ägare
  line) and, in a couple of spots in tidigare-produktion.html, the next
  image is embedded *inside* a caption <p> instead of its own wrapper div
  (a Sandvox editing artifact) -- both are handled by
  extract_painting_blocks().
- fotoalbum/*.html (13 flat pages + the 2 already-nested
  8-utstallning-i-tyreso/, 9-utstallning-i-tyreso/ index.html pages): all
  photos on one page become ONE gallery bundle. Only the single
  <p> immediately following an image is that image's caption; any
  further paragraphs (intro prose, a "Foto: NN" credit line, ...) become
  page body prose instead -- extract_album() below.

One-off migration tool, not part of the `hugo --minify` build. See
README.md in this directory. Safe to re-run (idempotent): re-running
overwrites the generated index.sv.md files and re-copies images.

Usage:
    python scripts/migrate_photos/parse_cina_captions.py [--dry-run]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).parent))
from common import ImageResource, PageBundle, find_media, slugify, write_bundle  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC_CINA = ROOT / "cina"
SRC_FOTOALBUM = SRC_CINA / "fotoalbum"
MEDIA_DIR = SRC_CINA / "_Media"
OUT_CINA = ROOT / "content" / "cina"

# Painting source pages -> their content/ output directory.
PAINTING_PAGES = {
    "aktuella-tavlor.html": OUT_CINA / "aktuella-tavlor",
    "tidigare-produktion.html": OUT_CINA / "tidigare-produktion",
}

_SUFFIX_RE = re.compile(r"(_med_hr|_med|_360|_\d+_hr|_\d+)$", re.IGNORECASE)
_DASH_ONLY_RE = re.compile(r"^[\s\-–—]*$")

# [<medium> -] Motiv: <subject> - Storlek: <dims> cm [- Ägare: <owner>]
# Storlek is required for a "clean" match (per the caption-hybrid decision);
# Ägare and the medium prefix are optional. Colon after "Storlek" is
# sometimes missing in the source, tolerated here. Applied with fullmatch
# against the *whole* caption, so multi-paragraph captions (joined with a
# blank line) never match -- "." doesn't cross a newline -- which is
# exactly the desired "don't force-fit" behavior for the one freeform
# "Beskrivning av tavlan" outlier.
_PAINTING_CAPTION_RE = re.compile(
    r"(?:(?P<medium>Applikation|Akvarell)\s*-\s*)?"
    r"Motiv:\s*(?P<motif>.+?)"
    r"\s*-\s*Storlek:?\s*(?P<size>.+?)"
    r"(?:\s*-\s*Ägare:\s*(?P<owner>.+?))?"
    r"\s*\.?\s*"
)


def base_stem(filename: str) -> str:
    """Strip a size/variant suffix off a legacy media filename, e.g.
    "tks053_med_hr.jpeg" -> "tks053"."""
    stem = Path(filename).stem
    m = _SUFFIX_RE.search(stem)
    if m:
        return stem[: m.start()]
    return stem


def node_to_md(node) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name in ("strong", "b"):
        inner = "".join(node_to_md(c) for c in node.children).strip()
        return f"**{inner}**" if inner else ""
    if node.name in ("em", "i"):
        inner = "".join(node_to_md(c) for c in node.children).strip()
        return f"*{inner}*" if inner else ""
    if node.name == "a" and node.get("href"):
        inner = "".join(node_to_md(c) for c in node.children).strip()
        href = node["href"]
        return f"[{inner or href}]({href})"
    if node.name == "br":
        return "  \n"
    if node.name == "img":
        return ""
    return "".join(node_to_md(c) for c in node.children)


def paragraph_md(p_tag: Tag) -> str:
    text = "".join(node_to_md(c) for c in p_tag.children)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_content_div(soup: BeautifulSoup) -> Tag | None:
    return soup.select_one("div.article-content div.RichTextElement > div")


def top_level_children(content: Tag) -> list:
    return [c for c in content.children if isinstance(c, Tag) or (isinstance(c, NavigableString) and c.strip())]


def extract_title(soup: BeautifulSoup) -> str:
    span = soup.select_one("h2.title span.in")
    if span is None:
        return ""
    # No separator: some titles split a single word across nested <span>
    # style wrappers (e.g. "U" + "tställningarna ...") with no whitespace
    # of their own between them in the source -- inserting a join
    # separator there would wrongly add a space mid-word. Any *real*
    # whitespace (incl. newlines from pretty-printed source markup) is
    # collapsed afterwards instead.
    title = re.sub(r"\s+", " ", span.get_text()).strip()
    title = re.sub(r"\s+([.,])(\s|$)", r"\1\2", title).strip()
    return title


# ---------------------------------------------------------------------------
# aktuella-tavlor.html / tidigare-produktion.html: one bundle per painting
# ---------------------------------------------------------------------------


def extract_painting_blocks(soup: BeautifulSoup) -> list[tuple[str, str | None]]:
    """Return [(image-src-filename, raw-caption-or-None), ...], one entry
    per painting. A caption is every plain-text <p> between one image and
    the next, joined with blank lines (handles the one multi-paragraph
    "Beskrivning av tavlan" outlier). A couple of spots in
    tidigare-produktion.html embed the *next* image inside what looks
    like a caption <p> (`<p>text<img .../></p>`) instead of its own
    wrapper div -- handled by treating the text portion of such a <p> as
    the caption for the image seen *before* it, and the embedded <img> as
    the start of a new block.
    """
    content = get_content_div(soup)
    if content is None:
        return []
    children = top_level_children(content)

    blocks: list[list] = []  # each: [src, [caption paragraph, ...]]
    current: list | None = None

    for node in children:
        if not isinstance(node, Tag):
            continue
        img_tag = node if node.name == "img" else node.find("img")
        has_img = img_tag is not None and img_tag.get("src")

        if node.name == "p":
            text = paragraph_md(node)
            valid_text = bool(text) and not _DASH_ONLY_RE.match(text)
            if valid_text and current is not None:
                current[1].append(text)
            if has_img:
                current = [Path(img_tag["src"]).name, []]
                blocks.append(current)
        elif has_img:
            # A normal div.ImageElement-wrapped image.
            current = [Path(img_tag["src"]).name, []]
            blocks.append(current)
        # Any other tag (e.g. stray wrapper divs) is ignored.

    return [(src, "\n\n".join(paras) if paras else None) for src, paras in blocks]


def parse_painting_caption(raw: str) -> dict[str, str]:
    """Best-effort structured extraction. Returns {} if the caption does
    not *cleanly* match the whole Motiv/Storlek[/Ägare] pattern (never
    force-fit -- see the caption-hybrid decision in the migration plan)."""
    m = _PAINTING_CAPTION_RE.fullmatch(raw.strip())
    if not m:
        return {}
    out: dict[str, str] = {"motif": m.group("motif").strip()}
    out["size"] = m.group("size").strip()
    if m.group("owner"):
        out["owner"] = m.group("owner").strip()
    if m.group("medium"):
        out["medium"] = m.group("medium").strip()
    return out


def resolve_one(src_name: str) -> Path | None:
    stem = base_stem(src_name)
    chosen = find_media(MEDIA_DIR, stem)
    if chosen is None:
        print(f"  WARNING: no media match for stem {stem!r} (from {src_name})")
    return chosen


def process_paintings(dry_run: bool) -> tuple[int, int]:
    total = 0
    structured = 0
    for html_name, out_dir in PAINTING_PAGES.items():
        html_path = SRC_CINA / html_name
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        blocks = extract_painting_blocks(soup)
        slug_counts: dict[str, int] = {}
        print(f"== {html_name} ({len(blocks)} paintings) ==")
        for idx, (src, raw_caption) in enumerate(blocks, start=1):
            chosen = resolve_one(src)
            if chosen is None:
                continue
            fields = parse_painting_caption(raw_caption) if raw_caption else {}
            motif = fields.get("motif")
            if motif:
                base_slug = slugify(motif)
                n = slug_counts.get(base_slug, 0) + 1
                slug_counts[base_slug] = n
                slug = base_slug if n == 1 else f"{base_slug}-{n}"
                title = motif
                structured += 1
            else:
                slug = f"malning-{idx}"
                title = f"Målning {idx}"

            # params carries motif too (redundant with `title`, but the
            # content model calls for params.motif explicitly so templates
            # can read all four structured fields from one place).
            params = dict(fields)
            image = ImageResource(src=chosen.name, caption=raw_caption)
            bundle = PageBundle(
                slug_path=out_dir / slug,
                title=title,
                date=None,
                draft=False,
                layout="painting",
                caption=raw_caption,
                params=params,
                images=[image],
            )
            media_paths = {chosen.name: chosen}
            if dry_run:
                print(f"  [dry-run] {slug} <- {src} (title={title!r}, params={params})")
            else:
                path = write_bundle(bundle, media_paths)
                print(f"  wrote {path.relative_to(ROOT)}")
            total += 1
    return total, structured


# ---------------------------------------------------------------------------
# fotoalbum/*.html: one gallery bundle per album page
# ---------------------------------------------------------------------------


def album_source_pages() -> list[tuple[Path, str]]:
    """Return [(html_path, album_slug), ...] for the 13 flat album pages
    plus the 2 already-nested subdirectory albums."""
    pages: list[tuple[Path, str]] = []
    for html_path in sorted(SRC_FOTOALBUM.glob("*.html")):
        if html_path.name == "index.html":
            continue
        pages.append((html_path, html_path.stem))
    for sub in sorted(SRC_FOTOALBUM.iterdir()):
        if sub.is_dir():
            index = sub / "index.html"
            if index.exists():
                pages.append((index, sub.name))
    return pages


def extract_album(soup: BeautifulSoup) -> tuple[list[ImageResource], str, str]:
    """Walk an album page: only the single <p> immediately following an
    image is treated as that image's caption; anything else (intro
    prose, a trailing "Foto: NN" credit line, ...) becomes leading/
    trailing body prose instead."""
    content = get_content_div(soup)
    if content is None:
        return [], "", ""
    children = top_level_children(content)

    images: list[ImageResource] = []
    leading_parts: list[str] = []
    trailing_parts: list[str] = []
    seen_image = False

    n = len(children)
    i = 0
    while i < n:
        node = children[i]
        img_tag = None
        if isinstance(node, Tag):
            img_tag = node if node.name == "img" else node.find("img")
        if img_tag is not None and img_tag.get("src"):
            seen_image = True
            src_name = Path(img_tag["src"]).name
            caption = None
            if i + 1 < n:
                nxt = children[i + 1]
                if isinstance(nxt, Tag) and nxt.name == "p":
                    text = paragraph_md(nxt)
                    if text and not _DASH_ONLY_RE.match(text):
                        caption = text
                    i += 1  # consume this paragraph either way, don't reprocess it below
            images.append(ImageResource(src=src_name, caption=caption))
        elif isinstance(node, Tag) and node.name == "p":
            text = paragraph_md(node)
            if text and not _DASH_ONLY_RE.match(text):
                (trailing_parts if seen_image else leading_parts).append(text)
        i += 1

    leading = "\n\n".join(leading_parts)
    trailing = "\n\n".join(trailing_parts)
    return images, leading, trailing


def resolve_media(images: list[ImageResource]) -> tuple[list[ImageResource], dict[str, Path]]:
    resolved: list[ImageResource] = []
    media_paths: dict[str, Path] = {}
    for img in images:
        stem = base_stem(img.src)
        chosen = find_media(MEDIA_DIR, stem)
        if chosen is None:
            print(f"  WARNING: no media match for stem {stem!r} (from {img.src})")
            continue
        resolved.append(ImageResource(src=chosen.name, caption=img.caption))
        media_paths[chosen.name] = chosen
    return resolved, media_paths


def process_fotoalbum(dry_run: bool) -> tuple[int, int]:
    n_albums = 0
    n_images = 0
    for html_path, slug in album_source_pages():
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        title = extract_title(soup) or slug
        images, leading, trailing = extract_album(soup)
        resolved_images, media_paths = resolve_media(images)
        body_parts = [p for p in (leading, trailing) if p]

        bundle = PageBundle(
            slug_path=OUT_CINA / "fotoalbum" / slug,
            title=title,
            date=None,
            draft=False,
            layout="gallery" if resolved_images else None,
            body="\n\n".join(body_parts),
            images=resolved_images,
        )
        if dry_run:
            print(f"[dry-run] {html_path.relative_to(SRC_CINA)} -> fotoalbum/{slug} "
                  f"(title={title!r}, images={len(resolved_images)})")
        else:
            path = write_bundle(bundle, media_paths)
            print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
        n_albums += 1
        n_images += len(resolved_images)
    return n_albums, n_images


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    dry_run = "--dry-run" in sys.argv

    print("== paintings (aktuella-tavlor + tidigare-produktion) ==")
    n_paintings, n_structured = process_paintings(dry_run)
    print()
    print("== fotoalbum ==")
    n_albums, n_images = process_fotoalbum(dry_run)

    print()
    print(f"{n_paintings} paintings ({n_structured} with structured motif/size params, "
          f"{n_paintings - n_structured} raw-caption-only), "
          f"{n_albums} fotoalbum albums ({n_images} images total)"
          f"{' (dry run, nothing written)' if dry_run else ''}")


if __name__ == "__main__":
    main()
