"""Rendering helpers for chat history entries into Dash UI components.

This module contains the pure functions that convert chat history entries
(text, photos, tags, photos_and_tags, errors, loading) into Dash HTML
components, plus the gallery/slideshow builders used by both the history
renderer and the gallery-sort callback.
"""

import json
import logging
from urllib.parse import quote

import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html

from src.constants import (
    DEFAULT_SLIDESHOW_THRESHOLD,
    SORT_KEY_RELEVANCE,
    SORT_OPTIONS,
    SORT_ORDER_ASC,
    SORT_ORDER_DESC,
    default_order_for,
)

logger = logging.getLogger(__name__)


# Arrow glyphs shown by the order toggle button. ``\u25b2`` is an up arrow
# (ascending), ``\u25bc`` a down arrow (descending).
_ORDER_ARROW = {SORT_ORDER_ASC: "\u25b2", SORT_ORDER_DESC: "\u25bc"}
_ORDER_TITLE = {SORT_ORDER_ASC: "Ascending", SORT_ORDER_DESC: "Descending"}


def _order_button(hist_idx: int, order: str) -> dbc.Button:
    """Build the asc/desc toggle button for a gallery or slideshow sort row."""
    return dbc.Button(
        _ORDER_ARROW.get(order, _ORDER_ARROW[SORT_ORDER_ASC]),
        id={"type": "sort-order", "index": hist_idx},
        color="secondary",
        size="sm",
        n_clicks=0,
        className="ms-2",
        title=_ORDER_TITLE.get(order, _ORDER_TITLE[SORT_ORDER_ASC]),
        style={"width": "38px", "padding": "0.25rem 0"},
    )


def _order_from_children(children) -> str:
    """Infer the current order (``asc``/``desc``) from a toggle button label."""
    glyph = children if isinstance(children, str) else ""
    for order, arrow in _ORDER_ARROW.items():
        if glyph == arrow:
            return order
    return SORT_ORDER_ASC


def _slideshow_threshold_for(folder: str | None) -> int:
    """Return the slideshow threshold for *folder*.

    Reads the per-folder ``settings.json``; falls back to the cached
    ``AppConfig`` value (env/default) when the folder has no stored setting
    or the value is missing/invalid. A negative value is treated as 0.
    """
    if folder:
        try:
            from src.folder_settings import KEY_SLIDESHOW_THRESHOLD, read_folder_settings

            raw = read_folder_settings(folder).get(KEY_SLIDESHOW_THRESHOLD)
            if raw is not None:
                try:
                    return max(0, int(raw))
                except (TypeError, ValueError):
                    pass
        except Exception:
            logger.debug("Could not read slideshow threshold for %s", folder, exc_info=True)
    try:
        from .common import _get_app_config

        return max(0, _get_app_config().slideshow_threshold)
    except Exception:
        return DEFAULT_SLIDESHOW_THRESHOLD


def _build_slideshow_button(hist_idx: int, count: int) -> html.Div:
    """Build the \u201cStart slideshow\u201d button shown in place of a large gallery.

    The button uses a pattern-matching id keyed by the chat history index so
    ``register_slideshow_open_callback`` can look up the matching history
    entry (and its photo paths) when the button is clicked. A sort dropdown
    sits next to the button so the ordering can be chosen before opening the
    slideshow; its value is read by the slideshow open callback.
    """
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Sort:", className="text-muted me-2", style={"fontSize": "0.85rem"}),
                    dcc.Dropdown(
                        id={"type": "slideshow-sort", "index": hist_idx},
                        options=SORT_OPTIONS,
                        value=SORT_KEY_RELEVANCE,
                        clearable=False,
                        style={"width": "180px"},
                        className="sort-dropdown d-inline-block",
                    ),
                    _order_button(hist_idx, default_order_for(SORT_KEY_RELEVANCE)),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                },
            ),
            dbc.Button(
                f"\u25b6 Start slideshow ({count} photos)",
                id={"type": "btn-start-slideshow", "index": hist_idx},
                color="primary",
                n_clicks=0,
                className="ms-2",
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "flexWrap": "wrap",
            "marginBottom": "10px",
        },
    )


