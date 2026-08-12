"""Status tool - Checks the status of active processing jobs."""

from src.services.chat_tools.base import BaseTool, ToolMetadata
from src.services.chat_response import ChatResponse
from typing import Optional


class StatusTool(BaseTool):
    """Tool that checks processing status for a folder."""
    
    metadata = ToolMetadata(
        command="/status",
        name="Status",
        description="Checks the status of active processing jobs",
        help_text="/status - Checks the status of active processing jobs",
        usage="/status",
        requires_folder=False  # Can work with or without folder
    )
    
    def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
        """Execute the status tool.
        
        Checks batch state and database tracker for the specified folder.
        
        Args:
            folder_path: The folder path to check status for (optional)
            args: Not used for this tool
            
        Returns:
            ChatResponse with status information
        """
        try:
            # Check batch state for the current folder
            if folder_path:
                from src.batch_state import read_batch_state
                from src.simple_processing_tracker import SimpleProcessingTracker
                
                batch_state = read_batch_state(folder_path)
                
                # Also get tracker info for more details
                tracker = SimpleProcessingTracker(folder_path)
                stats = tracker.get_stats()
                
                if batch_state:
                    status = batch_state.get("status", "unknown")
                    total = batch_state.get("total", 0)
                    completed = batch_state.get("completed", 0)
                    status_msg = batch_state.get("status_msg", "")
                    
                    response = f"**Batch Status for {folder_path}:**\n\n"
                    response += f"Status: {status}\n"
                    response += f"Total: {total}\n"
                    response += f"Completed: {completed}\n"
                    if status_msg:
                        response += f"Message: {status_msg}\n"
                    response += f"\n**Database Tracker:**\n"
                    response += f"Total images: {stats.get('total', 0)}\n"
                    response += f"Pending: {stats.get('pending', 0)}\n"
                    response += f"Processed: {stats.get('processed', 0)}\n"
                    response += f"Failed: {stats.get('failed', 0)}"
                    
                    return ChatResponse(
                        status="success",
                        response=response,
                        sender="assistant",
                        model="N/A"
                    )
                else:
                    # No batch state but check tracker
                    response = f"**No active batch processing for {folder_path}**\n\n"
                    response += f"**Database Tracker Status:**\n"
                    response += f"Total images: {stats.get('total', 0)}\n"
                    response += f"Pending: {stats.get('pending', 0)}\n"
                    response += f"Processed: {stats.get('processed', 0)}\n"
                    response += f"Failed: {stats.get('failed', 0)}\n\n"
                    response += "Note: If processing was started via chat, batch state should be visible. "
                    response += "Otherwise, only database tracker info is shown."
                    
                    return ChatResponse(
                        status="success",
                        response=response,
                        sender="assistant",
                        model="N/A"
                    )
            
            # No folder specified
            return ChatResponse(
                status="success",
                response="**No folder specified.**\n\nNote: Processing status requires a folder to be selected and batch processing to be active.",
                sender="assistant",
                model="N/A"
            )
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error("Error checking status: %s", e)
            logger.error(traceback.format_exc())
            return ChatResponse(
                status="error",
                response=f"Failed to check status: {str(e)}",
                sender="assistant",
                model="N/A"
            )
