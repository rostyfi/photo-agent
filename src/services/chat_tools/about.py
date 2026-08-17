"""About tool - Shows information about the agent."""

from src.services.chat_response import ChatResponse
from src.services.chat_tools.base import BaseTool, ToolMetadata
from src.version import __version__


class AboutTool(BaseTool):
    """Tool that provides information about the agent."""

    metadata = ToolMetadata(
        command="/about",
        name="About",
        description="Shows information about the agent",
        help_text="/about - Shows information about the agent",
        usage="/about",
        requires_folder=False,
    )

    def execute(self, folder_path: str | None = None, args: str | None = None) -> ChatResponse:
        """Execute the about tool.

        Args:
            folder_path: Not used for this tool
            args: Not used for this tool

        Returns:
            ChatResponse with agent information
        """
        return ChatResponse(
            status="success",
            response=(
                f"I am the **Local Photo Agent** (v{__version__}), a chat assistant for a photo feature "
                "extraction system. I have access to specific tools for querying photo databases. "
                "Use `/tools` to see available commands."
            ),
            sender="assistant",
            model="N/A",
        )
