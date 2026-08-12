"""
Simple processing callbacks for the Dash web UI.

This module provides simplified callbacks for processing images:
- Process new images (simple sequential)
- Process all images in folder
- Stop processing
- Polling for status

The simplified approach:
- Simple sequential processing of files
- Database tracking via SimpleProcessingTracker
- No batch-specific state or infrastructure
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from src.batch_state import write_batch_state, read_batch_state, clear_batch_state
from src.file_processing import ProcessableFileLister
from src.sequential_processor import SequentialProcessor
from src.state import reset_shutdown_event, request_shutdown
from plugins.llm import create_extractor
from .common import _make_processing_config

logger = logging.getLogger(__name__)


def register_process_callback(app, app_config):
    """
    Register callback for processing new images.
    
    This processes up to limit unprocessed images from the folder.
    """
    @app.callback(
        Output("processing-status", "children"),
        Input("btn-process-batch", "n_clicks"),
        State("input-folder", "value"),
        State("chk-recursive", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        State("input-backend", "value"),
        State("input-timeout", "value"),
        State("chk-dry-run", "value"),
        State("chk-embedding-enabled", "value"),
        State("input-embedding-model", "value"),
        State("input-embedding-backend", "value"),
        background=True,
        prevent_initial_call=True,
        running=[
            (Output("btn-process-batch", "disabled"), True, False),
            (Output("btn-process-all", "disabled"), True, False),
            (Output("btn-reprocess", "disabled"), True, False),
        ],
    )
    def process_new_images(n_clicks, folder, recursive, host, port, model, backend, timeout, dry_run, embedding_enabled, embedding_model, embedding_backend):
        if not n_clicks or not folder:
            return dash.no_update

        try:
            # Get file lister to get pending files
            file_lister = ProcessableFileLister(folder, recursive=bool(recursive))
            pending_count = file_lister.total_pending()
            
            if pending_count == 0:
                return "No new images to process."
            
            logger.info("[Process] Processing %d pending images", pending_count)
            
            # Get pending files
            pending_files = file_lister.get_pending_files()
            
            # Create extractor
            pc = _make_processing_config(
                host, port, model, backend, timeout, app_config.default_prompt,
                dry_run=bool(dry_run),
                app_config=app_config,
                embedding_enabled=embedding_enabled,
                embedding_model=embedding_model,
                embedding_backend=embedding_backend
            )
            extractor = create_extractor(
                backend=pc.backend,
                host=pc.host,
                port=pc.port,
                model=pc.model,
                timeout=pc.timeout,
                default_prompt=pc.default_prompt,
            )
            
            # Progress callback to update batch state
            def update_progress(processed, total):
                if processed == 0:
                    status_msg = "Starting processing..."
                elif processed < total:
                    status_msg = f"Processing — {processed}/{pending_count}"
                else:
                    status_msg = f"Finalizing — {processed}/{pending_count}"
                write_batch_state(folder, "running", pending_count, processed, status_msg=status_msg)
            
            # Initial progress update to show processing has started
            update_progress(0, pending_count)
            
            # Process files sequentially
            processor = SequentialProcessor(
                extractor, 
                config=pc,
                embedding_enabled=pc.embedding_enabled,
                folder=folder,
            )
            result = processor.process_paths(
                pending_files,
                prompt=pc.default_prompt,
                resume=False,  # We already filtered to pending only
                progress_callback=update_progress,
            )
            
            prefix = "Dry-run" if dry_run else "Process"
            return f"{prefix} complete. Processed {result['successes']} image(s), {result['failures']} failed."
        except Exception as e:
            logger.error("Error in process_new_images: %s", e, exc_info=True)
            return f"Error: {str(e)}"


def register_process_all_callback(app, app_config):
    """
    Register callback for processing ALL images in the folder.
    """
    @app.callback(
        Output("processing-status", "children", allow_duplicate=True),
        Input("btn-process-all", "n_clicks"),
        State("input-folder", "value"),
        State("chk-recursive", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        State("input-backend", "value"),
        State("input-timeout", "value"),
        State("chk-dry-run", "value"),
        State("chk-embedding-enabled", "value"),
        State("input-embedding-model", "value"),
        State("input-embedding-backend", "value"),
        background=True,
        prevent_initial_call=True,
        running=[
            (Output("btn-process-all", "disabled"), True, False),
            (Output("btn-process-batch", "disabled"), True, False),
            (Output("btn-reprocess", "disabled"), True, False),
            (Output("btn-stop-all", "disabled"), False, True),
            (Output("btn-rescan", "disabled"), True, False),
        ],
    )
    def process_all_images(n_clicks, folder, recursive, host, port, model, backend, timeout, dry_run, embedding_enabled, embedding_model, embedding_backend):
        if not n_clicks or not folder:
            return dash.no_update

        try:
            existing_state = read_batch_state(folder)
            if existing_state and existing_state.get("status") in ("running_all", "running"):
                return "A processing job is already running for this folder."

            reset_shutdown_event()
            
            pc = _make_processing_config(
                host, port, model, backend, timeout, app_config.default_prompt,
                dry_run=bool(dry_run),
                app_config=app_config,
                embedding_enabled=embedding_enabled,
                embedding_model=embedding_model,
                embedding_backend=embedding_backend
            )

            # Get all image files
            file_lister = ProcessableFileLister(folder, recursive=bool(recursive))
            all_files = file_lister.get_all_files()
            total_all = len(all_files)
            
            if total_all == 0:
                return "No images found in this folder."
            
            logger.info("[Process All] Processing %d images", total_all)
            
            # Write initial state
            write_batch_state(folder, "running_all", total_all, 0, status_msg="Process All started")
            
            # Create extractor
            extractor = create_extractor(
                backend=pc.backend,
                host=pc.host,
                port=pc.port,
                model=pc.model,
                timeout=pc.timeout,
                default_prompt=pc.default_prompt,
            )
            
            # Progress callback to update batch state
            def update_progress(processed, total):
                # Show "Processing..." for the first update, then show count
                if processed == 0:
                    status_msg = "Starting processing..."
                elif processed < total:
                    status_msg = f"Processing — {processed}/{total_all}"
                else:
                    status_msg = f"Finalizing — {processed}/{total_all}"
                write_batch_state(folder, "running_all", total_all, processed, status_msg=status_msg)
            
            # Initial progress update to show processing has started
            update_progress(0, total_all)
            
            # Process all files
            processor = SequentialProcessor(
                extractor, 
                config=pc,
                embedding_enabled=pc.embedding_enabled,
                folder=folder,
            )
            result = processor.process_paths(
                all_files,
                prompt=pc.default_prompt,
                resume=False,  # Process all, don't skip any
                progress_callback=update_progress,
            )
            
            # Write final state
            write_batch_state(
                folder, "done_all", total_all,
                result['successes'] + result['failures'],
                status_msg=f"All {result['successes'] + result['failures']} images processed"
            )
            
            prefix = "Dry-run" if dry_run else "Process All"
            return f"{prefix} complete. {result['successes']} successes, {result['failures']} failures."
        except Exception as e:
            logger.error("Error in process_all_images: %s", e, exc_info=True)
            # Try to clear the running state if we wrote it
            try:
                clear_batch_state(folder)
            except Exception as e:
                logger.debug("Failed to clear batch state for %s: %s", folder, e, exc_info=True)
            return f"Error: {str(e)}"


def register_reprocess_callback(app, app_config):
    """
    Register callback for reprocessing ALL images (ignoring existing results).
    """
    @app.callback(
        Output("processing-status", "children", allow_duplicate=True),
        Input("btn-reprocess", "n_clicks"),
        State("input-folder", "value"),
        State("chk-recursive", "value"),
        State("input-host", "value"),
        State("input-port", "value"),
        State("input-model", "value"),
        State("input-backend", "value"),
        State("input-timeout", "value"),
        State("chk-dry-run", "value"),
        State("chk-embedding-enabled", "value"),
        State("input-embedding-model", "value"),
        State("input-embedding-backend", "value"),
        background=True,
        prevent_initial_call=True,
        running=[
            (Output("btn-reprocess", "disabled"), True, False),
            (Output("btn-process-all", "disabled"), True, False),
            (Output("btn-process-batch", "disabled"), True, False),
            (Output("btn-stop-all", "disabled"), False, True),
            (Output("btn-rescan", "disabled"), True, False),
        ],
    )
    def reprocess_all_images(n_clicks, folder, recursive, host, port, model, backend, timeout, dry_run, embedding_enabled, embedding_model, embedding_backend):
        if not n_clicks or not folder:
            return dash.no_update

        try:
            existing_state = read_batch_state(folder)
            if existing_state and existing_state.get("status") in ("running_all", "running"):
                return "A processing job is already running for this folder."

            reset_shutdown_event()
            
            pc = _make_processing_config(
                host, port, model, backend, timeout, app_config.default_prompt,
                dry_run=bool(dry_run),
                app_config=app_config,
                embedding_enabled=embedding_enabled,
                embedding_model=embedding_model,
                embedding_backend=embedding_backend
            )
            
            # Get all image files
            file_lister = ProcessableFileLister(folder, recursive=bool(recursive))
            all_files = file_lister.get_all_files()
            total_all = len(all_files)
            
            if total_all == 0:
                return "No images found in this folder."
            
            logger.info("[Reprocess] Reprocessing %d images", total_all)
            
            # Write initial state
            write_batch_state(folder, "running_all", total_all, 0, status_msg="Reprocess All started")
            
            # Create extractor
            extractor = create_extractor(
                backend=pc.backend,
                host=pc.host,
                port=pc.port,
                model=pc.model,
                timeout=pc.timeout,
                default_prompt=pc.default_prompt,
            )
            
            # Progress callback to update batch state
            def update_progress(processed, total):
                if processed == 0:
                    status_msg = "Starting reprocessing..."
                elif processed < total:
                    status_msg = f"Reprocessing — {processed}/{total_all}"
                else:
                    status_msg = f"Finalizing — {processed}/{total_all}"
                write_batch_state(folder, "running_all", total_all, processed, status_msg=status_msg)
            
            # Initial progress update to show processing has started
            update_progress(0, total_all)
            
            # Process all files (this will overwrite existing results)
            processor = SequentialProcessor(
                extractor, 
                config=pc,
                embedding_enabled=pc.embedding_enabled,
                folder=folder,
            )
            result = processor.process_paths(
                all_files,
                prompt=pc.default_prompt,
                resume=False,  # Process all, don't skip any
                progress_callback=update_progress,
            )
            
            # Write final state
            write_batch_state(
                folder, "done_all", total_all,
                result['successes'] + result['failures'],
                status_msg=f"All {result['successes'] + result['failures']} images reprocessed"
            )
            
            prefix = "Dry-run" if dry_run else "Reprocess All"
            return f"{prefix} complete. {result['successes']} successes, {result['failures']} failures."
        except Exception as e:
            logger.error("Error in reprocess_all_images: %s", e, exc_info=True)
            # Try to clear the running state if we wrote it
            try:
                clear_batch_state(folder)
            except Exception as e:
                logger.debug("Failed to clear batch state for %s: %s", folder, e, exc_info=True)
            return f"Error: {str(e)}"


def register_stop_callback(app):
    """Register callback for stopping all processing."""
    @app.callback(
        Output("btn-stop-all", "disabled", allow_duplicate=True),
        Input("btn-stop-all", "n_clicks"),
        prevent_initial_call=True,
    )
    def stop_all(n_clicks):
        if n_clicks:
            request_shutdown()
        return True


def register_polling_callback(app):
    """Register callback for polling processing status."""
    @app.callback(
        Output("queue-status", "children"),
        Output("batch-progress-overall", "value"),
        Output("batch-progress-current", "value"),
        Output("batch-progress-current", "style"),
        Output("batch-progress-wrapper", "style"),
        Output("batch-progress-label", "children"),
        Output("batch-history", "children"),
        Output("batch-history-wrapper", "style"),
        Output("pending-count", "children"),
        Input("poll-interval", "n_intervals"),
        State("input-folder", "value"),
        State("chk-recursive", "value"),
        State("folder-cache", "data"),
        prevent_initial_call=True,
    )
    def poll_queue_status(_n_intervals, folder, recursive, cache_data):
        _hidden = {"display": "none"}
        _visible = {"display": "block"}
        _no_label = ""

        def _pending_text(total_remaining, processed=0):
            if total_remaining <= 0:
                if processed > 0:
                    return f"{processed} processed"
                return ""
            if processed > 0:
                return f"{total_remaining} / {total_remaining + processed} pending · {processed} processed"
            return f"{total_remaining} / {total_remaining} pending"

        _folder_remaining = None

        def _get_folder_remaining():
            nonlocal _folder_remaining
            if _folder_remaining is None:
                try:
                    file_lister = ProcessableFileLister(folder, recursive=bool(recursive))
                    _folder_remaining = file_lister.total_pending()
                except Exception:
                    _folder_remaining = 0
            return _folder_remaining

        _idle = (
            dbc.Badge("No folder set", color="secondary"),
            0, 0, _hidden, _hidden, _no_label,
            html.Div(), _hidden, "",
        )

        if not folder:
            return _idle

        try:
            state = read_batch_state(folder)
            if state:
                status = state.get("status")
                total = state.get("total", 0)
                completed = state.get("completed", 0)
                pct = int((completed / total) * 100) if total else 0
                
                # Get stats from file lister (cached)
                file_lister = ProcessableFileLister(folder, recursive=bool(recursive))
                
                if status in ("running", "running_all"):
                    status_msg = state.get("status_msg", "")
                    display_msg = status_msg if status_msg else f"Processing — {completed}/{total}"
                    badge = dbc.Badge(display_msg, color="warning")
                    remaining = max(0, total - completed)
                    pending_str = _pending_text(remaining, completed)
                    label = f"{pct}% ({completed}/{total})"
                    return (
                        badge, pct, 0, _hidden, _visible,
                        label, html.Div(), _hidden, pending_str
                    )

                if status == "done":
                    cnt = state.get("completed", total)
                    badge = dbc.Badge(
                        f"Batch complete — {cnt} processed",
                        color="success",
                    )
                    return (
                        badge, 100, 0, _hidden, _visible,
                        "100%", html.Div(), _hidden,
                        _pending_text(_get_folder_remaining(), cnt)
                    )

                if status == "done_all":
                    cnt = state.get("completed", total)
                    label_done = f"Complete — {cnt} images processed"
                    badge = dbc.Badge(label_done, color="success")
                    return (
                        badge, 100, 0, _hidden, _visible,
                        label_done, html.Div(), _hidden,
                        _pending_text(0, cnt)
                    )

                if status == "aborted":
                    badge = dbc.Badge(
                        f"Aborted — {completed}/{total} processed", color="danger"
                    )
                    return (
                        badge, pct, 0, _hidden, _visible,
                        f"{pct}%", html.Div(), _hidden,
                        _pending_text(_get_folder_remaining(), completed)
                    )

            # Get stats from file lister for idle state
            file_lister = ProcessableFileLister(folder, recursive=bool(recursive))
            total_all = file_lister.total_all()
            total_remaining = file_lister.total_pending()
            
            if total_all == 0:
                return (
                    dbc.Badge("No images found in folder", color="secondary"),
                    0, 0, _hidden, _hidden, _no_label,
                    html.Div(), _hidden, "",
                )
            if total_remaining == 0:
                return (
                    dbc.Badge(f"Complete — {total_all} total", color="success"),
                    0, 0, _hidden, _hidden, _no_label,
                    html.Div(), _hidden, _pending_text(0, total_all)
                )
            processed = total_all - total_remaining
            return (
                dbc.Badge(f"Idle — {total_remaining} pending", color="secondary"),
                0, 0, _hidden, _hidden, _no_label,
                html.Div(), _hidden, _pending_text(total_remaining, processed)
            )
        except Exception:
            logger.warning("Failed to read folder status for %s", folder, exc_info=True)
            return (
                dbc.Badge("Error reading status", color="danger"),
                0, 0, _hidden, _hidden, _no_label,
                html.Div(), _hidden, "",
            )


def register_history_toggle_callback(app):
    """Register callback for toggling batch history visibility."""
    @app.callback(
        Output("history-collapse", "is_open"),
        Input("btn-toggle-history", "n_clicks"),
        State("history-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_history(n_clicks, is_open):
        if n_clicks is None:
            return dash.no_update
        return not is_open


def register_embedding_warnings_callback(app):
    """Register callback to display embedding health check warnings in the UI."""
    @app.callback(
        Output("embedding-warnings-display", "children"),
        Input("poll-interval", "n_intervals"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def update_embedding_warnings(_n_intervals, folder):
        if not folder:
            return html.Div()
        
        try:
            state = read_batch_state(folder)
            if not state:
                return html.Div()
            
            failure_count = state.get("embedding_health_failures", 0)
            if failure_count <= 0:
                return html.Div()
            
            msg_parts = [
                html.Strong(f"⚠️ {failure_count} image(s) skipped embedding: "),
                "Embedding backend health check failed"
            ]
            if folder:
                msg_parts.append(html.Br())
                msg_parts.append(html.Small(f"Folder: {folder}", className="text-muted"))
            
            return dbc.Alert(
                msg_parts,
                color="warning",
                dismissable=True,
                className="mb-2",
            )
            
        except Exception as e:
            logger.error("Failed to read embedding warnings for folder %s: %s", folder, e)
            return html.Div()
