"""HEIC/HEIF image conversion helpers."""

import io
import os
from pathlib import Path

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False


_DEFAULT_QUALITY = 95


def _env_quality() -> int:
    raw = os.getenv("LOCAL_PHOTO_AGENT_HEIC_JPEG_QUALITY")
    if raw is None:
        return _DEFAULT_QUALITY
    try:
        q = int(raw)
        return max(1, min(100, q))
    except (ValueError, TypeError):
        return _DEFAULT_QUALITY


def validate_heic_integrity(image_path: str | Path) -> bool:
    """Check if a HEIC/HEIF file has a valid signature and minimum size.

    Returns True if the file appears structurally sound, False otherwise.
    """
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return False
    try:
        size = path.stat().st_size
        if size < 12:
            return False
        with open(path, "rb") as f:
            header = f.read(12)
        if len(header) < 12:
            return False
        if header[4:8] != b"ftyp":
            return False
        return header[8:12] in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1")
    except OSError:
        return False


def convert_heic_to_jpeg_bytes(image_path: str | Path, quality: int | None = None) -> bytes:
    """
    Convert a HEIC/HEIF image to JPEG bytes.

    Requires Pillow and pillow-heif. Raises RuntimeError if either is missing.
    """
    if quality is None:
        quality = _env_quality()

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if not PIL_AVAILABLE:
        raise RuntimeError("HEIC/HEIF support requires Pillow. Install it: pip install pillow")
    if not HEIF_AVAILABLE:
        raise RuntimeError("HEIC/HEIF support requires pillow-heif. Install it: pip install pillow-heif")

    with Image.open(path) as img:
        exif = img.info.get("exif")
        icc_profile = img.info.get("icc_profile")

        rgb_img = img.convert("RGB")
        buffer = io.BytesIO()

        save_kwargs = {"format": "JPEG", "quality": quality}
        if exif:
            save_kwargs["exif"] = exif
        if icc_profile:
            save_kwargs["icc_profile"] = icc_profile

        rgb_img.save(buffer, **save_kwargs)
        return buffer.getvalue()
