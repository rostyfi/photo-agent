"""Builder for the chat interface card."""

import dash_bootstrap_components as dbc
from dash import dcc, html


def build_chat_interface():
    """Build the simple chat interface component.

    Returns:
        A dbc.Card containing input, send button, and response textbox.
    """
    return dbc.Card(
        [
            dbc.CardHeader(
                html.H5("Chat with your photos", className="mb-0 d-flex align-items-center"),
            ),
            dbc.CardBody(
                [
                    # Response display (textbox above input) - fills available space
                    html.Div(
                        id="chat-response-container",
                        style={
                            "flex": "1 1 auto",
                            "minHeight": "100px",
                            "padding": "10px",
                            "backgroundColor": "#212529",
                            "borderRadius": "5px",
                            "marginBottom": "15px",
                            "overflowY": "auto",
                            "color": "#f8f9fa",
                            "position": "relative",
                        },
                        children=[
                            # Actual chat response content
                            html.Div(
                                id="chat-response",
                                style={
                                    "whiteSpace": "pre-wrap",
                                },
                                className="chat-response-content",
                            ),
                        ],
                    ),
                    # Live processing progress bar — populated by clientside
                    # polling of /_api/process_status when /process or /status
                    # is invoked. Hidden until processing is active.
                    html.Div(
                        id="chat-progress-bar",
                        style={"display": "none", "marginBottom": "15px"},
                    ),
                    # Input and buttons container
                    html.Div(
                        [
                            # Input area with Send and Clear Chat buttons inline
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dcc.Input(
                                            id="chat-input",
                                            type="text",
                                            placeholder="Type a message or use /about, /tools...",
                                            className="bg-dark text-light",
                                            style={
                                                "width": "100%",
                                                "padding": "0.5rem",
                                                "border": "1px solid #495057",
                                                "borderRadius": "0.25rem",
                                                "height": "38px",
                                            },
                                            debounce=True,
                                        ),
                                        width=8,
                                        className="pe-1",
                                    ),
                                    dbc.Col(
                                        dbc.Button(
                                            "Clear Chat",
                                            id="btn-clear-chat",
                                            color="secondary",
                                            className="w-100",
                                            style={"height": "38px"},
                                        ),
                                        width=2,
                                        className="px-1",
                                    ),
                                    dbc.Col(
                                        dbc.Button(
                                            "Send",
                                            id="chat-send",
                                            color="primary",
                                            className="w-100",
                                            style={"height": "38px"},
                                        ),
                                        width=2,
                                        className="ps-1",
                                    ),
                                ],
                                className="g-0 mb-2 align-items-center",
                            ),
                        ],
                        style={"flex": "0 0 auto"},
                    ),
                ],
                style={"display": "flex", "flexDirection": "column", "height": "100%", "overflow": "hidden"},
            ),
        ],
        className="mb-4 d-flex flex-column",
        style={"width": "100%", "marginLeft": "auto", "marginRight": "auto", "height": "100%", "maxWidth": "1400px"},
    )
