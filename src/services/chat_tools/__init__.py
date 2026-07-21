"""Chat tools package for Open Photo Agent.

This package provides a pluggable tool system for chat commands.
Tools are dynamically discovered and loaded from this package.

Usage:
    from src.services.chat_tools import BaseTool, ToolMetadata, load_all_tools
    
    # Load all tools
    tools = load_all_tools(config)
    
    # Get a specific tool
    from src.services.chat_tools import get_tool
    about_tool = get_tool("/about", tools)
"""

from src.services.chat_tools.base import BaseTool, ToolMetadata
from src.services.chat_tools.loader import load_all_tools, get_tool, discover_tools, reload_tools

# Re-export for convenience
__all__ = [
    "BaseTool",
    "ToolMetadata",
    "load_all_tools",
    "get_tool",
    "discover_tools",
    "reload_tools",
]
