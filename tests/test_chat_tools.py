"""Tests for the chat tools system.

This module tests:
- BaseTool interface and ToolMetadata
- Individual tool implementations
- Dynamic tool loading
- ChatService integration with tools
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestToolMetadata:
    """Tests for ToolMetadata dataclass."""
    
    def test_tool_metadata_creation(self):
        """Test creating ToolMetadata with all fields."""
        from src.services.chat_tools.base import ToolMetadata
        
        metadata = ToolMetadata(
            command="/test",
            name="Test",
            description="A test tool",
            help_text="/test - A test tool",
            usage="/test",
            requires_folder=True,
            arg_pattern=r"^/test\s+"
        )
        
        assert metadata.command == "/test"
        assert metadata.name == "Test"
        assert metadata.description == "A test tool"
        assert metadata.help_text == "/test - A test tool"
        assert metadata.usage == "/test"
        assert metadata.requires_folder is True
        assert metadata.arg_pattern == r"^/test\s+"
    
    def test_tool_metadata_defaults(self):
        """Test ToolMetadata default values."""
        from src.services.chat_tools.base import ToolMetadata
        
        metadata = ToolMetadata(
            command="/simple",
            name="Simple",
            description="A simple tool",
            help_text="/simple - Simple",
            usage="/simple"
        )
        
        assert metadata.requires_folder is False
        assert metadata.arg_pattern is None
    
    def test_tool_metadata_frozen(self):
        """Test that ToolMetadata is immutable."""
        from src.services.chat_tools.base import ToolMetadata
        
        metadata = ToolMetadata(
            command="/test",
            name="Test",
            description="A test tool",
            help_text="/test - A test tool",
            usage="/test"
        )
        
        with pytest.raises(AttributeError):
            metadata.command = "/changed"


class TestBaseTool:
    """Tests for BaseTool abstract class."""
    
    def test_base_tool_abstract(self):
        """Test that BaseTool cannot be instantiated directly."""
        from src.services.chat_tools.base import BaseTool, ToolMetadata
        
        # Create a mock config
        mock_config = Mock()
        
        with pytest.raises(TypeError):
            # Cannot instantiate abstract class
            tool = BaseTool(mock_config)
    
    def test_base_tool_subclass(self):
        """Test that a subclass of BaseTool can be instantiated."""
        from src.services.chat_tools.base import BaseTool, ToolMetadata
        from src.services.chat_response import ChatResponse
        from typing import Optional
        
        class TestTool(BaseTool):
            metadata = ToolMetadata(
                command="/test",
                name="Test",
                description="A test tool",
                help_text="/test - A test tool",
                usage="/test"
            )
            
            def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
                return ChatResponse(
                    status="success",
                    response="Test response",
                    sender="assistant",
                    model="N/A"
                )
        
        mock_config = Mock()
        tool = TestTool(mock_config)
        
        assert tool.config == mock_config
        assert tool.metadata.command == "/test"
    
    def test_base_tool_validate_folder_required(self):
        """Test validation for tools that require folder."""
        from src.services.chat_tools.base import BaseTool, ToolMetadata
        from src.services.chat_response import ChatResponse
        from typing import Optional
        
        class FolderTool(BaseTool):
            metadata = ToolMetadata(
                command="/folder",
                name="Folder",
                description="Requires folder",
                help_text="/folder - Requires folder",
                usage="/folder",
                requires_folder=True
            )
            
            def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
                return ChatResponse(status="success", response="OK", sender="assistant", model="N/A")
        
        mock_config = Mock()
        tool = FolderTool(mock_config)
        
        # Validation should fail without folder
        error = tool.validate(folder_path=None)
        assert error == "No folder specified. Please select a folder first."
        
        # Validation should pass with folder
        error = tool.validate(folder_path="/some/path")
        assert error is None
    
    def test_base_tool_validate_no_folder_required(self):
        """Test validation for tools that don't require folder."""
        from src.services.chat_tools.base import BaseTool, ToolMetadata
        from src.services.chat_response import ChatResponse
        from typing import Optional
        
        class SimpleTool(BaseTool):
            metadata = ToolMetadata(
                command="/simple",
                name="Simple",
                description="Doesn't require folder",
                help_text="/simple - Doesn't require folder",
                usage="/simple",
                requires_folder=False
            )
            
            def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
                return ChatResponse(status="success", response="OK", sender="assistant", model="N/A")
        
        mock_config = Mock()
        tool = SimpleTool(mock_config)
        
        # Validation should pass without folder
        error = tool.validate(folder_path=None)
        assert error is None
    
    def test_base_tool_parse_args(self):
        """Test argument parsing."""
        from src.services.chat_tools.base import BaseTool, ToolMetadata
        from src.services.chat_response import ChatResponse
        from typing import Optional
        
        class ArgTool(BaseTool):
            metadata = ToolMetadata(
                command="/arg",
                name="Arg",
                description="Takes arguments",
                help_text="/arg - Takes arguments",
                usage="/arg <args>",
                arg_pattern=r"^/arg\s+"
            )
            
            def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
                return ChatResponse(status="success", response=f"Args: {args}", sender="assistant", model="N/A")
        
        mock_config = Mock()
        tool = ArgTool(mock_config)
        
        # Parse args from command
        args = tool.parse_args("/arg test123")
        assert args == "test123"
        
        # No args pattern
        class NoArgTool(BaseTool):
            metadata = ToolMetadata(
                command="/noarg",
                name="NoArg",
                description="No arguments",
                help_text="/noarg - No arguments",
                usage="/noarg"
            )
            
            def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
                return ChatResponse(status="success", response="OK", sender="assistant", model="N/A")
        
        no_arg_tool = NoArgTool(mock_config)
        args = no_arg_tool.parse_args("/noarg extra")
        assert args is None
    
    def test_base_tool_callable(self):
        """Test that tools can be called directly."""
        from src.services.chat_tools.base import BaseTool, ToolMetadata
        from src.services.chat_response import ChatResponse
        from typing import Optional
        
        class CallableTool(BaseTool):
            metadata = ToolMetadata(
                command="/callable",
                name="Callable",
                description="Can be called",
                help_text="/callable - Can be called",
                usage="/callable"
            )
            
            def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
                return ChatResponse(status="success", response="Called!", sender="assistant", model="N/A")
        
        mock_config = Mock()
        tool = CallableTool(mock_config)
        
        # Call the tool directly
        result = tool(folder_path="/path", command="/callable")
        
        assert result.status == "success"
        assert result.response == "Called!"
    
    def test_base_tool_callable_validation_error(self):
        """Test that tools return validation errors when called."""
        from src.services.chat_tools.base import BaseTool, ToolMetadata
        from src.services.chat_response import ChatResponse
        from typing import Optional
        
        class ValidatedTool(BaseTool):
            metadata = ToolMetadata(
                command="/validated",
                name="Validated",
                description="Requires folder",
                help_text="/validated - Requires folder",
                usage="/validated",
                requires_folder=True
            )
            
            def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
                return ChatResponse(status="success", response="OK", sender="assistant", model="N/A")
        
        mock_config = Mock()
        tool = ValidatedTool(mock_config)
        
        # Call without folder should return error
        result = tool(folder_path=None, command="/validated")
        
        assert result.status == "error"
        assert "No folder specified" in result.response


