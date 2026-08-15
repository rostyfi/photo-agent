"""
Main layout for the Local Photo Agent web UI.

This module builds the complete Dash Bootstrap layout by composing
reusable component functions from layout_components.py.
"""

from datetime import datetime

import dash_bootstrap_components as dbc
from dash import html, dcc

from src.config import AppConfig
from src.components import build_chat_interface
from src.layout_components import (
    build_settings_modal,
    build_sql_explorer_modal,
    build_detail_modal,
    build_fullscreen_modal,
    build_tools_section,
)

# Captured once at process start so the footer shows when the running
# container booted. Lets users confirm their browser is on the latest build.
_BUILD_STAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_layout(app_config: AppConfig):
    """Build the full Dash Bootstrap layout for the web UI.

    Returns a ``dbc.Container`` containing the Settings card, Process Server
    Folder card, polling interval, and footer.
    """
    return dbc.Container(
        [
            # CSS Links
            html.Link(
                rel="stylesheet",
                href="/assets/settings_modal.css",
            ),
            html.Link(
                rel="stylesheet",
                href="/assets/chat.css",
            ),

            # Header Row
            dbc.Row(
                [
                    dbc.Col(
                        dbc.RadioItems(
                            id="mode-toggle",
                            options=[
                                {"label": "Agentic", "value": "agentic"},
                                {"label": "Tools", "value": "tools"},
                            ],
                            value="agentic",
                            inline=True,
                            className="mb-0",
                        ),
                        width=2,
                        className="mb-3",
                    ),
                    dbc.Col(
                        html.H2("Local Photo Agent", className="text-center my-3"),
                        width=8,
                        className="d-flex justify-content-center",
                    ),
                    dbc.Col(
                        [
                            dbc.Button(
                                html.Span("⚙", style={"fontSize": "24px", "color": "#f8f9fa"}),
                                id="btn-settings",
                                title="Settings",
                                style={"width": "48px", "height": "48px", "backgroundColor": "#343a40", "borderColor": "#343a40"},
                                className="d-flex align-items-center justify-content-center",
                            ),
                            dbc.Button(
                                html.Span("🗄", style={"fontSize": "24px", "color": "#f8f9fa"}),
                                id="btn-sql-explorer",
                                title="SQL Explorer",
                                style={"width": "48px", "height": "48px", "backgroundColor": "#343a40", "borderColor": "#343a40"},
                                className="d-flex align-items-center justify-content-center mx-2",
                            ),
                        ],
                        width=2,
                        className="d-flex align-items-center justify-content-end",
                    ),
                ],
                className="align-items-center",
            ),

            # Modals
            build_settings_modal(app_config),
            build_sql_explorer_modal(),

            # Tools section (hidden by default, shown when mode is "tools")
            build_tools_section(app_config),

            # Chat section (hidden by default, shown when mode is "agentic")
            html.Div(
                id="chat-section",
                style={"display": "flex", "flexDirection": "column", "height": "85vh", "overflow": "hidden"},
                children=[build_chat_interface()],
            ),

            # Modals for photo viewing
            build_detail_modal(),
            build_fullscreen_modal(),

            # Poll interval for queue status
            # Increased from 1000ms to 5000ms to reduce CPU usage from constant file I/O
            dbc.Row(
                dbc.Col(
                    dcc.Interval(id="poll-interval", interval=5000, n_intervals=0),
                )
            ),

            # Stores (persistent state)
            dcc.Store(id="folder-cache", data={}),
            dcc.Store(id="photo-list-store", data={"paths": [], "index": None}),
            dcc.Store(id="tag-cloud-data-store", data=None),
            dcc.Store(id="selected-tags-store", data=[]),
            dcc.Store(id="similar-photos-store", data=None),
            dcc.Store(id="errors-store", data={"errors": [], "folder": None}),
            dcc.Store(id="chat-history-store", data=[], storage_type="local"),
            dcc.Store(id="chat-pending-request", data=None, storage_type="memory"),
            dcc.Store(id="mode-store", data="agentic", storage_type="local"),

            # Dummy elements for keyboard and scroll handling
            html.Div(id="keyboard-dummy", style={"display": "none"}),
            html.Div(id="scroll-dummy", style={"display": "none"}),
            html.Div(id="chat-nav-dummy", style={"display": "none"}),
            html.Div(id="reveal-dummy", style={"display": "none"}),

            # Footer
            html.Footer(
                html.P(
                    [
                        f"Local Photo Agent · {datetime.now().year} · build {_BUILD_STAMP}",
                    ],
                    className="text-center text-muted mb-0",
                )
            ),
        ],
        fluid=True,
        className="py-3",
    )
