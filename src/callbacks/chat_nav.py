"""Clientside callbacks for chat scroll behaviour and keyboard history navigation.

This module provides:
- ``register_chat_scroll_callback`` — auto-scroll chat to bottom on updates
- ``register_chat_history_navigation_callback`` — UP/DOWN arrow recall of previous messages
"""

from dash import Input, Output


def register_chat_scroll_callback(app):
    """Register clientside callbacks to scroll chat to bottom on update.

    We use two callbacks:
    1. On history store change (triggers when messages are added)
    2. On chat-response children change (triggers when display updates)

    This ensures scrolling works even with async updates.
    """
    # Scroll when history changes
    app.clientside_callback(
        """
        function(history) {
            // Use setTimeout to ensure DOM has fully updated with new messages
            setTimeout(function() {
                var chatContainer = document.getElementById('chat-response-container');
                if (chatContainer) {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            }, 100);
            return "";
        }
        """,
        Output("scroll-dummy", "children"),
        Input("chat-history-store", "data"),
        prevent_initial_call=True,
    )

    # Also scroll when chat response display updates (catches all cases)
    app.clientside_callback(
        """
        function(children) {
            // Use setTimeout to ensure DOM has fully updated
            setTimeout(function() {
                var chatContainer = document.getElementById('chat-response-container');
                if (chatContainer) {
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
            }, 50);
            return children;
        }
        """,
        Output("chat-response", "children", allow_duplicate=True),
        Input("chat-response", "children"),
        prevent_initial_call=True,
    )


def register_chat_history_navigation_callback(app):
    """Register clientside callback for UP/DOWN arrow key navigation through chat history.

    This allows users to press UP to recall previous user messages and DOWN to recall next ones,
    enabling easy navigation through their message history.
    """
    # Single clientside callback: cache user messages AND set up keyboard
    # navigation. Merging these into one callback avoids two clientside
    # callbacks racing on the same Input/Output, which broke Dash's renderer
    # ("Cannot read properties of undefined (reading 'props')").
    app.clientside_callback(
        """
        function(history_data) {
            // Store user messages in global variable for keyboard navigation
            window._chatUserMessages = [];
            if (history_data && Array.isArray(history_data)) {
                for (var i = 0; i < history_data.length; i++) {
                    var entry = history_data[i];
                    if (entry && entry.sender === 'user' && entry.content && typeof entry.content === 'string') {
                        window._chatUserMessages.push(entry.content);
                    }
                }
            }

            // Set up keyboard navigation on the chat input (once only)
            var input = document.getElementById('chat-input');
            if (input && !input._chatNavSetup) {
                input._chatNavSetup = true;

                var current_nav_index = -1;
                var last_input_value = "";

                input.addEventListener('keydown', function(e) {
                    // Only handle UP and DOWN arrows
                    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') {
                        // If user types any other key while navigating, reset
                        if (current_nav_index !== -1) {
                            current_nav_index = -1;
                            last_input_value = input.value;
                        }
                        return;
                    }

                    var user_messages = window._chatUserMessages || [];

                    if (user_messages.length === 0) return;

                    e.preventDefault();

                    if (e.key === 'ArrowUp') {
                        if (current_nav_index === -1) {
                            // First UP press - save current input and go to most recent
                            last_input_value = input.value || "";
                            current_nav_index = 0;
                            input.value = user_messages[user_messages.length - 1];
                        } else if (current_nav_index < user_messages.length - 1) {
                            // Go to older message
                            current_nav_index++;
                            input.value = user_messages[user_messages.length - 1 - current_nav_index];
                        }
                        // If already at oldest, do nothing
                        input.selectionStart = input.selectionEnd = input.value.length;
                    } else if (e.key === 'ArrowDown') {
                        if (current_nav_index > 0) {
                            // Go to newer message
                            current_nav_index--;
                            input.value = user_messages[user_messages.length - 1 - current_nav_index];
                        } else if (current_nav_index === 0) {
                            // At most recent, restore to what user had typed
                            current_nav_index = -1;
                            input.value = last_input_value;
                        }
                        // If already at -1 (no navigation), do nothing
                        input.selectionStart = input.selectionEnd = input.value.length;
                    }
                });

                // Reset navigation when user manually types (not using arrow keys)
                input.addEventListener('input', function(e) {
                    if (current_nav_index !== -1) {
                        current_nav_index = -1;
                        last_input_value = input.value;
                    }
                });
            }

            return "";
        }
        """,
        Output("chat-nav-dummy", "children"),
        Input("chat-history-store", "data"),
        prevent_initial_call=True,
    )
