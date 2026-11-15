"""Callbacks for sending chat messages, streaming responses, and testing the chat endpoint.

This module provides:
- ``register_chat_callback`` — send a message via button/Enter, store pending request
- ``register_chat_stream_callback`` — clientside SSE streaming from /_api/chat/stream
- ``register_clear_chat_callback`` — clear the chat window
- ``register_chat_endpoint_test_callback`` — test the /_api/chat endpoint from Settings
"""

import logging
from typing import Any

import dash
import dash_bootstrap_components as dbc
import requests
from dash import Input, Output, State, html

logger = logging.getLogger(__name__)


def _call_chat_endpoint(
    message: str,
    ollama_host: str | None = None,
    ollama_port: int | None = None,
    ollama_model: str | None = None,
    folder: str | None = None,
    app_config: Any | None = None,
    chat_history: list | None = None,
) -> dict[str, Any]:
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

        payload: dict[str, Any] = {"message": message}
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
            "message": f"Failed to connect to chat service: {e!s}",
        }
    except Exception as e:
        logger.error("Error calling /_api/chat endpoint: %s", e, exc_info=True)
        return {"status": "error", "response": "", "sender": "assistant", "message": f"Error: {e!s}"}


def register_chat_callback(app, app_config: Any | None = None):
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
    def send_message(
        n_clicks: int | None,
        n_submit: int | None,
        message: str | None,
        chat_history: list | None,
        folder: str | None,
        host: str | None,
        port: int | None,
        model: str | None,
    ):
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

        user_message_entry = {"sender": "user", "content": user_msg, "type": "text"}

        loading_entry = {"sender": "assistant", "type": "loading", "content": "", "pending_id": len(chat_history)}

        updated_history = [*chat_history, user_message_entry, loading_entry]

        return "", updated_history, pending_data