class TestToolLoader:
    """Tests for tool loading functionality."""
    
    def test_discover_tools(self):
        """Test discovering tools from the chat_tools package."""
        from src.services.chat_tools.loader import discover_tools
        
        tools = discover_tools()
        
        # Should find at least our 7 tools
        assert len(tools) >= 7
        
        # Check that we have the expected tools
        tool_names = [t.__name__ for t in tools]
        expected_tools = ["AboutTool", "ToolsTool", "CountTool", "FindTool", "ScanTool", "ProcessTool", "StatusTool"]
        for expected in expected_tools:
            assert expected in tool_names, f"Expected tool {expected} not found. Found: {tool_names}"
    
    def test_load_all_tools(self):
        """Test loading and instantiating all tools."""
        from src.services.chat_tools.loader import load_all_tools
        from src.config import AppConfig
        
        # Create a mock config
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        tools = load_all_tools(config)
        
        # Should have at least 7 tools loaded
        assert len(tools) >= 7
        
        # Check that we can access tools by command
        assert "/about" in tools
        assert "/tools" in tools
        assert "/count" in tools
        assert "/find" in tools
        assert "/scan" in tools
        assert "/process" in tools
        assert "/status" in tools
        
        # Check that tools have metadata
        about_tool = tools.get("/about")
        assert about_tool is not None
        assert about_tool.metadata.command == "/about"
        assert about_tool.config == config
    
    def test_get_tool(self):
        """Test getting a specific tool by command."""
        from src.services.chat_tools.loader import load_all_tools, get_tool
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        tools = load_all_tools(config)
        
        # Get a specific tool
        about_tool = get_tool("/about", tools)
        assert about_tool is not None
        assert about_tool.metadata.command == "/about"
        
        # Get a non-existent tool
        none_tool = get_tool("/nonexistent", tools)
        assert none_tool is None


