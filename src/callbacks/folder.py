import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from src.components import build_folder_controls
from src.discovery import PhotoList, clear_processed_cache
from src.simple_processing_tracker import SimpleProcessingTracker


def register_folder_callback(app):
    @app.callback(
        Output("folder-file-list", "children"),
        Output("folder-cache", "data"),
        Output("photo-list-store", "data"),
        Output("selected-tags-store", "data", allow_duplicate=True),
        Output("tag-cloud-data-store", "data", allow_duplicate=True),
        Output("tag-cloud-results", "children", allow_duplicate=True),
        Input("input-folder", "value"),
        Input("btn-rescan", "n_clicks"),
        State("chk-recursive", "value"),
        prevent_initial_call="initial_duplicate",
        running=[
            (Output("btn-rescan", "disabled"), True, False),
            (Output("btn-rescan", "children"), "Scanning…", "Rescan folder"),
        ],
    )
    def update_folder_list(folder, n_clicks, recursive):
        if not folder:
            return dbc.Badge("Enter a folder path", color="secondary"), {}, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        if n_clicks:
            clear_processed_cache(folder)

        try:
            # Get all images from folder
            photo_list = PhotoList(recursive=bool(recursive))
            all_images = photo_list.list_photos([folder])
            total_all = len(all_images)
            
            # Get processed files
            tracker = SimpleProcessingTracker(folder)
            processed_files = tracker.get_processed_files()
            
            # Filter to get pending files
            pending_images = [img for img in all_images if img not in processed_files]
            total_remaining = len(pending_images)
            
            cache_data = {
                "folder": folder,
                "recursive": recursive,
                "total_all": total_all,
                "total_remaining": total_remaining,
            }

            controls = build_folder_controls(pending_images, total_remaining=total_remaining, total_all=total_all, folder=folder)
            list_data = {"paths": pending_images, "index": None}
            if total_all == 0:
                return html.Div([
                    controls,
                    html.Div("No images found in this folder.", className="text-muted mt-2"),
                ]), cache_data, list_data, [], None, html.Div()

            return controls, cache_data, list_data, [], None, html.Div()
        except Exception as e:
            return html.Div(f"Error listing folder: {e}", className="text-danger"), {}, dash.no_update, dash.no_update, dash.no_update, dash.no_update


def register_toggle_callback(app):
    @app.callback(
        Output("folder-files-collapse", "is_open"),
        Input("btn-toggle-files", "n_clicks"),
        State("folder-files-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_file_list(n_clicks, is_open):
        if n_clicks is None:
            return dash.no_update
        return not is_open
