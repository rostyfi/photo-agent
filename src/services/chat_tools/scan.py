"""Scan tool - Scans a folder for photos."""

from src.services.chat_response import ChatResponse
from src.services.chat_tools.base import BaseTool, ToolMetadata


class ScanTool(BaseTool):
    """Tool that scans a folder for photos and reports counts."""

    metadata = ToolMetadata(
        command="/scan",
        name="Scan",
        description="Scans a folder for photos",
        help_text="/scan - Scans a folder for photos",
        usage="/scan",
        requires_folder=True,
    )

    def execute(self, folder_path: str | None = None, args: str | None = None) -> ChatResponse:
        """Execute the scan tool.

        Scans the specified folder for photos and returns counts.

        Args:
            folder_path: The folder path to scan
            args: Not used for this tool

        Returns:
            ChatResponse with scan results
        """
        try:
            from src.file_processing import ProcessableFileLister

            lister = ProcessableFileLister(folder_path, recursive=True)
            all_files = lister.get_all_files()
            total = len(all_files)
            pending = lister.total_pending()

            return ChatResponse(
                status="success",
                response=f"**Photo Folder Scan Results:**\n\n📁 Total photos found: {total}\n📄 Available to process: {pending}",
                sender="assistant",
                model="N/A",
            )
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error("Error scanning folder: %s", e)
            return ChatResponse(
                status="error", response=f"Failed to scan folder: {e!s}", sender="assistant", model="N/A"
            )
