import sqlite3

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dash_table, html

from .common import _db_session


def register_sql_explorer_callback(app):
    @app.callback(
        Output("sql-explorer-modal", "is_open"),
        Input("btn-sql-explorer", "n_clicks"),
        Input("btn-close-sql-explorer", "n_clicks"),
        State("sql-explorer-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_sql_explorer_modal(n_open, n_close, is_open):
        ctx = dash.callback_context
        if not ctx.triggered:
            return dash.no_update

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_id == "btn-sql-explorer":
            return True
        elif trigger_id == "btn-close-sql-explorer":
            return False
        return is_open

    @app.callback(
        Output("sql-results", "children"),
        Input("btn-run-sql", "n_clicks"),
        State("input-folder", "value"),
        State("sql-input", "value"),
        prevent_initial_call=True,
    )
    def run_sql(n_clicks, folder, sql_text):
        if n_clicks is None:
            return dash.no_update

        if not folder:
            return dbc.Alert(
                "Enter a folder path above before running queries.",
                color="warning",
            )

        with _db_session(folder) as db:
            if db is None:
                return dbc.Alert(
                    "No features.db found for this folder. Scan the folder first.",
                    color="warning",
                )
            try:
                columns, rows = db.execute_query(sql_text)
            except (sqlite3.Error, FileNotFoundError, OSError) as e:
                return dbc.Alert(str(e), color="danger")

        if not columns:
            return html.Div("Query returned no columns.", className="text-muted")

        if not rows:
            return html.Div("Query returned an empty result set.", className="text-muted")

        return dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in columns],
            data=[dict(zip(columns, row, strict=False)) for row in rows],
            style_table={"overflowX": "auto"},
            sort_action="native",
            filter_action="native",
            page_action="native",
            page_size=20,
        )
