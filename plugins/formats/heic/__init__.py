from plugins.formats.registry import register_format

from .converter import convert_heic_to_jpeg_bytes, validate_heic_integrity


def _read_heic(path):
    """Read a HEIC/HEIF file and return JPEG bytes via pillow-heif conversion.

    Runs integrity validation first. Raises ValueError if the file appears
    truncated or corrupted.
    """
    if not validate_heic_integrity(path):
        raise ValueError(f"HEIC/HEIF file appears truncated or corrupted: {path}")
    return convert_heic_to_jpeg_bytes(path)


register_format((".heic", ".heif"), _read_heic)
