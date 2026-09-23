import json
import logging

import dash
from dash import Input, Output, State, callback_context

from src.components import build_detail_modal_content
from src.constants import SORT_ORDER_ASC, SORT_ORDER_DESC, default_order_for

from .common import (
    _db_session,
    _get_app_config,
    _open_fullscreen_content,
    _open_modal,
    sort_paths,
)

logger = logging.getLogger(__name__)

# Arrow glyphs for the fullscreen order toggle. ``\u25b2`` up (ascending),
# ``\u25bc`` down (descending).
_ORDER_ARROW = {SORT_ORDER_ASC: "\u25b2", SORT_ORDER_DESC: "\u25bc"}


def _order_from_label(children) -> str | None:
    """Infer the order (``asc``/``desc``) from a toggle button label, else None."""
    glyph = children if isinstance(children, str) else ""
    for order, arrow in _ORDER_ARROW.items():
        if glyph == arrow:
            return order
    return None


def register_detail_modal_callback(app):
    @app.callback(
        Output("detail-modal", "is_open"),
        Output("detail-modal-body", "children"),
        Output("photo-list-store", "data", allow_duplicate=True),
        Input({"type": "thumbnail", "source": dash.ALL, "index": dash.ALL}, "n_clicks"),
        Input("btn-prev-photo", "n_clicks"),
        Input("btn-next-photo", "n_clicks"),
        Input("btn-close-detail", "n_clicks"),
        State({"type": "thumbnail", "source": dash.ALL, "index": dash.ALL}, "id"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def handle_modal(_thumbnail_clicks, _prev_clicks, _next_clicks, _close_clicks, _thumbnail_ids, store_data, folder):
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update, dash.no_update

        prop_id = ""
        value = None
        for t in ctx.triggered:
            pid = t.get("prop_id", "")
            val = t.get("value")
            if pid and pid != ".":
                prop_id = pid
                value = val
                break
        else:
            return dash.no_update, dash.no_update, dash.no_update

        # Close modal
        if "btn-close-detail" in prop_id:
            return False, dash.no_update, dash.no_update

        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None

        # Previous photo
        if "btn-prev-photo" in prop_id:
            if current_index is not None and paths:
                new_index = (current_index - 1) % len(paths)
                image_path = paths[new_index]
                return _open_modal(image_path, folder, new_index, paths)
            return dash.no_update, dash.no_update, dash.no_update

        # Next photo
        if "btn-next-photo" in prop_id:
            if current_index is not None and paths:
                new_index = (current_index + 1) % len(paths)
                image_path = paths[new_index]
                return _open_modal(image_path, folder, new_index, paths)
            return dash.no_update, dash.no_update, dash.no_update

        # Thumbnail click
        if "thumbnail" in prop_id:
            if not value:
                return dash.no_update, dash.no_update, dash.no_update
            try:
                id_part = prop_id.rsplit(".", 1)[0]
                btn_id = json.loads(id_part)
                index_val = btn_id.get("index")
                # Chat thumbnails encode {path, n} as a JSON string in the
                # ``index`` field (Dash forbids dict-valued index). Other
                # sources (tag cloud, search) use a plain string path.
                if isinstance(index_val, dict):
                    image_path = index_val.get("path", "")
                elif isinstance(index_val, str):
                    try:
                        parsed = json.loads(index_val)
                        image_path = parsed.get("path", index_val) if isinstance(parsed, dict) else index_val
                    except (json.JSONDecodeError, ValueError):
                        image_path = index_val
                else:
                    image_path = index_val
            except (json.JSONDecodeError, ValueError):
                return dash.no_update, dash.no_update, dash.no_update

            if not image_path or not folder:
                return dash.no_update, dash.no_update, dash.no_update

            if image_path in paths:
                new_index = paths.index(image_path)
            else:
                # Fallback: path not in current list, treat as single-image view
                paths = [image_path]
                new_index = 0

            return _open_modal(image_path, folder, new_index, paths)

        return dash.no_update, dash.no_update, dash.no_update


def register_fullscreen_open_callback(app):
    """Open the fullscreen viewer from the detail modal's Fullscreen button.

    The photo list is re-ordered according to the fullscreen sort dropdown,
    keeping the currently displayed image in view at its new position.
    """

    @app.callback(
        Output("fullscreen-modal", "is_open"),
        Output("fullscreen-modal-body", "children"),
        Output("detail-modal", "is_open", allow_duplicate=True),
        Output("photo-list-store", "data", allow_duplicate=True),
        Input("btn-open-fullscreen", "n_clicks"),
        State("photo-list-store", "data"),
        State("detail-modal", "is_open"),
        State("input-folder", "value"),
        State("fullscreen-sort-select", "value"),
        State("fullscreen-sort-order", "children"),
        prevent_initial_call=True,
    )
    def open_fullscreen(n_clicks, store_data, detail_is_open, folder, sort_key, order_label):
        if not n_clicks or not folder:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None
        original_paths = (
            store_data.get("original_paths") if isinstance(store_data, dict) else None
        ) or paths

        if current_index is None or current_index >= len(paths):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        order = _order_from_label(order_label)
        current_image = paths[current_index]
        sorted_paths = sort_paths(
            original_paths, sort_key, folder, original_paths=original_paths, order=order
        )
        try:
            new_index = sorted_paths.index(current_image)
        except ValueError:
            new_index = 0
            sorted_paths = [current_image, *sorted_paths]

        content, store = _open_fullscreen_content(
            sorted_paths[new_index], folder, new_index, sorted_paths, original_paths=original_paths
        )
        return True, content, False, store


def _extract_paths_and_scores(entry):
    """Return ``(paths, scores)`` from a chat history entry.

    ``scores`` is a ``{path: score}`` dict for entries whose items carry a
    ``score`` (``/find`` results); otherwise it is an empty dict.

    ``all_photo_paths`` (a flat list of image paths, used by the ``/tag`` tool
    to carry every matching photo regardless of the 20-photo preview cap) is
    preferred over ``photo_paths``/``photos`` so the slideshow can page through
    the full result set.
    """
    all_paths = entry.get("all_photo_paths")
    if all_paths:
        paths = []
        for path in all_paths:
            if isinstance(path, bytes):
                try:
                    path = path.decode("utf-8")
                except (UnicodeDecodeError, AttributeError):
                    path = path.decode("latin-1", errors="replace")
            elif not isinstance(path, str):
                path = str(path)
            if path:
                paths.append(path)
        return paths, {}

    raw = entry.get("photo_paths") or entry.get("photos", []) or []
    paths = []
    scores = {}
    for item in raw:
        if isinstance(item, dict):
            path = item.get("path", "")
            score = item.get("score")
        else:
            path = item
            score = None
        if isinstance(path, bytes):
            try:
                path = path.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                path = path.decode("latin-1", errors="replace")
        elif not isinstance(path, str):
            path = str(path)
        if not path:
            continue
        paths.append(path)
        if score is not None:
            scores[path] = score
    return paths, scores


def register_slideshow_open_callback(app):
    """Open the fullscreen viewer from a chat \u201cStart slideshow\u201d button.

    When a chat result exceeds the slideshow threshold, the gallery is
    replaced by a ``btn-start-slideshow`` button (plus a ``slideshow-sort``
    dropdown) keyed by the chat history index. Below the threshold the gallery
    is shown with its own ``gallery-sort`` dropdown and a ``btn-start-slideshow``
    button in the same sort row. Clicking either button loads that history
    entry's photo paths into ``photo-list-store`` (starting at the first photo)
    and opens the same fullscreen viewer used by the detail modal's Fullscreen
    button. The paths are ordered according to the sort dropdown next to the
    clicked button (``slideshow-sort`` or, falling back, ``gallery-sort``).
    """

    @app.callback(
        Output("fullscreen-modal", "is_open", allow_duplicate=True),
        Output("fullscreen-modal-body", "children", allow_duplicate=True),
        Output("photo-list-store", "data", allow_duplicate=True),
        Output("fullscreen-sort-select", "value", allow_duplicate=True),
        Output("fullscreen-sort-order", "children", allow_duplicate=True),
        Input({"type": "btn-start-slideshow", "index": dash.ALL}, "n_clicks"),
        State("chat-history-store", "data"),
        State("input-folder", "value"),
        State({"type": "slideshow-sort", "index": dash.ALL}, "value"),
        State({"type": "slideshow-sort", "index": dash.ALL}, "id"),
        State({"type": "gallery-sort", "index": dash.ALL}, "value"),
        State({"type": "gallery-sort", "index": dash.ALL}, "id"),
        State({"type": "sort-order", "index": dash.ALL}, "id"),
        State({"type": "sort-order", "index": dash.ALL}, "children"),
        prevent_initial_call=True,
    )
    def open_slideshow(
        n_clicks_list,
        chat_history,
        folder,
        sort_values,
        sort_ids,
        gallery_values,
        gallery_ids,
        order_ids,
        order_labels,
    ):
        ctx = callback_context
        if not ctx.triggered or not n_clicks_list:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        # Identify the exact button that was clicked from the triggered
        # prop_id (robust against stale n_clicks on sibling buttons).
        triggered_id = ""
        for t in ctx.triggered:
            pid = t.get("prop_id", "")
            if pid and pid != "." and t.get("value"):
                triggered_id = pid
                break
        if not triggered_id:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            id_part = triggered_id.rsplit(".", 1)[0]
            btn_id = json.loads(id_part)
            hist_idx = btn_id.get("index")
        except (json.JSONDecodeError, ValueError, AttributeError):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        if not isinstance(chat_history, list) or hist_idx is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        if hist_idx < 0 or hist_idx >= len(chat_history):
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        # Read the sort dropdown value matching the clicked button's index.
        # ``slideshow-sort`` is used by the above-threshold slideshow button;
        # ``gallery-sort`` by the below-threshold gallery's "Start slideshow"
        # button. Fall back to ``gallery-sort`` when no ``slideshow-sort``
        # dropdown matches (i.e. the button was rendered in a gallery).
        sort_key = None
        for pos, sid in enumerate(sort_ids or []):
            if sid.get("index") == hist_idx:
                sort_key = sort_values[pos] if pos < len(sort_values) else None
                break
        if sort_key is None:
            for pos, gid in enumerate(gallery_ids or []):
                if gid.get("index") == hist_idx:
                    sort_key = gallery_values[pos] if pos < len(gallery_values) else None
                    break

        # Read the matching order toggle direction.
        order = None
        for pos, oid in enumerate(order_ids or []):
            if oid.get("index") == hist_idx:
                order = _order_from_label(order_labels[pos] if pos < len(order_labels) else None)
                break

        entry = chat_history[hist_idx] or {}
        original_paths, scores = _extract_paths_and_scores(entry)
        if not original_paths or not folder:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        sorted_paths = sort_paths(
            original_paths,
            sort_key,
            folder,
            original_paths=original_paths,
            scores=scores or None,
            order=order,
        )
        content, store = _open_fullscreen_content(
            sorted_paths[0], folder, 0, sorted_paths, original_paths=original_paths
        )
        # Sync the fullscreen controls to the chosen sort and order.
        from src.constants import DEFAULT_SORT_KEY, default_order_for

        sync_sort = sort_key or DEFAULT_SORT_KEY
        sync_order = order or default_order_for(sort_key)
        return True, content, store, sync_sort, _ORDER_ARROW.get(sync_order, _ORDER_ARROW["asc"])


def register_fullscreen_nav_callback(app):
    """Handle prev/next navigation inside the fullscreen viewer."""

    @app.callback(
        Output("fullscreen-modal-body", "children", allow_duplicate=True),
        Output("photo-list-store", "data", allow_duplicate=True),
        Input("btn-prev-fullscreen", "n_clicks"),
        Input("btn-next-fullscreen", "n_clicks"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def navigate_fullscreen(_prev_clicks, _next_clicks, store_data, folder):
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update

        prop_id = ""
        for t in ctx.triggered:
            pid = t.get("prop_id", "")
            if pid and pid != ".":
                prop_id = pid
                break
        else:
            return dash.no_update, dash.no_update

        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None
        original_paths = (
            store_data.get("original_paths") if isinstance(store_data, dict) else None
        ) or paths

        if current_index is None or not paths:
            return dash.no_update, dash.no_update

        if "btn-prev-fullscreen" in prop_id:
            new_index = (current_index - 1) % len(paths)
        elif "btn-next-fullscreen" in prop_id:
            new_index = (current_index + 1) % len(paths)
        else:
            return dash.no_update, dash.no_update

        image_path = paths[new_index]
        content, store = _open_fullscreen_content(
            image_path, folder, new_index, paths, original_paths=original_paths
        )
        return content, store


def register_fullscreen_sort_callback(app):
    """Re-sort the fullscreen viewer when its sort dropdown or order toggle changes.

    Re-orders from the stored ``original_paths`` (the search-result order)
    and keeps the currently displayed image in view at its new position.
    Switching the sort key resets the order to that key's natural default;
    clicking the order toggle flips asc/desc.
    """

    @app.callback(
        Output("fullscreen-modal-body", "children", allow_duplicate=True),
        Output("photo-list-store", "data", allow_duplicate=True),
        Output("fullscreen-sort-order", "children", allow_duplicate=True),
        Input("fullscreen-sort-select", "value"),
        Input("fullscreen-sort-order", "n_clicks"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        State("fullscreen-sort-order", "children"),
        prevent_initial_call=True,
    )
    def sort_fullscreen(sort_key, _order_clicks, store_data, folder, order_label):
        if not isinstance(store_data, dict):
            return dash.no_update, dash.no_update, dash.no_update

        paths = store_data.get("paths", []) or []
        original_paths = store_data.get("original_paths") or paths
        current_index = store_data.get("index")

        if not paths or not folder:
            return dash.no_update, dash.no_update, dash.no_update

        ctx = callback_context
        _triggered_prop = ctx.triggered[0].get("prop_id", "") if ctx.triggered else ""
        triggered_by_order = _triggered_prop.startswith("fullscreen-sort-order.")

        if triggered_by_order:
            current = _order_from_label(order_label) or SORT_ORDER_ASC
            order = SORT_ORDER_DESC if current == SORT_ORDER_ASC else SORT_ORDER_ASC
        else:
            order = default_order_for(sort_key)

        current_image = paths[current_index] if current_index is not None and current_index < len(paths) else None
        sorted_paths = sort_paths(
            original_paths, sort_key, folder, original_paths=original_paths, order=order
        )

        if current_image and current_image in sorted_paths:
            new_index = sorted_paths.index(current_image)
        else:
            new_index = 0

        content, store = _open_fullscreen_content(
            sorted_paths[new_index], folder, new_index, sorted_paths, original_paths=original_paths
        )
        new_label = _ORDER_ARROW.get(order, _ORDER_ARROW[SORT_ORDER_ASC])
        return content, store, new_label


def register_fullscreen_sort_visibility_callback(app):
    """Show the fullscreen sort control only when browsing multiple photos."""

    @app.callback(
        Output("fullscreen-sort-container", "style", allow_duplicate=True),
        Input("photo-list-store", "data"),
        State("fullscreen-sort-container", "style"),
        prevent_initial_call=True,
    )
    def toggle_sort_visibility(store_data, current_style):
        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        visible = len(paths) > 1
        # Merge into the existing style so positioning/zIndex/background are
        # preserved; only the display property is toggled.
        new_style = dict(current_style) if current_style else {}
        new_style["display"] = "flex" if visible else "none"
        return new_style


def register_fullscreen_close_callback(app):
    """Close the fullscreen viewer and update the detail modal to reflect any
    navigation that happened inside fullscreen."""

    @app.callback(
        Output("fullscreen-modal", "is_open", allow_duplicate=True),
        Output("detail-modal", "is_open", allow_duplicate=True),
        Output("detail-modal-body", "children", allow_duplicate=True),
        Input("btn-close-fullscreen", "n_clicks"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def close_fullscreen(n_clicks, store_data, folder):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update

        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None

        updated_body = dash.no_update
        if current_index is not None and current_index < len(paths) and folder:
            image_path = paths[current_index]
            metadata = None
            embedding = None
            embedding_error = None
            with _db_session(folder) as db:
                if db is not None:
                    try:
                        metadata = db.get_feature_summary(image_path)
                        # Try to get embedding vector
                        try:
                            config = _get_app_config()
                            embedding = db.get_embedding(image_path, config.embedding_model)
                        except RuntimeError as e:
                            # Vector search library not available - don't truncate this important error
                            embedding_error = f"Vector search not available: {e!s}"
                            logger.debug("Vector search library not available for %s: %s", image_path, e)
                        except Exception as e:
                            # Other error (e.g., embedding not found)
                            embedding_error = f"Embedding not found: {str(e)[:100]}"
                            logger.debug("No embedding found for %s: %s", image_path, e)
                    except Exception:
                        logger.warning("Failed to load metadata for %s", image_path, exc_info=True)
            updated_body = build_detail_modal_content(image_path, folder, metadata, embedding, embedding_error)

        return False, True, updated_body


def register_fullscreen_metadata_toggle_callback(app):
    """Toggle the metadata overlay visibility in the fullscreen viewer."""

    @app.callback(
        Output("fullscreen-metadata-overlay", "style", allow_duplicate=True),
        Input("btn-toggle-metadata-fullscreen", "n_clicks"),
        State("fullscreen-metadata-overlay", "style"),
        prevent_initial_call=True,
    )
    def toggle_metadata(n_clicks, current_style):
        if n_clicks is None:
            return dash.no_update
        new_style = dict(current_style) if current_style else {}
        current_display = new_style.get("display", "block")
        new_style["display"] = "none" if current_display == "block" else "block"
        return new_style


def register_fullscreen_folder_change_callback(app):
    """Close the fullscreen viewer when the user changes folder."""

    @app.callback(
        Output("fullscreen-modal", "is_open", allow_duplicate=True),
        Input("input-folder", "value"),
        prevent_initial_call=True,
    )
    def close_on_folder_change(folder):
        return False


def register_fullscreen_find_similar_callback(app):
    """Handle 'Find Similar' button click in fullscreen viewer.

    Uses REST-based vector search that doesn't require sqlite-vec.
    """

    @app.callback(
        Output("similar-photos-store", "data", allow_duplicate=True),
        Input("btn-find-similar-fullscreen", "n_clicks"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def find_similar_fullscreen(n_clicks, store_data, folder):
        if not n_clicks or not folder:
            return None

        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None

        if current_index is None or current_index >= len(paths):
            return None

        current_image_path = paths[current_index]

        try:
            # Get config
            config = _get_app_config()

            # Check if database exists
            from src.sidecar.database.db import FeaturesDatabase

            db_path = FeaturesDatabase.default_db_path(folder)
            if not db_path.exists():
                logger.warning("No database found for folder: %s", folder)
                return None

            # Call REST API endpoint to find similar photos by image
            import requests

            # Build the API URL (same server, different endpoint)
            # Use localhost for internal requests (works in Docker container)
            api_url = f"http://127.0.0.1:{config.dash_port}/_api/find_similar"

            payload = {
                "folder": folder,
                "image_path": current_image_path,
                "model_name": config.embedding_model,
                "limit": config.similarity_limit,
            }

            try:
                response = requests.post(api_url, json=payload, timeout=300)

                if response.status_code != 200:
                    error_msg = f"API request failed with status {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                    except (ValueError, KeyError):
                        error_msg = f"{error_msg}: {response.text[:200]}"

                    logger.error("REST vector search API error: %s", error_msg)
                    return None

                result = response.json()

                if result.get("status") != "success":
                    logger.error("REST vector search failed: %s", result.get("message", "Unknown error"))
                    return None

                similar_results = result.get("results", [])

                # Return similar images data in the expected format
                return {
                    "images": [item.get("image_path") for item in similar_results],
                    "scores": [item.get("score", 0.0) for item in similar_results],
                }

            except requests.exceptions.RequestException as e:
                logger.error("REST vector search request failed: %s", e)
                return None

        except Exception as e:
            logger.error("Failed to find similar images in fullscreen: %s", e)
            return None


_REVEAL_CLIENTSIDE = """
function(nClicks, storeData, folder) {
    if (!nClicks) {
        return dash_clientside.no_update;
    }
    var paths = (storeData && storeData.paths) || [];
    var idx = storeData && storeData.index;
    if (idx === null || idx === undefined || idx < 0 || idx >= paths.length) {
        return dash_clientside.no_update;
    }
    var imagePath = paths[idx];
    fetch('/_api/reveal', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: imagePath, folder: folder})
    }).then(function(r) {
        return r.json().then(function(data) {
            if (!r.ok || data.status !== 'success') {
                alert('Could not get photo path: ' + (data.message || ('HTTP ' + r.status)));
                return;
            }
            var path = data.path || '';
            var folderPath = data.folder || path;
            // Copy the folder path to the clipboard.
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(path).catch(function(){});
            }
            // Show a transient toast with the full path and a Copy button.
            var existing = document.getElementById('reveal-toast');
            if (existing) { existing.remove(); }
            var toast = document.createElement('div');
            toast.id = 'reveal-toast';
            toast.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:2000;' +
                'max-width:480px;background:#343a40;color:#f8f9fa;border:1px solid #495057;' +
                'border-radius:8px;padding:12px 14px;font-family:inherit;font-size:14px;' +
                'box-shadow:0 4px 12px rgba(0,0,0,0.4);word-break:break-all;';
            var head = document.createElement('div');
            head.style.cssText = 'font-weight:bold;margin-bottom:6px;';
            head.textContent = 'Photo path (copied to clipboard):';
            toast.appendChild(head);
            var body = document.createElement('div');
            body.textContent = path;
            body.style.cssText = 'user-select:text;cursor:text;margin-bottom:8px;';
            toast.appendChild(body);
            var copyBtn = document.createElement('button');
            copyBtn.textContent = 'Copy';
            copyBtn.style.cssText = 'margin-right:8px;background:#0d6efd;color:#fff;border:none;border-radius:4px;padding:4px 10px;cursor:pointer;';
            copyBtn.onclick = function() {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(path).then(function(){ copyBtn.textContent = 'Copied'; });
                } else {
                    var range = document.createRange(); range.selectNode(body);
                    window.getSelection().removeAllRanges(); window.getSelection().addRange(range);
                    document.execCommand('copy'); window.getSelection().removeAllRanges();
                    copyBtn.textContent = 'Copied';
                }
            };
            toast.appendChild(copyBtn);
            var closeBtn = document.createElement('button');
            closeBtn.textContent = 'Close';
            closeBtn.style.cssText = 'background:#6c757d;color:#fff;border:none;border-radius:4px;padding:4px 10px;cursor:pointer;';
            closeBtn.onclick = function() { toast.remove(); };
            toast.appendChild(closeBtn);
            document.body.appendChild(toast);
            setTimeout(function() { if (document.getElementById('reveal-toast')) { document.getElementById('reveal-toast').remove(); } }, 8000);
        });
    }).catch(function(e) {
        alert('Could not get photo path: ' + e);
    });
    return dash_clientside.no_update;
}
"""


def register_reveal_callbacks(app):
    """Wire the 'Copy Path' buttons to POST /_api/reveal.

    One clientside callback covers the detail-modal button; a second covers
    the fullscreen-viewer button. Both read the current image from
    ``photo-list-store`` and the active folder from ``input-folder``, fetch
    the photo's path from the server, copy it to the clipboard, and show it
    in a transient toast.
    """
    app.clientside_callback(
        _REVEAL_CLIENTSIDE,
        Output("reveal-dummy", "children"),
        Input("btn-reveal-detail", "n_clicks"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        _REVEAL_CLIENTSIDE,
        Output("reveal-dummy", "children", allow_duplicate=True),
        Input("btn-reveal-fullscreen", "n_clicks"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
