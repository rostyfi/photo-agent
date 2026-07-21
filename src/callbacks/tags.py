import json
import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback_context, html

from src.components import build_photo_cards, build_selected_tags_bar, build_tag_cloud

from .common import _db_session

logger = logging.getLogger(__name__)


def register_tag_cloud_load_callback(app):
    """Load tag frequency data into a store when the user clicks Load Tag Cloud."""
    @app.callback(
        Output("tag-cloud-data-store", "data"),
        Input("btn-load-tag-cloud", "n_clicks"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def load_tag_cloud(n_clicks, folder):
        if n_clicks is None:
            return dash.no_update

        if not folder:
            return {"folder": "", "tags": []}

        with _db_session(folder) as db:
            if db is None:
                return {"folder": folder, "tags": []}
            try:
                tags_with_counts = db.list_tag_frequencies()
            except (sqlite3.Error, OSError) as e:
                logger.warning("Failed to load tag frequencies: %s", e)
                return {"folder": folder, "tags": []}

        # Serialize tag tuples to lists for JSON
        return {"folder": folder, "tags": tags_with_counts}


def register_tag_cloud_render_callback(app):
    """Render the tag cloud and selected-tags bar from stores.

    Shows the full tag cloud when no filters are active.
    When tags are selected, the cloud is restricted to tags that
    co-occur with the active selection in at least one photo.
    """
    @app.callback(
        Output("tag-cloud-container", "children"),
        Output("selected-tags-bar", "children"),
        Input("tag-cloud-data-store", "data"),
        Input("selected-tags-store", "data"),
        prevent_initial_call=True,
    )
    def render_tag_cloud(tag_cloud_data, selected_tags):
        if not tag_cloud_data:
            return html.Div(), html.Div()

        folder = tag_cloud_data.get("folder", "")
        if not folder:
            return html.Div(), html.Div()

        selected_tags = list(selected_tags or [])

        if not selected_tags:
            # No active filters — show everything that was loaded.
            tags_with_counts = tag_cloud_data.get("tags", [])
        else:
            # Active filters — query DB for co-occurring tags.
            with _db_session(folder) as db:
                if db is None:
                    return html.Div(), html.Div()
                try:
                    tags_with_counts = db.list_tag_frequencies_restricted(
                        selected_tags, limit=100
                    )
                except (sqlite3.Error, OSError) as e:
                    logger.warning("Failed to load restricted tag frequencies: %s", e)
                    tags_with_counts = []

        if not tags_with_counts:
            msg = (
                "No other tags co-occur with the current selection."
                if selected_tags else "No tags found."
            )
            return html.Div(msg, className="text-muted"), build_selected_tags_bar(selected_tags)

        return build_tag_cloud(
            tags_with_counts, selected_tags=selected_tags
        ), build_selected_tags_bar(selected_tags)


def register_tag_toggle_callback(app):
    """Handle tag click, pill removal, and clear-all for the tag chain."""
    @app.callback(
        Output("selected-tags-store", "data"),
        Output("tag-cloud-results", "children"),
        Output("photo-list-store", "data", allow_duplicate=True),
        Input({"type": "tag-cloud-btn", "index": dash.ALL}, "n_clicks"),
        Input({"type": "tag-clear-btn", "index": dash.ALL}, "n_clicks"),
        Input("btn-tag-clear-all", "n_clicks"),
        State({"type": "tag-cloud-btn", "index": dash.ALL}, "id"),
        State({"type": "tag-clear-btn", "index": dash.ALL}, "id"),
        State("selected-tags-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def tag_toggled(_tag_cloud_clicks, _clear_tag_clicks, _clear_all_clicks,
                    _tag_cloud_ids, _clear_tag_ids, current_tags, folder):
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update, dash.no_update, dash.no_update

        triggered_id = ctx.triggered[0].get("prop_id", "")
        if triggered_id == ".":
            return dash.no_update, dash.no_update, dash.no_update

        # Handle Clear All
        if "btn-tag-clear-all" in triggered_id:
            return [], html.Div(), dash.no_update

        # Identify clicked tag and whether it's a removal
        clicked_tag = None
        remove = False
        for t in ctx.triggered:
            prop_id = t.get("prop_id", "")
            if not t.get("value"):
                continue
            if "tag-cloud-btn" in prop_id:
                try:
                    id_part = prop_id.rsplit(".", 1)[0]
                    btn_id = json.loads(id_part)
                    clicked_tag = btn_id.get("index")
                    remove = False
                except (json.JSONDecodeError, ValueError):
                    continue
            elif "tag-clear-btn" in prop_id:
                try:
                    id_part = prop_id.rsplit(".", 1)[0]
                    btn_id = json.loads(id_part)
                    clicked_tag = btn_id.get("index")
                    remove = True
                except (json.JSONDecodeError, ValueError):
                    continue

        if not clicked_tag:
            return dash.no_update, dash.no_update, dash.no_update

        current_tags = list(current_tags or [])
        current_lower = {t.lower() for t in current_tags}
        is_active = clicked_tag.lower() in current_lower

        if remove:
            new_tags = [t for t in current_tags if t.lower() != clicked_tag.lower()]
        elif is_active:
            new_tags = [t for t in current_tags if t.lower() != clicked_tag.lower()]
        else:
            new_tags = current_tags + [clicked_tag]

        if not new_tags:
            return [], html.Div(), dash.no_update

        if not folder:
            return new_tags, dbc.Alert("Enter a folder path above.", color="warning"), dash.no_update

        with _db_session(folder) as db:
            if db is None:
                return new_tags, dbc.Alert(
                    "No features.db found for this folder.",
                    color="warning",
                ), dash.no_update
            try:
                results = db.get_features_by_tags(new_tags)
            except (sqlite3.Error, OSError) as e:
                logger.warning("Failed to get features by tags: %s", e)
                return new_tags, dbc.Alert(f"Error loading photos: {e}", color="danger"), dash.no_update

        children = html.Div(
            [
                dbc.Alert(f"Photos tagged with: {', '.join(new_tags)}", color="info", dismissable=False),
                build_photo_cards(results, folder=folder, source="tag") if results else html.Div("No photos match all selected tags.", className="text-muted"),
            ]
        )
        list_data = {"paths": [r.get("image_path", "") for r in results], "index": None} if results else dash.no_update
        return new_tags, children, list_data
