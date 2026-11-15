"""UI component builders for the Local Photo Agent web UI.

This package contains focused builders for each UI surface:
- ``preview``           — shared /preview URL helper
- ``detail_modal``      — photo detail modal content
- ``similar_carousel``  — similar-photos carousel
- ``fullscreen_viewer`` — fullscreen photo viewer content
- ``errors_display``    — errors panel
- ``chat_interface``    — chat input/response card
"""

from .chat_interface import build_chat_interface
from .detail_modal import build_detail_modal_content
from .errors_display import build_errors_display
from .fullscreen_viewer import build_fullscreen_viewer
from .preview import _preview_url
from .similar_carousel import build_similar_photos_carousel

__all__ = [
    "_preview_url",
    "build_chat_interface",
    "build_detail_modal_content",
    "build_errors_display",
    "build_fullscreen_viewer",
    "build_similar_photos_carousel",
]
