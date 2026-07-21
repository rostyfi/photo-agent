"""Dynamic tool loading utilities for chat tools.

This module provides utilities for discovering and loading chat tools
dynamically from the chat_tools package.
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import AppConfig
    from src.services.chat_tools.base import BaseTool


def discover_tools() -> List[Type["BaseTool"]]:
    """Discover all tool classes in the chat_tools package.
    
    Uses pkgutil to iterate through all modules in the chat_tools package
    and find all BaseTool subclasses.
    
    Returns:
        List of BaseTool subclass types
    """
    from src.services.chat_tools.base import BaseTool
    
    tools: List[Type[BaseTool]] = []
    
    # Get the chat_tools package path
    package_path = Path(__file__).parent
    package_name = "src.services.chat_tools"
    
    # Iterate through all Python files in the package
    for finder, name, ispkg in pkgutil.iter_modules([str(package_path)]):
        # Skip __init__ and private modules
        if name.startswith("_"):
            continue
        
        try:
            module = importlib.import_module(f"{package_name}.{name}")
            
            # Find all BaseTool subclasses in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseTool)
                    and attr is not BaseTool
                    and hasattr(attr, "metadata")
                ):
                    tools.append(attr)
        except ImportError as e:
            # Log but don't fail on import errors
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to import tool module {name}: {e}")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error loading tool module {name}: {e}", exc_info=True)
    
    return tools


def load_all_tools(config: "AppConfig") -> Dict[str, "BaseTool"]:
    """Load and instantiate all discovered tools.
    
    Discovers all tool classes using discover_tools(), then instantiates
    each one with the provided config.
    
    Args:
        config: AppConfig instance to pass to tool constructors
        
    Returns:
        Dictionary mapping command names to tool instances
    """
    from src.services.chat_tools.base import BaseTool
    
    tools_map: Dict[str, BaseTool] = {}
    
    for tool_class in discover_tools():
        try:
            tool_instance = tool_class(config)
            tools_map[tool_instance.metadata.command] = tool_instance
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to instantiate {tool_class.__name__}: {e}", exc_info=True)
    
    return tools_map


def get_tool(command: str, tools: Dict[str, "BaseTool"]) -> "BaseTool":
    """Get a tool instance by command name.
    
    Args:
        command: The command string (e.g., "/about")
        tools: Dictionary of loaded tools (command -> tool instance)
        
    Returns:
        The tool instance, or None if not found
    """
    return tools.get(command)


def reload_tools(config: "AppConfig") -> Dict[str, "BaseTool"]:
    """Reload all tools from disk.
    
    This is useful for development or when tools are added/removed at runtime.
    
    Args:
        config: AppConfig instance to pass to tool constructors
        
    Returns:
        Fresh dictionary of loaded tools
    """
    # Clear module cache for chat_tools
    import sys
    package_name = "src.services.chat_tools"
    
    # Remove all chat_tools modules from sys.modules
    modules_to_remove = [
        key for key in sys.modules.keys()
        if key.startswith(package_name)
    ]
    for module in modules_to_remove:
        del sys.modules[module]
    
    # Now reload and return fresh tools
    return load_all_tools(config)