def register_chat_stream_callback(app):
    """Register a clientside callback that streams chat responses via SSE.

    This replaces the blocking server-side callback with a browser-side
    fetch to the /_api/chat/stream SSE endpoint. Tokens are appended to
    the chat window incrementally as they arrive from the LLM. Tools the
    LLM invokes implicitly (native tool calling) surface as ``tool`` events
    shown as "Running <name>…". When the stream completes,
    dash_clientside.set_props updates the history and photo-list stores so
    that init_chat_history re-renders the final formatted message.
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

                // Collapsible reasoning-trace block (debug mode). Populated from
                // "thinking" SSE events; hidden until the first chunk arrives.
                var thinkingDetails = document.createElement('details');
                thinkingDetails.style.marginBottom = '6px';
                thinkingDetails.style.opacity = '0.85';
                thinkingDetails.style.display = 'none';
                var thinkingSummary = document.createElement('summary');
                thinkingSummary.textContent = 'Reasoning trace';
                thinkingSummary.style.cursor = 'pointer';
                thinkingSummary.style.fontStyle = 'italic';
                thinkingSummary.style.color = '#adb5bd';
                thinkingDetails.appendChild(thinkingSummary);
                var thinkingSpan = document.createElement('span');
                thinkingSpan.style.whiteSpace = 'pre-wrap';
                thinkingSpan.style.color = '#adb5bd';
                thinkingSpan.style.fontSize = '0.9em';
                thinkingDetails.appendChild(thinkingSpan);
                streamDiv.appendChild(thinkingDetails);

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
            var thinkingText = '';
            var model = pendingData.model || 'unknown';
            var finalResponse = null;
            var finalThinking = null;
            var responseType = null;
            var sender = 'assistant';
            var toolsCalled = [];

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
                                    } else if (evt.type === 'thinking') {
                                        thinkingText += evt.content;
                                        if (thinkingSpan) {
                                            thinkingSpan.textContent = thinkingText;
                                            if (thinkingDetails) {
                                                thinkingDetails.style.display = 'block';
                                                thinkingDetails.open = true;
                                            }
                                            scrollChat();
                                        }
                                    } else if (evt.type === 'tool') {
                                        // The LLM invoked a tool implicitly (native
                                        // tool calling); show what is running.
                                        if (textSpan) {
                                            textSpan.textContent = 'Running ' + (evt.name || 'tool') + '…';
                                            scrollChat();
                                        }
                                    } else if (evt.type === 'done') {
                                        model = evt.model || model;
                                        responseType = evt.response_type || responseType;
                                        sender = evt.sender || sender;
                                        finalResponse = evt.response;
                                        finalThinking = evt.thinking || (thinkingText || null);
                                        toolsCalled = evt.tools_called || [];
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
                    entry = {sender: sender, type: 'photos', photo_paths: photoList, count: count, thinking: finalThinking || null};
                    var paths = [];
                    for (var i = 0; i < photoList.length; i++) {
                        if (typeof photoList[i] === 'object') {
                            paths.push(photoList[i].path || '');
                        } else {
                            paths.push(photoList[i]);
                        }
                    }
                    photoStoreData = {paths: paths, original_paths: paths, index: null};
                } else if (responseType === 'tags' && finalResponse && typeof finalResponse === 'object') {
                    // Handle tags response - render as clickable buttons
                    var tags = finalResponse.tags || [];
                    var text = finalResponse.text || '';
                    var topic = finalResponse.topic || null;
                    entry = {sender: sender, type: 'tags', tags: tags, text: text, topic: topic, thinking: finalThinking || null};
                } else if (responseType === 'photos_and_tags' && finalResponse && typeof finalResponse === 'object') {
                    // Handle photos_and_tags response - show photos and related tags
                    var photos = finalResponse.photos || [];
                    var relatedTags = finalResponse.related_tags || [];
                    var text = finalResponse.text || '';
                    var tag = finalResponse.tag || '';
                    var totalPhotos = finalResponse.total_photos || 0;
                    var selectedTags = finalResponse.selected_tags || (tag ? [tag] : []);
                    entry = {
                        sender: sender,
                        type: 'photos_and_tags',
                        photos: photos,
                        related_tags: relatedTags,
                        text: text,
                        tag: tag,
                        total_photos: totalPhotos,
                        selected_tags: selectedTags,
                        thinking: finalThinking || null
                    };
                    var paths = [];
                    for (var i = 0; i < photos.length; i++) {
                        if (typeof photos[i] === 'object') {
                            paths.push(photos[i].path || '');
                        } else {
                            paths.push(photos[i]);
                        }
                    }
                    photoStoreData = {paths: paths, original_paths: paths, index: null};
                } else {
                    var textContent = (finalResponse !== null && finalResponse !== undefined) ? finalResponse : fullText;
                    if (typeof textContent === 'object') {
                        textContent = JSON.stringify(textContent);
                    }
                    entry = {
                        sender: sender,
                        content: textContent || 'No response',
                        type: responseType === 'error' ? 'error' : 'text',
                        model: model,
                        thinking: finalThinking || null
                    };
                }

                // Collapse the live reasoning-trace block once streaming ends
                // (it remains visible and expandable in the persisted history).
                if (thinkingDetails && thinkingDetails.style.display !== 'none') {
                    thinkingDetails.open = false;
                }

                finalizeHistory(entry, photoStoreData);

                // --- Live processing progress bar ---
                // When the user starts processing (/process) or checks status
                // (/status), poll /_api/process_status and render a real-time
                // progress bar. Also trigger when the response text indicates a
                // batch was started or status reported (covers LLM redirects).
                var sentMsg = (pendingData.message || '').trim().toLowerCase();
                var respText = (typeof finalResponse === 'string') ? finalResponse : '';
                var shouldPollProgress = (
                    sentMsg === '/process' || sentMsg === '/status' ||
                    toolsCalled.indexOf('process') !== -1 || toolsCalled.indexOf('status') !== -1 ||
                    /processing (has started|started for)/i.test(respText) ||
                    /batch status for/i.test(respText)
                );
                if (shouldPollProgress && pendingData.folder) {
                    startProgressPolling(pendingData.folder);
                }
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

            // --- Progress bar polling helpers ---
            // Polls /_api/process_status for the folder and updates the
            // #chat-progress-bar element in real time. Stops automatically when
            // the batch reaches a terminal state (done/aborted) or no batch is
            // active. Cancels any previous poll loop before starting.
            function startProgressPolling(folder) {
                var bar = document.getElementById('chat-progress-bar');
                if (!bar) return;
                if (window._progressPollTimer) {
                    clearTimeout(window._progressPollTimer);
                    window._progressPollTimer = null;
                }

                function renderBar(data) {
                    var total = data.total || 0;
                    var completed = data.completed || 0;
                    var pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
                    var status = data.status || 'unknown';
                    var msg = data.status_msg || '';
                    var label;
                    if (status.indexOf('running') === 0) {
                        label = 'Processing ' + completed + '/' + total + ' (' + pct + '%)';
                    } else if (status.indexOf('done') === 0) {
                        label = 'Completed ' + completed + '/' + total;
                        pct = 100;
                    } else if (status === 'aborted') {
                        label = 'Processing aborted';
                    } else if (status === 'idle') {
                        label = 'No active processing';
                    } else {
                        label = status + ' — ' + completed + '/' + total;
                    }
                    var statusColor = status.indexOf('running') === 0 ? '#0d6efd'
                        : status.indexOf('done') === 0 ? '#198754'
                        : status === 'aborted' ? '#dc3545' : '#6c757d';
                    var barHtml =
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">' +
                          '<strong style="font-size:0.9rem;">' + label + '</strong>' +
                          '<span style="font-size:0.8rem;color:#adb5bd;">' + pct + '%</span>' +
                        '</div>' +
                        '<div style="width:100%;height:14px;background:#343a40;border-radius:7px;overflow:hidden;">' +
                          '<div style="width:' + pct + '%;height:100%;background:' + statusColor + ';border-radius:7px;transition:width 0.4s ease;"></div>' +
                        '</div>';
                    if (msg && status.indexOf('running') === 0) {
                        barHtml += '<div style="font-size:0.78rem;color:#adb5bd;margin-top:4px;">' + msg + '</div>';
                    }
                    bar.innerHTML = barHtml;
                    bar.style.display = 'block';
                }

                function hideBar() {
                    var barEl = document.getElementById('chat-progress-bar');
                    if (barEl) {
                        window._progressPollTimer = setTimeout(function() {
                            barEl.style.display = 'none';
                            window._progressPollTimer = null;
                        }, 3000);
                    }
                }

                function poll() {
                    fetch('/_api/process_status?folder=' + encodeURIComponent(folder))
                        .then(function(r) { return r.json(); })
                        .then(function(data) {
                            renderBar(data);
                            if (data.active) {
                                window._progressPollTimer = setTimeout(poll, 1500);
                            } else {
                                hideBar();
                            }
                        })
                        .catch(function() {
                            window._progressPollTimer = setTimeout(poll, 3000);
                        });
                }
                poll();
            }

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
    def clear_chat(n_clicks: int | None):
        """Clear the chat response and history."""
        if n_clicks is None:
            return dash.no_update, dash.no_update, dash.no_update
        return "", [], None


def register_chat_endpoint_test_callback(app, app_config: Any | None = None):
    """Register callback to test the /_api/chat endpoint."""

    @app.callback(
        Output("chat-endpoint-test-result", "children"),
        Input("btn-test-chat-endpoint", "n_clicks"),
        State("chat-endpoint-test-message", "value"),
        prevent_initial_call=True,
    )
    def test_chat_endpoint(n_clicks: int | None, message: str | None):
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
                            style={"whiteSpace": "pre-wrap", "maxHeight": "200px", "overflowY": "auto"},
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
                f"Error: {e!s}",
                color="danger",
                className="mb-0",
            )
