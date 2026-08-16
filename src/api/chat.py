"""API handler for the /_api/chat endpoint.

This module provides a thin wrapper around the ChatService that handles
Flask request/response conversion, keeping the endpoint logic clean.
"""

import json
import logging

from flask import Response, request, stream_with_context

from src.config import AppConfig
from src.services.chat import ChatService
from src.services.chat_response import ChatResponse

logger = logging.getLogger(__name__)


def api_chat_handler(config: AppConfig, chat_service: ChatService):
    """Handler for /_api/chat endpoint.

    This is a thin wrapper that:
    1. Extracts request data from Flask request
    2. Delegates processing to ChatService
    3. Converts ChatResponse to Flask-compatible response

    Args:
        config: AppConfig instance for default values
        chat_service: ChatService instance for message processing

    Returns:
        Flask response tuple (data_dict, status_code) or just data_dict
    """
    try:
        data = request.get_json(silent=True)
        logger.debug("Chat endpoint received: %s", data)

        if not data:
            return {"status": "error", "message": "No JSON payload provided"}, 400

        message = data.get("message", "")
        host = data.get("host", config.llm_host)
        port = data.get("port", config.llm_port)
        model = data.get("model", config.llm_model)
        folder_path = data.get("folder")
        history = data.get("history", [])

        logger.debug(
            "Chat endpoint: message='%s', host=%s, port=%s, model=%s, history_len=%s",
            message,
            host,
            port,
            model,
            len(history),
        )

        if not message or not message.strip():
            return {"status": "error", "message": "Message is required"}, 400

        # Process message through chat service
        response: ChatResponse = chat_service.process_message(
            message=message, host=host, port=port, model=model, folder_path=folder_path, history=history
        )

        # Convert ChatResponse to API response format
        api_response = {
            "status": response.status,
            "response": response.response,
            "sender": response.sender,
            "model": response.model,
        }

        if response.response_type:
            api_response["response_type"] = response.response_type

        return api_response

    except Exception as e:
        logger.error("Chat API error: %s", e, exc_info=True)
        return {"status": "error", "message": str(e), "model": config.llm_model}, 500


def api_chat_stream_handler(config: AppConfig, chat_service: ChatService):
    """Handler for the /_api/chat/stream SSE endpoint.

    Streams chat responses to the browser as Server-Sent Events. Each event
    is a JSON object on a ``data:`` line:

    - ``{"type": "token", "content": "..."}`` — incremental LLM text chunk
    - ``{"type": "done", "response": ..., "model": ..., ...}`` — final result
    - ``{"type": "error", "message": "..."}`` — failure

    Args:
        config: AppConfig instance for default values.
        chat_service: ChatService instance for message processing.

    Returns:
        A Flask ``Response`` with ``text/event-stream`` mimetype.
    """
    data = request.get_json(silent=True)
    if not data:
        return {"status": "error", "message": "No JSON payload provided"}, 400

    message = data.get("message", "")
    host = data.get("host", config.llm_host)
    port = data.get("port", config.llm_port)
    model = data.get("model", config.llm_model)
    folder_path = data.get("folder")
    history = data.get("history", [])

    if not message or not message.strip():
        return {"status": "error", "message": "Message is required"}, 400

    def generate():
        try:
            for event in chat_service.process_message_stream(
                message=message,
                host=host,
                port=port,
                model=model,
                folder_path=folder_path,
                history=history,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error("Chat stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
