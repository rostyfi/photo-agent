"""Callbacks for the chat interface.

This module provides callbacks for:
- Sending messages to the chat endpoint and receiving responses
"""

import json
import logging
from typing import Any

import dash
import dash_bootstrap_components as dbc
import requests
from dash import Input, Output, State, callback_context, dcc, html

from src.constants import DEFAULT_SLIDESHOW_THRESHOLD, SORT_OPTIONS
from src.constants import SORT_KEY_RELEVANCE, SORT_ORDER_ASC, SORT_ORDER_DESC, default_order_for

from .common import sort_paths

logger = logging.getLogger(__name__)


# Arrow glyphs shown by the order toggle button. ``\u25b2`` is an up arrow
# (ascending), ``\u25bc`` a down arrow (descending).
_ORDER_ARROW = {SORT_ORDER_ASC: "\u25b2", SORT_ORDER_DESC: "\u25bc"}
_ORDER_TITLE = {SORT_ORDER_ASC: "Ascending", SORT_ORDER_DESC: "Descending"}


def _order_button(hist_idx: int, order: str) -> dbc.Button:
    """Build the asc/desc toggle button for a gallery or slideshow sort row."""
    return dbc.Button(
        _ORDER_ARROW.get(order, _ORDER_ARROW[SORT_ORDER_ASC]),
        id={"type": "sort-order", "index": hist_idx},
        color="secondary",
        size="sm",
        n_clicks=0,
        className="ms-2",
        title=_ORDER_TITLE.get(order, _ORDER_TITLE[SORT_ORDER_ASC]),
        style={"width": "38px", "padding": "0.25rem 0"},
    )


def _order_from_children(children) -> str:
    """Infer the current order (``asc``/``desc``) from a toggle button label."""
    glyph = children if isinstance(children, str) else ""
    for order, arrow in _ORDER_ARROW.items():
        if glyph == arrow:
            return order
    return SORT_ORDER_ASC


def _slideshow_threshold_for(folder: str | None) -> int:
    """Return the slideshow threshold for *folder*.

    Reads the per-folder ``settings.json``; falls back to the cached
    ``AppConfig`` value (env/default) when the folder has no stored setting
    or the value is missing/invalid. A negative value is treated as 0.
    """
    if folder:
        try:
            from src.folder_settings import KEY_SLIDESHOW_THRESHOLD, read_folder_settings

            raw = read_folder_settings(folder).get(KEY_SLIDESHOW_THRESHOLD)
            if raw is not None:
                try:
                    return max(0, int(raw))
                except (TypeError, ValueError):
                    pass
        except Exception:
            logger.debug("Could not read slideshow threshold for %s", folder, exc_info=True)
    try:
        from .common import _get_app_config

        return max(0, _get_app_config().slideshow_threshold)
    except Exception:
        return DEFAULT_SLIDESHOW_THRESHOLD


def _build_slideshow_button(hist_idx: int, count: int) -> html.Div:
    """Build the \u201cStart slideshow\u201d button shown in place of a large gallery.

    The button uses a pattern-matching id keyed by the chat history index so
    ``register_slideshow_open_callback`` can look up the matching history
    entry (and its photo paths) when the button is clicked. A sort dropdown
    sits next to the button so the ordering can be chosen before opening the
    slideshow; its value is read by the slideshow open callback.
    """
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Sort:", className="text-muted me-2", style={"fontSize": "0.85rem"}),
                    dcc.Dropdown(
                        id={"type": "slideshow-sort", "index": hist_idx},
                        options=SORT_OPTIONS,
                        value=SORT_KEY_RELEVANCE,
                        clearable=False,
                        style={"width": "180px"},
                        className="sort-dropdown d-inline-block",
                    ),
                    _order_button(hist_idx, default_order_for(SORT_KEY_RELEVANCE)),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                },
            ),
            dbc.Button(
                f"\u25b6 Start slideshow ({count} photos)",
                id={"type": "btn-start-slideshow", "index": hist_idx},
                color="primary",
                n_clicks=0,
                className="ms-2",
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "flexWrap": "wrap",
            "marginBottom": "10px",
        },
    )


