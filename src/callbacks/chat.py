"""Callbacks for the chat interface.

This module provides callbacks for:
- Sending messages to the chat endpoint and receiving responses
- Handling the /whoami tool command
"""

import logging
import json
from typing import Any, Dict, Optional

import requests

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, dcc, callback_context

logger = logging.getLogger(__name__)


def whoami_tool() -> str:
    """Return the agent description for the /whoami command."""
    return (
        "I am the **Local Photo Agent**, a tool for extracting features, descriptions, "
        "and metadata from photos using Ollama vision models over a local network. "
        "I can process images to identify subjects, objects, colors, settings, moods, and tags. "
        "I also support vector embeddings for similarity search and semantic queries."
    )


def _call_chat_endpoint(message: str, ollama_host: Optional[str] = None, ollama_port: Optional[int] = None, 
                        ollama_model: Optional[str] = None, folder: Optional[str] = None, 
                        app_config: Optional[Any] = None, chat_history: Optional[list] = None) -> Dict[str, Any]:
    """Call the /_api/chat endpoint to send a message and get a response."""
    try:
        if app_config:
            dash_host = app_config.dash_host
            dash_port = app_config.dash_port
            if dash_host in ("0.0.0.0", "::"):
                dash_host = "127.0.0.1"
            base_url = f"http://{dash_host}:{dash_port}"
        else:
            base_url = "http://127.0.0.1:8050"
        
        payload = {"message": message}
        if ollama_host:
            payload["host"] = ollama_host
        if ollama_port:
            payload["port"] = ollama_port
        if ollama_model:
            payload["model"] = ollama_model
        if folder:
            payload["folder"] = folder
        if chat_history:
            payload["history"] = chat_history
        
        url = f"{base_url}/_api/chat"
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error("Error calling /_api/chat endpoint: %s", e)
        return {
            "status": "error",
            "response": "",
            "sender": "assistant",
            "message": f"Failed to connect to chat service: {str(e)}"
        }
    except Exception as e:
        logger.error("Error calling /_api/chat endpoint: %s", e, exc_info=True)
        return {
            "status": "error",
            "response": "",
            "sender": "assistant",
            "message": f"Error: {str(e)}"
        }


