"""Parse Sandvox "PhotoGridIndex" bare one-page-per-photo galleries into
Hugo page bundles:

- ivan/bilder/2015/{januari,februari}/*.html -> one gallery bundle per
  month under content/ivan/bilder/2015/<month>/ (no captions -- these
  pages never had any, just a bare image + camera-native filename title).
- ivan/till-marita/*.html -> one gallery bundle under
  content/ivan/till-marita/<date>/ (date parsed straight from each
  page's YYYYMMDD-NNNN[.suffix] filename; grouped defensively rather
  than hardcoded to a single date -- see README).
- ivan/20200725-ah-3045.html -- a stray, unlinked orphan page shaped
  like a bare PhotoGridIndex entry, except its RichTextElement contains
  a broken Sandvox VideoElement (no playable embed survives static
  export) rather than an ImageElement. get_orphan_thumbnail() below
  extracts the one still-image asset that *does* exist for it (the
  video's poster-frame JPEG, 20200725-ah-3045-2.jpeg) so
  parse_sandvox_flatyear.py can fold it into the 2020-07-25 gallery
  bundle produced from bilder/2020.html (same real-world date, and that
  bundle already exists) instead of losing the only visible asset for
  this page silently. See README.md for the full writeup of this
  decision.

One-off migration tool, not part of the `hugo --minify` build. See
README.md in this directory. Safe to re-run (idempotent): re-running
overwrites the generated index.sv.md files and re-copies images.

Usage:
    python scripts/migrate_photos/parse_sandvox_grid.py [--dry-run]
"""
from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from common import (  # noqa: E402
    ImageResource,
    PageBundle,
    extract_img_src,
    find_media,
    parse_filename_date,
    write_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
SRC_IVAN = ROOT / "ivan"
MEDIA_DIR = SRC_IVAN / "_Media"
OUT_IVAN = ROOT / "content" / "ivan"

_SV_MONTH_NAMES = {"januari": "Januari", "februari": "Februari"}


def _photo_page_image(html_path: Path) -> ImageResource | None:
    """Scrape the single photo off a bare PhotoGridIndex leaf page (a
    015_13a.html / 20180815-5149.html-style page: one image, a
    prev/next pager, no caption text)."""
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    content = soup.select_one("div.article-content div.RichTextElement > div")
    if content is None:
        return None
    img_tag = content.find(lambda t: t.name == "img" or (t.name == "span" and t.get("data-img-src-hr")))
    src = extract_img_src(img_tag)
    if not src:
        return None
    return ImageResource(src=src, caption=None)


def _resolve(images: list[ImageResource]) -> tuple[list[ImageResource], dict[str, Path]]:
    resolved: list[ImageResource] = []
    media_paths: dict[str, Path] = {}
    for img in images:
        stem = Path(img.src).stem
        chosen = find_media(MEDIA_DIR, stem)
        if chosen is None:
            print(f"  WARNING: no media match for stem {stem!r} (from {img.src})")
            continue
        resolved.append(ImageResource(src=chosen.name, caption=None))
        media_paths[chosen.name] = chosen
    return resolved, media_paths


def process_2015_grid(dry_run: bool) -> int:
    """ivan/bilder/2015/{januari,februari}/ -> content/ivan/bilder/2015/<month>/,
    one bundle per month folder, no captions (source never had any)."""
    count = 0
    base = SRC_IVAN / "bilder" / "2015"
    for month_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        month_slug = month_dir.name  # "januari" / "februari", already URL-safe
        month_label = _SV_MONTH_NAMES.get(month_slug, month_slug.capitalize())
        images: list[ImageResource] = []
        for html_path in sorted(month_dir.glob("*.html")):
            if html_path.name == "index.html":
                continue
            img = _photo_page_image(html_path)
            if img is None:
                print(f"  WARNING: no image found in {html_path.relative_to(ROOT)}")
                continue
            images.append(img)
        if not images:
            continue
        resolved_images, media_paths = _resolve(images)
        month_num = {"januari": "01", "februari": "02"}.get(month_slug, "01")
        bundle = PageBundle(
            slug_path=OUT_IVAN / "bilder" / "2015" / month_slug,
            title=f"{month_label} 2015",
            date=f"2015-{month_num}-01",
            draft=False,
            layout="gallery",
            images=resolved_images,
        )
        if dry_run:
            print(f"[dry-run] bilder/2015/{month_slug}/ -> {bundle.slug_path.relative_to(ROOT)} "
                  f"({len(resolved_images)} image(s), no captions)")
        else:
            path = write_bundle(bundle, media_paths)
            print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
        count += 1
    return count


def process_till_marita(dry_run: bool) -> int:
    """ivan/till-marita/*.html -> content/ivan/till-marita/<date>/, grouped
    by the date embedded in each page's YYYYMMDD-NNNN[.suffix] filename
    (all 72 pages happen to share one date, 2018-08-15, but grouping is
    computed rather than hardcoded in case that's ever not true)."""
    base = SRC_IVAN / "till-marita"
    by_date: dict[str, list[ImageResource]] = {}
    for html_path in sorted(base.glob("*.html")):
        if html_path.name == "index.html":
            continue
        date = parse_filename_date(html_path.stem)
        if not date:
            print(f"  WARNING: no date parseable from {html_path.name}, skipping")
            continue
        img = _photo_page_image(html_path)
        if img is None:
            print(f"  WARNING: no image found in {html_path.relative_to(ROOT)}")
            continue
        by_date.setdefault(date, []).append(img)

    count = 0
    for date, images in sorted(by_date.items()):
        images.sort(key=lambda i: i.src)
        resolved_images, media_paths = _resolve(images)
        bundle = PageBundle(
            slug_path=OUT_IVAN / "till-marita" / date,
            title=date,
            date=date,
            draft=False,
            layout="gallery",
            images=resolved_images,
        )
        if dry_run:
            print(f"[dry-run] till-marita ({date}) -> {bundle.slug_path.relative_to(ROOT)} "
                  f"({len(resolved_images)} image(s), no captions)")
        else:
            path = write_bundle(bundle, media_paths)
            print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
        count += 1
    return count


def get_orphan_thumbnail() -> tuple[ImageResource, Path] | None:
    """Return (ImageResource, source-path) for the still-image asset
    salvageable from the orphaned, unlinked ivan/20200725-ah-3045.html
    page (a broken embedded-video page -- see module docstring). Used by
    parse_sandvox_flatyear.py to fold this photo into the 2020-07-25
    gallery bundle. Returns None if the media file can't be found."""
    # Use the "-2" stem specifically: find_media's exact-match priority
    # would otherwise happily match the (non-image) 20200725-ah-3045.mov
    # file, since its stem equals "20200725-ah-3045" with no suffix.
    chosen = find_media(MEDIA_DIR, "20200725-ah-3045-2")
    if chosen is None:
        print("  WARNING: 20200725-ah-3045 orphan thumbnail not found in _Media")
        return None
    return ImageResource(src=chosen.name, caption=None), chosen


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    dry_run = "--dry-run" in sys.argv

    print("== bilder/2015 (PhotoGridIndex, per-month) ==")
    n_2015 = process_2015_grid(dry_run)
    print()
    print("== till-marita (PhotoGridIndex, per-date) ==")
    n_marita = process_till_marita(dry_run)

    print()
    print(f"{n_2015} bilder/2015 month gallery(ies), {n_marita} till-marita date gallery(ies)"
          f"{' (dry run, nothing written)' if dry_run else ''}")


if __name__ == "__main__":
    main()
