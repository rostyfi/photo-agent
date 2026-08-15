import json
import logging

import dash
from dash import Input, Output, State, callback_context

from src.components import build_detail_modal_content

from .common import _db_session, _get_app_config, _open_fullscreen_content, _open_modal

logger = logging.getLogger(__name__)


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
    def handle_modal(_thumbnail_clicks, _prev_clicks, _next_clicks, _close_clicks,
                     _thumbnail_ids, store_data, folder):
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
                image_path = btn_id.get("index")
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
    """Open the fullscreen viewer from the detail modal's Fullscreen button."""
    @app.callback(
        Output("fullscreen-modal", "is_open"),
        Output("fullscreen-modal-body", "children"),
        Output("detail-modal", "is_open", allow_duplicate=True),
        Input("btn-open-fullscreen", "n_clicks"),
        State("photo-list-store", "data"),
        State("detail-modal", "is_open"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def open_fullscreen(n_clicks, store_data, detail_is_open, folder):
        if not n_clicks or not folder:
            return dash.no_update, dash.no_update, dash.no_update

        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None

        if current_index is None or current_index >= len(paths):
            return dash.no_update, dash.no_update, dash.no_update

        image_path = paths[current_index]
        content, _ = _open_fullscreen_content(image_path, folder, current_index, paths)
        return True, content, False


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

        if current_index is None or not paths:
            return dash.no_update, dash.no_update

        if "btn-prev-fullscreen" in prop_id:
            new_index = (current_index - 1) % len(paths)
        elif "btn-next-fullscreen" in prop_id:
            new_index = (current_index + 1) % len(paths)
        else:
            return dash.no_update, dash.no_update

        image_path = paths[new_index]
        content, store = _open_fullscreen_content(image_path, folder, new_index, paths)
        return content, store


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
                            embedding_error = f"Vector search not available: {str(e)}"
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
                "limit": config.similarity_limit
            }
            
            try:
                response = requests.post(
                    api_url,
                    json=payload,
                    timeout=300
                )
                
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

