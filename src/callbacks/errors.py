"""Callbacks for the Errors tab in the web UI.

This module provides callbacks for loading and displaying errors from the
simple processing tracker.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from src.components import build_errors_display

logger = logging.getLogger(__name__)

from .common import _get_tracker

# Cache for failed entries to avoid re-reading every poll
_TRACKER_FAILED_CACHE: dict = {}  # folder -> (failed_entries, mtime)


def register_errors_callback(app):
    """Register callbacks for loading and displaying errors."""
    
    @app.callback(
        [
            Output("errors-store", "data"),
            Output("errors-count", "children"),
            Output("errors-list", "children"),
        ],
        Input("btn-refresh-errors", "n_clicks"),
        Input("poll-interval", "n_intervals"),
        State("input-folder", "value"),
        State("errors-store", "data"),
        prevent_initial_call=True,
    )
    def load_errors(n_clicks, n_intervals, folder, current_data):
        """Load failed images from simple tracker and display them."""
        if not folder:
            return dash.no_update, dash.no_update, dash.no_update
        
        try:
            # Use cached tracker instance to get failed entries
            tracker = _get_tracker(folder)
            failed_entries = tracker.get_failed_files()
            _TRACKER_FAILED_CACHE[folder] = (failed_entries, 0)
            
            # Build error list with additional info
            errors = []
            for entry in failed_entries:
                error_dict = {
                    "image_path": entry.get("image_path", ""),
                    "error_code": entry.get("error_code", "unknown"),
                    "error_msg": entry.get("error_msg", "No error message"),
                    "ts": "",  # Not stored in simple tracker
                }
                errors.append(error_dict)
            
            # Update store
            new_data = {
                "errors": errors,
                "folder": folder,
            }
            
            # Build count display
            count_display = html.Div(
                [
                    html.Strong(f"{len(errors)} failed images"),
                    html.Small(f" in {folder}", className="text-muted ms-2"),
                ]
            )
            
            # Build error list display
            errors_display = build_errors_display(errors, folder)
            
            return new_data, count_display, errors_display
            
        except Exception as e:
            logger.error("Failed to load errors for folder %s: %s", folder, e)
            error_display = html.Div(
                [
                    dbc.Alert(
                        [
                            html.Span("⚠ ", className="me-2"),
                            f"Failed to load errors: {e}",
                        ],
                        color="danger",
                    )
                ],
                className="mb-3",
            )
            return {"errors": [], "folder": folder}, html.Div("0 errors"), error_display
    
    @app.callback(
        Output("errors-store", "data", allow_duplicate=True),
        Input("btn-clear-errors", "n_clicks"),
        State("errors-store", "data"),
        prevent_initial_call=True,
    )
    def clear_errors(n_clicks, current_data):
        """Clear the errors display."""
        if n_clicks:
            return {"errors": [], "folder": current_data.get("folder")}
        return dash.no_update
    
    @app.callback(
        Output("errors-list", "children", allow_duplicate=True),
        Input("errors-store", "data"),
        prevent_initial_call=True,
    )
    def update_errors_display(data):
        """Update the errors display when store changes."""
        if not data:
            return dash.no_update
        
        errors = data.get("errors", [])
        folder = data.get("folder", "")
        return build_errors_display(errors, folder)


def register_copy_error_callback(app):
    """Register clientside callback to copy error message to clipboard."""
    # Use a dummy output since we're doing everything clientside
    app.clientside_callback(
        """
        function(n_clicks, data) {
            if (!n_clicks) { return window.dash_clientside.no_update; }
            
            // Get the button that was clicked
            const triggered = dash_clientside.callback_context.triggered || [];
            if (triggered.length === 0) { return window.dash_clientside.no_update; }
            
            const propId = triggered[0].prop_id;
            // Extract the index from the button ID like "{'type':'btn-copy-error','index':2}.n_clicks"
            const match = propId.match(/index":(\\d+)/);
            if (!match) { return window.dash_clientside.no_update; }
            
            const index = parseInt(match[1]);
            const errors = data.errors || [];
            
            if (index < errors.length) {
                const errorMsg = errors[index].error_msg || "";
                // Copy to clipboard
                navigator.clipboard.writeText(errorMsg).then(function() {
                    console.log("Copied error to clipboard");
                }).catch(function(err) {
                    console.error("Failed to copy:", err);
                    // Fallback: try to select the text
                    const spanId = '{"type":"error-msg","index":' + index + '}';
                    const span = document.querySelector('[id="' + spanId.replace(/\"/g, '\\\\"') + '"]');
                    if (span) {
                        const range = document.createRange();
                        range.selectNode(span);
                        window.getSelection().removeAllRanges();
                        window.getSelection().addRange(range);
                        try {
                            document.execCommand('copy');
                        } catch(e) {
                            console.error("Fallback copy failed:", e);
                        }
                        window.getSelection().removeAllRanges();
                    }
                });
            }
            
            return window.dash_clientside.no_update;
        }
        """,
        Output("errors-store", "data", allow_duplicate=True),
        Input({"type": "btn-copy-error", "index": dash.dependencies.ALL}, "n_clicks"),
        State("errors-store", "data"),
        prevent_initial_call=True,
    )


def register_all_errors_callbacks(app):
    """Register all error-related callbacks."""
    register_errors_callback(app)
    register_copy_error_callback(app)