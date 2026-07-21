import logging
import mimetypes
from importlib import import_module
from pathlib import Path
from typing import Optional, Union

from plugins.formats.registry import get_reader

logger = logging.getLogger(__name__)


_readers_imported = False


def _ensure_plugins_loaded():
    """Auto-discover and import format plugin sub-packages under plugins.formats."""
    global _readers_imported
    if _readers_imported:
        return
    _readers_imported = True

    import plugins.formats
    import pkgutil
    for _, name, is_pkg in pkgutil.iter_modules(plugins.formats.__path__, plugins.formats.__name__ + "."):
        if is_pkg:
            try:
                import_module(name)
            except Exception:
                logger.warning("Failed to load format plugin %s", name, exc_info=True)


def _detect_extension_by_magic(path: Path) -> Optional[str]:
    """Try to determine the image file extension from magic bytes in the header.

    Returns a lowercase extension (e.g. ``'.jpg'``) or None if unrecognised.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(12)
    except OSError:
        return None

    if header[:2] == b"\xff\xd8\xff":
        return ".jpg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if header[:2] == b"BM":
        return ".bmp"
    if header[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    if header[4:8] == b"ftyp":
        # ISO base media file format (HEIC/HEIF)
        if b"heic" in header[8:].lower():
            return ".heic"
        if b"heif" in header[8:].lower():
            return ".heif"

    return None


def read_image_bytes(image_path: Union[str, Path]) -> bytes:
    """Read an image file into raw bytes, dispatching through the plugin registry.

    Falls back to raw binary read if the format is not recognised.
    Raises FileNotFoundError if the path does not exist.
    """
    _ensure_plugins_loaded()

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = path.suffix.lower()
    reader = get_reader(suffix)
    if reader is not None:
        return reader(path)

    # Extension-based lookup failed, try MIME-type detection
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type and mime_type.startswith("image/"):
        ext = mimetypes.guess_extension(mime_type)
        if ext:
            reader = get_reader(ext.lower())
            if reader is not None:
                return reader(path)

    # Content-based detection via magic bytes
    magic_ext = _detect_extension_by_magic(path)
    if magic_ext:
        reader = get_reader(magic_ext)
        if reader is not None:
            return reader(path)

    with open(path, "rb") as f:
        return f.read()
