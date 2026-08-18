"""Chat service for handling chat messages and tool commands.

This module provides the ChatService class which handles:
- Dynamic tool command execution (loaded from src.services.chat_tools)
- LLM interaction via abstract LLMChatClient
- Response processing and formatting

Tools are dynamically loaded from the src.services.chat_tools package,
allowing for extensibility without modifying this file.
"""

import logging
from collections.abc import Generator
from typing import Any

import requests

from src.config import AppConfig
from src.interfaces import LLMChatClient
from src.services.chat_response import ChatResponse

logger = logging.getLogger(__name__)


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
            self._tools["/tools"]._all_tools = self._tools

    def _get_tool_commands(self) -> list[str]:
        """Get list of all registered tool commands.

        Returns:
            List of command strings (e.g., ["/about", "/count", ...])
        """
        return list(self._tools.keys())

    def _get_tools_list(self) -> str:
        """Generate the list of available tools for the system prompt.

        Returns:
            Formatted string listing all tools and their descriptions
        """
        lines = []
        for command, tool in sorted(self._tools.items()):
            metadata = tool.metadata
            # For /find, /tags, and /tag, include the usage pattern
            if command == "/find":
                lines.append(
                    f"{command} <number> <description> [@<date>] - {metadata.description} / {metadata.usage}"
                )
            elif command == "/tags":
                lines.append(f"{command} [topic] - {metadata.description} / {metadata.usage}")
            elif command == "/tag":
                lines.append(f"{command} <tagname> - {metadata.description} / {metadata.usage}")
            else:
                lines.append(f"{command} - {metadata.description}")
        return "\n".join(lines)

    def _get_tool_examples(self) -> str:
        """Generate example mappings for the system prompt.

        Returns:
            Formatted string with examples of user inputs and tool responses
        """
        examples = []

        # Special examples for /find
        examples.append("  User: 'find photos of cats' -> YOU: '/find cats'")
        examples.append("  User: 'find 5 photos of cats' -> YOU: '/find 5 cats'")
        examples.append("  User: 'show me 10 images of dogs' -> YOU: '/find 10 dogs'")
        examples.append("  User: 'I want to see 20 pictures of mountains' -> YOU: '/find 20 mountains'")
        examples.append("  User: 'can you find 3 photos of beaches' -> YOU: '/find 3 beaches'")
        examples.append("  User: 'show me photos of animals' -> YOU: '/find animals'")
        examples.append("  User: 'show me photos of birds' -> YOU: '/find birds'")
        # /find with a date filter (append @<date> when the user mentions a time)
        examples.append("  User: 'find photos of a car from last summer' -> YOU: '/find car @last summer'")
        examples.append("  User: 'show me 5 photos of dogs from summer 2024' -> YOU: '/find 5 dogs @summer 2024'")
        examples.append("  User: 'find photos of snow from January 2024' -> YOU: '/find snow @january 2024'")
        examples.append("  User: 'show me beach photos from 2023' -> YOU: '/find beach @2023'")
        examples.append("  User: 'find photos of flowers from last month' -> YOU: '/find flowers @last month'")

        # Examples for /tags tool
        examples.append("  User: 'show me tags related to sport' -> YOU: '/tags sport'")
        examples.append("  User: 'list all tags' -> YOU: '/tags'")
        examples.append("  User: 'what tags do you have?' -> YOU: '/tags'")
        examples.append("  User: 'find tags about animals' -> YOU: '/tags animals'")

        # Examples for /tag tool (ONLY for exact existing tag names)
        examples.append("  User: 'show me photos with the nature tag' -> YOU: '/tag nature'")
        examples.append("  User: 'show me photos tagged with football' -> YOU: '/tag football'")

        # Examples for other tools
        examples.append("  User: 'scan the folder' -> YOU: '/scan'")
        examples.append("  User: 'start processing the photos' -> YOU: '/process'")
        examples.append("  User: 'how many photos have been processed?' -> YOU: '/count'")
        examples.append("  User: 'what is the status?' -> YOU: '/status'")
        examples.append("  User: 'what can you do' -> YOU: '/tools'")
        examples.append("  User: 'who are you' -> YOU: '/about'")

        return "\n".join(examples)

    def get_system_prompt(self) -> str:
        """Build the system prompt for the LLM.

        The system prompt is dynamically generated from the loaded tools'
        metadata, ensuring it stays up-to-date when new tools are added.

        Returns:
            The system prompt string to guide LLM behavior
        """
        tools_list = self._get_tools_list()
        examples = self._get_tool_examples()

        return (
            "You are the Local Photo Agent, a chat assistant for a photo feature extraction system.\n"
            "You MUST follow these rules EXACTLY:\n\n"
            "RULE 1: If the user's intent matches ANY tool, respond with EXACTLY ONE tool command and NOTHING else.\n"
            "RULE 2: If the user's intent does NOT match any tool, respond as a helpful assistant.\n\n"
            "CRITICAL INSTRUCTIONS FOR TOOL COMMANDS:\n"
            "- Return ONLY the tool command text, NO other text, NO markdown, NO explanations\n"
            "- The tool command must be EXACTLY like: /scan or /process or /find cats\n"
            "- NEVER add words before, after, or around the tool command\n"
            "- NEVER say 'I can do that with...' or 'Here is...' or any other text\n"
            "- NEVER use markdown formatting like **bold** or code blocks\n"
            "- The ONLY exception: if user asks about your capabilities, you may describe them\n\n"
            f"AVAILABLE TOOL COMMANDS:\n"
            f"{tools_list}\n\n"
            "IMPORTANT: When the user says ANYTHING that matches a tool's purpose, return ONLY the tool command.\n"
            "For /find command: If the user specifies a number (e.g., 'find 5 photos of cats', 'show me 10 images'), \n"
            "extract the number and include it at the beginning of the description in the tool command.\n"
            "For /tags command: Use '/tags' for listing all tags, '/tags <topic>' for finding tags related to a topic.\n"
            "For /tag command: Use '/tag <tagname>' for showing photos with a specific tag and related tags.\n"
            "\n"
            "ROUTING RULES (choose the correct tool):\n"
            "- /find: search photos by a DESCRIPTION or SUBJECT the user describes (e.g., 'photos of animals', 'photos of birds', 'dogs running'). Use /find for any 'show me photos of X' where X is a subject/description, NOT an exact tag name.\n"
            "  When the user mentions WHEN the photo was taken (e.g., 'last summer', 'summer 2024', 'January 2024', '2023', 'last month', 'last winter with a baby'), separate the visual description from the time words. Preferred form: '/find <description> @<date>' e.g. '/find car @last summer' or '/find 5 baby @last winter'. If you cannot cleanly separate them, output '/find <description and date words as written>' and the find tool will split them itself. Never drop the description or the date.\n"
            "- /tag: ONLY filter photos by an EXACT tag name the user already knows exists (e.g., 'photos with the nature tag'). Never use /tag for general subject searches — use /find instead.\n"
            "- /tags: list or discover available tag names by topic.\n"
            "- If unsure whether the user means a subject search or an exact tag, prefer /find.\n"
            "For example:\n"
            f"{examples}\n\n"
            "REMEMBER: The tool command must be the ONLY text in your response. Nothing else."
        )

    def handle_tool_command(self, command: str, folder_path: str | None = None) -> ChatResponse:
        """Execute a tool command and return the response.

        This is the single entry point for all tool command handling.
        Tools are dynamically loaded and executed based on the command string.

        Args:
            command: The tool command string (e.g., "/count", "/find cats")
            folder_path: Optional folder path for database operations

        Returns:
            ChatResponse with the result of the tool command
        """
        # Preserve original case of arguments (tag names are case-sensitive in
        # some queries); match only the command keyword case-insensitively.
        command = command.strip()
        command_lower = command.lower()

        # Handle /find and /tags specially since they have arguments
        if command_lower.startswith("/find "):
            tool = self._tools.get("/find")
            if tool:
                return tool(folder_path, command)

        if command_lower.startswith("/tags"):
            tool = self._tools.get("/tags")
            if tool:
                return tool(folder_path, command)

        if command_lower.startswith("/tag "):
            tool = self._tools.get("/tag")
            if tool:
                return tool(folder_path, command)

        # Look up exact command match (case-insensitive)
        tool = self._tools.get(command_lower)
        if tool:
            return tool(folder_path, command)

        return ChatResponse(status="error", response=f"Unknown command: {command}", sender="assistant", model="N/A")

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
        2. LLM-based chat for non-command messages
        3. Tool commands returned by the LLM (e.g., LLM returns "/find cats")

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

        # Check if message is a direct tool command
        message_lower = message.lower().strip()

        # Get list of tool commands for checking
        tool_commands = self._get_tool_commands()

        # Check for exact slash command match first
        if message_lower in tool_commands:
            return self.handle_tool_command(message, folder_path)

        # Check for /find with description
        if message_lower.startswith("/find "):
            return self.handle_tool_command(message, folder_path)

        # Check for /tags with topic
        if message_lower.startswith("/tags"):
            return self.handle_tool_command(message, folder_path)

        # Check for /tag with tag name
        if message_lower.startswith("/tag "):
            return self.handle_tool_command(message, folder_path)

        # Not a direct command, send to LLM
        try:
            # Get the chat client (will create one if needed using host/port/model)
            chat_client = self._ensure_chat_client()

            # Use provided parameters or fall back to chat client's defaults
            effective_model = model or chat_client.model

            # Get system prompt
            system_prompt = self.get_system_prompt()

            raw_response = chat_client.chat(message, system_prompt=system_prompt, history=history)
            logger.debug("[Chat LLM] Raw response: %r", raw_response)

            # Clean up response
            cleaned_response = self._clean_response(raw_response)
            logger.debug("[Chat LLM] Cleaned response: %r", cleaned_response)

            # Check if the LLM returned a tool command
            response_stripped = cleaned_response.strip()
            logger.debug("[Chat LLM] Stripped response: %r", response_stripped)

            if response_stripped in tool_commands:
                result = self.handle_tool_command(response_stripped, folder_path)
                # Update model in response to reflect the actual model used
                result.model = effective_model
                return result

            if response_stripped.startswith("/find ") and folder_path:
                result = self.handle_tool_command(response_stripped, folder_path)
                result.model = effective_model
                return result

            if response_stripped.startswith("/tags") and folder_path:
                result = self.handle_tool_command(response_stripped, folder_path)
                result.model = effective_model
                return result

            if response_stripped.startswith("/tag ") and folder_path:
                result = self.handle_tool_command(response_stripped, folder_path)
                result.model = effective_model
                return result

            # Regular LLM response
            return ChatResponse(status="success", response=cleaned_response, sender="assistant", model=effective_model)

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

        Mirrors :meth:`process_message` but streams LLM tokens incrementally.
        Direct tool commands and LLM-detected tool redirects produce a
        single ``done`` event (no token streaming) since the tool result
        is computed server-side.

        Event types yielded:

        - ``{"type": "token", "content": "..."}`` — incremental LLM text
        - ``{"type": "done", "response": ..., "model": ..., ...}`` — final
          result (response may differ from concatenated tokens when a
          tool redirect occurred)
        - ``{"type": "error", "message": "..."}`` — failure
        """
        message = message.strip()
        if not message:
            yield {"type": "error", "message": "Message is required"}
            return

        message_lower = message.lower().strip()
        tool_commands = self._get_tool_commands()

        # Direct tool commands: execute immediately (no streaming)
        if (
            message_lower in tool_commands
            or message_lower.startswith("/find ")
            or message_lower.startswith("/tags")
            or message_lower.startswith("/tag ")
        ):
            result = self.handle_tool_command(message, folder_path)
            yield from self._chat_response_to_events(result)
            return

        # Regular LLM message: stream tokens
        try:
            chat_client = self._ensure_chat_client()
            effective_model = model or chat_client.model
            system_prompt = self.get_system_prompt()

            full_response = ""
            for chunk in chat_client.chat_stream(message, system_prompt=system_prompt, history=history):
                full_response += chunk
                yield {"type": "token", "content": chunk}

            # Check whether the LLM's complete response is a tool command
            cleaned_response = self._clean_response(full_response)
            response_stripped = cleaned_response.strip()

            is_tool_command = response_stripped in tool_commands
            is_find_command = response_stripped.startswith("/find ") and folder_path
            is_tags_command = response_stripped.startswith("/tags") and folder_path
            is_tag_command = response_stripped.startswith("/tag ") and folder_path

            if is_tool_command or is_find_command or is_tags_command or is_tag_command:
                result = self.handle_tool_command(response_stripped, folder_path)
                result.model = effective_model
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