def _build_gallery_sort_dropdown(hist_idx: int, slideshow_count: int | None = None) -> html.Div:
    """Build the sort dropdown shown above a preview gallery.

    When ``slideshow_count`` is given, also render a "Start slideshow" button
    so the user can open the fullscreen viewer with the full result set even
    when the preview gallery is shown (i.e. below the slideshow threshold).
    """
    children = [
        html.Span("Sort:", className="text-muted me-2", style={"fontSize": "0.85rem"}),
        dcc.Dropdown(
            id={"type": "gallery-sort", "index": hist_idx},
            options=SORT_OPTIONS,
            value=SORT_KEY_RELEVANCE,
            clearable=False,
            style={"width": "180px"},
            className="sort-dropdown d-inline-block",
        ),
        _order_button(hist_idx, default_order_for(SORT_KEY_RELEVANCE)),
    ]
    if slideshow_count is not None:
        children.append(
            dbc.Button(
                f"\u25b6 Start slideshow ({slideshow_count} photos)",
                id={"type": "btn-start-slideshow", "index": hist_idx},
                color="primary",
                n_clicks=0,
                className="ms-2",
            )
        )
    return html.Div(
        children,
        style={
            "display": "flex",
            "alignItems": "center",
            "flexWrap": "wrap",
            "marginTop": "10px",
            "marginBottom": "10px",
        },
    )


def _decode_path(img_path) -> str:
    """Decode a photo path (possibly bytes) to ``str``."""
    if isinstance(img_path, bytes):
        try:
            return img_path.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            return img_path.decode("latin-1", errors="replace")
    if isinstance(img_path, str):
        return img_path
    return str(img_path)


def _build_gallery_items(photo_items: list, folder_str: str, hist_idx: int) -> list:
    """Build the list of thumbnail divs for a preview gallery.

    Handles both ``/find`` results (items carry ``score``) and ``/tag``
    results (items carry ``description``). Each thumbnail's pattern-matching
    id encodes ``{path, n}`` so the detail-modal callback can locate it.
    """
    from urllib.parse import quote

    gallery_items = []
    for photo_item in photo_items:
        if isinstance(photo_item, dict):
            img_path_str = _decode_path(photo_item.get("path", ""))
            score = photo_item.get("score")
            description = photo_item.get("description", "")
        else:
            img_path_str = _decode_path(photo_item)
            score = None
            description = ""

        preview_url = f"/preview?path={quote(img_path_str)}&folder={quote(folder_str)}&size=thumb"
        if score is not None:
            display_title = f"{img_path_str} (score: {score:.4f})"
        elif description:
            display_title = description[:50]
        else:
            display_title = img_path_str

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
                                "userSelect": "none",
                            },
                            className="img-fluid",
                            title=display_title,
                            draggable="false",
                        ),
                        id={
                            "type": "thumbnail",
                            "source": "chat",
                            "index": json.dumps({"path": img_path_str, "n": hist_idx}),
                        },
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
    return gallery_items


