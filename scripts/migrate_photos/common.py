"""Shared helpers for the one-off legacy-site -> Hugo content migration
scripts in scripts/migrate_photos/.

Not part of the `hugo --minify` build. See README.md in this directory.
"""
from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------

_SLUG_SUBS = {
    "å": "a", "ä": "a", "ö": "o",
    "Å": "a", "Ä": "a", "Ö": "o",
    "é": "e", "É": "e",
    "ü": "u", "Ü": "u",
}


def slugify(text: str) -> str:
    """Lowercase, ASCII-ish, hyphenated slug. Swedish-aware (åäö -> aao)."""
    text = text.strip()
    for src, dst in _SLUG_SUBS.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "untitled"


# ---------------------------------------------------------------------------
# Swedish date parsing
# ---------------------------------------------------------------------------

_SV_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}

_TIMESTAMP_RE = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>[a-zA-Z]{3})\s+(?P<year>\d{4})"
    r"(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2}))?"
)


def parse_sv_timestamp(text: str) -> str | None:
    """Parse a Sandvox-style Swedish timestamp, e.g. "5 feb 2011 17:29",
    into an ISO date string "2011-02-05". Returns None if unparseable.
    """
    if not text:
        return None
    m = _TIMESTAMP_RE.search(text.strip())
    if not m:
        return None
    month = _SV_MONTHS.get(m.group("month").lower())
    if not month:
        return None
    day = int(m.group("day"))
    year = int(m.group("year"))
    return f"{year:04d}-{month:02d}-{day:02d}"


# ---------------------------------------------------------------------------
# Image variant selection
# ---------------------------------------------------------------------------

# Priority order for picking one canonical rendition of a photo when the
# legacy _Media library has several pre-generated sizes for the same stem
# (e.g. foo_med_hr.jpeg, foo_360.jpeg, foo_med.jpeg, foo_128_hr.jpeg...).
# Observed suffixes in masten/_Media vary per-photo; we do not assume every
# photo has every suffix, so this always falls back to *any* remaining
# match for that stem (first sorted) rather than failing.
VARIANT_PRIORITY = ["_med_hr", "", "_360", "_med"]


def find_media(media_dir: Path, stem: str) -> Path | None:
    """Find the best-available rendition of `stem` in `media_dir`.

    `stem` is matched case-insensitively against the filename stem (minus
    extension and any known size suffix). Returns the chosen Path, or None
    if nothing matches.
    """
    stem_lower = stem.lower()
    candidates: dict[str, Path] = {}
    for p in media_dir.iterdir():
        if not p.is_file():
            continue
        name_lower = p.stem.lower()  # filename without extension
        for suffix in VARIANT_PRIORITY:
            if name_lower == (stem_lower + suffix):
                candidates.setdefault(suffix, p)

    if not candidates:
        # Fall back to a loose prefix match, e.g. stem + "_128_hr" only.
        prefix = stem_lower + "_"
        loose = sorted(
            (p for p in media_dir.iterdir() if p.is_file() and p.stem.lower().startswith(prefix)),
            key=lambda p: p.name,
        )
        return loose[0] if loose else None

    for suffix in VARIANT_PRIORITY:
        if suffix in candidates:
            return candidates[suffix]
    # Shouldn't happen given the loop above always seeds "" or a known
    # suffix, but be defensive.
    return sorted(candidates.values(), key=lambda p: p.name)[0]


# ---------------------------------------------------------------------------
# YAML front matter (hand-rolled: avoids adding a PyYAML dependency for a
# handful of predictable field shapes)
# ---------------------------------------------------------------------------


def _yaml_scalar(value: str) -> str:
    # Double-quoted YAML scalars can't contain a literal, unescaped
    # newline (or backslash) -- multi-paragraph captions (e.g. cina's
    # "Beskrivning av tavlan" outlier) need these escaped or the emitted
    # front matter is invalid YAML. Order matters: backslashes first, so
    # we don't double-escape the backslashes just introduced below.
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\r\n", "\\n").replace("\n", "\\n")
    return f'"{value}"'


@dataclass
class ImageResource:
    src: str
    caption: str | None = None


@dataclass
class PageBundle:
    slug_path: Path  # directory under content/, e.g. content/masten/second-hand/resultat/kazakstan
    title: str
    date: str | None = None
    draft: bool = False
    layout: str | None = None  # "gallery" to opt into layouts/_default/gallery.html, "painting" for single-image entries
    body: str = ""
    images: list[ImageResource] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    caption: str | None = None  # page-level raw caption (painting bundles: 100% fidelity, hybrid caption decision)
    params: dict[str, str] = field(default_factory=dict)  # page-level params, e.g. painting motif/size/owner/medium


def write_front_matter(fm_lines: list[str], bundle: PageBundle) -> None:
    fm_lines.append(f"title: {_yaml_scalar(bundle.title)}")
    if bundle.date:
        fm_lines.append(f"date: {bundle.date}")
    if bundle.layout:
        fm_lines.append(f"layout: {bundle.layout}")
    fm_lines.append(f"draft: {'true' if bundle.draft else 'false'}")
    if bundle.aliases:
        fm_lines.append("aliases:")
        for a in bundle.aliases:
            fm_lines.append(f'  - "{a}"')
    if bundle.caption:
        fm_lines.append(f"caption: {_yaml_scalar(bundle.caption)}")
    if bundle.params:
        fm_lines.append("params:")
        for key, value in bundle.params.items():
            fm_lines.append(f"  {key}: {_yaml_scalar(value)}")
    if bundle.images:
        fm_lines.append("resources:")
        for img in bundle.images:
            fm_lines.append(f'  - src: "{img.src}"')
            if img.caption:
                cap = _yaml_scalar(img.caption)
                fm_lines.append(f"    title: {cap}")
                fm_lines.append("    params:")
                fm_lines.append(f"      caption: {cap}")


def write_bundle(bundle: PageBundle, media_paths: dict[str, Path]) -> Path:
    """Write index.sv.md + copy image files for a page bundle. Idempotent:
    safe to re-run (overwrites the markdown, re-copies images).

    `media_paths` maps each ImageResource.src -> source Path to copy from.
    """
    bundle.slug_path.mkdir(parents=True, exist_ok=True)

    for img in bundle.images:
        src_path = media_paths.get(img.src)
        if src_path is None:
            continue
        dest = bundle.slug_path / img.src
        if not dest.exists() or dest.stat().st_size != src_path.stat().st_size:
            shutil.copyfile(src_path, dest)

    fm_lines: list[str] = ["---"]
    write_front_matter(fm_lines, bundle)
    fm_lines.append("---")
    content = "\n".join(fm_lines) + "\n"
    if bundle.body.strip():
        content += "\n" + bundle.body.strip() + "\n"

    index_path = bundle.slug_path / "index.sv.md"
    index_path.write_text(content, encoding="utf-8")
    return index_path
