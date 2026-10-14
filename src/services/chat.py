"""Chat service for handling chat messages and tool commands.

This module provides the ChatService class which handles:
- Dynamic tool command execution (loaded from src.services.chat_tools)
- LLM interaction via abstract LLMChatClient
- Response processing and formatting

Tools are dynamically loaded from the src.services.chat_tools package,
allowing for extensibility without modifying this file.
"""

import json
import logging
import re
from collections.abc import Generator
from typing import Any

import requests

from src.config import AppConfig
from src.interfaces import LLMChatClient, ToolCall
from src.services.chat_response import ChatResponse

logger = logging.getLogger(__name__)

# Response types that render as structured UI (photo galleries, tag chips).
# These are returned to the user directly instead of being summarized by the
# LLM, exactly as when the user types the matching slash command.
_STRUCTURED_RESPONSE_TYPES = frozenset({"photos", "tags", "photos_and_tags"})

# Maximum number of tool-calling turns per message before giving up.
_MAX_TOOL_TURNS = 5


class ChatService:
    """Service for handling chat messages and tool commands.

    This service provides a clean separation between:
    - Tool command handling (dynamic loading from chat_tools package)
    - LLM chat functionality
    - Response formatting

    Tools are dynamically loaded from the src.services.chat_tools package,
    allowing for extensibility without modifying this file.

    The ChatService uses an abstract LLMChatClient for LLM interactions,
    allowing different backends to be used without the service knowing
    which specific backend is being used.

    Attributes:
        config: AppConfig instance with application settings
        _tools: Dictionary mapping command names to tool instances
        _chat_client: LLMChatClient instance for chat interactions
    """

    def __init__(self, config: AppConfig, chat_client: LLMChatClient | None = None):
        """Initialize the chat service with configuration and optional chat client.

        Args:
            config: AppConfig instance with application settings
            chat_client: Optional LLMChatClient instance. If not provided, one will be
                       created using the config settings.
        """
        self.config = config
        self._tools: dict[str, Any] = {}

        # Store the chat client or create a default one
        self._chat_client = chat_client

        self._load_tools()

    def _load_tools(self) -> None:
        """Dynamically load all tools from the chat_tools package.

        This method discovers all tool classes in the chat_tools package,
        instantiates them with the config, and stores them in self._tools.
        Special handling is done for ToolsTool which needs a reference to
        all loaded tools.
        """
        from src.services.chat_tools import load_all_tools

        # Load all tools
        tools = load_all_tools(self.config)

        # Special case: ToolsTool needs reference to all tools
        # We'll handle this after all tools are loaded
        self._tools = tools

        # Now update ToolsTool with the complete tools dict
        if "/tools" in self._tools:
            self._tools["/tools"]._all_tools = self._tools  # type: ignore[attr-defined]

    def _get_tool_commands(self) -> list[str]:
        """Get list of all registered tool commands.

        Returns:
            List of command strings (e.g., ["/about", "/count", ...])
        """
        return list(self._tools.keys())

    def get_system_prompt(self) -> str:
        """Build the system prompt for the LLM.

        With native tool calling the model receives the tool specifications
        alongside this prompt (see :meth:`_get_tool_specs`); the prompt
        describes the assistant's role and the routing rules for choosing
        between similar tools.

        Returns:
            The system prompt string to guide LLM behavior
        """
        think_rule = ""
        if getattr(self.config, "debug_reasoning", False):
            think_rule = (
                "RULE 0: ALWAYS reason briefly in your thinking before responding, even when calling "
                "tools. Your thinking is internal and separate from your response.\n\n"
            )

        return (
            "You are the Local Photo Agent, a chat assistant for a photo feature extraction system.\n"
            "You MUST follow these rules EXACTLY:\n\n"
            f"{think_rule}"
            "RULE 1: If the user's intent matches ANY tool, call that tool — do not ask for permission "
            "and do not describe what you will do instead of doing it.\n"
            "RULE 2: If the user's intent does NOT match any tool, respond as a helpful assistant.\n"
            "When a tool returns results, summarize them concisely for the user.\n\n"
            "ROUTING RULES (choose the correct tool):\n"
            "- find: search photos by a DESCRIPTION or SUBJECT the user describes (e.g. 'photos of "
            "animals', 'dogs running'). Use find for any 'show me photos of X' where X is a subject or "
            "description, NOT an exact tag name.\n"
            "  When the user mentions WHEN the photo was taken (e.g. 'last summer', 'summer 2024', "
            "'January 2024', '2023', 'last month'), pass it as the date parameter (e.g. 'last summer'). "
            "When the user specifies a number of photos (e.g. 'show me 10 images of dogs'), pass it as "
            "the limit parameter.\n"
            "- tag: ONLY filter photos by an EXACT tag name the user already knows exists (e.g. 'photos "
            "with the nature tag'). Never use tag for general subject searches — use find instead.\n"
            "- tags: list or discover available tag names by topic.\n"
            "- If unsure whether the user means a subject search or an exact tag, prefer find.\n"
            "- scan, process, and count require a folder to be selected. If a tool reports that no folder "
            "is selected, tell the user to select a folder first.\n"
        )

    def handle_tool_command(self, command: str, folder_path: str | None = None) -> ChatResponse:
        """Execute a tool command and return the response.

        This is the single entry point for all tool command handling.
        Tools are dynamically loaded and executed based on the command string.

        The command keyword is matched case-insensitively and may carry
        arguments (e.g. ``/find 5 cats``). Argument case is preserved because
        tag names are case-sensitive. Matching uses a word boundary after the
        keyword, so ``/tagsxyz`` is rejected instead of being routed to the
        ``/tags`` tool.

        Args:
            command: The tool command string (e.g., "/count", "/find cats")
            folder_path: Optional folder path for database operations

        Returns:
            ChatResponse with the result of the tool command
        """
        command = command.strip()
        normalized = self._normalize_tool_command(command)
        if normalized is None:
            return ChatResponse(status="error", response=f"Unknown command: {command}", sender="assistant", model="N/A")

        keyword = normalized.split(None, 1)[0]
        tool = self._tools.get(keyword)
        if tool is None:
            return ChatResponse(status="error", response=f"Unknown command: {command}", sender="assistant", model="N/A")

        return tool(folder_path, normalized)

    def _ensure_chat_client(self) -> LLMChatClient:
        """Ensure we have a chat client, creating a default one if needed.

        Returns:
            The LLMChatClient instance to use.

        Raises:
            RuntimeError: If no chat client is available and cannot be created.
        """
        if self._chat_client is None:
            # Import here to avoid circular imports
            from plugins.llm import OllamaChatClient

            # Create a default chat client using config
            llm_config = self.config
            self._chat_client = OllamaChatClient(
                host=getattr(llm_config, "llm_host", None),
                port=getattr(llm_config, "llm_port", None),
                model=getattr(llm_config, "llm_model", None),
                timeout=getattr(llm_config, "timeout", 120),
            )
        return self._chat_client

    def _clean_response(self, raw_response: str) -> str:
        """Clean up the LLM response by removing markdown code fences.

        Args:
            raw_response: The raw response from the LLM

        Returns:
            Cleaned response string
        """
        if raw_response.startswith("```"):
            raw_response = raw_response[3:].lstrip()
        if raw_response.endswith("```"):
            raw_response = raw_response[:-3].rstrip()
        return raw_response.strip()

    def _command_alternation(self) -> str:
        """Build a regex alternation of all registered tool commands.

        Commands are sorted longest-first so that e.g. ``/tags`` is tried
        before ``/tag`` and the shorter command cannot shadow the longer one.

        Returns:
            Regex alternation string of escaped command keywords.
        """
        commands = sorted(self._tools.keys(), key=len, reverse=True)
        return "|".join(re.escape(command) for command in commands)

    def _canonical_keyword(self, keyword: str) -> str:
        """Map a matched command keyword to its registered (canonical) form.

        Matching is case-insensitive (models emit ``/Find`` as often as
        ``/find``); the returned keyword is the registered command so tools
        can slice arguments by ``len(metadata.command)`` reliably.

        Args:
            keyword: The matched keyword, possibly in non-canonical case.

        Returns:
            The registered command string (e.g. ``/find``).
        """
        lowered = keyword.lower()
        for command in self._tools:
            if command.lower() == lowered:
                return command
        return keyword

    @staticmethod
    def _strip_command_wrappers(text: str) -> str:
        """Strip formatting a model may wrap around a command.

        Removes surrounding whitespace, markdown emphasis/quotes/backticks
        (``**/scan**``, ``"/scan"``, `` `/scan` ``) and trailing sentence
        punctuation (``/scan.``).

        Args:
            text: The raw line or string to clean.

        Returns:
            The cleaned string.
        """
        return text.strip().strip("* `\"'").strip().rstrip(".,;:!?").strip()

    def _normalize_tool_command(self, text: str) -> str | None:
        """Match a whole string against a registered tool command.

        Args:
            text: The candidate command string (e.g. direct user input).

        Returns:
            The canonical command (``/find 5 cats``) with the keyword
            normalised to its registered form and the arguments preserved
            verbatim, or None when the text is not a single tool command.
        """
        candidate = self._strip_command_wrappers(self._clean_response(text or ""))
        match = re.match(rf"^({self._command_alternation()})(?:\s+([\s\S]*))?$", candidate, re.IGNORECASE)
        if not match:
            return None
        keyword = self._canonical_keyword(match.group(1))
        args = (match.group(2) or "").strip()
        return f"{keyword} {args}" if args else keyword

    def _extract_tool_command(self, text: str) -> str | None:
        """Extract a tool command from a free-form LLM response.

        The system prompt asks the model to answer with exactly one tool
        command and nothing else, but models frequently wrap the command in
        quotes/backticks, add trailing punctuation, or prepend prose. This
        recovers the command in those cases:

        1. A line that is exactly a command (ignoring wrappers/punctuation).
        2. A command mentioned after sentence punctuation, e.g.
           ``Sure! /find cats``.

        Helpful answers that merely mention a command in running prose
        (``You can use /scan to list photos``) are deliberately not matched.

        Args:
            text: The raw LLM response.

        Returns:
            The canonical command string, or None when no command is found.
        """
        cleaned = self._clean_response(text or "")
        if not cleaned:
            return None
        alternation = self._command_alternation()
        lines = cleaned.splitlines()

        # Pass 1: a line that is exactly a command.
        for line in lines:
            candidate = self._strip_command_wrappers(line)
            match = re.match(rf"^({alternation})(?:\s+([\s\S]*))?$", candidate, re.IGNORECASE)
            if match:
                keyword = self._canonical_keyword(match.group(1))
                args = (match.group(2) or "").strip()
                return f"{keyword} {args}" if args else keyword

        # Pass 2: a command after sentence punctuation within a line.
        inline = re.compile(rf"(?<=[.!?;:])\s*({alternation})(?=\s|$|[.,;:!?])", re.IGNORECASE)
        for line in lines:
            match = inline.search(line)
            if match:
                keyword = self._canonical_keyword(match.group(1))
                args = self._strip_command_wrappers(line[match.end() :])
                return f"{keyword} {args}" if args else keyword

        return None

    def _get_tool_specs(self) -> list[dict]:
        """Build tool specifications for native LLM tool calling.

        Returns:
            List of tool spec dicts (Ollama ``tools`` format), one per
            loaded tool.
        """
        return [tool.to_tool_spec() for tool in self._tools.values()]

    def _function_command(self, function_name: str) -> str | None:
        """Map an LLM tool function name back to its slash command.

        Args:
            function_name: The function name from a tool call (e.g. ``find``).

        Returns:
            The registered command (e.g. ``/find``), or None when unknown.
        """
        for command, tool in self._tools.items():
            if tool.function_name == function_name:
                return command
        return None

    def _execute_tool_calls(
        self, tool_calls: tuple[ToolCall, ...], folder_path: str | None
    ) -> list[tuple[ToolCall, ChatResponse]]:
        """Execute tool calls requested by the LLM.

        Args:
            tool_calls: Tool invocations (name + arguments) from the model.
            folder_path: Optional folder path for database operations.

        Returns:
            List of (tool_call, ChatResponse) pairs, in call order.
        """
        executed: list[tuple[ToolCall, ChatResponse]] = []
        for call in tool_calls:
            command = self._function_command(call.name)
            if command is None:
                logger.warning("LLM requested unknown tool %r", call.name)
                result = ChatResponse(
                    status="error",
                    response=f"Unknown tool: {call.name}",
                    sender="assistant",
                    model="N/A",
                )
            else:
                tool = self._tools[command]
                command_str = tool.command_from_arguments(call.arguments)
                logger.debug("[Chat LLM] Tool call %s(%r) -> %r", call.name, call.arguments, command_str)
                result = self.handle_tool_command(command_str, folder_path)
            executed.append((call, result))
        return executed

    @staticmethod
    def _tool_result_text(result: ChatResponse) -> str:
        """Render a tool result as text for feeding back to the LLM."""
        if isinstance(result.response, dict):
            return json.dumps(result.response, ensure_ascii=False)
        text = str(result.response)
        if result.status == "error":
            return f"Tool error: {text}"
        return text

    def process_message(
        self,
        message: str,
        host: str | None = None,
        port: int | None = None,
        model: str | None = None,
        folder_path: str | None = None,
        history: list | None = None,
    ) -> ChatResponse:
        """Process a chat message and return a response.

        This is the main entry point for message processing. It handles:
        1. Direct tool commands (e.g., user types "/count")
        2. LLM-based chat with native tool calling for non-command messages:
           the model invokes tools implicitly, tool results are fed back to
           the model, and its final text answer is returned. Structured tool
           results (photo galleries, tag chips) are returned directly.
        3. Tool commands emitted by the LLM as text (fallback for models that
           reply with e.g. "/find cats" instead of calling the tool)

        Args:
            message: The user's message
            host: Ollama server host (ignored if chat_client was provided in constructor)
            port: Ollama server port (ignored if chat_client was provided in constructor)
            model: Model to use for LLM (ignored if chat_client was provided in constructor)
            folder_path: Optional folder path for database operations
            history: Optional chat history for conversation context

        Returns:
            ChatResponse with the processed response
        """
        message = message.strip()
        if not message:
            return ChatResponse(status="error", response="Message is required", sender="assistant", model="N/A")

        # Check if the message is a direct tool command
        normalized = self._normalize_tool_command(message)
        if normalized is not None:
            return self.handle_tool_command(normalized, folder_path)

        # Not a direct command, send to the LLM with native tool calling
        try:
            # Get the chat client (will create one if needed using host/port/model)
            chat_client = self._ensure_chat_client()

            # Use provided parameters or fall back to chat client's defaults
            effective_model = model or chat_client.model

            system_prompt = self.get_system_prompt()
            think = bool(getattr(self.config, "debug_reasoning", False))
            tool_specs = self._get_tool_specs()
            messages = LLMChatClient.build_messages(message, system_prompt=system_prompt, history=history)

            thinking_parts: list[str] = []
            called_functions: list[str] = []

            for _turn in range(_MAX_TOOL_TURNS + 1):
                reply = chat_client.chat_messages(messages, tools=tool_specs, think=think)
                if reply.thinking:
                    thinking_parts.append(reply.thinking)
                    logger.debug("[Chat LLM] Reasoning trace: %r", reply.thinking)

                if not reply.tool_calls:
                    # Final text answer. Keep the slash-command text routing
                    # as a fallback for models that emit a command as text
                    # instead of calling the tool.
                    cleaned_response = self._clean_response(reply.content)
                    logger.debug("[Chat LLM] Cleaned response: %r", cleaned_response)
                    extracted = self._extract_tool_command(reply.content)
                    if extracted is not None:
                        logger.debug("[Chat LLM] Extracted tool command: %r", extracted)
                        result = self.handle_tool_command(extracted, folder_path)
                        result.model = effective_model
                        result.thinking = "\n".join(thinking_parts) or None
                        result.tools_called = called_functions or None
                        return result
                    return ChatResponse(
                        status="success",
                        response=cleaned_response,
                        sender="assistant",
                        model=effective_model,
                        thinking="\n".join(thinking_parts) or None,
                        tools_called=called_functions or None,
                    )

                # Execute the requested tools. Structured results (photo
                # galleries, tag chips) are returned to the user directly,
                # exactly as when the matching slash command is typed.
                called_functions.extend(call.name for call in reply.tool_calls)
                executed = self._execute_tool_calls(reply.tool_calls, folder_path)
                for _call, result in executed:
                    if result.response_type in _STRUCTURED_RESPONSE_TYPES:
                        result.model = effective_model
                        result.thinking = "\n".join(thinking_parts) or None
                        result.tools_called = called_functions
                        return result

                # Feed text results back so the model can compose an answer.
                messages.append(
                    {
                        "role": "assistant",
                        "content": reply.content or "",
                        "tool_calls": [
                            {"function": {"name": call.name, "arguments": call.arguments}} for call in reply.tool_calls
                        ],
                    }
                )
                for call, result in executed:
                    messages.append({"role": "tool", "name": call.name, "content": self._tool_result_text(result)})

            logger.error("LLM exceeded the maximum of %d tool-calling turns", _MAX_TOOL_TURNS)
            return ChatResponse(
                status="error",
                response="The model did not finish after several tool calls. Please rephrase your request.",
                sender="assistant",
                model=effective_model,
                response_type="error",
                tools_called=called_functions or None,
            )

        except requests.exceptions.RequestException as e:
            logger.error("Chat API request failed: %s", e)
            return ChatResponse(
                status="error",
                response=f"Failed to connect to LLM: {e!s}",
                sender="assistant",
                model=model or "unknown",
            )
        except Exception as e:
            logger.error("Chat API error: %s", e, exc_info=True)
            return ChatResponse(
                status="error", response=str(e), sender="assistant", model=model or "unknown", response_type="error"
            )

    # ------------------------------------------------------------------
    # Streaming support
    # ------------------------------------------------------------------

    @staticmethod
    def _chat_response_to_events(result: ChatResponse) -> Generator[dict[str, Any], None, None]:
        """Convert a ChatResponse into SSE-style event dicts (non-streaming).

        Used for direct tool commands and tool redirects: a single
        ``done`` event carries the complete response payload.
        """
        yield {
            "type": "done",
            "response": result.response,
            "model": result.model,
            "sender": result.sender,
            "status": result.status,
            "response_type": result.response_type,
            "thinking": result.thinking,
            "tools_called": list(result.tools_called or []),
        }

    def process_message_stream(
        self,
        message: str,
        host: str | None = None,
        port: int | None = None,
        model: str | None = None,
        folder_path: str | None = None,
        history: list | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Process a chat message with streaming, yielding event dicts.

        Mirrors :meth:`process_message` but streams LLM tokens incrementally
        and runs the same native tool-calling loop. Direct tool commands and
        LLM-detected tool redirects produce a single ``done`` event (no token
        streaming) since the tool result is computed server-side.

        Event types yielded:

        - ``{"type": "token", "content": "..."}`` — incremental LLM text
        - ``{"type": "thinking", "content": "..."}`` — incremental reasoning
          trace (only when debug reasoning is enabled)
        - ``{"type": "tool", "name": "..."}`` — a tool the LLM invoked
          implicitly (native tool calling); emitted before execution
        - ``{"type": "done", "response": ..., "model": ..., ...}`` — final
          result (response may differ from concatenated tokens when a
          tool redirect occurred)
        - ``{"type": "error", "message": "..."}`` — failure
        """
        message = message.strip()
        if not message:
            yield {"type": "error", "message": "Message is required"}
            return

        # Direct tool commands: execute immediately (no streaming)
        normalized = self._normalize_tool_command(message)
        if normalized is not None:
            result = self.handle_tool_command(normalized, folder_path)
            yield from self._chat_response_to_events(result)
            return

        # Regular LLM message: stream tokens, calling tools as requested
        try:
            chat_client = self._ensure_chat_client()
            effective_model = model or chat_client.model
            system_prompt = self.get_system_prompt()
            think = bool(getattr(self.config, "debug_reasoning", False))
            tool_specs = self._get_tool_specs()
            messages = LLMChatClient.build_messages(message, system_prompt=system_prompt, history=history)

            thinking_text = ""
            called_functions: list[str] = []

            for _turn in range(_MAX_TOOL_TURNS + 1):
                full_response = ""
                turn_tool_calls: list[ToolCall] = []

                for chunk in chat_client.chat_messages_stream(messages, tools=tool_specs, think=think):
                    if chunk.kind == "thinking":
                        thinking_text += chunk.content
                        yield {"type": "thinking", "content": chunk.content}
                    elif chunk.kind == "tool_calls":
                        turn_tool_calls.extend(chunk.tool_calls)
                        for call in chunk.tool_calls:
                            called_functions.append(call.name)
                            yield {"type": "tool", "name": call.name}
                    else:
                        full_response += chunk.content
                        yield {"type": "token", "content": chunk.content}

                if not turn_tool_calls:
                    # Final text answer (with the slash-command text routing
                    # fallback, as in process_message).
                    cleaned_response = self._clean_response(full_response)
                    extracted = self._extract_tool_command(full_response)
                    if extracted is not None:
                        result = self.handle_tool_command(extracted, folder_path)
                        result.model = effective_model
                        result.thinking = thinking_text or None
                        result.tools_called = called_functions or None
                        yield from self._chat_response_to_events(result)
                        return

                    # Regular LLM response — final event carries the cleaned text
                    yield {
                        "type": "done",
                        "response": cleaned_response,
                        "model": effective_model,
                        "sender": "assistant",
                        "status": "success",
                        "response_type": None,
                        "thinking": thinking_text or None,
                        "tools_called": called_functions,
                    }
                    return

                # Execute the requested tools. Structured results (photo
                # galleries, tag chips) are returned to the user directly,
                # exactly as when the matching slash command is typed.
                executed = self._execute_tool_calls(tuple(turn_tool_calls), folder_path)
                for _call, result in executed:
                    if result.response_type in _STRUCTURED_RESPONSE_TYPES:
                        result.model = effective_model
                        result.thinking = thinking_text or None
                        result.tools_called = called_functions
                        yield from self._chat_response_to_events(result)
                        return

                # Feed text results back so the model can compose an answer.
                messages.append(
                    {
                        "role": "assistant",
                        "content": full_response,
                        "tool_calls": [
                            {"function": {"name": call.name, "arguments": call.arguments}} for call in turn_tool_calls
                        ],
                    }
                )
                for call, result in executed:
                    messages.append({"role": "tool", "name": call.name, "content": self._tool_result_text(result)})

            yield {
                "type": "error",
                "message": "The model did not finish after several tool calls. Please rephrase your request.",
                "model": effective_model,
            }

        except requests.exceptions.RequestException as e:
            logger.error("Chat stream request failed: %s", e)
            yield {
                "type": "error",
                "message": f"Failed to connect to LLM: {e!s}",
                "model": model or "unknown",
            }
        except Exception as e:
            logger.error("Chat stream error: %s", e, exc_info=True)
            yield {
                "type": "error",
                "message": str(e),
                "model": model or "unknown",
            }
