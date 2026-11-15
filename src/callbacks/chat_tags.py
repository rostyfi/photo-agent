"""Callbacks for chat tag interactions (click, clear, remove).

This module provides:
- ``register_chat_tag_click_callback`` — clicking a tag button sends /tag <tag>
- ``register_chat_tag_clear_callback`` — "Clear" button resets to /tags (list all)
- ``register_chat_tag_remove_callback`` — removing one chip from a tag chain re-queries
"""

import logging

import dash
from dash import Input, Output, State

logger = logging.getLogger(__name__)


def _build_pending(n_clicks_list, chat_history, folder, host, port, model, message):
    """Build the (input, history, pending) return tuple for a tag command.

    Shared by all three tag callbacks so the message-construction logic
    lives in exactly one place.
    """
    if chat_history is None:
        chat_history = []

    user_message_entry = {"sender": "user", "content": message, "type": "text"}
    loading_entry = {"sender": "assistant", "type": "loading", "content": "", "pending_id": len(chat_history)}
    updated_history = [*chat_history, user_message_entry, loading_entry]

    try:
        ollama_port_int = int(port) if port and str(port).strip() else None
    except (ValueError, TypeError):
        ollama_port_int = None

    pending_data = {
        "message": message,
        "host": host if host and str(host).strip() else None,
        "port": ollama_port_int,
        "model": model if model and str(model).strip() else None,
        "folder": folder if folder and str(folder).strip() else None,
        "chat_history": chat_history,
    }

    return "", updated_history, pending_data


def register_chat_tag_click_callback(app):
    """Register callback to handle clicks on tag buttons in chat responses.

    When a user clicks on a tag button, it sends a /tags <tagname> command.
    """

    @app.callback(
        Output("chat-input", "value", allow_duplicate=True),
        Output("chat-history-store", "data", allow_duplicate=True),
        Output("chat-pending-request", "data", allow_duplicate=True),
        Input({"type": "chat-tag-btn", "tag": dash.ALL}, "n_clicks"),
        State({"type": "chat-tag-btn", "tag": dash.ALL}, "id"),
        State("chat-history-store", "data"),
        State("input-folder", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        prevent_initial_call=True,
    )
    def handle_tag_click(n_clicks_list, tag_ids, chat_history, folder, host, port, model):
        """Handle tag button click by sending a /tags <tagname> command."""
        if not n_clicks_list:
            return dash.no_update, dash.no_update, dash.no_update

        # Find which button was clicked
        clicked_tag = None
        for i, n_clicks in enumerate(n_clicks_list):
            if n_clicks and n_clicks > 0:
                if i < len(tag_ids) and tag_ids[i]:
                    try:
                        tag_id = tag_ids[i]
                        if isinstance(tag_id, dict):
                            clicked_tag = tag_id.get("tag")
                        elif isinstance(tag_id, str):
                            # Parse the JSON-like string
                            import json

                            try:
                                parsed = json.loads(tag_id.replace("'", '"'))
                                clicked_tag = parsed.get("tag")
                            except (json.JSONDecodeError, ValueError, AttributeError):
                                clicked_tag = tag_id
                    except Exception:
                        pass
                break

        if not clicked_tag:
            return dash.no_update, dash.no_update, dash.no_update

        # Create the /tag command (singular) to show photos with this specific tag
        message = f"/tag {clicked_tag}"

        return _build_pending(n_clicks_list, chat_history, folder, host, port, model, message)


def register_chat_tag_clear_callback(app):
    """Register callback for the chat "Clear" tag-selection button.

    Resets the tag chain by issuing ``/tags`` (list all tags), mirroring
    the tag-cloud "Clear filters" behavior.
    """

    @app.callback(
        Output("chat-input", "value", allow_duplicate=True),
        Output("chat-history-store", "data", allow_duplicate=True),
        Output("chat-pending-request", "data", allow_duplicate=True),
        Input({"type": "chat-tag-clear-btn", "index": dash.ALL}, "n_clicks"),
        State("chat-history-store", "data"),
        State("input-folder", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        prevent_initial_call=True,
    )
    def handle_tag_clear(n_clicks_list, chat_history, folder, host, port, model):
        """Clear the tag selection by listing all tags."""
        # Pattern-matching with dash.ALL yields an empty list when no Clear
        # button is present on the page; tolerate that gracefully.
        if not n_clicks_list or not any(n and n > 0 for n in n_clicks_list):
            return dash.no_update, dash.no_update, dash.no_update

        message = "/tags"

        return _build_pending(n_clicks_list, chat_history, folder, host, port, model, message)


def register_chat_tag_remove_callback(app):
    """Register callback to remove a single tag from the selected chain.

    Each selected tag is rendered as a removable chip (see
    ``_history_to_messages``). Clicking it re-issues ``/tag`` with the
    remaining tags; if the last tag is removed, it falls back to ``/tags``
    (list all), mirroring the Clear-all behavior.
    """

    @app.callback(
        Output("chat-input", "value", allow_duplicate=True),
        Output("chat-history-store", "data", allow_duplicate=True),
        Output("chat-pending-request", "data", allow_duplicate=True),
        Input({"type": "chat-tag-remove-btn", "index": dash.ALL}, "n_clicks"),
        State({"type": "chat-tag-remove-btn", "index": dash.ALL}, "id"),
        State("chat-history-store", "data"),
        State("input-folder", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        prevent_initial_call=True,
    )
    def handle_tag_remove(n_clicks_list, btn_ids, chat_history, folder, host, port, model):
        """Remove one tag from the selection and re-query."""
        # dash.ALL yields an empty list when no remove chip is on the page.
        if not n_clicks_list or not any(n and n > 0 for n in n_clicks_list):
            return dash.no_update, dash.no_update, dash.no_update

        # Find the clicked chip (first with a fresh click).
        clicked_id = None
        for i, n_clicks in enumerate(n_clicks_list):
            if n_clicks and n_clicks > 0:
                if i < len(btn_ids) and btn_ids[i]:
                    clicked_id = btn_ids[i]
                break

        if not isinstance(clicked_id, dict):
            return dash.no_update, dash.no_update, dash.no_update

        remove_tag = clicked_id.get("remove")
        chain = clicked_id.get("chain")
        if not remove_tag or not chain:
            return dash.no_update, dash.no_update, dash.no_update

        # Rebuild the chain without the removed tag (case-insensitive match,
        # preserving the original casing of the remaining tags).
        remaining = []
        removed = False
        for t in chain.split(","):
            t = t.strip()
            if not t:
                continue
            if not removed and t.lower() == remove_tag.lower():
                removed = True
                continue
            remaining.append(t)

        # If nothing remains, list all tags (same as Clear).
        message = f"/tag {','.join(remaining)}" if remaining else "/tags"

        return _build_pending(n_clicks_list, chat_history, folder, host, port, model, message)
