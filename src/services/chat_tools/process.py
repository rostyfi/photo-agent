"""Process tool - Processes photos in the current folder."""

import threading

from src.services.chat_response import ChatResponse
from src.services.chat_tools.base import BaseTool, ToolMetadata


class ProcessTool(BaseTool):
    """Tool that processes photos in a folder using LLM extraction."""

    metadata = ToolMetadata(
        command="/process",
        name="Process",
        description="Processes photos in the current folder",
        help_text="/process - Processes photos in the current folder",
        usage="/process",
        requires_folder=True,
        tool_description=(
            "Start processing all pending photos in the current folder with the vision model; processing "
            "runs in the background. Call only when the user explicitly asks to process their photos or "
            "extract features. Requires a folder to be selected."
        ),
    )

    def execute(self, folder_path: str | None = None, args: str | None = None) -> ChatResponse:
        """Execute the process tool.

        Starts background processing of all pending photos in the folder.

        Args:
            folder_path: The folder path containing photos to process
            args: Not used for this tool

        Returns:
            ChatResponse confirming processing has started
        """
        if not folder_path:
            return ChatResponse(
                status="error",
                response="No folder specified. Please select a folder first.",
                sender="assistant",
                model="N/A",
            )
        try:
            import logging

            from plugins.llm import create_extractor
            from src.batch_state import clear_batch_state, write_batch_state
            from src.config import ProcessingConfig
            from src.file_processing import ProcessableFileLister
            from src.sequential_processor import SequentialProcessor
            from src.simple_processing_tracker import SimpleProcessingTracker
            from src.utils import compute_duration_stats

            logger = logging.getLogger(__name__)

            # Get pending files
            lister = ProcessableFileLister(folder_path, recursive=True)
            pending_files = lister.get_pending_files()
            total = len(pending_files)
            # Already-processed photos are skipped by extraction but may still
            # be missing embeddings — they are backfilled after processing.
            pending_set = set(pending_files)
            skipped_files = [f for f in lister.get_all_files() if f not in pending_set]

            if total == 0:
                # Nothing to extract, but already-processed photos may still
                # be missing embeddings — backfill them in the background.
                if skipped_files:
                    threading.Thread(
                        target=_backfill_in_background,
                        args=(folder_path, skipped_files),
                        daemon=True,
                    ).start()
                    return ChatResponse(
                        status="success",
                        response=(
                            "No photos to process. All photos in this folder have already been "
                            f"processed. Checking {len(skipped_files)} photo(s) for missing embeddings "
                            "in the background."
                        ),
                        sender="assistant",
                        model="N/A",
                    )
                return ChatResponse(
                    status="success",
                    response="No photos to process. All photos in this folder have already been processed.",
                    sender="assistant",
                    model="N/A",
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
            # Apply the live UI setting for batch concurrency (Settings modal
            # mutates the shared AppConfig instance held by self.config).
            config.batch_concurrency = self.config.batch_concurrency
            # Per-folder settings file is the source of truth at processing
            # start: it overrides env/UI defaults (host/port/model/backend,
            # timeout, batch concurrency, embedding options) when present.
            from src.folder_settings import apply_folder_settings

            apply_folder_settings(config, folder_path)
            extractor = create_extractor(
                backend=config.backend,
                host=config.host,
                port=config.port,
                model=config.model,
                timeout=config.timeout,
                default_prompt=config.default_prompt,
            )

            # Track progress
            SimpleProcessingTracker(folder_path)

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
                                status_msg=f"Processing - {processed}/{total}",
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
                        concurrency=config.batch_concurrency,
                    )

                    # Backfill embeddings for photos that were already
                    # processed (skipped above) but are missing them.
                    backfilled = processor.backfill_missing_embeddings(skipped_files)
                    if backfilled:
                        logger.info("[Chat /process] Backfilled %d embedding(s) in %s", backfilled, folder_path)

                    # Write final state
                    durations = [
                        r.get("total_duration_ms")
                        for r in result.get("results", [])
                        if r.get("success") and r.get("total_duration_ms") is not None
                    ]
                    duration_stats = compute_duration_stats(durations)
                    write_batch_state(
                        folder_path,
                        "done_all",
                        total,
                        result["successes"] + result["failures"],
                        status_msg=f"All {result['successes'] + result['failures']} images processed",
                        min_duration_ms=duration_stats["min_ms"],
                        max_duration_ms=duration_stats["max_ms"],
                        avg_duration_ms=duration_stats["avg_ms"],
                        total_model_time_s=duration_stats["total_s"],
                    )

                    logger.info("[Chat /process] Completed: %s", result)
                except Exception as e:
                    logger.error("[Chat /process] Error: %s", e)
                    # Write error state
                    try:
                        write_batch_state(folder_path, "aborted", total, 0, status_msg=f"Processing failed: {e!s}")
                    except Exception as exc:
                        logger.debug("Failed to write aborted batch state for %s: %s", folder_path, exc, exc_info=True)

            # Start processing in background thread
            thread = threading.Thread(target=process_in_background, daemon=True)
            thread.start()

            return ChatResponse(
                status="success",
                response=f"**Processing started for {total} photos in {folder_path}**\n\nProcessing has started in the background. Use `/status` to check progress.",
                sender="assistant",
                model="N/A",
            )
        except Exception as e:
            import logging
            import traceback

            logger = logging.getLogger(__name__)
            logger.error("Error starting processing: %s", e)
            logger.error(traceback.format_exc())
            return ChatResponse(
                status="error", response=f"Failed to start processing: {e!s}", sender="assistant", model="N/A"
            )


def _backfill_in_background(folder_path: str, paths: list[str]) -> None:
    """Backfill missing embeddings for already-processed photos (web UI).

    Runs in a daemon thread when ``/process`` finds nothing to extract but
    already-processed photos may be missing embeddings (e.g. they were
    processed before embeddings were enabled, or with another model).
    """
    import logging

    from plugins.llm import create_extractor
    from src.config import ProcessingConfig
    from src.folder_settings import apply_folder_settings
    from src.sequential_processor import backfill_embeddings

    logger = logging.getLogger(__name__)
    try:
        config = ProcessingConfig.from_env()
        apply_folder_settings(config, folder_path)
        if not config.embedding_enabled:
            return
        extractor = create_extractor(
            backend=config.backend,
            host=config.host,
            port=config.port,
            model=config.model,
            timeout=config.timeout,
            default_prompt=config.default_prompt,
        )
        backfilled = backfill_embeddings(paths, extractor, folder=folder_path, config=config)
        if backfilled:
            logger.info("[Chat /process] Backfilled %d embedding(s) in %s", backfilled, folder_path)
    except Exception as e:
        logger.error("[Chat /process] Embedding backfill failed for %s: %s", folder_path, e)