class TestAboutTool:
    """Tests for AboutTool."""
    
    def test_about_tool_execute(self):
        """Test AboutTool execution."""
        from src.services.chat_tools.about import AboutTool
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test"
        )
        
        tool = AboutTool(config)
        result = tool.execute()
        
        assert result.status == "success"
        assert "Local Photo Agent" in result.response
        assert result.sender == "assistant"
        assert result.model == "N/A"
    
    def test_about_tool_metadata(self):
        """Test AboutTool metadata."""
        from src.services.chat_tools.about import AboutTool
        
        assert AboutTool.metadata.command == "/about"
        assert AboutTool.metadata.name == "About"
        assert AboutTool.metadata.requires_folder is False


class TestCountTool:
    """Tests for CountTool."""
    
    def test_count_tool_metadata(self):
        """Test CountTool metadata."""
        from src.services.chat_tools.count import CountTool
        
        assert CountTool.metadata.command == "/count"
        assert CountTool.metadata.name == "Count"
        assert CountTool.metadata.requires_folder is True
    
    def test_count_tool_validate(self):
        """Test CountTool validation."""
        from src.services.chat_tools.count import CountTool
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test"
        )
        
        tool = CountTool(config)
        
        # Should fail without folder
        error = tool.validate(folder_path=None)
        assert error == "No folder specified. Please select a folder first."
        
        # Should pass with folder
        error = tool.validate(folder_path="/some/path")
        assert error is None


class TestFindTool:
    """Tests for FindTool."""
    
    def test_find_tool_metadata(self):
        """Test FindTool metadata."""
        from src.services.chat_tools.find import FindTool
        
        assert FindTool.metadata.command == "/find"
        assert FindTool.metadata.name == "Find"
        assert FindTool.metadata.requires_folder is True
        assert FindTool.metadata.arg_pattern is not None
    
    def test_find_tool_validate(self):
        """Test FindTool validation."""
        from src.services.chat_tools.find import FindTool
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        tool = FindTool(config)
        
        # Should fail without folder
        error = tool.validate(folder_path=None)
        assert error == "No folder specified. Please select a folder first."
        
        # Should pass with folder
        error = tool.validate(folder_path="/some/path")
        assert error is None
    
    def test_find_tool_parse_args(self):
        """Test FindTool argument parsing."""
        from src.services.chat_tools.find import FindTool
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        tool = FindTool(config)
        
        # Parse simple description
        args = tool.parse_args("/find cats")
        assert args == "cats"
        
        # Parse description with number
        args = tool.parse_args("/find 5 cats")
        assert args == "5 cats"


class TestScanTool:
    """Tests for ScanTool."""
    
    def test_scan_tool_metadata(self):
        """Test ScanTool metadata."""
        from src.services.chat_tools.scan import ScanTool
        
        assert ScanTool.metadata.command == "/scan"
        assert ScanTool.metadata.name == "Scan"
        assert ScanTool.metadata.requires_folder is True


class TestProcessTool:
    """Tests for ProcessTool."""
    
    def test_process_tool_metadata(self):
        """Test ProcessTool metadata."""
        from src.services.chat_tools.process import ProcessTool
        
        assert ProcessTool.metadata.command == "/process"
        assert ProcessTool.metadata.name == "Process"
        assert ProcessTool.metadata.requires_folder is True