def _build_gallery_grid(photo_items: list, folder_str: str, hist_idx: int) -> html.Div:
    """Build the gallery grid container (with a targetable id) and its items."""
    return html.Div(
        _build_gallery_items(photo_items, folder_str, hist_idx),
        id={"type": "gallery-grid", "index": hist_idx},
        className="gallery-grid",
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fill, minmax(200px, 1fr))",
            "gap": "10px",
            "marginTop": "10px",
        },
    )


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
                                    } else if (evt.type === 'done') {
                                        model = evt.model || model;
                                        responseType = evt.response_type || responseType;
                                        sender = evt.sender || sender;
                                        finalResponse = evt.response;
                                        finalThinking = evt.thinking || (thinkingText || null);
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


def _thinking_block(entry: dict):
    """Build a collapsible reasoning-trace block from a history entry.

    Returns ``None`` when the entry has no thinking content.
    """
    thinking = entry.get("thinking")
    if not thinking:
        return None
    return html.Details(
        [
            html.Summary(
                "Reasoning trace",
                style={"cursor": "pointer", "fontStyle": "italic", "color": "#adb5bd"},
            ),
            html.Span(
                str(thinking),
                style={"whiteSpace": "pre-wrap", "color": "#adb5bd", "fontSize": "0.9em"},
            ),
        ],
        style={"marginBottom": "6px", "opacity": "0.85"},
    )


def _history_to_messages(history: list, folder: str | bytes | None = None):
    """Convert history entries to display messages."""
    if history is None or len(history) == 0:
        return []

    from urllib.parse import quote

    messages = []
    for hist_idx, entry in enumerate(history):
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
        elif entry_type == "tags":
            tags = entry.get("tags", [])
            topic = entry.get("topic", None)
            text = entry.get("text", "")
            header = f"Tags related to '{topic}':" if topic else "All tags:"

            # Create clickable tag buttons
            tag_buttons = []
            for tag_info in tags:
                tag_name = tag_info.get("name", "")
                tag_count = tag_info.get("count", 0)
                tag_buttons.append(
                    dbc.Button(
                        f"{tag_name} ({tag_count})",
                        id={"type": "chat-tag-btn", "tag": tag_name},
                        color="primary",
                        size="sm",
                        className="me-2 mb-2",
                        n_clicks=0,
                    )
                )

            # When no tags match, show the explanatory text from the tool
            # instead of an empty button row.
            body = [html.Div(tag_buttons, style={"marginTop": "10px"})]
            if not tags and text:
                body = [html.Div(text, style={"marginTop": "10px", "whiteSpace": "pre-wrap"})]

            messages.append(
                html.Div(
                    [
                        html.Strong(f"Local Photo Agent: {header}"),
                        _thinking_block(entry),
                        *body,
                    ],
                    style={"textAlign": "left", "marginBottom": "10px"},
                )
            )
        elif entry_type == "photos_and_tags":
            photos = entry.get("photos", [])
            related_tags = entry.get("related_tags", [])
            entry.get("text", "")
            tag = entry.get("tag", "")
            total_photos = entry.get("total_photos", 0)
            selected_tags = entry.get("selected_tags", []) or ([tag] if tag else [])

            if isinstance(folder, bytes):
                try:
                    folder_str = folder.decode("utf-8")
                except (UnicodeDecodeError, AttributeError):
                    folder_str = folder.decode("latin-1", errors="replace")
            elif isinstance(folder, str):
                folder_str = folder
            else:
                folder_str = "."

            # Concise header; the thumbnail grid shows photos and the
            # buttons show related tags, so the markdown bullet lists in
            # ``text`` are redundant and are not rendered.
            label = ", ".join(selected_tags) if selected_tags else tag
            header = f"Photos with tag(s) '{label}' ({total_photos} total)"
            photo_header = html.Strong(f"Local Photo Agent: {header}")
            thinking = _thinking_block(entry)

            slideshow_threshold = _slideshow_threshold_for(folder_str)
            # ``photos`` is capped at 20 by the /tag tool; ``total_photos`` is
            # the full match count, so the threshold check and the slideshow
            # button label reflect every matching photo.
            slideshow_count = total_photos or len(photos)
            use_slideshow = slideshow_threshold > 0 and slideshow_count > slideshow_threshold

            if use_slideshow:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_slideshow_button(hist_idx, slideshow_count),
                    ],
                    style={"marginBottom": "20px"},
                )
                messages.append(photo_container)
            else:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_gallery_sort_dropdown(hist_idx, slideshow_count),
                        _build_gallery_grid(photos, folder_str, hist_idx),
                    ],
                    style={"marginBottom": "20px"},
                )
                messages.append(photo_container)

            # Selected tags: each is a removable chip. Clicking the chip removes
            # that single tag from the chain and re-queries (see
            # register_chat_tag_remove_callback). ``hist_idx`` and the full
            # ``chain`` are encoded in the id so the callback can rebuild the
            # remaining selection across multiple photos_and_tags entries.
            if selected_tags:
                selected_chain = ",".join(selected_tags)
                selected_chips = []
                for tag_name in selected_tags:
                    selected_chips.append(
                        dbc.Button(
                            [html.Span(tag_name), html.Span(" ×", className="ms-1")],
                            id={
                                "type": "chat-tag-remove-btn",
                                "index": hist_idx,
                                "remove": tag_name,
                                "chain": selected_chain,
                            },
                            color="primary",
                            size="sm",
                            className="me-2 mb-2",
                            n_clicks=0,
                        )
                    )
                # Clear-all button resets the whole selection at once.
                selected_chips.append(
                    dbc.Button(
                        "Clear",
                        id={"type": "chat-tag-clear-btn", "index": hist_idx},
                        color="secondary",
                        size="sm",
                        className="me-2 mb-2",
                        n_clicks=0,
                    )
                )
                messages.append(
                    html.Div(
                        [
                            html.Strong("Selected tags: "),
                            html.Div(selected_chips, style={"marginTop": "10px"}),
                        ],
                        style={"textAlign": "left", "marginBottom": "10px"},
                    )
                )

            # Add related tags as clickable buttons (chained with AND semantics)
            tag_buttons = []
            for tag_info in related_tags:
                tag_name = tag_info.get("name", "")
                tag_count = tag_info.get("count", 0)
                # Encode the full chain (existing selected tags + this tag)
                chain = ",".join([*selected_tags, tag_name]) if selected_tags else tag_name
                tag_buttons.append(
                    dbc.Button(
                        f"{tag_name} ({tag_count})",
                        id={"type": "chat-tag-btn", "tag": chain},
                        color="info",
                        size="sm",
                        className="me-2 mb-2",
                        n_clicks=0,
                    )
                )

            if tag_buttons:
                messages.append(
                    html.Div(
                        [
                            html.Strong("Related tags: "),
                            html.Div(tag_buttons, style={"marginTop": "10px"}),
                        ],
                        style={"textAlign": "left", "marginBottom": "10px"},
                    )
                )
        elif entry_type == "photos":
            if isinstance(folder, bytes):
                try:
                    folder_str = folder.decode("utf-8")
                except (UnicodeDecodeError, AttributeError):
                    folder_str = folder.decode("latin-1", errors="replace")
            elif isinstance(folder, str):
                folder_str = folder
            else:
                folder_str = "."

            photo_paths = entry.get("photo_paths") or entry.get("photos", [])
            count = entry.get("count", len(photo_paths))
            photo_header = html.Strong(f"Local Photo Agent: Found {count} matching photos:")
            thinking = _thinking_block(entry)

            slideshow_threshold = _slideshow_threshold_for(folder_str)
            use_slideshow = slideshow_threshold > 0 and len(photo_paths) > slideshow_threshold

            if use_slideshow:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_slideshow_button(hist_idx, len(photo_paths)),
                    ],
                    style={"marginBottom": "20px"},
                )
                messages.append(photo_container)
            else:
                photo_container = html.Div(
                    [
                        photo_header,
                        thinking,
                        _build_gallery_sort_dropdown(hist_idx, len(photo_paths)),
                        _build_gallery_grid(photo_paths, folder_str, hist_idx),
                    ],
                    style={"marginBottom": "20px"},
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
            display_sender = (
                "You" if sender == "user" else ("Local Photo Agent" if sender == "assistant" else sender.capitalize())
            )
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
                            _thinking_block(entry),
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
                            _thinking_block(entry),
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
    def init_chat_history(history: list | None, folder: str | None):
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

        # Clear the input and trigger the message
        return "", updated_history, pending_data


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


def register_gallery_sort_callback(app):
    """Re-sort a preview gallery when its sort dropdown or order toggle changes.

    Each gallery renders a ``gallery-sort`` dropdown and a ``sort-order``
    toggle button (both keyed by chat history index) above a ``gallery-grid``
    container. Changing either control reorders the thumbnails and updates
    ``photo-list-store`` so the detail-modal navigation follows the sorted
    order. Switching the sort key resets the order to that key's natural
    default; clicking the toggle flips asc/desc.
    """

    @app.callback(
        Output({"type": "gallery-grid", "index": dash.ALL}, "children", allow_duplicate=True),
        Output("photo-list-store", "data", allow_duplicate=True),
        Output({"type": "sort-order", "index": dash.ALL}, "children", allow_duplicate=True),
        Input({"type": "gallery-sort", "index": dash.ALL}, "value"),
        Input({"type": "sort-order", "index": dash.ALL}, "n_clicks"),
        State({"type": "gallery-sort", "index": dash.ALL}, "id"),
        State({"type": "sort-order", "index": dash.ALL}, "id"),
        State({"type": "sort-order", "index": dash.ALL}, "children"),
        State("chat-history-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def handle_gallery_sort(
        sort_values, order_clicks, sort_ids, order_ids, order_labels, chat_history, folder
    ):
        n_grid = len(sort_ids) if sort_ids else 0
        no_update_grids = [dash.no_update] * n_grid
        n_order = len(order_ids) if order_ids else 0
        no_update_labels = [dash.no_update] * n_order

        ctx = callback_context
        triggered_id = ""
        if ctx.triggered:
            for t in ctx.triggered:
                pid = t.get("prop_id", "")
                if pid and pid != ".":
                    triggered_id = pid
                    break
        if not triggered_id:
            return no_update_grids, dash.no_update, no_update_labels

        triggered_by_order = '"type":"sort-order"' in triggered_id

        try:
            id_part = triggered_id.rsplit(".", 1)[0]
            btn_id = json.loads(id_part)
            hist_idx = btn_id.get("index")
        except (json.JSONDecodeError, ValueError, AttributeError):
            return no_update_grids, dash.no_update, no_update_labels

        # Resolve the active sort key.
        sort_key = None
        for pos, sid in enumerate(sort_ids):
            if sid.get("index") == hist_idx:
                sort_key = sort_values[pos] if pos < len(sort_values) else None
                break

        # Resolve the effective order and the new toggle label.
        if triggered_by_order:
            current = SORT_ORDER_ASC
            for pos, oid in enumerate(order_ids or []):
                if oid.get("index") == hist_idx:
                    current = _order_from_children(order_labels[pos] if pos < len(order_labels) else "")
                    break
            order = SORT_ORDER_DESC if current == SORT_ORDER_ASC else SORT_ORDER_ASC
        else:
            # Sort key changed (or unknown trigger): reset to the key's default.
            order = default_order_for(sort_key)

        new_label = _ORDER_ARROW.get(order, _ORDER_ARROW[SORT_ORDER_ASC])

        if not isinstance(chat_history, list) or hist_idx is None or hist_idx < 0 or hist_idx >= len(chat_history):
            return no_update_grids, dash.no_update, no_update_labels
        entry = chat_history[hist_idx] or {}

        raw_items = entry.get("photo_paths") or entry.get("photos", []) or []
        original_paths = []
        scores = {}
        item_by_path = {}
        for item in raw_items:
            if isinstance(item, dict):
                path = _decode_path(item.get("path", ""))
                score = item.get("score")
            else:
                path = _decode_path(item)
                score = None
            if not path:
                continue
            original_paths.append(path)
            item_by_path[path] = item
            if score is not None:
                scores[path] = score

        if not original_paths:
            return no_update_grids, dash.no_update, no_update_labels

        if isinstance(folder, bytes):
            folder_str = folder.decode("utf-8", errors="replace")
        elif folder is None:
            folder_str = "."
        else:
            folder_str = str(folder)

        sorted_paths = sort_paths(
            original_paths,
            sort_key,
            folder_str,
            original_paths=original_paths,
            scores=scores or None,
            order=order,
        )
        sorted_items = [item_by_path.get(p, p) for p in sorted_paths]
        new_children = _build_gallery_items(sorted_items, folder_str, hist_idx)

        grid_outputs: list[Any] = list(no_update_grids)
        grid_matched = False
        for pos, sid in enumerate(sort_ids):
            if sid.get("index") == hist_idx:
                grid_outputs[pos] = new_children
                grid_matched = True
                break

        label_outputs: list[Any] = list(no_update_labels)
        for pos, oid in enumerate(order_ids or []):
            if oid.get("index") == hist_idx:
                label_outputs[pos] = new_label
                break

        # Only update photo-list-store when a gallery grid was actually
        # reordered; for a slideshow sort-row toggle (no gallery grid) we
        # flip just the label and leave the store untouched so an open
        # fullscreen viewer is not clobbered.
        if grid_matched:
            store: Any = {"paths": sorted_paths, "original_paths": original_paths, "index": None}
        else:
            store = dash.no_update
        return grid_outputs, store, label_outputs
