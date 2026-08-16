"""
Layout component builders for the Local Photo Agent web UI.

This module contains helper functions to build reusable layout components,
reducing complexity in the main layout.py file.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from src.config import AppConfig
from src.constants import DEFAULT_LLM_MODEL

# =============================================================================
# STYLE CONSTANTS
# =============================================================================

INPUT_STYLE = "bg-dark text-light"
BUTTON_STYLE = "w-100"
MB_2 = "mb-2"
MB_3 = "mb-3"


# =============================================================================
# MODAL COMPONENTS
# =============================================================================


def build_settings_modal(app_config: AppConfig):
    """Build the Settings modal with all its tabs."""
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Settings"), close_button=True),
            dbc.ModalBody(
                [
                    dbc.Tabs(
                        [
                            build_connection_tab(app_config),
                            build_embedding_tab(app_config),
                            build_vector_tools_tab(),
                            build_api_testers_tab(),
                            build_photo_testers_tab(),
                            build_errors_tab(),
                        ],
                        id="settings-tabs",
                        active_tab="tab-connection",
                    ),
                ]
            ),
            dbc.ModalFooter(dbc.Button("Close", id="btn-close-settings", color="secondary")),
        ],
        id="settings-modal",
        is_open=False,
        dialogClassName="settings-modal-1000",
        dialogStyle={"maxWidth": "1000px", "width": "1000px", "margin": "auto"},
    )


def build_connection_tab(app_config: AppConfig):
    """Build the Connection tab for settings modal."""
    return dbc.Tab(
        label="Connection",
        tab_id="tab-connection",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Host"),
                            dbc.Input(
                                id="input-host",
                                type="text",
                                value=app_config.llm_host,
                                placeholder="localhost",
                                className=INPUT_STYLE,
                            ),
                        ],
                        width=6,
                        className=MB_2,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Port"),
                            dbc.Input(
                                id="input-port",
                                type="number",
                                value=app_config.llm_port,
                                placeholder="11434",
                                className=INPUT_STYLE,
                            ),
                        ],
                        width=6,
                        className=MB_2,
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Model"),
                            dbc.Input(
                                id="input-model",
                                type="text",
                                value=app_config.llm_model,
                                placeholder=DEFAULT_LLM_MODEL,
                                className=INPUT_STYLE,
                            ),
                        ],
                        width=6,
                        className=MB_2,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Backend"),
                            dbc.Input(
                                id="input-backend",
                                type="text",
                                value=app_config.llm_backend,
                                placeholder="ollama",
                                className=INPUT_STYLE,
                            ),
                        ],
                        width=6,
                        className=MB_2,
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Timeout (s)"),
                            dbc.Input(
                                id="input-timeout",
                                type="number",
                                value=app_config.timeout,
                                min=10,
                                max=600,
                                className=INPUT_STYLE,
                            ),
                        ],
                        width=12,
                        className=MB_2,
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("\u00a0"),
                            dbc.Button(
                                "Check Server",
                                id="btn-health",
                                color="info",
                                className=BUTTON_STYLE,
                            ),
                        ],
                        width=12,
                        className=MB_2,
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Checkbox(
                            id="chk-recursive",
                            label="Scan sub-folders",
                            value=app_config.recursive,
                            className=MB_2,
                        ),
                        width=6,
                    ),
                    dbc.Col(
                        dbc.Checkbox(
                            id="chk-dry-run",
                            label="Dry run (no LLM calls — writes placeholder sidecars)",
                            value=app_config.dry_run,
                            className=MB_2,
                        ),
                        width=6,
                    ),
                ],
                className=MB_2,
            ),
            html.Div(id="health-status", className=MB_2),
        ],
        className="p-2",
    )


def build_embedding_tab(app_config: AppConfig):
    """Build the Embedding tab for settings modal."""
    return dbc.Tab(
        label="Embedding",
        tab_id="tab-embedding",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Checkbox(
                            id="chk-embedding-enabled",
                            label="Enable embedding generation",
                            value=app_config.embedding_enabled,
                            className=MB_2,
                        ),
                        width=12,
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Embedding Model"),
                            dbc.Input(
                                id="input-embedding-model",
                                type="text",
                                value=app_config.embedding_model,
                                placeholder="nomic-embed-text",
                                className=INPUT_STYLE,
                            ),
                        ],
                        width=6,
                        className=MB_2,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Embedding Backend"),
                            dbc.Input(
                                id="input-embedding-backend",
                                type="text",
                                value=app_config.embedding_backend,
                                placeholder="ollama",
                                className=INPUT_STYLE,
                            ),
                        ],
                        width=6,
                        className=MB_2,
                    ),
                ]
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Button(
                            "Check Vector Database",
                            id="btn-check-vector-db",
                            color="info",
                            className="w-100 mb-2",
                        ),
                        width=12,
                    ),
                ]
            ),
            html.Div(id="vector-db-check-result", className=MB_2),
            html.Div(id="embedding-status-indicator", className=MB_2),
            html.Div(id="vector-search-status-indicator", className=MB_2),
        ],
        className="p-2",
    )


def build_vector_tools_tab():
    """Build the Vector Tools tab for settings modal."""
    return dbc.Tab(
        label="Vector Tools",
        tab_id="tab-vector-tools",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Button(
                            "Test Vector Search",
                            id="btn-test-vector-search",
                            color="success",
                            className=BUTTON_STYLE,
                        ),
                        width=12,
                        className=MB_2,
                    ),
                ]
            ),
            html.Div(id="vector-test-result", className=MB_2),
            html.Hr(),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Store Custom Vector", className="fw-bold"),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("Image Path", size="sm"),
                                            dbc.Input(
                                                id="input-store-image-path",
                                                type="text",
                                                placeholder="/path/to/image.jpg",
                                                size="sm",
                                                className="mb-2 bg-dark text-light",
                                            ),
                                        ],
                                        width=6,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Label("Model Name", size="sm"),
                                            dbc.Input(
                                                id="input-store-model-name",
                                                type="text",
                                                placeholder="nomic-embed-text",
                                                size="sm",
                                                className="mb-2 bg-dark text-light",
                                            ),
                                        ],
                                        width=6,
                                    ),
                                ],
                                className=MB_2,
                            ),
                            dbc.Label("Vector (comma-separated floats)", size="sm"),
                            dbc.Textarea(
                                id="input-store-vector",
                                placeholder="0.123, 0.456, 0.789, ...",
                                rows=3,
                                size="sm",
                                className="mb-2 font-monospace bg-dark text-light",
                            ),
                            dbc.Button(
                                "Store Vector in Database",
                                id="btn-store-vector",
                                color="primary",
                                size="sm",
                                className="w-100 mb-2",
                            ),
                        ],
                        width=12,
                    ),
                ]
            ),
            html.Div(id="vector-store-result", className=MB_2),
        ],
        className="p-2",
    )


def build_api_testers_tab():
    """Build the API Testers tab for settings modal."""
    return dbc.Tab(
        label="API Testers",
        tab_id="tab-api-testers",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H4("Chat Endpoint Test", className="mb-3"),
                            html.P(
                                "Test the /_api/chat endpoint to verify it's working correctly.",
                                className="text-muted small mb-3",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("Test Message", className="fw-bold"),
                                            dbc.Input(
                                                id="chat-endpoint-test-message",
                                                type="text",
                                                placeholder="Try '/about' or 'Hello'",
                                                className="bg-dark text-light mb-2",
                                            ),
                                        ],
                                        width=9,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Label(" "),
                                            dbc.Button(
                                                "Test",
                                                id="btn-test-chat-endpoint",
                                                color="info",
                                                className="w-100",
                                            ),
                                        ],
                                        width=3,
                                        className="d-flex align-items-end",
                                    ),
                                ]
                            ),
                            html.Div(id="chat-endpoint-test-result", className=MB_2),
                        ],
                        className="p-2",
                    ),
                ]
            ),
        ],
    )


def build_photo_testers_tab():
    """Build the Photo Testers tab for settings modal."""
    return dbc.Tab(
        label="Photo Testers",
        tab_id="tab-photo-testers",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H4("Prompt Tester", className="mb-3"),
                            html.P(
                                "Upload a photo and extract features to evaluate prompt quality and model performance.",
                                className="text-muted small mb-3",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("Upload Photo", className="fw-bold"),
                                            dcc.Upload(
                                                id="prompt-tester-upload",
                                                children=dbc.Button(
                                                    "Select Image",
                                                    color="primary",
                                                    className="w-100",
                                                ),
                                                multiple=False,
                                                accept="image/*",
                                                className="mb-2",
                                            ),
                                            html.Div(id="prompt-tester-filename", className="small text-muted mb-2"),
                                        ],
                                        width=12,
                                    ),
                                ]
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("Custom Prompt (optional)", className="fw-bold"),
                                            dbc.Textarea(
                                                id="prompt-tester-prompt",
                                                placeholder="Leave empty to use default prompt...",
                                                rows=3,
                                                className="mb-2 font-monospace bg-dark text-light",
                                            ),
                                            dbc.Button(
                                                "Extract Features",
                                                id="btn-prompt-tester-extract",
                                                color="success",
                                                className="w-100 mb-2",
                                            ),
                                        ],
                                        width=12,
                                    ),
                                ]
                            ),
                            html.Div(id="prompt-tester-progress", className=MB_2),
                            html.Div(id="prompt-tester-result", className=MB_2),
                            dcc.Store(id="prompt-tester-store", data=None, storage_type="memory"),
                            dcc.Store(id="prompt-tester-running", data=False, storage_type="memory"),
                            html.Hr(),
                            html.H4("Metadata Tester", className="mb-3"),
                            html.P(
                                "Upload a photo to extract and view its EXIF metadata (camera info, GPS, dates, etc.).",
                                className="text-muted small mb-3",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Label("Upload Photo", className="fw-bold"),
                                            dcc.Upload(
                                                id="metadata-tester-upload",
                                                children=dbc.Button(
                                                    "Select Image",
                                                    color="primary",
                                                    className="w-100",
                                                ),
                                                multiple=False,
                                                accept="image/*",
                                                className="mb-2",
                                            ),
                                            html.Div(id="metadata-tester-filename", className="small text-muted mb-2"),
                                        ],
                                        width=12,
                                    ),
                                ]
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Button(
                                                "Extract Metadata",
                                                id="btn-metadata-tester-extract",
                                                color="success",
                                                className="w-100 mb-2",
                                            ),
                                        ],
                                        width=12,
                                    ),
                                ]
                            ),
                            html.Div(id="metadata-tester-progress", className=MB_2),
                            html.Div(id="metadata-tester-result", className=MB_2),
                            dcc.Store(id="metadata-tester-store", data=None, storage_type="memory"),
                            dcc.Store(id="metadata-tester-running", data=False, storage_type="memory"),
                        ],
                        className="p-2",
                    ),
                ]
            ),
        ],
    )


def build_errors_tab():
    """Build the Errors tab for settings modal."""
    return dbc.Tab(
        label="Errors",
        tab_id="tab-errors",
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Row(
                                [
                                    dbc.Col("Errors", width="auto"),
                                    dbc.Col(
                                        dbc.Button(
                                            "\u21bb",
                                            id="btn-refresh-errors",
                                            color="light",
                                            size="sm",
                                            title="Refresh errors",
                                            className="ms-2",
                                        ),
                                        width="auto",
                                    ),
                                ],
                                className="w-100 d-flex align-items-center mb-2",
                            ),
                            html.Div(id="errors-count", className=MB_2),
                            html.Div(id="errors-list"),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Button(
                                            "Clear all errors",
                                            id="btn-clear-errors",
                                            color="danger",
                                            size="sm",
                                            className="mt-2",
                                        ),
                                        width=12,
                                    ),
                                ],
                                className="mt-2",
                            ),
                        ],
                        className="p-2",
                    ),
                ]
            ),
        ],
    )


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
