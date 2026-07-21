import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from src.components import build_photo_cards

from .common import _db_session


def register_search_callback(app):
    @app.callback(
        Output("search-results", "children"),
        Output("search-status", "children"),
        Output("photo-list-store", "data", allow_duplicate=True),
        Input("btn-search", "n_clicks"),
        State("search-input", "value"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def run_search(btn_search, query, folder):
        if btn_search is None:
            return dash.no_update, dash.no_update, dash.no_update

        if not folder:
            return (
                dash.no_update,
                dbc.Alert("Enter a folder path above before searching.", color="warning"),
                dash.no_update,
            )

        with _db_session(folder) as db:
            if db is None:
                return (
                    dash.no_update,
                    dbc.Alert(
                        "No features.db found for this folder. Process the folder first.",
                        color="warning",
                    ),
                    dash.no_update,
                )

            if not query:
                return (
                    dash.no_update,
                    dbc.Alert("Enter a search query.", color="warning"),
                    dash.no_update,
                )
            results = db.search_features(query)
            if not results:
                return (
                    html.Div("No results found.", className="text-muted"),
                    dash.no_update,
                    dash.no_update,
                )
            return (
                build_photo_cards(results, folder=folder, source="search"),
                dbc.Alert(f"{len(results)} result(s) found.", color="success", dismissable=True),
                {"paths": [r.get("image_path", "") for r in results], "index": None},
            )
