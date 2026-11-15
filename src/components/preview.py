"""Shared preview URL builder."""

from urllib.parse import quote


def _preview_url(path: str, folder: str, size: str = "thumb") -> str:
    """Return a URL for the /preview server route."""
    return f"/preview?path={quote(path)}&folder={quote(folder)}&size={size}"
