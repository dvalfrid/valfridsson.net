"""Parse ivan/bilder's flat "one page per year" photo-diary pages into
Hugo page bundles, grouped by the real calendar date of each photo:

- ivan/bilder/untitled.html (year 2015 -- see README for why this is the
  canonical "2015" flat page and not the stale top-level ivan/untitled.html
  duplicate) and ivan/bilder/2016.html..2020.html: each is a single long
  RichTextElement of repeating (image, caption) pairs, one full calendar
  year, most-recent-first. Every image has exactly one real caption
  (never split across paragraphs here, unlike cina), occasionally
  followed by a purely decorative "****...." divider paragraph with no
  content of its own. Walk the DOM structurally -- do NOT split on the
  literal "****" text, some years use it as a divider and some don't,
  and it's never part of a real caption.

  Captions embed the photo's real date in one of two hand-typed Swedish
  styles depending on the year ("26 december 2018" / "23/12 -15" -- see
  common.parse_sv_caption_date), with the legacy media filename's own
  embedded date as a fallback, and simple carry-forward from the
  previously-dated photo as a last resort for the rare caption that's a
  pure continuation of the previous one's date. Each resulting date
  gets its own gallery bundle: content/ivan/bilder/<year>/<date>/.

- ivan/bilder/micke.html (the canonical, complete "Micke" photo album --
  see README for why this one is picked over the smaller, incomplete
  top-level ivan/micke.html duplicate): same repeating-image-block shape,
  but every "caption" here is just the image's own filename echoed back
  (not a real caption, and the images span 1970-2019 so there's no
  sensible single date to group by) -- so process_micke() below collects
  every photo into ONE undated gallery bundle and discards the
  filename-echo pseudo-captions.

One-off migration tool, not part of the `hugo --minify` build. See
README.md in this directory. Safe to re-run (idempotent): re-running
overwrites the generated index.sv.md files and re-copies images.

Usage:
    python scripts/migrate_photos/parse_sandvox_flatyear.py [--dry-run]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).parent))
from common import (  # noqa: E402
    ImageResource,
    PageBundle,
    extract_img_src,
    find_media,
    parse_filename_date,
    parse_sv_caption_date,
    write_bundle,
)
from parse_sandvox_grid import get_orphan_thumbnail  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC_IVAN = ROOT / "ivan"
SRC_BILDER = SRC_IVAN / "bilder"
MEDIA_DIR = SRC_IVAN / "_Media"
OUT_IVAN = ROOT / "content" / "ivan"

# year -> source flat-page filename. 2015's canonical flat page is
# bilder/untitled.html, not bilder/2015/ (that's the separate, orphaned
# PhotoGridIndex folder handled by parse_sandvox_grid.py instead) -- see
# README for the full untitled.html dedup writeup.
FLAT_YEAR_PAGES = {
    2015: "untitled.html",
    2016: "2016.html",
    2017: "2017.html",
    2018: "2018.html",
    2019: "2019.html",
    2020: "2020.html",
}

# Purely decorative divider paragraphs seen between entries: runs of
# "*", "-"/"–"/"—", or (2020 only) "<"/">" -- never real caption text.
_DIVIDER_ONLY_RE = re.compile(r"^[\s*<>=\-–—]*$")


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
    if node.name in ("img", "span"):
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


def _is_photo_tag(tag) -> bool:
    return isinstance(tag, Tag) and (tag.name == "img" or (tag.name == "span" and tag.get("data-img-src-hr")))


def extract_dated_pairs(soup: BeautifulSoup) -> list[tuple[str, str | None]]:
    """Walk the flat year page's content div structurally: an
    ImageElement-wrapper div (or a bare <img>/hi-res <span>) followed by
    the single <p> caption that immediately follows it (a divider-only
    <p> is discarded, not treated as a caption).

    A handful of spots (a few per year) have an extra standalone <p>
    that is *not* immediately after an image -- a short intro/section
    sentence for the photo(s) that follow, e.g. "Förberedelse för
    fiberinstallation på Danhäll..." ahead of a cluster of fiber-install
    photos, or "Under dessa coronatider..." ahead of a cluster of 2020
    photos. Rather than drop these (or guess how many following photos
    they cover), each is prepended to the very next photo's own caption
    (blank-line joined). The one recurring exception that's expected to
    never get consumed is the trailing "Åter till Album!" link at the
    very end of every page (nothing follows it).
    """
    content = get_content_div(soup)
    if content is None:
        return []
    children = top_level_children(content)

    pairs: list[tuple[str, str | None]] = []
    pending_intro: str | None = None
    n = len(children)
    i = 0
    while i < n:
        node = children[i]
        img_tag = node if _is_photo_tag(node) else (node.find(_is_photo_tag) if isinstance(node, Tag) else None)
        if img_tag is not None:
            src = extract_img_src(img_tag)
            own_caption = None
            if i + 1 < n:
                nxt = children[i + 1]
                if isinstance(nxt, Tag) and nxt.name == "p":
                    text = paragraph_md(nxt)
                    if text and not _DIVIDER_ONLY_RE.match(text):
                        own_caption = text
                    i += 1
            if pending_intro:
                caption = f"{pending_intro}\n\n{own_caption}" if own_caption else pending_intro
                pending_intro = None
            else:
                caption = own_caption
            if src:
                pairs.append((src, caption))
        elif isinstance(node, Tag) and node.name == "p":
            text = paragraph_md(node)
            if text and not _DIVIDER_ONLY_RE.match(text):
                pending_intro = f"{pending_intro}\n\n{text}" if pending_intro else text
        i += 1

    return pairs


def group_by_date(pairs: list[tuple[str, str | None]]) -> dict[str, list[ImageResource]]:
    """Compute a date for every (src, caption) pair -- caption text
    first, then the media filename's own embedded date, then simple
    carry-forward from the previous photo's date -- and group into one
    list per resulting ISO date."""
    groups: dict[str, list[ImageResource]] = {}
    last_date: str | None = None
    for src, caption in pairs:
        date = parse_sv_caption_date(caption) if caption else None
        if not date:
            date = parse_filename_date(Path(src).stem)
        if not date:
            date = last_date
        if not date:
            print(f"  WARNING: no date parseable (caption or filename) for {src!r}, skipping")
            continue
        last_date = date
        groups.setdefault(date, []).append(ImageResource(src=src, caption=caption))
    return groups


def _resolve(images: list[ImageResource]) -> tuple[list[ImageResource], dict[str, Path]]:
    resolved: list[ImageResource] = []
    media_paths: dict[str, Path] = {}
    for img in images:
        stem = Path(img.src).stem
        chosen = find_media(MEDIA_DIR, stem)
        if chosen is None:
            print(f"  WARNING: no media match for stem {stem!r} (from {img.src})")
            continue
        resolved.append(ImageResource(src=chosen.name, caption=img.caption))
        media_paths[chosen.name] = chosen
    return resolved, media_paths


def process_flat_year(year: int, dry_run: bool) -> int:
    html_path = SRC_BILDER / FLAT_YEAR_PAGES[year]
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    pairs = extract_dated_pairs(soup)
    groups = group_by_date(pairs)

    if year == 2020:
        # Fold in the one salvageable still image from the orphaned,
        # unlinked ivan/20200725-ah-3045.html page (a broken embedded
        # video with no real ImageElement of its own) -- same real-world
        # date as this bundle, rather than inventing a separate
        # near-empty gallery for it. See parse_sandvox_grid.get_orphan_thumbnail.
        orphan = get_orphan_thumbnail()
        if orphan is not None:
            img, media_path = orphan
            groups.setdefault("2020-07-25", []).append(img)
            print(f"  folding in orphan thumbnail {img.src} (from ivan/20200725-ah-3045.html) into 2020-07-25")

    count = 0
    for date, images in sorted(groups.items()):
        resolved_images, media_paths = _resolve(images)
        if not resolved_images:
            continue
        bundle = PageBundle(
            slug_path=OUT_IVAN / "bilder" / str(year) / date,
            title=date,
            date=date,
            draft=False,
            layout="gallery",
            images=resolved_images,
        )
        if dry_run:
            print(f"[dry-run] bilder/{year} ({date}) -> {bundle.slug_path.relative_to(ROOT)} "
                  f"({len(resolved_images)} image(s))")
        else:
            path = write_bundle(bundle, media_paths)
            print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
        count += 1
    return count


def process_micke(dry_run: bool) -> int:
    """ivan/bilder/micke.html -> content/ivan/bilder/micke/, one undated
    gallery bundle, captions dropped (they're just the filename echoed
    back, not real captions -- see module docstring)."""
    html_path = SRC_BILDER / "micke.html"
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    content = get_content_div(soup)
    if content is None:
        print("  WARNING: could not find content div in bilder/micke.html")
        return 0

    # Collect every photo element in document order regardless of DOM
    # nesting -- one caption <p> in this page has an image embedded
    # *inside* it (a Sandvox editing artifact, same kind seen in cina's
    # tidigare-produktion.html), which would confuse a strict top-level
    # sibling walk. Since captions are discarded anyway here, a flat
    # find_all() sidesteps that entirely. Skip a plain <img> that's
    # nested inside a data-img-src-hr <span> -- that's just the
    # <noscript> low-res fallback for the same photo the span itself
    # already represents (via extract_img_src's data-img-src-hr
    # preference), not a second distinct photo.
    def _is_top_level_photo_tag(tag) -> bool:
        if not _is_photo_tag(tag):
            return False
        if tag.name == "img" and tag.find_parent(lambda t: t.name == "span" and t.get("data-img-src-hr")):
            return False
        return True

    photo_tags = content.find_all(_is_top_level_photo_tag)
    images: list[ImageResource] = []
    seen_src: set[str] = set()
    for tag in photo_tags:
        src = extract_img_src(tag)
        if not src or src in seen_src:
            continue
        seen_src.add(src)
        images.append(ImageResource(src=src, caption=None))

    resolved_images, media_paths = _resolve(images)
    bundle = PageBundle(
        slug_path=OUT_IVAN / "bilder" / "micke",
        title="Micke",
        date=None,
        draft=False,
        layout="gallery",
        images=resolved_images,
    )
    if dry_run:
        print(f"[dry-run] bilder/micke.html -> {bundle.slug_path.relative_to(ROOT)} "
              f"({len(resolved_images)} image(s), no captions)")
        return 1
    path = write_bundle(bundle, media_paths)
    print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
    return 1


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    dry_run = "--dry-run" in sys.argv

    total_bundles = 0
    for year in sorted(FLAT_YEAR_PAGES):
        print(f"== bilder/{FLAT_YEAR_PAGES[year]} (year {year}) ==")
        n = process_flat_year(year, dry_run)
        print(f"  {n} date gallery(ies)")
        total_bundles += n

    print()
    print("== bilder/micke.html ==")
    n_micke = process_micke(dry_run)
    total_bundles += n_micke

    print()
    print(f"{total_bundles} gallery bundle(s) total across bilder/2015-2020 + micke"
          f"{' (dry run, nothing written)' if dry_run else ''}")


if __name__ == "__main__":
    main()
