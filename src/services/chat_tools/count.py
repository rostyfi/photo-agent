"""Count tool - Shows number of processed photos."""

from src.services.chat_tools.base import BaseTool, ToolMetadata
from src.services.chat_response import ChatResponse
from typing import Optional


class CountTool(BaseTool):
    """Tool that counts processed photos in a folder."""
    
    metadata = ToolMetadata(
        command="/count",
        name="Count",
        description="Shows number of processed photos",
        help_text="/count - Shows number of processed photos",
        usage="/count",
        requires_folder=True
    )
    
    def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
        """Execute the count tool.
        
        Counts the number of processed photos in the specified folder.
        
        Args:
            folder_path: The folder path to count photos in
            args: Not used for this tool
            
        Returns:
            ChatResponse with the count of processed photos
        """
        try:
            from src.sidecar.database.db import FeaturesDatabase
            
            db_path = FeaturesDatabase.default_db_path(folder_path)
            db = FeaturesDatabase(db_path)
            extractions = db.list_extractions()
            count = len(extractions)
            db.close()
            
            return ChatResponse(
                status="success",
                response=f"**Processed Photos:** {count}",
                sender="assistant",
                model="N/A"
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Error counting photos: %s", e)
            return ChatResponse(
                status="error",
                response=f"Failed to count photos: {str(e)}",
                sender="assistant",
                model="N/A"
            )