def _build_gallery_sort_dropdown(hist_idx: int, slideshow_count: int | None = None) -> html.Div:
    """Build the sort dropdown shown above a preview gallery.

    When ``slideshow_count`` is given, also render a "Start slideshow" button
    so the user can open the fullscreen viewer with the full result set even
    when the preview gallery is shown (i.e. below the slideshow threshold).
    """
    children = [
        html.Span("Sort:", className="text-muted me-2", style={"fontSize": "0.85rem"}),
        dcc.Dropdown(
            id={"type": "gallery-sort", "index": hist_idx},
            options=SORT_OPTIONS,
            value=SORT_KEY_RELEVANCE,
            clearable=False,
            style={"width": "180px"},
            className="sort-dropdown d-inline-block",
        ),
        _order_button(hist_idx, default_order_for(SORT_KEY_RELEVANCE)),
    ]
    if slideshow_count is not None:
        children.append(
            dbc.Button(
                f"\u25b6 Start slideshow ({slideshow_count} photos)",
                id={"type": "btn-start-slideshow", "index": hist_idx},
                color="primary",
                n_clicks=0,
                className="ms-2",
            )
        )
    return html.Div(
        children,
        style={
            "display": "flex",
            "alignItems": "center",
            "flexWrap": "wrap",
            "marginTop": "10px",
            "marginBottom": "10px",
        },
    )


def _decode_path(img_path) -> str:
    """Decode a photo path (possibly bytes) to ``str``."""
    if isinstance(img_path, bytes):
        try:
            return img_path.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return img_path.decode("latin-1", errors="replace")
    if isinstance(img_path, str):
        return img_path
    return str(img_path)


def _build_gallery_items(photo_items: list, folder_str: str, hist_idx: int) -> list:
    """Build the list of thumbnail divs for a preview gallery.

    Handles both ``/find`` results (items carry ``score``) and ``/tag``
    results (items carry ``description``). Each thumbnail's pattern-matching
    id encodes ``{path, n}`` so the detail-modal callback can locate it.
    """
    gallery_items = []
    for photo_item in photo_items:
        if isinstance(photo_item, dict):
            img_path_str = _decode_path(photo_item.get("path", ""))
            score = photo_item.get("score")
            description = photo_item.get("description", "")
        else:
            img_path_str = _decode_path(photo_item)
            score = None
            description = ""

        preview_url = f"/preview?path={quote(img_path_str)}&folder={quote(folder_str)}&size=thumb"
        if score is not None:
            display_title = f"{img_path_str} (score: {score:.4f})"
        elif description:
            display_title = description[:50]
        else:
            display_title = img_path_str

        gallery_items.append(
            html.Div(
                [
                    html.Div(
                        html.Img(
                            src=preview_url,
                            style={
                                "width": "100%",
                                "height": "150px",
                                "objectFit": "cover",
                                "borderRadius": "4px",
                                "pointerEvents": "none",
                                "userSelect": "none",
                            },
                            className="img-fluid",
                            title=display_title,
                            draggable="false",
                        ),
                        id={
                            "type": "thumbnail",
                            "source": "chat",
                            "index": json.dumps({"path": img_path_str, "n": hist_idx}),
                        },
                        n_clicks=0,
                        style={"cursor": "pointer", "userSelect": "none", "overflow": "hidden"},
                    ),
                    html.Small(
                        [html.Span(display_title, className="text-muted", style={"fontSize": "0.75rem"})],
                        className="d-block text-center mt-1",
                    ),
                ],
                className="gallery-item mb-3",
                style={"cursor": "pointer"},
            )
        )
    return gallery_items


def _build_gallery_grid(photo_items: list, folder_str: str, hist_idx: int) -> html.Div:
    """Build the gallery grid container (with a targetable id) and its items."""
    return html.Div(
        _build_gallery_items(photo_items, folder_str, hist_idx),
        id={"type": "gallery-grid", "index": hist_idx},
        className="gallery-grid",
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fill, minmax(200px, 1fr))",
            "gap": "10px",
            "marginTop": "10px",
        },
    )


def _thinking_block(entry: dict):
    """Build a collapsible reasoning-trace block from a history entry.

    Returns ``None`` when the entry has no thinking content.
    """
    thinking = entry.get("thinking")
    if not thinking:
        return None
    return html.Details(
        [
            html.Summary(
                "Reasoning trace",
                style={"cursor": "pointer", "fontStyle": "italic", "color": "#adb5bd"},
            ),
            html.Span(
                str(thinking),
                style={"whiteSpace": "pre-wrap", "color": "#adb5bd", "fontSize": "0.9em"},
            ),
        ],
        style={"marginBottom": "6px", "opacity": "0.85"},
    )