def register_chat_callback(app, app_config: Optional[Any] = None):
    """Register the simple chat callback for sending messages and displaying responses."""
    
    @app.callback(
        Output("chat-input", "value"),
        Output("chat-history-store", "data", allow_duplicate=True),
        Output("chat-pending-request", "data", allow_duplicate=True),
        Input("chat-send", "n_clicks"),
        Input("chat-input", "n_submit"),
        State("chat-input", "value"),
        State("chat-history-store", "data"),
        State("input-folder", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        prevent_initial_call=True,
    )
    def send_message(n_clicks: Optional[int],
                     n_submit: Optional[int],
                     message: Optional[str], 
                     chat_history: Optional[list],
                     folder: Optional[str],
                     host: Optional[str],
                     port: Optional[int],
                     model: Optional[str]):
        """Handle sending a message via Send button click or Enter key."""
        
        if n_clicks is None and n_submit is None:
            return dash.no_update, dash.no_update, dash.no_update
        
        if not message or not message.strip():
            return dash.no_update, dash.no_update, dash.no_update
        
        logger.debug("Sending message: %s", message)
        
        if chat_history is None:
            chat_history = []
        
        user_msg = message.strip()
        
        try:
            ollama_port_int = int(port) if port and str(port).strip() else None
        except (ValueError, TypeError):
            ollama_port_int = None
        
        pending_data = {
            "message": user_msg,
            "host": host if host and str(host).strip() else None,
            "port": ollama_port_int,
            "model": model if model and str(model).strip() else None,
            "folder": folder if folder and str(folder).strip() else None,
            "chat_history": chat_history,
        }
        
        user_message_entry = {
            "sender": "user",
            "content": user_msg,
            "type": "text"
        }
        
        loading_entry = {
            "sender": "assistant",
            "type": "loading",
            "content": "",
            "pending_id": len(chat_history)
        }
        
        updated_history = chat_history + [user_message_entry, loading_entry]
        
        return "", updated_history, pending_data


def register_chat_stream_callback(app):
    """Register a clientside callback that streams chat responses via SSE.

    This replaces the blocking server-side callback with a browser-side
    fetch to the /_api/chat/stream SSE endpoint. Tokens are appended to
    the chat window incrementally as they arrive from the LLM. When the
    stream completes, dash_clientside.set_props updates the history and
    photo-list stores so that init_chat_history re-renders the final
    formatted message.
    """
    app.clientside_callback(
        """
        function(pendingData, historyData) {
            if (!pendingData || !pendingData.message) {
                return dash_clientside.no_update;
            }

            var history = historyData || [];
            var loadingIndex = -1;
            for (var i = history.length - 1; i >= 0; i--) {
                var entry = history[i];
                if (entry && entry.type === 'loading' && entry.sender === 'assistant') {
                    loadingIndex = i;
                    break;
                }
            }
            if (loadingIndex === -1) {
                return null;
            }

            // Abort any previous in-flight stream
            if (window._chatStreamController) {
                try { window._chatStreamController.abort(); } catch(e) {}
                window._chatStreamController = null;
            }

            // Build request payload
            var payload = {
                message: pendingData.message,
                history: pendingData.chat_history || []
            };
            if (pendingData.host) payload.host = pendingData.host;
            if (pendingData.port) payload.port = pendingData.port;
            if (pendingData.model) payload.model = pendingData.model;
            if (pendingData.folder) payload.folder = pendingData.folder;

            // Find the loading spinner in the DOM and replace with streaming text
            var chatResponseEl = document.getElementById('chat-response');
            var spinner = chatResponseEl ? chatResponseEl.querySelector('.spinner-chat') : null;
            var streamDiv = null;
            var textSpan = null;

            if (spinner && spinner.parentElement) {
                streamDiv = document.createElement('div');
                streamDiv.style.textAlign = 'left';
                streamDiv.style.marginBottom = '10px';
                streamDiv.style.whiteSpace = 'pre-wrap';

                var label = document.createElement('strong');
                label.textContent = 'Local Photo Agent: ';
                streamDiv.appendChild(label);

                textSpan = document.createElement('span');
                textSpan.className = 'chat-streaming-text';
                streamDiv.appendChild(textSpan);

                var cursor = document.createElement('span');
                cursor.className = 'chat-streaming-cursor';
                cursor.textContent = '\\u25AE';
                streamDiv.appendChild(cursor);

                spinner.parentElement.replaceChild(streamDiv, spinner);
            }

            function scrollChat() {
                var container = document.getElementById('chat-response-container');
                if (container) container.scrollTop = container.scrollHeight;
            }

            function updateStreamText(text) {
                if (textSpan) {
                    textSpan.textContent = text;
                    scrollChat();
                }
            }

            function removeCursor() {
                if (streamDiv) {
                    var c = streamDiv.querySelector('.chat-streaming-cursor');
                    if (c) c.remove();
                }
            }

            function finalizeHistory(entry, photoStoreData) {
                var newHistory = history.slice();
                newHistory[loadingIndex] = entry;
                dash_clientside.set_props('chat-history-store', {data: newHistory});
                if (photoStoreData) {
                    dash_clientside.set_props('photo-list-store', {data: photoStoreData});
                }
            }

            var fullText = '';
            var model = pendingData.model || 'unknown';
            var finalResponse = null;
            var responseType = null;
            var sender = 'assistant';

            var controller = new AbortController();
            window._chatStreamController = controller;

            fetch('/_api/chat/stream', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload),
                signal: controller.signal
            }).then(function(response) {
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                var reader = response.body.getReader();
                var decoder = new TextDecoder();
                var buffer = '';

                function pump() {
                    return reader.read().then(function(result) {
                        if (result.done) {
                            return;
                        }
                        buffer += decoder.decode(result.value, {stream: true});
                        var parts = buffer.split('\\n');
                        buffer = parts.pop();
                        for (var i = 0; i < parts.length; i++) {
                            var line = parts[i].trim();
                            if (line.substring(0, 6) === 'data: ') {
                                try {
                                    var evt = JSON.parse(line.substring(6));
                                    if (evt.type === 'token') {
                                        fullText += evt.content;
                                        updateStreamText(fullText);
                                    } else if (evt.type === 'done') {
                                        model = evt.model || model;
                                        responseType = evt.response_type || responseType;
                                        sender = evt.sender || sender;
                                        finalResponse = evt.response;
                                    } else if (evt.type === 'error') {
                                        fullText = '';
                                        finalResponse = evt.message || 'Error';
                                        responseType = 'error';
                                        updateStreamText(finalResponse);
                                    }
                                } catch(e) { /* partial JSON, skip */ }
                            }
                        }
                        return pump();
                    });
                }

                return pump();
            }).then(function() {
                window._chatStreamController = null;
                removeCursor();

                var entry;
                var photoStoreData = null;

                if (responseType === 'photos' && finalResponse && typeof finalResponse === 'object') {
                    var photoList = finalResponse.photos || [];
                    var count = finalResponse.count || photoList.length;
                    entry = {sender: sender, type: 'photos', photo_paths: photoList, count: count};
                    var paths = [];
                    for (var i = 0; i < photoList.length; i++) {
                        if (typeof photoList[i] === 'object') {
                            paths.push(photoList[i].path || '');
                        } else {
                            paths.push(photoList[i]);
                        }
                    }
                    photoStoreData = {paths: paths, index: null};
                } else {
                    var textContent = (finalResponse !== null && finalResponse !== undefined) ? finalResponse : fullText;
                    if (typeof textContent === 'object') {
                        textContent = JSON.stringify(textContent);
                    }
                    entry = {
                        sender: sender,
                        content: textContent || 'No response',
                        type: responseType === 'error' ? 'error' : 'text',
                        model: model
                    };
                }

                finalizeHistory(entry, photoStoreData);
            }).catch(function(err) {
                window._chatStreamController = null;
                if (err && err.name === 'AbortError') {
                    return;
                }
                removeCursor();
                var errMsg = 'Error: ' + (err && err.message ? err.message : 'Connection failed');
                if (textSpan) {
                    textSpan.textContent = errMsg;
                }
                finalizeHistory(
                    {sender: 'assistant', content: errMsg, type: 'error'},
                    null
                );
            });

            // Return null to clear the pending request immediately;
            // the history store is updated via set_props when streaming completes.
            return null;
        }
        """,
        Output("chat-pending-request", "data", allow_duplicate=True),
        Input("chat-pending-request", "data"),
        State("chat-history-store", "data"),
        prevent_initial_call=True,
    )


def register_clear_chat_callback(app):
    """Register callback to clear the chat response."""
    
    @app.callback(
        Output("chat-response", "children"),
        Output("chat-history-store", "data"),
        Output("chat-pending-request", "data"),
        Input("btn-clear-chat", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_chat(n_clicks: Optional[int]):
        """Clear the chat response and history."""
        if n_clicks is None:
            return dash.no_update, dash.no_update, dash.no_update
        return "", [], None


def register_chat_endpoint_test_callback(app, app_config: Optional[Any] = None):
    """Register callback to test the /_api/chat endpoint."""
    
    @app.callback(
        Output("chat-endpoint-test-result", "children"),
        Input("btn-test-chat-endpoint", "n_clicks"),
        State("chat-endpoint-test-message", "value"),
        prevent_initial_call=True,
    )
    def test_chat_endpoint(n_clicks: Optional[int], message: Optional[str]):
        """Test the /_api/chat endpoint and display the result."""
        if n_clicks is None:
            return dash.no_update
        
        if not message or not message.strip():
            return dbc.Alert("Please enter a test message", color="warning")
        
        try:
            result = _call_chat_endpoint(
                message=message.strip(),
                app_config=app_config,
            )
            
            if result.get("status") == "success":
                return dbc.Alert(
                    [
                        html.Strong("Success! "),
                        html.Span(f"Sender: {result.get('sender', 'unknown')}"),
                        html.Br(),
                        html.Small(f"Model: {result.get('model', 'unknown')}"),
                        html.Br(),
                        html.Br(),
                        html.Div(
                            result.get("response", ""),
                            style={"whiteSpace": "pre-wrap", "maxHeight": "200px", "overflowY": "auto"}
                        ),
                    ],
                    color="success",
                    className="mb-0",
                )
            else:
                return dbc.Alert(
                    f"Error: {result.get('message', 'Unknown error')}",
                    color="danger",
                    className="mb-0",
                )
        except Exception as e:
            logger.error("Error testing chat endpoint: %s", e, exc_info=True)
            return dbc.Alert(
                f"Error: {str(e)}",
                color="danger",
                className="mb-0",
            )


def _history_to_messages(history: list, folder: Optional[str] = None):
    """Convert history entries to display messages."""
    if history is None or len(history) == 0:
        return []
    
    from urllib.parse import quote
    
    messages = []
    for entry in history:
        sender = entry.get("sender", "")
        content = entry.get("content", "")
        entry_type = entry.get("type", "text")
        
        if entry_type == "loading":
            messages.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(className="bounce1"),
                                html.Div(className="bounce2"),
                                html.Div(className="bounce3"),
                            ],
                            className="spinner-chat",
                            style={"display": "flex", "margin": "10px 0"},
                        ),
                    ],
                    style={"textAlign": "left", "marginBottom": "10px"},
                )
            )
        elif entry_type == "photos":
            photo_paths = entry.get("photo_paths", [])
            count = entry.get("count", len(photo_paths))
            
            if isinstance(folder, bytes):
                try:
                    folder_str = folder.decode('utf-8')
                except (UnicodeDecodeError, AttributeError):
                    folder_str = folder.decode('latin-1', errors='replace')
            elif isinstance(folder, str):
                folder_str = folder
            elif folder is None:
                folder_str = '.'
            else:
                folder_str = str(folder)
            
            photo_components = [html.Strong(f"Local Photo Agent: Found {count} matching photos:")]
            gallery_items = []
            for photo_item in photo_paths:
                if isinstance(photo_item, dict):
                    img_path = photo_item.get("path", "")
                    score = photo_item.get("score", None)
                else:
                    img_path = photo_item
                    score = None
                
                if isinstance(img_path, bytes):
                    try:
                        img_path_str = img_path.decode('utf-8')
                    except (UnicodeDecodeError, AttributeError):
                        img_path_str = img_path.decode('latin-1', errors='replace')
                elif isinstance(img_path, str):
                    img_path_str = img_path
                else:
                    img_path_str = str(img_path)
                
                preview_url = f"/preview?path={quote(img_path_str)}&folder={quote(folder_str)}&size=thumb"
                display_title = f"{img_path_str} (score: {score:.4f})" if score is not None else img_path_str
                
                gallery_items.append(
                    html.Div(
                        [
                            html.Div(
                                html.Img(
                                    src=preview_url,
                                    style={
                                        "width": "100%", 
                                        "height": "150px", 
                                        "objectFit": "cover", 
                                        "borderRadius": "4px",
                                        "pointerEvents": "none", 
                                        "userSelect": "none"
                                    },
                                    className="img-fluid",
                                    title=display_title,
                                    draggable="false",
                                ),
                                id={"type": "thumbnail", "source": "chat", "index": img_path_str},
                                n_clicks=0,
                                style={"cursor": "pointer", "userSelect": "none", "overflow": "hidden"},
                            ),
                            html.Small(
                                [html.Span(display_title, className="text-muted", style={"fontSize": "0.75rem"})],
                                className="d-block text-center mt-1",
                            ),
                        ],
                        className="gallery-item mb-3",
                        style={"cursor": "pointer"},
                    )
                )
            
            photo_container = html.Div(
                [
                    photo_components[0],
                    html.Div(
                        gallery_items,
                        className="gallery-grid",
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "repeat(auto-fill, minmax(200px, 1fr))",
                            "gap": "10px",
                            "marginTop": "10px"
                        }
                    )
                ],
                style={"marginBottom": "20px"}
            )
            messages.append(photo_container)
        elif entry_type == "error":
            messages.append(
                html.Div(
                    [html.Strong("Error: "), str(content)],
                    className="text-danger",
                    style={"whiteSpace": "pre-wrap", "marginBottom": "10px"},
                )
            )
        else:
            display_sender = "You" if sender == "user" else ("Local Photo Agent" if sender == "assistant" else sender.capitalize())
            model_info = entry.get("model", "")
            message_style = {"whiteSpace": "pre-wrap", "marginBottom": "10px"}
            
            if sender == "user":
                message_style["textAlign"] = "right"
            else:
                message_style["textAlign"] = "left"
            
            if model_info:
                messages.append(
                    html.Div(
                        [
                            html.Strong(f"{display_sender}: "),
                            html.Span(str(content)),
                            html.Br(),
                            html.Small(f"Model: {model_info}", className="text-muted"),
                        ],
                        style=message_style,
                    )
                )
            else:
                messages.append(
                    html.Div(
                        [
                            html.Strong(f"{display_sender}: "),
                            html.Span(str(content)),
                        ],
                        style=message_style,
                    )
                )
    
    return messages


