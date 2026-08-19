"""Callbacks for health check and settings management.

This module contains callbacks for:
- LLM server health check
- Settings modal toggle
- Vector search availability test
- Vector search status indicator
- Embedding generation status
- Vector database check

Vector search operations use the unified availability check.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback_context, html

from src.sqlite_utils import open_connection
from src.vector_search.availability import is_vector_search_available

from .common import _get_app_config, _get_extractor

logger = logging.getLogger(__name__)

# Cache for vector search availability check (doesn't change during runtime)
_VECTOR_SEARCH_AVAILABLE_CACHE = None
_VECTOR_SEARCH_AVAILABLE_CHECKED = False


def register_health_callback(app, create_extractor_fn, app_config):
    @app.callback(
        Output("health-status", "children"),
        Input("btn-health", "n_clicks"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        State("input-backend", "value"),
        State("input-timeout", "value"),
        State("chk-dry-run", "value"),
        prevent_initial_call=True,
    )
    def check_health(n_clicks, host, port, model, backend, timeout, dry_run):
        if n_clicks is None:
            return dash.no_update

        if dry_run:
            return dbc.Alert(
                "Dry-run mode active — no LLM connectivity needed.",
                color="info",
                dismissable=True,
            )

        extractor = _get_extractor(host, port, model, backend, timeout, app_config.default_prompt)
        if extractor.health_check():
            return dbc.Alert(
                f"LLM server is reachable at {extractor.base_url} (model: {extractor.model})",
                color="success",
                dismissable=True,
            )
        else:
            return dbc.Alert(
                f"Cannot reach LLM at {extractor.base_url}. Please check your settings.",
                color="danger",
                dismissable=True,
            )


def register_settings_modal_callback(app):
    @app.callback(
        Output("settings-modal", "is_open"),
        Input("btn-settings", "n_clicks"),
        Input("btn-close-settings", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_settings(open_clicks, close_clicks):
        ctx = callback_context
        if not ctx.triggered:
            return dash.no_update
        prop_id = ctx.triggered[0].get("prop_id", "")
        return "btn-settings" in prop_id


def register_concurrency_setting_callback(app, app_config):
    """Persist the batch concurrency to the active folder's settings file.

    The Settings modal exposes a "Batch concurrency" number input
    (``input-concurrency``). When the user changes it, this callback writes the
    value to ``<active-folder>/.local-photo-agent/settings.json`` so it is read
    at processing start (by ``/process`` and the CLI). It also keeps the
    in-memory ``app_config.batch_concurrency`` in sync as a fallback. Values
    <1 are coerced to 1 (sequential).

    The active folder comes from the hidden ``input-folder`` field.
    """

    @app.callback(
        Output("input-concurrency", "valid"),
        Input("input-concurrency", "value"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def update_concurrency(value, folder):
        try:
            concurrency = int(value) if value is not None else 1
        except (TypeError, ValueError):
            concurrency = 1
        if concurrency < 1:
            concurrency = 1
        app_config.batch_concurrency = concurrency
        # Persist to the per-folder settings file so it survives restarts and
        # is read at processing start. Missing/empty folder just skips the
        # write (the in-memory value still serves as a fallback).
        if folder and str(folder).strip():
            from src.folder_settings import KEY_BATCH_CONCURRENCY, write_folder_setting

            try:
                write_folder_setting(str(folder).strip(), KEY_BATCH_CONCURRENCY, concurrency)
            except OSError as e:
                logger.warning("Could not write folder concurrency setting for %s: %s", folder, e)
        # Mark the input as valid (Dash uses `valid`/`invalid` styling); we
        # always coerce to a valid value, so this is always True.
        return True


def _check_vector_search_status():
    """Check if vector search library is available.

    Uses the unified availability check from vector_search module.
    Uses caching since availability doesn't change during runtime.

    Returns:
        tuple: (is_available, status_message, color)
    """
    global _VECTOR_SEARCH_AVAILABLE_CACHE, _VECTOR_SEARCH_AVAILABLE_CHECKED

    # Return cached result if available
    if _VECTOR_SEARCH_AVAILABLE_CHECKED:
        return _VECTOR_SEARCH_AVAILABLE_CACHE

    try:
        is_available = is_vector_search_available()
        if is_available:
            result = (
                True,
                "✓ Vector search is available - embeddings will be indexed for fast similarity search",
                "success",
            )
        else:
            result = (
                False,
                "sqlite-vec library is not available. Please install the required vector search library.",
                "danger",
            )
    except Exception as e:
        result = False, f"sqlite-vec error: {e}", "danger"

    # Cache the result
    _VECTOR_SEARCH_AVAILABLE_CACHE = result
    _VECTOR_SEARCH_AVAILABLE_CHECKED = True

    return result


def register_vector_test_callback(app, app_config):
    """Register callback to test vector search availability and generate a test embedding.

    Uses the unified availability check from vector_search module.
    """

    @app.callback(
        [
            Output("vector-test-result", "children"),
            Output("input-store-vector", "value"),
            Output("input-store-model-name", "value"),
        ],
        Input("btn-test-vector-search", "n_clicks"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-embedding-model", "value"),
        State("input-embedding-backend", "value"),
        State("chk-embedding-enabled", "value"),
        prevent_initial_call=True,
    )
    def test_vector_search(n_clicks, host, port, embedding_model, embedding_backend, embedding_enabled):
        if n_clicks is None:
            return dash.no_update

        # Use app_config defaults if form values are not provided
        use_host = host or app_config.llm_host
        use_port = int(port) if port else app_config.llm_port
        use_embedding_model = embedding_model or app_config.embedding_model
        use_embedding_backend = embedding_backend or app_config.embedding_backend
        use_embedding_enabled = embedding_enabled if embedding_enabled is not None else app_config.embedding_enabled

        if not use_embedding_enabled:
            return (
                dbc.Alert(
                    "Embedding generation is disabled in settings. Enable it first, then try again.",
                    color="warning",
                    dismissable=True,
                ),
                dash.no_update,
                dash.no_update,
            )

        # Check if vector search library is available
        vec_available = is_vector_search_available()

        if not vec_available:
            return (
                dbc.Alert(
                    [
                        html.Strong("❌ Vector Search Not Available: "),
                        html.Span(
                            "sqlite-vec library is not available. Please install the required vector search library."
                        ),
                    ],
                    color="danger",
                    dismissable=True,
                ),
                dash.no_update,
                dash.no_update,
            )

        # Vector search library is available, now try to generate a test embedding
        try:
            from src.embeddings import create_generator

            generator = create_generator(
                backend=use_embedding_backend,
                host=use_host,
                port=use_port,
                model=use_embedding_model,
                timeout=app_config.timeout,
            )

            # Try to generate an embedding from text (works with text embedding models like nomic-embed-text)
            test_text = "This is a test sentence for vector embedding generation."
            test_vector = None

            try:
                test_vector = generator.generate_from_text(test_text)
            except (RuntimeError, NotImplementedError, AttributeError) as e:
                # This model might not support text embedding
                # Try to check if it's a vision model
                error_msg = str(e).lower()
                if "text" in error_msg or "prompt" in error_msg:
                    # This is likely a vision model, try a different approach
                    # For vision models, we can't easily generate a test without an image
                    # So we'll just verify the generator is initialized correctly
                    pass

            if test_vector is None and hasattr(generator, "health_check"):
                # Try to check if the generator can at least connect to the server
                if generator.health_check():
                    return (
                        dbc.Alert(
                            [
                                html.Strong("✓ Connection Successful, but text embedding not supported: "),
                                html.Br(),
                                html.Small(
                                    [
                                        html.Strong("Backend: "),
                                        f"{use_embedding_backend} at {use_host}:{use_port}",
                                        html.Br(),
                                        html.Strong("Model: "),
                                        f"{use_embedding_model} (vision model - requires image input)",
                                        html.Br(),
                                        html.Span(
                                            "Vector search library is available and ready for vector search operations."
                                        ),
                                    ]
                                ),
                            ],
                            color="info",
                            dismissable=True,
                        ),
                        dash.no_update,
                        use_embedding_model,
                    )
                else:
                    return (
                        dbc.Alert(
                            [
                                html.Strong("⚠️ Embedding Generation Failed: "),
                                html.Span(f"Cannot connect to embedding server at {use_host}:{use_port}"),
                            ],
                            color="warning",
                            dismissable=True,
                        ),
                        dash.no_update,
                        use_embedding_model,
                    )

            # Success! Now test the database by storing and retrieving the vector
            vector_length = len(test_vector)
            vector_preview = ", ".join(f"{v:.6f}" for v in test_vector[:10])

            # Test the database by storing and retrieving the vector
            test_image_path = "/test/vector_search_test.jpg"

            try:
                import json

                from flask import current_app

                # Step 1: Store the vector using the API
                with current_app.test_client() as client:
                    store_response = client.post(
                        "/_api/store_vector",
                        data=json.dumps(
                            {"image_path": test_image_path, "model_name": use_embedding_model, "vector": test_vector}
                        ),
                        content_type="application/json",
                    )
                    store_data = store_response.get_json()

                    if store_response.status_code != 200 or store_data.get("status") != "success":
                        store_error = store_data.get("message", "Unknown error")
                        raise Exception(f"Failed to store vector: {store_error}")

                    # Step 2: Retrieve the vector using the API
                    get_response = client.get(
                        f"/_api/get_vector?image_path={test_image_path}&model_name={use_embedding_model}"
                    )
                    get_data = get_response.get_json()

                    if get_response.status_code != 200 or get_data.get("status") != "success":
                        get_error = get_data.get("message", "Unknown error")
                        raise Exception(f"Failed to retrieve vector: {get_error}")

                    retrieved_vector = get_data.get("vector")

                    # Step 3: Verify the data matches
                    if len(retrieved_vector) != len(test_vector):
                        raise Exception(f"Dimension mismatch: expected {len(test_vector)}, got {len(retrieved_vector)}")

                    # Check values match (with float tolerance)
                    values_match = True
                    for orig, retr in zip(test_vector, retrieved_vector, strict=False):
                        if abs(orig - retr) > 1e-6:
                            values_match = False
                            break

                    if not values_match:
                        raise Exception("Retrieved vector values don't match original")

                    db_test_passed = True
                    db_status = "✓ Database roundtrip successful"
                    db_color = "success"

            except Exception as e:
                db_test_passed = False
                db_status = f"⚠️ Database test failed: {e!s}"
                db_color = "warning"

            content = [
                html.Strong("✓ Vector Search Test Successful! "),
                html.Br(),
                html.Small(
                    [
                        html.Strong("Backend: "),
                        f"{use_embedding_backend} at {use_host}:{use_port}",
                        html.Br(),
                        html.Strong("Model: "),
                        f"{use_embedding_model}",
                        html.Br(),
                        html.Strong("Vector dimension: "),
                        f"{vector_length}",
                        html.Br(),
                        html.Strong("Preview (first 10 values): "),
                        html.Span(
                            vector_preview,
                            className="selectable-text",
                            style={"userSelect": "text", "cursor": "text", "whiteSpace": "pre-wrap"},
                        ),
                        html.Br(),
                        html.Strong("Full vector: "),
                        html.Span(
                            ", ".join(f"{v:.6f}" for v in test_vector),
                            className="selectable-text",
                            style={
                                "userSelect": "text",
                                "cursor": "text",
                                "whiteSpace": "pre-wrap",
                                "fontSize": "0.75rem",
                            },
                        ),
                        html.Br(),
                        html.Strong("Database test: "),
                        html.Span(db_status, className=f"text-{db_color}"),
                    ]
                ),
            ]

            # Format the vector as comma-separated string for the input field
            vector_str = ", ".join(f"{v:.6f}" for v in test_vector)
            return (
                dbc.Alert(
                    content,
                    color="success" if db_test_passed else "warning",
                    dismissable=True,
                ),
                vector_str,
                use_embedding_model,
            )

        except Exception as e:
            error_msg = str(e)
            return (
                dbc.Alert(
                    [
                        html.Strong("❌ Test Failed: "),
                        html.Span(error_msg),
                    ],
                    color="danger",
                    dismissable=True,
                ),
                dash.no_update,
                dash.no_update,
            )


def register_store_vector_callback(app, app_config):
    """Register callback to store a custom vector in the database."""

    @app.callback(
        Output("vector-store-result", "children"),
        Input("btn-store-vector", "n_clicks"),
        State("input-store-image-path", "value"),
        State("input-store-model-name", "value"),
        State("input-store-vector", "value"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def store_vector(n_clicks, image_path, model_name, vector_str, folder):
        if n_clicks is None:
            return dash.no_update

        if not image_path or not image_path.strip():
            return dbc.Alert(
                "Please enter an image path",
                color="warning",
                dismissable=True,
            )

        if not model_name or not model_name.strip():
            return dbc.Alert(
                "Please enter a model name",
                color="warning",
                dismissable=True,
            )

        if not vector_str or not vector_str.strip():
            return dbc.Alert(
                "Please enter a vector (comma-separated floats)",
                color="warning",
                dismissable=True,
            )

        # Parse the vector
        try:
            # Clean the string: remove whitespace, brackets, etc.
            cleaned = vector_str.strip().replace("[", "").replace("]", "").replace(" ", "")
            vector = [float(x.strip()) for x in cleaned.split(",") if x.strip()]

            if len(vector) == 0:
                return dbc.Alert(
                    "Invalid vector format. Please enter comma-separated floats.",
                    color="danger",
                    dismissable=True,
                )
        except ValueError as e:
            return dbc.Alert(
                f"Invalid vector format: {e}. Please enter comma-separated floats.",
                color="danger",
                dismissable=True,
            )

        # Check if we have a folder selected
        if not folder:
            return dbc.Alert(
                "Please select a folder first (use the folder input in the main UI)",
                color="warning",
                dismissable=True,
            )

        # Store the vector using the API endpoint
        try:
            import json

            from flask import current_app

            # Use the same API endpoint that we created
            # Prepare the request data
            request_data = {"image_path": image_path, "model_name": model_name, "vector": vector}

            # Make an internal POST request to our API
            with current_app.test_client() as client:
                response = client.post(
                    "/_api/store_vector", data=json.dumps(request_data), content_type="application/json"
                )

                response_data = response.get_json()

                if response.status_code != 200 or response_data.get("status") != "success":
                    error_msg = response_data.get("message", "Unknown error")
                    if response.status_code == 500:
                        error_msg = response_data.get("traceback", error_msg)
                    raise Exception(error_msg)

                vec_available = response_data.get("vec_available", False)

            # Build success message
            content = [
                html.Strong("✓ Vector stored successfully! "),
                html.Br(),
                html.Small(
                    [
                        html.Strong("Image: "),
                        image_path,
                        html.Br(),
                        html.Strong("Model: "),
                        model_name,
                        html.Br(),
                        html.Strong("Dimension: "),
                        f"{len(vector)}",
                    ]
                ),
            ]

            # Add vector search status
            if not vec_available:
                content.append(html.Br())
                content.append(
                    html.Small(
                        [
                            html.Strong("Note: "),
                            "sqlite-vec library is not available. Embedding saved to metadata only. ",
                            html.Span(
                                "Vector similarity search requires sqlite-vec to be properly loaded.",
                                className="text-muted",
                            ),
                        ],
                        className="text-warning",
                    )
                )
            else:
                content.append(html.Br())
                content.append(
                    html.Small(
                        [
                            html.Strong("Note: "),
                            html.Span(
                                "Vector stored in both metadata and vector search index (padded to 2048 dimensions).",
                                className="text-success",
                            ),
                        ]
                    )
                )

            return dbc.Alert(
                content,
                color="success" if vec_available else "warning",
                dismissable=True,
            )

        except Exception as e:
            error_msg = str(e)
            return dbc.Alert(
                [
                    html.Strong("❌ Failed to store vector: "),
                    html.Span(error_msg),
                ],
                color="danger",
                dismissable=True,
            )


def _check_embedding_status(host, port, backend, app_config):
    """Check embedding generation availability.

    Returns:
        tuple: (is_available, status_message, color)
    """
    if not app_config.embedding_enabled:
        return True, "Embeddings disabled in settings", "secondary"

    try:
        from src.embeddings import create_generator

        generator = create_generator(
            backend=backend or app_config.embedding_backend,
            host=host or app_config.llm_host,
            port=int(port) if port else app_config.llm_port,
            model=app_config.embedding_model,
        )
        if generator.health_check():
            return (
                True,
                f"Embeddings available (backend: {backend or app_config.embedding_backend}, model: {app_config.embedding_model})",
                "success",
            )
        else:
            return (
                False,
                "Ollama server running but embeddings endpoint not available (requires Ollama v0.1.0+)",
                "warning",
            )
    except ValueError as e:
        if "Unknown embedding backend" in str(e):
            return False, f"Unknown embedding backend: {backend or app_config.embedding_backend}", "danger"
        return False, str(e), "danger"
    except Exception as e:
        error_msg = str(e)
        if "Connection" in error_msg or "refused" in error_msg or "timeout" in error_msg.lower():
            return (
                False,
                f"Cannot connect to embedding server at {host or app_config.llm_host}:{port or app_config.llm_port}",
                "danger",
            )
        return False, f"Embedding error: {error_msg}", "danger"


def register_embedding_status_indicator_callback(app, app_config):
    """Register callback to show embedding generation status."""

    @app.callback(
        Output("embedding-status-indicator", "children"),
        Input("input-host", "value"),
        Input("input-port", "value"),
        Input("input-backend", "value"),
        Input("input-embedding-model", "value"),
        Input("input-embedding-backend", "value"),
        Input("chk-embedding-enabled", "value"),
        prevent_initial_call=False,
    )
    def update_embedding_status(host, port, backend, embedding_model, embedding_backend, embedding_enabled):
        # Build a temporary config with the current form values
        config = _get_app_config()

        # Use form values if provided, otherwise use config defaults
        use_host = host or config.llm_host
        use_port = int(port) if port else config.llm_port
        use_backend = backend or config.llm_backend
        use_embedding_model = embedding_model or config.embedding_model
        use_embedding_backend = embedding_backend or config.embedding_backend
        use_embedding_enabled = embedding_enabled if embedding_enabled is not None else config.embedding_enabled

        # Create a temporary config for checking
        class TempConfig:
            pass

        temp_config = TempConfig()
        temp_config.llm_host = use_host
        temp_config.llm_port = use_port
        temp_config.llm_backend = use_backend
        temp_config.embedding_enabled = use_embedding_enabled
        temp_config.embedding_model = use_embedding_model
        temp_config.embedding_backend = use_embedding_backend

        is_available, message, color = _check_embedding_status(host, port, backend, temp_config)

        # Build selectable content with copy button
        content = [
            html.Span(
                message,
                style={"userSelect": "text", "cursor": "text", "whiteSpace": "pre-wrap"},
                className="selectable-text me-2",
            ),
            dbc.Button(
                "📋",
                id="btn-copy-embedding-status",
                color="light",
                size="sm",
                className="p-0",
                title="Copy status message",
                style={"width": "24px", "height": "24px"},
            ),
        ]

        if is_available:
            return dbc.Alert(
                content,
                color=color,
                dismissable=False,
                className="mb-0 d-flex align-items-center",
            )
        else:
            return dbc.Alert(
                [html.Strong("⚠️ Embedding Generation Unavailable: "), *content],
                color=color,
                dismissable=False,
                className="mb-0 d-flex align-items-center",
            )

    # Add clientside callback for copying
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) {
                return window.dash_clientside.no_update;
            }
            const spans = document.querySelectorAll('#embedding-status-indicator .selectable-text');
            if (spans.length > 0) {
                const text = Array.from(spans).map(s => s.textContent).join(' ');
                navigator.clipboard.writeText(text).then(function() {
                    console.log("Copied embedding status to clipboard");
                }).catch(function(err) {
                    console.error("Failed to copy:", err);
                });
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("embedding-status-indicator", "children", allow_duplicate=True),
        Input("btn-copy-embedding-status", "n_clicks"),
        prevent_initial_call=True,
    )


def register_vector_search_status_callback(app):
    """Register callback to show vector search status.

    Uses the unified availability check from vector_search module.
    """

    @app.callback(
        Output("vector-search-status-indicator", "children"),
        Input("poll-interval", "n_intervals"),
        prevent_initial_call=False,
    )
    def update_vector_search_status(n_intervals):
        is_available, message, color = _check_vector_search_status()

        # Build selectable content with copy button
        content = [
            html.Span(
                message,
                id="vector-status-msg",
                style={"userSelect": "text", "cursor": "text", "whiteSpace": "pre-wrap"},
                className="selectable-text me-2",
            ),
            dbc.Button(
                "📋",
                id="btn-copy-vector-status",
                color="light",
                size="sm",
                className="p-0",
                title="Copy status message",
                style={"width": "24px", "height": "24px"},
            ),
        ]

        if is_available:
            return dbc.Alert(
                content,
                color=color,
                dismissable=False,
                className="mb-0 d-flex align-items-center",
            )
        else:
            return dbc.Alert(
                [
                    html.Strong("⚠️ Vector Search Unavailable: "),
                    html.Span(
                        "Embeddings will be saved to metadata only. Vector similarity search requires sqlite-vec. ",
                        style={"userSelect": "text", "cursor": "text"},
                        className="selectable-text",
                    ),
                    *content,
                ],
                color=color,
                dismissable=False,
                className="mb-0 d-flex align-items-center",
            )

    # Add clientside callback for copying
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) {
                return window.dash_clientside.no_update;
            }
            const msg = document.getElementById('vector-status-msg');
            if (msg) {
                navigator.clipboard.writeText(msg.textContent).then(function() {
                    console.log("Copied vector status to clipboard");
                }).catch(function(err) {
                    console.error("Failed to copy:", err);
                });
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("vector-search-status-indicator", "children", allow_duplicate=True),
        Input("btn-copy-vector-status", "n_clicks"),
        prevent_initial_call=True,
    )


def register_vector_db_check_callback(app):
    """Register callback to check vector database and list embeddings."""

    @app.callback(
        Output("vector-db-check-result", "children"),
        Input("btn-check-vector-db", "n_clicks"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def check_vector_db(n_clicks, folder):
        if n_clicks is None or not folder:
            return dbc.Alert(
                "Please select a folder first",
                color="warning",
                dismissable=True,
            )

        try:
            import os

            from src.sidecar.database import FeaturesDatabase

            db_path = FeaturesDatabase.default_db_path(folder)

            # Check if database exists
            if not os.path.exists(db_path):
                return dbc.Alert(
                    f"No database found at {db_path}",
                    color="warning",
                    dismissable=True,
                )

            # Read from image_embeddings table
            conn = open_connection(db_path)
            try:
                rows = conn.execute(
                    "SELECT image_path, model_name, embedding_dimension, created_at FROM image_embeddings ORDER BY created_at DESC"
                ).fetchall()

                if not rows:
                    return dbc.Alert(
                        f"No embeddings found in database at {db_path}",
                        color="info",
                        dismissable=True,
                    )

                # Build list with vectors
                embedding_list = []
                for row in rows:
                    image_path, model_name, dimension, created_at = row

                    # Try to get the vector
                    vector = None
                    try:
                        db = FeaturesDatabase(db_path)
                        vector = db.get_embedding(image_path, model_name)
                        db.close()
                    except Exception as e:
                        logger.debug("Failed to retrieve embedding for display (%s): %s", image_path, e, exc_info=True)

                    # Format vector for display
                    if vector:
                        vector_preview = ", ".join(f"{v:.6f}" for v in vector[:5])
                        if len(vector) > 5:
                            vector_preview += f", ... ({len(vector)} total)"
                        full_vector_str = ", ".join(f"{v:.6f}" for v in vector)
                        vector_details = html.Div(
                            [
                                html.Small("Vector: ", className="text-muted"),
                                html.Pre(
                                    full_vector_str,
                                    style={
                                        "fontSize": "0.75rem",
                                        "whiteSpace": "pre-wrap",
                                        "wordBreak": "break-all",
                                        "maxHeight": "100px",
                                        "overflowY": "auto",
                                        "backgroundColor": "#f8f9fa",
                                        "padding": "8px",
                                        "borderRadius": "4px",
                                        "marginTop": "4px",
                                        "border": "1px solid #dee2e6",
                                    },
                                ),
                            ]
                        )
                        status = "✓ Vector saved"
                        color = "success"
                    else:
                        vector_details = html.Span("No vector data", className="text-muted")
                        status = "✗ Vector missing"
                        color = "warning"
                        vector_preview = "N/A"

                    embedding_list.append(
                        dbc.ListGroupItem(
                            [
                                html.Div(
                                    [
                                        html.Strong(f"{image_path} "),
                                        html.Span(f"[{model_name}, {dimension}d]", className="text-muted"),
                                        html.Br(),
                                        html.Small(
                                            [
                                                html.Span(f"Created: {created_at} | ", className="text-muted"),
                                                html.Span(f"Status: {status}", className=f"text-{color}"),
                                            ]
                                        ),
                                        html.Br(),
                                        html.Small(
                                            [
                                                html.Span(f"Preview: {vector_preview}", className="text-muted"),
                                            ]
                                        ),
                                        vector_details,
                                    ]
                                ),
                            ]
                        )
                    )

                return dbc.Alert(
                    [
                        html.H5(f"Vector Database Status ({len(rows)} embeddings)"),
                        html.Hr(),
                        dbc.ListGroup(embedding_list, style={"maxHeight": "400px", "overflowY": "auto"}),
                    ],
                    color="info",
                    dismissable=True,
                )

            finally:
                conn.close()

        except Exception as e:
            import traceback

            logger.error("Error in check_vector_db: %s", e)
            logger.error(traceback.format_exc())
            return dbc.Alert(
                f"Error checking vector database: {e!s}",
                color="danger",
                dismissable=True,
            )
