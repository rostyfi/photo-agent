"""Builder for the errors display panel."""

import datetime
import os
from typing import Any

import dash_bootstrap_components as dbc
from dash import html


def build_errors_display(errors: list[dict], folder: str) -> html.Div:
    """Build a display of failed images with their error messages.

    Args:
        errors: List of error dicts with keys: image_path, error_code, error_msg, ts
        folder: Current folder path

    Returns:
        A dash.html.Div containing the error list or an empty-state message.
    """
    if not errors:
        return html.Div(
            dbc.Alert(
                [
                    html.Span("✓ ", className="me-2"),
                    "No errors found. All images processed successfully.",
                ],
                color="success",
                className="mb-0",
            )
        )

    # Sort by timestamp (newest first)
    sorted_errors = sorted(errors, key=lambda x: x.get("ts", ""), reverse=True)

    items: list[Any] = []
    for error in sorted_errors:
        image_path = error.get("image_path", "unknown")
        error_code = error.get("error_code", "unknown")
        error_msg = error.get("error_msg", "No error message")
        ts = error.get("ts", "")

        # Extract just the filename for display
        filename = os.path.basename(image_path)

        # Format timestamp
        try:
            dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ts_display = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            ts_display = ts[:19] if ts else "unknown"

        # Build error card
        items.append(
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.Div(
                                [
                                    html.Strong(filename, className="me-2"),
                                    dbc.Badge(
                                        error_code or "error",
                                        color="danger",
                                        className="me-2",
                                    ),
                                    html.Small(
                                        ts_display,
                                        className="text-muted",
                                    ),
                                ],
                                className="d-flex align-items-center mb-2",
                            ),
                            html.Div(
                                [
                                    html.Strong("Error: ", className="text-danger"),
                                    html.Span(
                                        error_msg,
                                        id={"type": "error-msg", "index": len(items)},
                                        className="selectable-text",
                                    ),
                                    dbc.Button(
                                        "📋",
                                        id={"type": "btn-copy-error", "index": len(items)},
                                        color="light",
                                        size="sm",
                                        className="ms-2 p-0",
                                        title="Copy error message",
                                        style={"width": "24px", "height": "24px"},
                                    ),
                                ],
                                className="mb-2 d-flex align-items-center",
                            ),
                            html.Div(
                                [
                                    html.Strong("Path: "),
                                    html.Code(image_path, className="text-muted small"),
                                ],
                                className="mb-1",
                            ),
                        ]
                    ),
                ],
                className="mb-2 shadow-sm",
            )
        )

    return html.Div(
        [
            dbc.Alert(
                [
                    html.Span(f"⚠ {len(errors)} error(s) found", className="me-2"),
                    dbc.Button(
                        "Clear all",
                        id="btn-clear-errors",
                        color="link",
                        size="sm",
                        className="p-0 ms-2",
                    ),
                ],
                color="warning",
                className="mb-3",
            ),
            html.Div(items),
        ]
    )
