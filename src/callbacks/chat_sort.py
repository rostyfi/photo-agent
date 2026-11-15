"""Callback for re-sorting preview galleries when sort controls change.

This module provides:
- ``register_gallery_sort_callback`` — re-sort gallery thumbnails on dropdown/toggle change
"""

import json
import logging
from typing import Any

import dash
from dash import Input, Output, State, callback_context

from src.constants import SORT_ORDER_ASC, SORT_ORDER_DESC, default_order_for

from .chat_render import (
    _ORDER_ARROW,
    _build_gallery_items,
    _decode_path,
    _order_from_children,
)
from .common import sort_paths

logger = logging.getLogger(__name__)


def register_gallery_sort_callback(app):
    """Re-sort a preview gallery when its sort dropdown or order toggle changes.

    Each gallery renders a ``gallery-sort`` dropdown and a ``sort-order``
    toggle button (both keyed by chat history index) above a ``gallery-grid``
    container. Changing either control reorders the thumbnails and updates
    ``photo-list-store`` so the detail-modal navigation follows the sorted
    order. Switching the sort key resets the order to that key's natural
    default; clicking the toggle flips asc/desc.
    """

    @app.callback(
        Output({"type": "gallery-grid", "index": dash.ALL}, "children", allow_duplicate=True),
        Output("photo-list-store", "data", allow_duplicate=True),
        Output({"type": "sort-order", "index": dash.ALL}, "children", allow_duplicate=True),
        Input({"type": "gallery-sort", "index": dash.ALL}, "value"),
        Input({"type": "sort-order", "index": dash.ALL}, "n_clicks"),
        State({"type": "gallery-sort", "index": dash.ALL}, "id"),
        State({"type": "sort-order", "index": dash.ALL}, "id"),
        State({"type": "sort-order", "index": dash.ALL}, "children"),
        State("chat-history-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def handle_gallery_sort(sort_values, order_clicks, sort_ids, order_ids, order_labels, chat_history, folder):
        n_grid = len(sort_ids) if sort_ids else 0
        no_update_grids = [dash.no_update] * n_grid
        n_order = len(order_ids) if order_ids else 0
        no_update_labels = [dash.no_update] * n_order

        ctx = callback_context
        triggered_id = ""
        if ctx.triggered:
            for t in ctx.triggered:
                pid = t.get("prop_id", "")
                if pid and pid != ".":
                    triggered_id = pid
                    break
        if not triggered_id:
            return no_update_grids, dash.no_update, no_update_labels

        triggered_by_order = '"type":"sort-order"' in triggered_id

        try:
            id_part = triggered_id.rsplit(".", 1)[0]
            btn_id = json.loads(id_part)
            hist_idx = btn_id.get("index")
        except (json.JSONDecodeError, ValueError, AttributeError):
            return no_update_grids, dash.no_update, no_update_labels

        # Resolve the active sort key.
        sort_key = None
        for pos, sid in enumerate(sort_ids):
            if sid.get("index") == hist_idx:
                sort_key = sort_values[pos] if pos < len(sort_values) else None
                break

        # Resolve the effective order and the new toggle label.
        if triggered_by_order:
            current = SORT_ORDER_ASC
            for pos, oid in enumerate(order_ids or []):
                if oid.get("index") == hist_idx:
                    current = _order_from_children(order_labels[pos] if pos < len(order_labels) else "")
                    break
            order = SORT_ORDER_DESC if current == SORT_ORDER_ASC else SORT_ORDER_ASC
        else:
            # Sort key changed (or unknown trigger): reset to the key's default.
            order = default_order_for(sort_key)

        new_label = _ORDER_ARROW.get(order, _ORDER_ARROW[SORT_ORDER_ASC])

        if not isinstance(chat_history, list) or hist_idx is None or hist_idx < 0 or hist_idx >= len(chat_history):
            return no_update_grids, dash.no_update, no_update_labels
        entry = chat_history[hist_idx] or {}

        raw_items = entry.get("photo_paths") or entry.get("photos", []) or []
        original_paths = []
        scores = {}
        item_by_path = {}
        for item in raw_items:
            if isinstance(item, dict):
                path = _decode_path(item.get("path", ""))
                score = item.get("score")
            else:
                path = _decode_path(item)
                score = None
            if not path:
                continue
            original_paths.append(path)
            item_by_path[path] = item
            if score is not None:
                scores[path] = score

        if not original_paths:
            return no_update_grids, dash.no_update, no_update_labels

        if isinstance(folder, bytes):
            folder_str = folder.decode("utf-8", errors="replace")
        elif folder is None:
            folder_str = "."
        else:
            folder_str = str(folder)

        sorted_paths = sort_paths(
            original_paths,
            sort_key,
            folder_str,
            original_paths=original_paths,
            scores=scores or None,
            order=order,
        )
        sorted_items = [item_by_path.get(p, p) for p in sorted_paths]
        new_children = _build_gallery_items(sorted_items, folder_str, hist_idx)

        grid_outputs: list[Any] = list(no_update_grids)
        grid_matched = False
        for pos, sid in enumerate(sort_ids):
            if sid.get("index") == hist_idx:
                grid_outputs[pos] = new_children
                grid_matched = True
                break

        label_outputs: list[Any] = list(no_update_labels)
        for pos, oid in enumerate(order_ids or []):
            if oid.get("index") == hist_idx:
                label_outputs[pos] = new_label
                break

        # Only update photo-list-store when a gallery grid was actually
        # reordered; for a slideshow sort-row toggle (no gallery grid) we
        # flip just the label and leave the store untouched so an open
        # fullscreen viewer is not clobbered.
        if grid_matched:
            store: Any = {"paths": sorted_paths, "original_paths": original_paths, "index": None}
        else:
            store = dash.no_update
        return grid_outputs, store, label_outputs