def _history_to_messages(history: list, folder: str | bytes | None = None):
    """Convert history entries to display messages."""
    if history is None or len(history) == 0:
        return []

    messages = []
    for hist_idx, entry in enumerate(history):
        sender = entry.get("sender", "")
        content = entry.get("content", "")
        entry_type = entry.get("type", "text")

        if entry_type == "loading":
            messages.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(className="bounce1"),
                                html.Div(className="bounce2"),
                                html.Div(className="bounce3"),
                            ],
                            className="spinner-chat",
                            style={"display": "flex", "margin": "10px 0"},
                        ),
                    ],
                    style={"textAlign": "left", "marginBottom": "10px"},
                )
            )
        elif entry_type == "tags":
            tags = entry.get("tags", [])
            topic = entry.get("topic", None)
            text = entry.get("text", "")
            header = f"Tags related to '{topic}':" if topic else "All tags:"

            # Create clickable tag buttons
            tag_buttons = []
            for tag_info in tags:
                tag_name = tag_info.get("name", "")
                tag_count = tag_info.get("count", 0)
                tag_buttons.append(
                    dbc.Button(
                        f"{tag_name} ({tag_count})",
                        id={"type": "chat-tag-btn", "tag": tag_name},
                        color="primary",
                        size="sm",
                        className="me-2 mb-2",
                        n_clicks=0,
                    )
                )

            # When no tags match, show the explanatory text from the tool
            # instead of an empty button row.
            body = [html.Div(tag_buttons, style={"marginTop": "10px"})]
            if not tags and text:
                body = [html.Div(text, style={"marginTop": "10px", "whiteSpace": "pre-wrap"})]

            messages.append(
                html.Div(
                    [
                        html.Strong(f"Local Photo Agent: {header}"),
                        _thinking_block(entry),
                        *body,
                    ],
                    style={"textAlign": "left", "marginBottom": "10px"},
                )
            )
        elif entry_type == "photos_and_tags":
            photos = entry.get("photos", [])
            related_tags = entry.get("related_tags", [])
            entry.get("text", "")
            tag = entry.get("tag", "")
            total_photos = entry.get("total_photos", 0)
            selected_tags = entry.get("selected_tags", []) or ([tag] if tag else [])

            if isinstance(folder, bytes):
                try:
                    folder_str = folder.decode("utf-8")
                except (UnicodeDecodeError, AttributeError):
                    folder_str = folder.decode("latin-1", errors="replace")
            elif isinstance(folder, str):
                folder_str = folder
            else:
                folder_str = "."

            # Concise header; the thumbnail grid shows photos and the
            # buttons show related tags, so the markdown bullet lists in
            # ``text`` are redundant and are not rendered.
            label = ", ".join(selected_tags) if selected_tags else tag
            header = f"Photos with tag(s) '{label}' ({total_photos} total)"
            photo_header = html.Strong(f"Local Photo Agent: {header}")
            thinking = _thinking_block(entry)

            slideshow_threshold = _slideshow_threshold_for(folder_str)
            # ``photos`` is capped at 20 by the /tag tool; ``total_photos`` is
            # the full match count, so the threshold check and the slideshow
            # button label reflect every matching photo.
            slideshow_count = total_photos or len(photos)
            use_slideshow = slideshow_threshold > 0 and slideshow_count > slideshow_threshold

            if use_slideshow:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_slideshow_button(hist_idx, slideshow_count),
                    ],
                    style={"marginBottom": "20px"},
                )
                messages.append(photo_container)
            else:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_gallery_sort_dropdown(hist_idx, slideshow_count),
                        _build_gallery_grid(photos, folder_str, hist_idx),
                    ],
                    style={"marginBottom": "20px"},
                )
                messages.append(photo_container)

            # Selected tags: each is a removable chip. Clicking the chip removes
            # that single tag from the chain and re-queries (see
            # register_chat_tag_remove_callback). ``hist_idx`` and the full
            # ``chain`` are encoded in the id so the callback can rebuild the
            # remaining selection across multiple photos_and_tags entries.
            if selected_tags:
                selected_chain = ",".join(selected_tags)
                selected_chips = []
                for tag_name in selected_tags:
                    selected_chips.append(
                        dbc.Button(
                            [html.Span(tag_name), html.Span(" ×", className="ms-1")],
                            id={
                                "type": "chat-tag-remove-btn",
                                "index": hist_idx,
                                "remove": tag_name,
                                "chain": selected_chain,
                            },
                            color="primary",
                            size="sm",
                            className="me-2 mb-2",
                            n_clicks=0,
                        )
                    )
                # Clear-all button resets the whole selection at once.
                selected_chips.append(
                    dbc.Button(
                        "Clear",
                        id={"type": "chat-tag-clear-btn", "index": hist_idx},
                        color="secondary",
                        size="sm",
                        className="me-2 mb-2",
                        n_clicks=0,
                    )
                )
                messages.append(
                    html.Div(
                        [
                            html.Strong("Selected tags: "),
                            html.Div(selected_chips, style={"marginTop": "10px"}),
                        ],
                        style={"textAlign": "left", "marginBottom": "10px"},
                    )
                )

            # Add related tags as clickable buttons (chained with AND semantics)
            tag_buttons = []
            for tag_info in related_tags:
                tag_name = tag_info.get("name", "")
                tag_count = tag_info.get("count", 0)
                # Encode the full chain (existing selected tags + this tag)
                chain = ",".join([*selected_tags, tag_name]) if selected_tags else tag_name
                tag_buttons.append(
                    dbc.Button(
                        f"{tag_name} ({tag_count})",
                        id={"type": "chat-tag-btn", "tag": chain},
                        color="info",
                        size="sm",
                        className="me-2 mb-2",
                        n_clicks=0,
                    )
                )

            if tag_buttons:
                messages.append(
                    html.Div(
                        [
                            html.Strong("Related tags: "),
                            html.Div(tag_buttons, style={"marginTop": "10px"}),
                        ],
                        style={"textAlign": "left", "marginBottom": "10px"},
                    )
                )
        elif entry_type == "photos":
            if isinstance(folder, bytes):
                try:
                    folder_str = folder.decode("utf-8")
                except (UnicodeDecodeError, AttributeError):
                    folder_str = folder.decode("latin-1", errors="replace")
            elif isinstance(folder, str):
                folder_str = folder
            else:
                folder_str = "."

            photo_paths = entry.get("photo_paths") or entry.get("photos", [])
            count = entry.get("count", len(photo_paths))
            photo_header = html.Strong(f"Local Photo Agent: Found {count} matching photos:")
            thinking = _thinking_block(entry)

            slideshow_threshold = _slideshow_threshold_for(folder_str)
            use_slideshow = slideshow_threshold > 0 and len(photo_paths) > slideshow_threshold

            if use_slideshow:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_slideshow_button(hist_idx, len(photo_paths)),
                    ],
                    style={"marginBottom": "20px"},
                )
                messages.append(photo_container)
            else:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_gallery_sort_dropdown(hist_idx, len(photo_paths)),
                        _build_gallery_grid(photo_paths, folder_str, hist_idx),
                    ],
                    style={"marginBottom": "20px"},
                )
                messages.append(photo_container)
        elif entry_type == "error":
            messages.append(
                html.Div(
                    [html.Strong("Error: "), str(content)],
                    className="text-danger",
                    style={"whiteSpace": "pre-wrap", "marginBottom": "10px"},
                )
            )
        else:
            display_sender = (
                "You" if sender == "user" else ("Local Photo Agent" if sender == "assistant" else sender.capitalize())
            )
            model_info = entry.get("model", "")
            message_style = {"whiteSpace": "pre-wrap", "marginBottom": "10px"}

            if sender == "user":
                message_style["textAlign"] = "right"
            else:
                message_style["textAlign"] = "left"

            if model_info:
                messages.append(
                    html.Div(
                        [
                            html.Strong(f"{display_sender}: "),
                            _thinking_block(entry),
                            html.Span(str(content)),
                            html.Br(),
                            html.Small(f"Model: {model_info}", className="text-muted"),
                        ],
                        style=message_style,
                    )
                )
            else:
                messages.append(
                    html.Div(
                        [
                            html.Strong(f"{display_sender}: "),
                            _thinking_block(entry),
                            html.Span(str(content)),
                        ],
                        style=message_style,
                    )
                )

    return messages


def register_chat_history_init_callback(app):
    """Register callback to initialize chat display from history store."""

    @app.callback(
        Output("chat-response", "children"),
        Input("chat-history-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=False,
    )
    def init_chat_history(history: list | None, folder: str | None):
        """Initialize chat response display from stored history on page load."""
        if history is None:
            return []
        return _history_to_messages(history, folder)
