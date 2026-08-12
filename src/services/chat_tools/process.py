"""Process tool - Processes photos in the current folder."""

import threading
from src.services.chat_tools.base import BaseTool, ToolMetadata
from src.services.chat_response import ChatResponse
from typing import Optional


class ProcessTool(BaseTool):
    """Tool that processes photos in a folder using LLM extraction."""
    
    metadata = ToolMetadata(
        command="/process",
        name="Process",
        description="Processes photos in the current folder",
        help_text="/process - Processes photos in the current folder",
        usage="/process",
        requires_folder=True
    )
    
    def execute(self, folder_path: Optional[str] = None, args: Optional[str] = None) -> ChatResponse:
        """Execute the process tool.
        
        Starts background processing of all pending photos in the folder.
        
        Args:
            folder_path: The folder path containing photos to process
            args: Not used for this tool
            
        Returns:
            ChatResponse confirming processing has started
        """
        try:
            from src.file_processing import ProcessableFileLister
            from src.sequential_processor import SequentialProcessor
            from src.config import ProcessingConfig
            from plugins.llm import create_extractor
            from src.batch_state import write_batch_state, clear_batch_state
            from src.simple_processing_tracker import SimpleProcessingTracker
            import logging
            
            logger = logging.getLogger(__name__)
            
            # Get pending files
            lister = ProcessableFileLister(folder_path, recursive=True)
            pending_files = lister.get_pending_files()
            total = len(pending_files)
            
            if total == 0:
                return ChatResponse(
                    status="success",
                    response="No photos to process. All photos in this folder have already been processed.",
                    sender="assistant",
                    model="N/A"
                )
            
            # Clear any existing batch state for this folder
            try:
                clear_batch_state(folder_path)
            except Exception as e:
                logger.debug("Failed to clear batch state for %s: %s", folder_path, e, exc_info=True)
            
            # Write initial batch state
            write_batch_state(folder_path, "running_all", total, 0, status_msg="Processing started via chat")
            
            # Create extractor
            config = ProcessingConfig.from_env()
            extractor = create_extractor(
                backend=config.backend,
                host=config.host,
                port=config.port,
                model=config.model,
                timeout=config.timeout,
                default_prompt=config.default_prompt,
            )
            
            # Track progress
            tracker = SimpleProcessingTracker(folder_path)
            
            # Process files in background thread
            def process_in_background():
                try:
                    logger.info("[Chat /process] Starting processing for %s files in %s", total, folder_path)
                    
                    # Create processor with folder for database operations
                    processor = SequentialProcessor(
                        extractor,
                        config=config,
                        embedding_enabled=config.embedding_enabled,
                        folder=folder_path,
                    )
                    
                    # Progress callback to update batch state
                    def update_progress(processed, current_total):
                        try:
                            write_batch_state(
                                folder_path,
                                "running_all",
                                total,
                                processed,
                                status_msg=f"Processing - {processed}/{total}"
                            )
                        except Exception as e:
                            logger.warning("Failed to write batch state: %s", e)
                    
                    # Initial progress update
                    update_progress(0, total)
                    
                    # Process all pending files
                    result = processor.process_paths(
                        pending_files,
                        prompt=None,
                        resume=False,  # Don't skip any - we already filtered pending
                        progress_callback=update_progress,
                    )
                    
                    # Write final state
                    write_batch_state(
                        folder_path,
                        "done_all",
                        total,
                        result['successes'] + result['failures'],
                        status_msg=f"All {result['successes'] + result['failures']} images processed"
                    )
                    
                    logger.info("[Chat /process] Completed: %s", result)
                except Exception as e:
                    logger.error("[Chat /process] Error: %s", e)
                    # Write error state
                    try:
                        write_batch_state(
                            folder_path,
                            "aborted",
                            total,
                            0,
                            status_msg=f"Processing failed: {str(e)}"
                        )
                    except Exception as exc:
                        logger.debug("Failed to write aborted batch state for %s: %s", folder_path, exc, exc_info=True)
            
            # Start processing in background thread
            thread = threading.Thread(target=process_in_background, daemon=True)
            thread.start()
            
            return ChatResponse(
                status="success",
                response=f"**Processing started for {total} photos in {folder_path}**\n\nProcessing has started in the background. Use `/status` to check progress.",
                sender="assistant",
                model="N/A"
            )
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error("Error starting processing: %s", e)
            logger.error(traceback.format_exc())
            return ChatResponse(
                status="error",
                response=f"Failed to start processing: {str(e)}",
                sender="assistant",
                model="N/A"
            )
