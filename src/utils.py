import base64

from plugins.formats import read_image_bytes


def encode_image_file(image_path: str) -> str:
    """Read an image file via the format plugin system and return its base64 string."""
    raw = read_image_bytes(image_path)
    return base64.b64encode(raw).decode("utf-8")


def compute_duration_stats(durations: list[float]) -> dict[str, float]:
    """Calculate min/max/avg/total duration statistics from a list of millisecond values.

    Args:
        durations: List of per-image processing times in milliseconds.

    Returns:
        A dict with keys ``min_ms``, ``max_ms``, ``avg_ms``, ``total_s``.
        Returns zeros for an empty list.
    """
    if not durations:
        return {"min_ms": 0.0, "max_ms": 0.0, "avg_ms": 0.0, "total_s": 0.0}
    return {
        "min_ms": min(durations),
        "max_ms": max(durations),
        "avg_ms": sum(durations) / len(durations),
        "total_s": sum(durations) / 1000.0,
    }
