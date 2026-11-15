"""Modal builders (SQL explorer, detail modal, fullscreen modal)."""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.constants import DEFAULT_SORT_KEY, SORT_OPTIONS, default_order_for


def build_sql_explorer_modal():
    """Build the SQL Explorer modal."""
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("SQL Explorer"), close_button=True),
            dbc.ModalBody(
                [
                    dbc.Label("Query"),
                    dbc.Textarea(
                        id="sql-input",
                        rows=5,
                        value="SELECT * FROM raw_features LIMIT 10",
                        className="font-monospace bg-dark text-light",
                    ),
                    dbc.Button(
                        "Run Query",
                        id="btn-run-sql",
                        color="primary",
                        className="mt-2",
                    ),
                    html.Div(id="sql-results", className="mt-3"),
                ]
            ),
            dbc.ModalFooter(dbc.Button("Close", id="btn-close-sql-explorer", color="secondary")),
        ],
        id="sql-explorer-modal",
        is_open=False,
        size="lg",
    )


def build_detail_modal():
    """Build the Detail modal for photo viewing."""
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Photo Details"), close_button=True),
            dbc.ModalBody(
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Button("\u2190", id="btn-prev-photo", color="light", size="lg", className="w-100"),
                            width="auto",
                            className="d-flex align-items-center",
                        ),
                        dbc.Col(
                            html.Div(id="detail-modal-body"),
                            width=True,
                        ),
                        dbc.Col(
                            dbc.Button("\u2192", id="btn-next-photo", color="light", size="lg", className="w-100"),
                            width="auto",
                            className="d-flex align-items-center",
                        ),
                    ],
                    className="g-2 flex-nowrap",
                )
            ),
            dbc.ModalFooter(dbc.Button("Close", id="btn-close-detail", color="secondary")),
        ],
        id="detail-modal",
        is_open=False,
        size="lg",
    )


def build_fullscreen_modal():
    """Build the Fullscreen photo viewer modal.

    The navigation/control buttons live in the static layout (as siblings of
    the dynamic ``fullscreen-modal-body``) so Dash always attaches their
    callback handlers. Only the image and metadata overlay are injected
    dynamically by ``build_fullscreen_viewer``.
    """
    return dbc.Modal(
        dbc.ModalBody(
            [
                html.Div(
                    id="fullscreen-modal-body",
                    style={
                        "height": "100%",
                        "width": "100%",
                    },
                ),
                html.Div(
                    [
                        html.Span(
                            "Sort:",
                            style={
                                "color": "white",
                                "fontSize": "0.9rem",
                                "marginRight": "8px",
                            },
                        ),
                        dcc.Dropdown(
                            id="fullscreen-sort-select",
                            options=SORT_OPTIONS,
                            value=DEFAULT_SORT_KEY,
                            clearable=False,
                            style={"width": "170px"},
                            className="sort-dropdown",
                        ),
                        dbc.Button(
                            "\u25bc" if default_order_for(DEFAULT_SORT_KEY) == "desc" else "\u25b2",
                            id="fullscreen-sort-order",
                            color="secondary",
                            size="sm",
                            n_clicks=0,
                            style={
                                "width": "38px",
                                "padding": "0.25rem 0",
                                "marginLeft": "6px",
                            },
                        ),
                    ],
                    id="fullscreen-sort-container",
                    style={
                        "position": "absolute",
                        "top": "20px",
                        "left": "20px",
                        "zIndex": "1100",
                        "display": "flex",
                        "alignItems": "center",
                        "background": "rgba(0,0,0,0.5)",
                        "borderRadius": "8px",
                        "padding": "6px 10px",
                    },
                ),
                dbc.Button(
                    "\u2715",
                    id="btn-close-fullscreen",
                    style={
                        "position": "absolute",
                        "top": "20px",
                        "right": "20px",
                        "zIndex": "1100",
                        "fontSize": "24px",
                        "color": "white",
                        "background": "rgba(0,0,0,0.5)",
                        "border": "none",
                        "borderRadius": "50%",
                        "width": "50px",
                        "height": "50px",
                        "cursor": "pointer",
                    },
                ),
                dbc.Button(
                    "\u2190",
                    id="btn-prev-fullscreen",
                    style={
                        "position": "absolute",
                        "left": "20px",
                        "top": "50%",
                        "transform": "translateY(-50%)",
                        "zIndex": "1000",
                        "fontSize": "36px",
                        "color": "white",
                        "background": "rgba(0,0,0,0.3)",
                        "border": "none",
                        "borderRadius": "50%",
                        "width": "60px",
                        "height": "60px",
                        "cursor": "pointer",
                    },
                ),
                dbc.Button(
                    "\u2192",
                    id="btn-next-fullscreen",
                    style={
                        "position": "absolute",
                        "right": "20px",
                        "top": "50%",
                        "transform": "translateY(-50%)",
                        "zIndex": "1000",
                        "fontSize": "36px",
                        "color": "white",
                        "background": "rgba(0,0,0,0.3)",
                        "border": "none",
                        "borderRadius": "50%",
                        "width": "60px",
                        "height": "60px",
                        "cursor": "pointer",
                    },
                ),
                dbc.Button(
                    "Find Similar",
                    id="btn-find-similar-fullscreen",
                    color="primary",
                    size="sm",
                    style={
                        "position": "absolute",
                        "bottom": "20px",
                        "right": "160px",
                        "zIndex": "1100",
                    },
                ),
                dbc.Button(
                    "Copy Path",
                    id="btn-reveal-fullscreen",
                    color="secondary",
                    size="sm",
                    style={
                        "position": "absolute",
                        "bottom": "20px",
                        "left": "20px",
                        "zIndex": "1100",
                    },
                ),
                dbc.Button(
                    "Toggle Info",
                    id="btn-toggle-metadata-fullscreen",
                    color="secondary",
                    size="sm",
                    style={
                        "position": "absolute",
                        "bottom": "20px",
                        "right": "20px",
                        "zIndex": "1100",
                    },
                ),
            ],
            style={
                "position": "relative",
                "padding": "0",
                "backgroundColor": "black",
                "height": "100vh",
                "width": "100vw",
                "overflow": "hidden",
            },
        ),
        id="fullscreen-modal",
        is_open=False,
        fullscreen=True,
    )
