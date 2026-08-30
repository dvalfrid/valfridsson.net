"""Parse masten/second-hand/fotografier/*.html and
masten/second-hand/resultat/*.html into Hugo page bundles under
content/masten/second-hand/{fotografier,resultat}/.

One-off migration tool, not part of the `hugo --minify` build. See
README.md in this directory. Safe to re-run (idempotent): re-running
overwrites the generated index.sv.md files and re-copies images.

Usage:
    python scripts/migrate_photos/parse_masten_gallery.py [--dry-run]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).parent))
from common import ImageResource, PageBundle, find_media, parse_sv_timestamp, slugify, write_bundle  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC_FOTO = ROOT / "masten" / "second-hand" / "fotografier"
SRC_RESULTAT = ROOT / "masten" / "second-hand" / "resultat"
MEDIA_DIR = ROOT / "masten" / "_Media"
OUT_FOTO = ROOT / "content" / "masten" / "second-hand" / "fotografier"
OUT_RESULTAT = ROOT / "content" / "masten" / "second-hand" / "resultat"

# Not linked from fotografier/index.html's nav list — an orphaned leftover
# revision with the same (empty) content as 2015-06-03-bilder-fran.html,
# just an older/stale timestamp. Dropped as a duplicate, not migrated.
SKIP_FOTO_FILES = {"bilder-fran-middag.html"}

_SUFFIX_RE = re.compile(r"(_med_hr|_med|_360|_\d+_hr|_\d+)$", re.IGNORECASE)
_DASH_ONLY_RE = re.compile(r"^[\s\-–—]*$")


def base_stem(filename: str) -> str:
    """Strip a size/variant suffix off a legacy media filename to recover
    the logical photo identifier, e.g. "handikap1405l_91_hr.jpeg" ->
    "handikap1405l"."""
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


def extract_title(soup: BeautifulSoup) -> str:
    span = soup.select_one("h2.title span.in")
    if span is None:
        return ""
    title = " ".join(span.get_text(" ", strip=True).split())
    # Sandvox sometimes splits a trailing "." into its own <a> tag right
    # after the linked title text, which get_text() turns into "Foo .".
    title = re.sub(r"\s+([.,])(\s|$)", r"\1\2", title).strip()
    return title


def extract_timestamp(soup: BeautifulSoup) -> str | None:
    ts = soup.select_one("div.timestamp.in span.in")
    if ts is None:
        return None
    return parse_sv_timestamp(ts.get_text(strip=True))


def extract_images_and_prose(soup: BeautifulSoup) -> tuple[list[ImageResource], str, str]:
    """Walk the article-content div and pull out (images-with-captions,
    leading-prose, trailing-prose). A paragraph immediately following an
    <img> is treated as that image's caption unless it's empty/dash-only,
    in which case the image gets no caption."""
    content = soup.select_one("div.article-content div.RichTextElement > div")
    if content is None:
        return [], "", ""

    images: list[ImageResource] = []
    leading_parts: list[str] = []
    trailing_parts: list[str] = []
    seen_image = False

    children = [c for c in content.children if isinstance(c, Tag) or (isinstance(c, NavigableString) and c.strip())]

    i = 0
    while i < len(children):
        node = children[i]
        if isinstance(node, Tag) and node.name == "img":
            img_tag = node
        elif isinstance(node, Tag):
            img_tag = node.find("img")
        else:
            img_tag = None

        if img_tag is not None and img_tag.get("src"):
            seen_image = True
            src_name = Path(img_tag["src"]).name
            caption = None
            if i + 1 < len(children):
                nxt = children[i + 1]
                if isinstance(nxt, Tag) and nxt.name == "p":
                    text = paragraph_md(nxt)
                    if text and not _DASH_ONLY_RE.match(text):
                        caption = text
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
    """Re-point each ImageResource at the canonical (best-variant) media
    file, and build the src-name -> source-path map write_bundle needs."""
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


def process_fotografier(dry_run: bool) -> int:
    count = 0
    for html_path in sorted(SRC_FOTO.glob("*.html")):
        if html_path.name in SKIP_FOTO_FILES or html_path.name == "index.html":
            continue
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        title = extract_title(soup)
        date = extract_timestamp(soup)
        if not date:
            print(f"  WARNING: no parseable timestamp in {html_path.name}, skipping")
            continue
        images, leading, trailing = extract_images_and_prose(soup)
        resolved_images, media_paths = resolve_media(images)

        body_parts = [p for p in (leading, trailing) if p]
        bundle = PageBundle(
            slug_path=OUT_FOTO / date,
            title=title,
            date=date,
            draft=False,
            layout="gallery" if resolved_images else None,
            body="\n\n".join(body_parts),
            images=resolved_images,
        )
        if dry_run:
            print(f"[dry-run] {html_path.name} -> {bundle.slug_path.relative_to(ROOT)} "
                  f"(title={title!r}, date={date}, images={len(resolved_images)})")
        else:
            path = write_bundle(bundle, media_paths)
            print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
        count += 1
    return count


def process_resultat(dry_run: bool) -> int:
    count = 0
    for html_path in sorted(SRC_RESULTAT.glob("*.html")):
        if html_path.name == "index.html":
            continue
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        title = extract_title(soup)
        if not title:
            continue
        img_tag = soup.select_one("div.article-content img")
        images: list[ImageResource] = []
        if img_tag is not None and img_tag.get("src"):
            images.append(ImageResource(src=Path(img_tag["src"]).name, caption=None))
        resolved_images, media_paths = resolve_media(images)

        slug = slugify(title)
        bundle = PageBundle(
            slug_path=OUT_RESULTAT / slug,
            title=title,
            date=None,
            draft=False,
            layout="gallery" if resolved_images else None,
            body="",
            images=resolved_images,
        )
        if dry_run:
            print(f"[dry-run] {html_path.name} -> {bundle.slug_path.relative_to(ROOT)} "
                  f"(title={title!r}, images={len(resolved_images)})")
        else:
            path = write_bundle(bundle, media_paths)
            print(f"  wrote {path.relative_to(ROOT)} ({len(resolved_images)} image(s))")
        count += 1
    return count


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    dry_run = "--dry-run" in sys.argv
    print("== fotografier ==")
    n_foto = process_fotografier(dry_run)
    print("== resultat ==")
    n_res = process_resultat(dry_run)
    print(f"\n{n_foto} fotografier entries, {n_res} resultat entries"
          f"{' (dry run, nothing written)' if dry_run else ''}")


if __name__ == "__main__":
    main()
