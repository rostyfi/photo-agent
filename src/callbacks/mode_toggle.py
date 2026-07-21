"""Callback for mode toggle functionality."""

from dash import Input, Output, State


def register_mode_toggle_callback(app):
    """Register callback for toggling between Agentic and Tools modes."""
    
    @app.callback(
        [
            Output("tools-section", "style"),
            Output("chat-section", "style"),
            Output("mode-store", "data"),
        ],
        Input("mode-toggle", "value"),
    )
    def toggle_mode(mode: str):
        """Toggle visibility between tools and chat sections based on mode selection."""
        if mode == "tools":
            return {"display": "block"}, {"display": "none"}, mode
        else:
            # Agentic mode - hide tools, show chat
            return {"display": "none"}, {"display": "flex", "flexDirection": "column", "height": "85vh", "overflow": "hidden"}, mode


def register_mode_visibility_callback(app):
    """Register callback to control visibility based on mode store for other updates."""
    
    @app.callback(
        [
            Output("tools-section", "style"),
            Output("chat-section", "style"),
        ],
        Input("mode-store", "data"),
    )
    def update_visibility(mode: str):
        """Update visibility of sections based on mode store."""
        if mode == "tools":
            return {"display": "block"}, {"display": "none"}
        else:
            # Agentic mode is default - hide tools, show chat
            return {"display": "none"}, {"display": "flex", "flexDirection": "column", "height": "85vh", "overflow": "hidden"}


def register_mode_sync_callback(app):
    """Register callback to sync mode-toggle value from mode-store on initial load."""
    
    @app.callback(
        Output("mode-toggle", "value"),
        Input("mode-store", "data"),
        prevent_initial_call=True,
    )
    def sync_mode_toggle(mode: str):
        """Sync the radio button value with the mode store."""
        return mode
