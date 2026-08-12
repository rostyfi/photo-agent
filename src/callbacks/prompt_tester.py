"""Callbacks for the prompt tester feature in settings.

This module provides callbacks for:
- Handling file upload for prompt testing
- Extracting features from uploaded images
- Displaying extraction results for prompt evaluation
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from src.interfaces import ProcessingResult
from src.constants import DEFAULT_LLM_HOST, DEFAULT_LLM_PORT, DEFAULT_LLM_TIMEOUT
from plugins.llm import create_extractor

logger = logging.getLogger(__name__)


def _get_extractor(host, port, model, backend, timeout, default_prompt):
    """Create and return an extractor with the given parameters."""
    return create_extractor(
        backend=backend or "ollama",
        host=host or DEFAULT_LLM_HOST,
        port=int(port) if port else DEFAULT_LLM_PORT,
        model=model,
        timeout=int(timeout) if timeout else DEFAULT_LLM_TIMEOUT,
        default_prompt=default_prompt,
    )


def build_extraction_result(contents, filename, result: ProcessingResult, dry_run=False):
    """Build the result display component for extracted features."""
    import json
    
    # Decode the base64 image for display
    if contents.startswith("data:"):
        # Extract the base64 part after the comma
        header, encoded = contents.split(",", 1)
        image_b64 = encoded
    else:
        image_b64 = contents
    
    # Parse the response if it's JSON
    parsed_response = None
    if result.response:
        try:
            # Try to parse as JSON
            parsed_response = json.loads(result.response)
        except (json.JSONDecodeError, TypeError):
            # Not JSON, use raw response
            parsed_response = result.response
    
    # Build the result display
    result_items = []
    
    # Add image preview
    result_items.append(
        html.Div([
            html.H6("Image Preview:", className="mt-2 mb-2"),
            html.Img(
                src=contents,
                style={
                    "maxWidth": "100%",
                    "maxHeight": "300px",
                    "objectFit": "contain",
                    "border": "1px solid #dee2e6",
                    "borderRadius": "4px",
                    "backgroundColor": "#f8f9fa",
                },
            ),
            html.Small(f"Filename: {filename}", className="text-muted"),
        ])
    )
    
    # Add model info
    result_items.append(
        html.Div([
            html.H6("Model Information:", className="mt-3 mb-2"),
            html.Div([
                html.Span(f"Model: {result.model}", className="me-3"),
                html.Span(f"Duration: {result.total_duration_ms:.1f}ms" if result.total_duration_ms else "Duration: N/A"),
                html.Span(f" | Eval Count: {result.eval_count}" if result.eval_count else ""),
            ], className="text-muted small"),
        ])
    )
    
    # Add parsed response if available
    if result.parsed:
        result_items.append(
            html.Div([
                html.H6("Parsed Features:", className="mt-3 mb-2"),
                html.Pre(
                    json.dumps(result.parsed, indent=2, ensure_ascii=False),
                    style={
                        "backgroundColor": "#f8f9fa",
                        "padding": "10px",
                        "borderRadius": "4px",
                        "border": "1px solid #dee2e6",
                        "maxHeight": "400px",
                        "overflowY": "auto",
                        "whiteSpace": "pre-wrap",
                        "wordBreak": "break-all",
                    },
                    className="selectable-text",
                ),
            ])
        )
    
    # Add raw response
    result_items.append(
        html.Div([
            html.H6("Raw Response:", className="mt-3 mb-2"),
            dbc.Collapse(
                [
                    html.Pre(
                        result.response,
                        style={
                            "backgroundColor": "#f8f9fa",
                            "padding": "10px",
                            "borderRadius": "4px",
                            "border": "1px solid #dee2e6",
                            "maxHeight": "400px",
                            "overflowY": "auto",
                            "whiteSpace": "pre-wrap",
                            "wordBreak": "break-all",
                        },
                        className="selectable-text",
                    ),
                ],
                id="collapse-raw-response",
                is_open=False,
            ),
            dbc.Button(
                "Show Raw Response",
                id="btn-toggle-raw-response",
                color="light",
                size="sm",
                className="mt-1",
            ),
        ])
    )
    
    # Add error if present
    if result.error:
        result_items.append(
            html.Div([
                html.H6("Error:", className="mt-3 mb-2"),
                dbc.Alert(
                    result.error,
                    color="danger",
                    dismissable=False,
                ),
            ])
        )
    
    # Add dry-run notice if applicable
    if dry_run:
        result_items.append(
            html.Div([
                dbc.Alert(
                    "This was a dry-run extraction. No actual LLM calls were made.",
                    color="info",
                    dismissable=True,
                ),
            ])
        )
    
    return dbc.Card([
        dbc.CardHeader(html.H5("Extraction Result")),
        dbc.CardBody(result_items),
    ], className="mt-3")


def register_prompt_tester_callbacks(app, create_extractor_fn, app_config):
    """Register all callbacks for the prompt tester feature.
    
    Args:
        app: Dash application instance
        create_extractor_fn: Function to create extractors
        app_config: AppConfig instance
    """
    
    @app.callback(
        [
            Output("prompt-tester-store", "data"),
            Output("prompt-tester-filename", "children"),
        ],
        Input("prompt-tester-upload", "contents"),
        State("prompt-tester-upload", "filename"),
        prevent_initial_call=True,
    )
    def store_upload(contents, filename):
        """Store the uploaded image content in a Store component and display filename."""
        if contents is None:
            return dash.no_update, dash.no_update
        
        # Display filename
        filename_display = f"Selected: {filename}" if filename else "Image uploaded"
        
        # Return the contents to store it and the filename display
        return contents, filename_display

    @app.callback(
        Output("prompt-tester-running", "data"),
        Input("btn-prompt-tester-extract", "n_clicks"),
        prevent_initial_call=True,
    )
    def set_running_state(n_clicks):
        """Set the running state when extract button is clicked."""
        if n_clicks is None:
            return dash.no_update
        # Start with running=True, the extract callback will set it to False when done
        return True

    @app.callback(
        Output("btn-prompt-tester-extract", "children"),
        Input("prompt-tester-running", "data"),
        prevent_initial_call=True,
    )
    def update_extract_button_text(is_running):
        """Update the extract button text based on running state."""
        if is_running is None or is_running == dash.no_update:
            return dash.no_update
        if is_running:
            return "Running..."
        return "Extract Features"

    @app.callback(
        [
            Output("collapse-raw-response", "is_open"),
            Output("btn-toggle-raw-response", "children"),
        ],
        Input("btn-toggle-raw-response", "n_clicks"),
        State("collapse-raw-response", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_raw_response(n_clicks, is_open):
        """Toggle the raw response collapse section and update button text."""
        if n_clicks is None:
            return dash.no_update, dash.no_update
        new_is_open = not is_open
        button_text = "Hide Raw Response" if new_is_open else "Show Raw Response"
        return new_is_open, button_text

    @app.callback(
        [
            Output("prompt-tester-progress", "children"),
            Output("prompt-tester-result", "children"),
            Output("prompt-tester-running", "data"),
        ],
        Input("btn-prompt-tester-extract", "n_clicks"),
        State("prompt-tester-store", "data"),
        State("prompt-tester-upload", "filename"),
        State("prompt-tester-prompt", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        State("input-backend", "value"),
        State("input-timeout", "value"),
        State("chk-dry-run", "value"),
        prevent_initial_call=True,
    )
    def extract_features(
        n_clicks,
        contents,
        filename,
        custom_prompt,
        host,
        port,
        model,
        backend,
        timeout,
        dry_run,
    ):
        """Extract features from the uploaded image using the configured extractor."""
        if n_clicks is None:
            return dash.no_update, dash.no_update, dash.no_update
        
        if contents is None:
            error_alert = dbc.Alert(
                [
                    html.Strong("⚠️ No image uploaded "),
                    html.Br(),
                    "Please select an image using the 'Select Image' button before extracting features.",
                ],
                color="warning",
                dismissable=True,
            )
            return dash.no_update, error_alert, False
        
        # Progress indicator
        progress = dbc.Alert(
            [
                html.Span("Extracting features... ", className="me-2"),
                dbc.Spinner(size="sm", color="primary"),
            ],
            color="info",
            dismissable=False,
        )
        
        try:
            # Create extractor
            if dry_run:
                extractor = create_extractor("dry_run")
            else:
                extractor = _get_extractor(
                    host, port, model, backend, timeout, app_config.default_prompt
                )
            
            # Decode the base64 image content
            # The upload content format is: "data:image/png;base64,<base64_data>"
            if contents.startswith("data:"):
                # Extract the base64 part after the comma
                header, encoded = contents.split(",", 1)
                image_b64 = encoded
            else:
                image_b64 = contents
            
            # Use the custom prompt or default
            prompt = custom_prompt if custom_prompt and custom_prompt.strip() else None
            
            # Extract features using base64
            result: ProcessingResult = extractor.extract_b64(
                image_b64=image_b64,
                prompt=prompt,
                options=None,
            )
            
            # Build the result display with image preview
            result_component = build_extraction_result(contents, filename, result, dry_run)
            
            return progress, result_component, False
            
        except Exception as e:
            logger.error(f"Error in prompt tester extraction: {e}", exc_info=True)
            error_msg = f"Error extracting features: {str(e)}"
            error_component = dbc.Alert(
                [
                    html.Strong("Extraction Failed: "),
                    html.Span(error_msg),
                ],
                color="danger",
                dismissable=True,
            )
            return progress, error_component, False
