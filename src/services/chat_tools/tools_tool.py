"""Tools tool - Lists all available tools."""

from src.services.chat_tools.base import BaseTool, ToolMetadata
from src.services.chat_response import ChatResponse
from typing import Optional, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.chat_tools.base import BaseTool as BaseToolType


class ToolsTool(BaseTool):
    """Tool that lists all available tools."""
    
    metadata = ToolMetadata(
        command="/tools",
        name="Tools",
        description="Lists available tools",
        help_text="/tools - Lists available tools",
        usage="/tools",
        requires_folder=False
    )
    
    def __init__(self, config, all_tools: Optional[Dict[str, "BaseToolType"]] = None):
        """Initialize the tools tool.
        
        Args:
            config: AppConfig instance
            all_tools: Dictionary of all loaded tools (injected by ChatService)
        """
        super().__init__(config)
        self._all_tools: Dict[str, "BaseToolType"] = all_tools or {}
    
    def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
        """Execute the tools tool.
        
        Builds a list of all available tools from the loaded tools dictionary.
        
        Args:
            folder_path: Not used for this tool
            args: Not used for this tool
            
        Returns:
            ChatResponse with formatted list of tools
        """
        # Build tools list from all registered tools
        tools_list = []
        for command, tool in sorted(self._all_tools.items()):
            tools_list.append(f"{command} - {tool.metadata.description}")
        
        response = "**Available Tools:**\n\n" + "\n".join(tools_list)
        
        return ChatResponse(
            status="success",
            response=response,
            sender="assistant",
            model="N/A"
        )
