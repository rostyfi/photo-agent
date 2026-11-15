"""Chat callbacks — re-export shim.

The chat callbacks have been split into focused sub-modules:
- ``chat_send``   — send / stream / clear / endpoint-test
- ``chat_render`` — history-to-UI rendering and gallery builders
- ``chat_nav``    — scroll and keyboard navigation (clientside)
- ``chat_tags``   — tag click / clear / remove callbacks
- ``chat_sort``   — gallery sort callback

This module re-exports everything so existing imports
(``from src.callbacks.chat import ...``) keep working.
"""

from .chat_nav import register_chat_history_navigation_callback, register_chat_scroll_callback
from .chat_render import (
    _build_gallery_grid,
    _build_gallery_items,
    _build_gallery_sort_dropdown,
    _build_slideshow_button,
    _decode_path,
    _history_to_messages,
    _order_button,
    _order_from_children,
    _slideshow_threshold_for,
    _thinking_block,
    register_chat_history_init_callback,
)
from .chat_send import (
    _call_chat_endpoint,
    register_chat_callback,
    register_chat_endpoint_test_callback,
    register_chat_stream_callback,
    register_clear_chat_callback,
)
from .chat_sort import register_gallery_sort_callback
from .chat_tags import (
    register_chat_tag_clear_callback,
    register_chat_tag_click_callback,
    register_chat_tag_remove_callback,
)

__all__ = [
    "_build_gallery_grid",
    "_build_gallery_items",
    "_build_gallery_sort_dropdown",
    "_build_slideshow_button",
    "_call_chat_endpoint",
    "_decode_path",
    "_history_to_messages",
    "_order_button",
    "_order_from_children",
    "_slideshow_threshold_for",
    "_thinking_block",
    "register_chat_callback",
    "register_chat_endpoint_test_callback",
    "register_chat_history_init_callback",
    "register_chat_history_navigation_callback",
    "register_chat_scroll_callback",
    "register_chat_stream_callback",
    "register_chat_tag_clear_callback",
    "register_chat_tag_click_callback",
    "register_chat_tag_remove_callback",
    "register_clear_chat_callback",
    "register_gallery_sort_callback",
]