def register_chat_history_init_callback(app):
    """Register callback to initialize chat display from history store."""
    
    @app.callback(
        Output("chat-response", "children"),
        Input("chat-history-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=False,
    )
    def init_chat_history(history: Optional[list], folder: Optional[str]):
        """Initialize chat response display from stored history on page load."""
        if history is None:
            return []
        return _history_to_messages(history, folder)


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
    # Callback to update global user messages cache when history changes
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
            return "";
        }
        """,
        Output("chat-nav-dummy", "children"),
        Input("chat-history-store", "data"),
        prevent_initial_call=True,
    )
    
    # Setup keyboard navigation on initial load
    app.clientside_callback(
        """
        function(n_dummy) {
            var input = document.getElementById('chat-input');
            if (!input) return "";
            
            // Only setup once
            if (input._chatNavSetup) return "";
            input._chatNavSetup = true;
            
            var current_nav_index = -1;
            var last_input_value = "";
            
            // Track the last value set by navigation for reset detection
            var nav_set_value = "";
            
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
                    nav_set_value = input.value;
                    input.selectionStart = input.selectionEnd = input.value.length;
                } else if (e.key === 'ArrowDown') {
                    if (current_nav_index > 0) {
                        // Go to newer message
                        current_nav_index--;
                        input.value = user_messages[user_messages.length - 1 - current_nav_index];
                        nav_set_value = input.value;
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
            
            return "";
        }
        """,
        Output("chat-nav-dummy", "children"),
        Input("chat-nav-dummy", "children"),
        prevent_initial_call=True,
    )
