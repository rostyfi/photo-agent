"""Base interface for all chat tools.

This module provides the BaseTool abstract class and ToolMetadata dataclass
that all chat tools must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from src.config import AppConfig
    from src.services.chat_response import ChatResponse


@dataclass(frozen=True)
class ToolMetadata:
    """Metadata for a chat tool.

    This dataclass contains all the metadata needed to describe a tool,
    including its command, name, description, and requirements.

    Attributes:
        command: The command string (e.g., "/about", "/find")
        name: Human-readable name (e.g., "About", "Find")
        description: Short description of what the tool does
        help_text: Text shown in /tools list
        usage: Usage example (e.g., "/find <number> <description>")
        requires_folder: Whether the tool needs a folder path
        arg_pattern: Optional regex pattern for argument extraction
        tool_description: Optional model-facing description for native tool
            calling. Falls back to ``description`` when not set.
    """

    command: str
    name: str
    description: str
    help_text: str
    usage: str
    requires_folder: bool = False
    arg_pattern: str | None = None
    tool_description: str | None = None


class BaseTool(ABC):
    """Abstract base class for all chat tools.

    All chat tools must inherit from this class and implement the execute() method.
    Tools are automatically discovered and loaded by the chat_tools package.

    Class Attributes:
        metadata: ToolMetadata class attribute with tool metadata

    Instance Attributes:
        config: AppConfig instance passed during initialization
    """

    metadata: ToolMetadata

    # JSON schema (Ollama tool-calling format) for the tool's arguments.
    # Tools that take arguments override this together with
    # command_from_arguments().
    parameters_schema: ClassVar[dict] = {"type": "object", "properties": {}, "required": []}

    def __init__(self, config: "AppConfig"):
        """Initialize the tool with application config.

        Args:
            config: AppConfig instance with application settings
        """
        self.config = config

    @property
    def function_name(self) -> str:
        """Name exposed to the LLM for native tool calling.

        The slash command without the leading slash (e.g. ``/find`` -> ``find``).
        """
        return self.metadata.command.lstrip("/")

    def to_tool_spec(self) -> dict:
        """Build the tool specification for native LLM tool calling.

        Returns:
            A tool spec dict (``{"type": "function", "function": {...}}`` in
            the Ollama ``tools`` format) with the function name, a
            model-facing description, and the JSON schema for the arguments.
        """
        metadata = self.metadata
        description = metadata.tool_description or metadata.description
        if metadata.requires_folder and "folder" not in description.lower():
            description = f"{description} Requires a folder to be selected."
        return {
            "type": "function",
            "function": {
                "name": self.function_name,
                "description": description,
                "parameters": self.parameters_schema,
            },
        }

    def command_from_arguments(self, arguments: dict | None = None) -> str:
        """Build the slash command equivalent from structured tool arguments.

        When the LLM invokes the tool via native tool calling, the structured
        arguments are converted back into the command string the tool already
        knows how to parse. Tools without arguments return their bare
        command; tools with arguments override this.

        Args:
            arguments: The parsed JSON arguments from the tool call.

        Returns:
            The equivalent slash command string (e.g. ``/find 5 cats``).
        """
        return self.metadata.command

    @abstractmethod
    def execute(self, folder_path: str | None = None, args: str | None = None) -> "ChatResponse":
        """Execute the tool and return a ChatResponse.

        This is the main method that each tool must implement.

        Args:
            folder_path: The folder path for database operations (if required)
            args: Optional arguments string (e.g., "5 cats" for /find)

        Returns:
            ChatResponse with the tool's result
        """
        pass

    def parse_args(self, command: str) -> str | None:
        """Extract arguments from the full command string.

        For simple commands like /about, returns None.
        For commands with args like /find 5 cats, returns "5 cats".

        Args:
            command: The full command string (e.g., "/find 5 cats")

        Returns:
            The arguments string, or None if no arguments
        """
        if self.metadata.arg_pattern:
            # For tools that need custom parsing
            return command[len(self.metadata.command) :].strip()
        return None

    def validate(self, folder_path: str | None = None, args: str | None = None) -> str | None:
        """Validate inputs before execution.

        Checks common validation requirements like folder_path being present.

        Args:
            folder_path: The folder path to validate
            args: The arguments string to validate

        Returns:
            Error message string if validation fails, None otherwise
        """
        if self.metadata.requires_folder and not folder_path:
            return "No folder specified. Please select a folder first."
        return None

    def __call__(self, folder_path: str | None = None, command: str | None = None) -> "ChatResponse":
        """Allow tool to be called directly with validation.

        This method enables tools to be called as functions, which is used
        by ChatService for dynamic tool dispatch.

        Args:
            folder_path: The folder path for database operations
            command: The full command string (for argument parsing)

        Returns:
            ChatResponse with the tool's result or validation error
        """
        from src.services.chat_response import ChatResponse

        args = self.parse_args(command) if command else None

        if error := self.validate(folder_path, args):
            return ChatResponse(status="error", response=error, sender="assistant", model="N/A")

        return self.execute(folder_path, args)
