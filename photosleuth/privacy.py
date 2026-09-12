"""EXIF stripping: produce a copy of an image with its metadata removed."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from .config import load_config

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("Missing 'Pillow'. Install: pip install Pillow") from exc

# Formats Pillow can re-encode without metadata.
_REENCODABLE = {".jpg", ".jpeg", ".jpe", ".png", ".tif", ".tiff", ".webp", ".bmp"}


def default_output_path(image_path, suffix: Optional[str] = None) -> Path:
    """Build the '<name><suffix><ext>' path used for cleaned copies."""
    path = Path(image_path)
    if suffix is None:
        suffix = load_config().get("privacy", {}).get("output_suffix", "_clean")
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def strip_exif(
    image_path,
    output_path=None,
    overwrite: Optional[bool] = None,
    suffix: Optional[str] = None,
    quality: int = 95,
) -> Tuple[Path, int]:
    """Write a metadata-free copy of *image_path*.

    Returns ``(output_path, tags_removed_estimate)``.  When *overwrite* is true
    the original is replaced, but only after the clean copy is fully written,
    so an error can never destroy the source image.
    """
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"File not found: {source}")

    privacy = load_config().get("privacy", {})
    if overwrite is None:
        overwrite = bool(privacy.get("overwrite", False))

    if overwrite:
        destination = source
    elif output_path is not None:
        destination = Path(output_path)
    else:
        destination = default_output_path(source, suffix)

    if not overwrite and destination.resolve() == source.resolve():
        raise ValueError("Output path matches the source; pass overwrite=True to replace the original.")

    extension = source.suffix.lower()
    if extension not in _REENCODABLE:
        raise ValueError(
            f"Cannot strip metadata from '{extension or 'unknown'}' files. "
            f"Supported: {', '.join(sorted(_REENCODABLE))}"
        )

    before = _count_metadata(source)

    if destination.parent and not destination.parent.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file first so a failure leaves both source and any
    # existing destination untouched.
    handle = tempfile.NamedTemporaryFile(
        dir=str(destination.parent or "."), prefix=".clean-", suffix=source.suffix, delete=False
    )
    handle.close()
    temp_path = Path(handle.name)
    try:
        with Image.open(source) as image:
            image.load()
            image_format = image.format
            # Pasting the pixels into a fresh image drops EXIF, IPTC, XMP, ICC
            # profiles and GPS in one step: the new image carries no `info`.
            clean = Image.new(image.mode, image.size)
            clean.paste(image)
            save_kwargs = {}
            if extension in (".jpg", ".jpeg", ".jpe"):
                save_kwargs["quality"] = quality
            clean.save(temp_path, format=image_format or None, **save_kwargs)
        os.replace(temp_path, destination)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise

    return destination, before


def _count_metadata(path: Path) -> int:
    """Best-effort count of metadata tags present in *path*."""
    try:
        import exifread

        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=False)
        return len([t for t in (tags or {}) if t not in ("JPEGThumbnail", "TIFFThumbnail", "Filename")])
    except Exception:
        return 0


def has_sensitive_metadata(metadata: dict) -> bool:
    """True when the extracted metadata contains privacy-relevant fields."""
    if metadata.get("gps"):
        return True
    sensitive_prefixes = ("GPS ", "Image Artist", "Image Copyright", "EXIF DateTimeOriginal")
    return any(tag.startswith(sensitive_prefixes) for tag in (metadata.get("exif") or {}))


def backup_original(image_path, suffix: str = ".bak") -> Path:
    """Copy the original alongside itself before a destructive operation."""
    source = Path(image_path)
    backup = source.with_name(source.name + suffix)
    counter = 1
    while backup.exists():
        backup = source.with_name(f"{source.name}{suffix}{counter}")
        counter += 1
    shutil.copy2(source, backup)
    return backup
