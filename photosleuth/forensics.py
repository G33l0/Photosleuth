"""Forensic checks: embedded-thumbnail comparison and perceptual hashing.

The headline check is *thumbnail-vs-image mismatch*.  Cameras embed a small
JPEG preview when the photo is taken.  Many editors update the pixels but leave
the original thumbnail behind, so a preview that no longer matches the full
image is a strong hint that the photo was cropped, rotated or retouched after
capture.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PIL import Image, ImageChops
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("Missing 'Pillow'. Install: pip install Pillow") from exc

try:
    import exifread
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("Missing 'exifread'. Install: pip install exifread") from exc

logging.getLogger("exifread").setLevel(logging.CRITICAL)

# Hamming distance on a 64-bit dHash.  Below LIKELY_MATCH the thumbnail clearly
# comes from the same picture; above LIKELY_MISMATCH it clearly does not.
LIKELY_MATCH = 10
LIKELY_MISMATCH = 22

# Editors that commonly rewrite pixels; seeing one is corroborating evidence.
EDITOR_HINTS = (
    "photoshop", "lightroom", "gimp", "affinity", "paint.net", "pixelmator",
    "snapseed", "picsart", "facetune", "capture one", "luminar", "darktable",
    "canva", "figma", "corel", "imagemagick",
)


@dataclass
class ThumbnailCheck:
    """Outcome of comparing an embedded thumbnail with the full image."""

    has_thumbnail: bool = False
    distance: Optional[int] = None
    thumbnail_size: Optional[tuple] = None
    image_size: Optional[tuple] = None
    aspect_delta: Optional[float] = None
    verdict: str = "no-thumbnail"
    confidence: str = "n/a"
    notes: List[str] = field(default_factory=list)

    @property
    def is_mismatch(self) -> bool:
        return self.verdict == "mismatch"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_thumbnail": self.has_thumbnail,
            "distance": self.distance,
            "thumbnail_size": list(self.thumbnail_size) if self.thumbnail_size else None,
            "image_size": list(self.image_size) if self.image_size else None,
            "aspect_delta": self.aspect_delta,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "notes": list(self.notes),
        }


def dhash(image: "Image.Image", size: int = 8) -> int:
    """64-bit difference hash: robust to scaling and mild compression."""
    grey = image.convert("L").resize((size + 1, size), Image.LANCZOS)
    pixels = grey.tobytes()
    bits = 0
    for row in range(size):
        offset = row * (size + 1)
        for col in range(size):
            bits <<= 1
            if pixels[offset + col] > pixels[offset + col + 1]:
                bits |= 1
    return bits


def ahash(image: "Image.Image", size: int = 8) -> int:
    """Average hash - a useful second opinion alongside dhash."""
    grey = image.convert("L").resize((size, size), Image.LANCZOS)
    pixels = grey.tobytes()
    mean = sum(pixels) / len(pixels)
    bits = 0
    for pixel in pixels:
        bits = (bits << 1) | (1 if pixel >= mean else 0)
    return bits


def hamming(left: int, right: int) -> int:
    return bin(left ^ right).count("1")


def hash_hex(value: int, bits: int = 64) -> str:
    return f"{value:0{bits // 4}x}"


def extract_embedded_thumbnail(image_path) -> Optional[bytes]:
    """Return the raw bytes of the EXIF thumbnail, if the file carries one."""
    path = Path(image_path)
    try:
        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=True)
    except (OSError, ValueError, MemoryError):
        return None

    for key in ("JPEGThumbnail", "TIFFThumbnail"):
        blob = (tags or {}).get(key)
        if blob:
            if isinstance(blob, (bytes, bytearray)):
                return bytes(blob)
            values = getattr(blob, "values", None)
            if isinstance(values, (bytes, bytearray)):
                return bytes(values)
            if isinstance(values, list):
                try:
                    return bytes(values)
                except (TypeError, ValueError):
                    continue
    return None


def _orientation(image_path) -> int:
    try:
        with open(image_path, "rb") as handle:
            tags = exifread.process_file(handle, details=False)
        tag = (tags or {}).get("Image Orientation")
        values = getattr(tag, "values", None) if tag else None
        return int(values[0]) if values else 1
    except Exception:
        return 1


def compare_thumbnail(image_path, metadata: Optional[Dict[str, Any]] = None) -> ThumbnailCheck:
    """Compare the embedded thumbnail against the full image."""
    result = ThumbnailCheck()
    path = Path(image_path)

    blob = extract_embedded_thumbnail(path)
    if not blob:
        result.notes.append("No embedded thumbnail to compare against.")
        return result

    result.has_thumbnail = True

    try:
        with Image.open(io.BytesIO(blob)) as thumbnail:
            thumbnail.load()
            result.thumbnail_size = thumbnail.size
            thumb_hash = dhash(thumbnail)
            thumb_ahash = ahash(thumbnail)
    except Exception as exc:
        result.verdict = "unreadable"
        result.notes.append(f"Embedded thumbnail could not be decoded: {exc}")
        return result

    try:
        with Image.open(path) as image:
            image.load()
            result.image_size = image.size
            # The thumbnail is stored pre-rotation; match the full image to it.
            oriented = image
            if _orientation(path) in (6, 8, 5, 7):
                oriented = image.rotate(90, expand=True)
            full_hash = dhash(oriented)
            full_ahash = ahash(oriented)
            alt_hash = dhash(image)
    except Exception as exc:
        result.verdict = "unreadable"
        result.notes.append(f"Image could not be decoded: {exc}")
        return result

    distance = min(hamming(thumb_hash, full_hash), hamming(thumb_hash, alt_hash))
    result.distance = distance
    average_distance = hamming(thumb_ahash, full_ahash)

    if result.thumbnail_size and result.image_size:
        thumb_ratio = result.thumbnail_size[0] / max(1, result.thumbnail_size[1])
        image_ratio = result.image_size[0] / max(1, result.image_size[1])
        result.aspect_delta = round(abs(thumb_ratio - image_ratio), 4)
        if result.aspect_delta > 0.06:
            result.notes.append(
                f"Aspect ratio differs (thumbnail {thumb_ratio:.2f} vs image {image_ratio:.2f}) "
                "- consistent with cropping."
            )

    if distance <= LIKELY_MATCH:
        result.verdict = "match"
        result.confidence = "high" if distance <= 6 else "medium"
        result.notes.append("Thumbnail matches the image; no evidence of post-capture editing here.")
    elif distance >= LIKELY_MISMATCH:
        result.verdict = "mismatch"
        result.confidence = "high" if distance >= 28 and average_distance >= 20 else "medium"
        result.notes.append(
            f"Thumbnail does not match the image (difference {distance}/64). "
            "The picture was probably altered after it was taken."
        )
    else:
        result.verdict = "inconclusive"
        result.confidence = "low"
        result.notes.append(
            f"Thumbnail is a partial match (difference {distance}/64). "
            "Heavy recompression can cause this on its own."
        )

    software = ""
    if metadata:
        exif = metadata.get("exif") or {}
        software = str(exif.get("Image Software") or exif.get("EXIF Software") or "")
    if software:
        lowered = software.lower()
        if any(hint in lowered for hint in EDITOR_HINTS):
            result.notes.append(f"EXIF names an image editor: {software}")
            if result.verdict == "inconclusive":
                result.confidence = "medium"

    return result


def file_hashes(image_path, algorithms=("sha256",)) -> Dict[str, str]:
    """Hash a file in chunks so large images do not have to fit in memory."""
    import hashlib

    digests = {name: hashlib.new(name) for name in algorithms}
    with open(image_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            for digest in digests.values():
                digest.update(chunk)
    return {name: digest.hexdigest() for name, digest in digests.items()}


def perceptual_fingerprint(image_path) -> Dict[str, str]:
    """dHash + aHash of the visible pixels, for duplicate spotting."""
    with Image.open(image_path) as image:
        image.load()
        return {"dhash": hash_hex(dhash(image)), "ahash": hash_hex(ahash(image))}


def analyze(image_path, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run every forensic check and return a serialisable summary."""
    path = Path(image_path)
    report: Dict[str, Any] = {"file": str(path), "name": path.name}

    check = compare_thumbnail(path, metadata)
    report["thumbnail_check"] = check.to_dict()

    try:
        report["hashes"] = file_hashes(path, ("md5", "sha256"))
    except OSError as exc:
        report["hashes"] = {}
        report.setdefault("errors", []).append(str(exc))

    try:
        report["fingerprint"] = perceptual_fingerprint(path)
    except Exception as exc:  # noqa: BLE001 - a non-image must not break the report
        report["fingerprint"] = {}
        report.setdefault("errors", []).append(str(exc))

    flags: List[str] = []
    if check.is_mismatch:
        flags.append("Embedded thumbnail does not match the image")
    exif = (metadata or {}).get("exif") or {}
    software = str(exif.get("Image Software") or "")
    if software and any(hint in software.lower() for hint in EDITOR_HINTS):
        flags.append(f"Edited with {software}")
    if metadata and not metadata.get("has_exif"):
        flags.append("No EXIF metadata at all (stripped, screenshot, or re-encoded)")
    report["flags"] = flags
    report["verdict"] = check.verdict
    return report