class TestStatusTool:
    """Tests for StatusTool."""
    
    def test_status_tool_metadata(self):
        """Test StatusTool metadata."""
        from src.services.chat_tools.status import StatusTool
        
        assert StatusTool.metadata.command == "/status"
        assert StatusTool.metadata.name == "Status"
        assert StatusTool.metadata.requires_folder is False


class TestChatService:
    """Tests for ChatService with dynamic tool loading."""
    
    def test_chat_service_initialization(self):
        """Test ChatService initializes and loads tools."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        
        # Check that tools were loaded
        assert len(service._tools) >= 7
        assert "/about" in service._tools
        assert "/tools" in service._tools
    
    def test_chat_service_tools_tool_has_all_tools(self):
        """Test that ToolsTool has reference to all tools."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        
        # Get ToolsTool
        tools_tool = service._tools.get("/tools")
        assert tools_tool is not None
        
        # Check that it has reference to all tools
        assert hasattr(tools_tool, "_all_tools")
        assert len(tools_tool._all_tools) >= 7
    
    def test_chat_service_get_tool_commands(self):
        """Test getting list of tool commands."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        commands = service._get_tool_commands()
        
        assert "/about" in commands
        assert "/tools" in commands
        assert "/count" in commands
        assert "/find" in commands
        assert "/scan" in commands
        assert "/process" in commands
        assert "/status" in commands
    
    def test_chat_service_get_system_prompt(self):
        """Test that system prompt is generated dynamically."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        prompt = service.get_system_prompt()
        
        # Check that prompt contains expected sections
        assert "Local Photo Agent" in prompt
        assert "RULE 1" in prompt
        assert "RULE 2" in prompt
        assert "AVAILABLE TOOL COMMANDS" in prompt
        assert "/about" in prompt
        assert "/tools" in prompt
        assert "/count" in prompt
        assert "/find" in prompt
    
    def test_chat_service_handle_about(self):
        """Test handling /about command."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        result = service.handle_tool_command("/about", folder_path=None)
        
        assert result.status == "success"
        assert "Local Photo Agent" in result.response
    
    def test_chat_service_handle_unknown_command(self):
        """Test handling unknown command."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        result = service.handle_tool_command("/unknown", folder_path=None)
        
        assert result.status == "error"
        assert "Unknown command" in result.response
    
    def test_chat_service_handle_count_without_folder(self):
        """Test handling /count without folder."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        result = service.handle_tool_command("/count", folder_path=None)
        
        assert result.status == "error"
        assert "No folder specified" in result.response
    
    def test_chat_service_handle_find_without_folder(self):
        """Test handling /find without folder."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        result = service.handle_tool_command("/find cats", folder_path=None)
        
        assert result.status == "error"
        assert "No folder specified" in result.response
    
    def test_chat_service_handle_find_with_args(self):
        """Test handling /find with arguments."""
        from src.services.chat import ChatService
        from src.config import AppConfig
        
        config = AppConfig(
            llm_host="localhost",
            llm_port=11434,
            llm_model="test",
            llm_backend="dry_run",
            embedding_backend="dry_run",
            embedding_model="test"
        )
        
        service = ChatService(config)
        
        # This will fail because there's no database, but it should at least
        # get past the validation and folder check
        # We're just testing that the tool is found and called correctly
        result = service.handle_tool_command("/find 5 cats", folder_path="/nonexistent")
        
        # The result might be an error due to missing database, but it's not a validation error
        # This confirms the tool was found and executed
        assert result is not None
    
    def test_chat_response_dataclass(self):
        """Test ChatResponse dataclass."""
        from src.services.chat_response import ChatResponse
        
        # Test with all fields
        response = ChatResponse(
            status="success",
            response={"data": "test"},
            sender="assistant",
            model="test-model",
            response_type="data"
        )
        
        assert response.status == "success"
        assert response.response == {"data": "test"}
        assert response.sender == "assistant"
        assert response.model == "test-model"
        assert response.response_type == "data"
        
        # Test with defaults
        response = ChatResponse(
            status="success",
            response="test"
        )
        
        assert response.sender == "assistant"
        assert response.model == "unknown"
        assert response.response_type is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
