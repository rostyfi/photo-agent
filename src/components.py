import datetime
import logging
import os
from typing import List, Tuple, Optional
from urllib.parse import quote

import dash_bootstrap_components as dbc
from dash import html, dcc

logger = logging.getLogger(__name__)


def _preview_url(path: str, folder: str, size: str = "thumb") -> str:
    """Return a URL for the /preview server route."""
    return f"/preview?path={quote(path)}&folder={quote(folder)}&size={size}"


def build_tag_cloud(tags_with_counts: List[Tuple[str, int]], max_tags: int = 100, selected_tags: List[str] = None) -> html.Div:
    """Build a visual tag cloud with font sizes scaled by frequency.

    Args:
        tags_with_counts: List of (tag, count) tuples.
        max_tags: Maximum number of tags to render.
        selected_tags: Tags currently active in the chain (highlighted).

    Returns:
        A ``dash.html.Div`` containing styled tag buttons or an empty-state message.
    """
    if not tags_with_counts:
        return html.Div("No tags found.", className="text-muted")

    tags_with_counts = tags_with_counts[:max_tags]
    counts = [c for _, c in tags_with_counts]
    min_count = min(counts)
    max_count = max(counts)

    MIN_FONT = 12
    MAX_FONT = 32

    def _font_size(count: int) -> int:
        if max_count == min_count:
            return int((MIN_FONT + MAX_FONT) / 2)
        ratio = (count - min_count) / (max_count - min_count)
        return int(MIN_FONT + ratio * (MAX_FONT - MIN_FONT))

    selected_lower = {t.lower() for t in (selected_tags or [])}
    buttons = []
    for tag, count in tags_with_counts:
        font_size = _font_size(count)
        is_selected = tag.lower() in selected_lower
        color = "primary" if is_selected else "light"
        buttons.append(
            dbc.Button(
                f"{tag} ({count})",
                id={"type": "tag-cloud-btn", "index": tag},
                color=color,
                size="sm",
                className="me-1 mb-1",
                style={"fontSize": f"{font_size}px"},
            )
        )

    return html.Div(buttons, className="d-flex flex-wrap align-items-center")


def build_selected_tags_bar(selected_tags: List[str]) -> html.Div:
    """Build a row of removable pill badges for the active tag chain.

    Args:
        selected_tags: Currently selected tag strings.

    Returns:
        A ``dash.html.Div`` with pill badges and small × remove buttons.
    """
    if not selected_tags:
        return html.Div()

    badges = []
    for tag in selected_tags:
        badges.append(
            html.Div(
                [
                    dbc.Badge(
                        tag,
                        color="primary",
                        pill=True,
                        className="me-1",
                    ),
                    dbc.Button(
                        "×",
                        id={"type": "tag-clear-btn", "index": tag},
                        color="link",
                        size="sm",
                        className="p-0 me-3",
                        style={"lineHeight": "1", "fontSize": "14px"},
                    ),
                ],
                className="d-inline-flex align-items-center",
            )
        )

    return html.Div(
        [
            html.Small("Active filters:", className="text-muted me-2"),
            *badges,
        ],
        className="d-flex flex-wrap align-items-center mb-2",
    )


def build_photo_cards(results, folder, source="search"):
    """Render search/tag results as a grid of clickable photo cards.

    Args:
        results: List of dicts from ``search_features`` / ``get_features_by_tag``.
        folder: Current folder path for preview URLs.
        source: Namespace for thumbnail IDs so they don't collide with folder thumbnails.

    Returns:
        A ``dbc.Row`` of clickable thumbnail cards, or a no-results message.
    """
    if not results:
        return html.Div("No results found.", className="text-muted")

    items = []
    for r in results:
        image_path = r.get("image_path", "")
        filename = os.path.basename(image_path)
        preview_url = _preview_url(image_path, folder, size="thumb") if folder else ""

        items.append(
            dbc.Col(
                html.Div(
                    html.Img(
                        src=preview_url,
                        style={"maxWidth": "140px", "maxHeight": "140px", "objectFit": "cover", "pointerEvents": "none", "userSelect": "none"},
                        className="img-thumbnail",
                        title=filename,
                        draggable="false",
                    ),
                    id={"type": "thumbnail", "source": source, "index": image_path},
                    n_clicks=0,
                    style={"cursor": "pointer", "userSelect": "none"},
                    className="text-center mb-3",
                ),
                width="auto",
            )
        )

    return dbc.Row(items, className="g-2 flex-wrap")


def build_folder_controls(image_paths, total_remaining=None, total_all=None, folder=None):
    """Build the folder controls with a thumbnail grid inside a collapsible panel.

    Args:
        image_paths: List of absolute image file paths.
        total_remaining: Total pending images (for label text).
        total_all: Total images in folder (for label text).
        folder: Current folder path (used to build preview URLs).
    """
    items = []
    for path in image_paths:
        filename = os.path.basename(path)
        preview = _preview_url(path, folder, size="thumb") if folder else ""
        items.append(
            dbc.Col(
                html.Div(
                    [
                        html.Img(
                            src=preview,
                            style={"maxWidth": "120px", "maxHeight": "120px", "objectFit": "cover", "cursor": "pointer", "pointerEvents": "none", "userSelect": "none"},
                            className="img-thumbnail",
                            title=filename,
                            draggable="false",
                        ),
                        html.Div(
                            filename,
                            className="small text-muted text-truncate text-center",
                            style={"maxWidth": "120px"},
                        ),
                    ],
                    id={"type": "thumbnail", "source": "folder", "index": path},
                    n_clicks=0,
                    style={"cursor": "pointer"},
                    className="text-center mb-2",
                ),
                width="auto",
            )
        )

    collapse_id = "folder-files-collapse"
    count_label = f"{len(items)}"
    if total_remaining is not None and total_remaining != len(items):
        count_label = f"{len(items)} of {total_remaining} pending"
    if total_all is not None and total_all != len(items):
        count_label = f"{count_label} ({total_all} total)"

    grid = dbc.Row(items, className="g-2 flex-wrap")

    return html.Div(
        [
            html.Div(grid, className="border rounded p-2", style={"maxHeight": "400px", "overflowY": "auto"}),
        ]
    )


def build_detail_modal_content(image_path, folder, metadata, embedding=None, embedding_error=None):
    """Build the content for the detail modal.

    Args:
        image_path: Absolute path to the image.
        folder: Current folder scope.
        metadata: Dict from ``FeaturesDatabase.get_feature_summary`` or None.
        embedding: Optional list of floats representing the embedding vector.
        embedding_error: Optional error message if embedding couldn't be loaded.

    Returns:
        A ``dash.html.Div`` with a large preview and metadata read-out.
    """
    preview_url = _preview_url(image_path, folder, size="full") if folder else ""
    img = html.Img(
        src=preview_url,
        style={"maxWidth": "100%", "maxHeight": "70vh", "objectFit": "contain", "userSelect": "none"},
        className="img-fluid mb-3 d-block mx-auto",
        draggable="false",
    )

    if not metadata:
        meta = html.Div("Not yet processed", className="text-muted")
    else:
        rows = []
        for key in ("description", "subjects", "objects", "colors", "setting", "mood"):
            val = metadata.get(key)
            if val:
                rows.append(html.P([html.Strong(f"{key.capitalize()}: "), str(val)], className="mb-1"))
        tags = metadata.get("tags")
        if tags:
            rows.append(
                html.P([html.Strong("Tags: "), ", ".join(str(t) for t in tags)], className="mb-1")
            )
        
        # Add image metadata if available
        image_metadata = metadata.get("metadata", {})
        if image_metadata and isinstance(image_metadata, dict) and len(image_metadata) > 0:
            # Add a separator between AI features and image metadata
            rows.append(html.Hr(className="my-2"))
            rows.append(html.H6("Image Metadata", className="text-muted mb-2"))
            
            # Try to use the database's formatted metadata display if available
            try:
                from src.sidecar.database.db import FeaturesDatabase
                # Create a temporary database instance for this folder to use get_metadata_for_display
                db_path = FeaturesDatabase.default_db_path(folder) if folder else None
                if db_path and db_path.exists():
                    db = FeaturesDatabase(db_path)
                    try:
                        display_metadata = db.get_metadata_for_display(image_path)
                        if display_metadata:
                            # Sort metadata keys for consistent display
                            for key in sorted(display_metadata.keys()):
                                value = display_metadata[key]
                                if value:  # Only display non-empty values
                                    rows.append(html.P([html.Strong(f"{key}: "), str(value)], className="mb-1"))
                    finally:
                        db.close()
                else:
                    # Fallback: manual formatting if we can't use database
                    try:
                        from src.metadata import format_metadata_for_display, ImageMetadata
                        
                        # Convert raw metadata to ImageMetadata object for formatting
                        metadata_obj = ImageMetadata()
                        for key, value in image_metadata.items():
                            if hasattr(metadata_obj, key):
                                setattr(metadata_obj, key, value)
                        
                        display_metadata = format_metadata_for_display(metadata_obj)
                        
                        # Sort metadata keys for consistent display
                        sorted_keys = sorted(display_metadata.keys())
                        for key in sorted_keys:
                            value = display_metadata[key]
                            if value:  # Only display non-empty values
                                rows.append(html.P([html.Strong(f"{key}: "), str(value)], className="mb-1"))
                    except ImportError:
                        # Fallback to simple display if metadata module imports fail
                        for key, value in sorted(image_metadata.items()):
                            if value is not None and str(value).strip():
                                rows.append(html.P([html.Strong(f"{key.replace('_', ' ').title()}: "), str(value)], className="mb-1"))
            except Exception as e:
                # If anything fails, fall back to simple display
                logger.debug("Failed to display formatted metadata for %s: %s", image_path, e)
                for key, value in sorted(image_metadata.items()):
                    if value is not None and str(value).strip():
                        rows.append(html.P([html.Strong(f"{key.replace('_', ' ').title()}: "), str(value)], className="mb-1"))
        elif image_metadata is None:
            # If metadata is None, it means no metadata has been extracted yet
            logger.debug("No metadata available for image: %s", image_path)
        
        meta = html.Div(rows)

    # Build embedding display
    embedding_display = html.Div()
    if embedding_error:
        embedding_display = html.Div(
            [
                html.Strong("Embedding: "),
                html.Span(
                    f"Error: {embedding_error}",
                    className="text-danger",
                ),
            ],
            className="mb-1",
        )
    elif embedding is not None and len(embedding) > 0:
        # Format embedding preview (show first 10 values)
        embedding_preview = ", ".join(f"{v:.4f}" for v in embedding[:10])
        if len(embedding) > 10:
            embedding_preview += f", ... ({len(embedding)} total)"
        embedding_display = html.Div(
            [
                html.Strong("Embedding: "),
                html.Span(
                    embedding_preview,
                    className="selectable-text",
                    style={"userSelect": "text", "cursor": "text"},
                ),
            ],
            className="mb-1",
        )
    else:
        # Show warning if embeddings are not available
        # Check if metadata has embedding_error
        embedding_warning = "Not available"
        if metadata and isinstance(metadata, dict):
            model_output = metadata.get("model_output")
            if isinstance(model_output, dict) and model_output.get("embedding_error"):
                embedding_warning = f"Generation failed: {model_output['embedding_error'][:100]}"
            elif isinstance(model_output, str):
                # model_output might be a JSON string
                import json
                try:
                    parsed = json.loads(model_output)
                    if isinstance(parsed, dict) and parsed.get("embedding_error"):
                        embedding_warning = f"Generation failed: {parsed['embedding_error'][:100]}"
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # If no specific error but image was processed successfully, provide guidance
        if embedding_warning == "Not available" and metadata and isinstance(metadata, dict):
            success = metadata.get("success", False)
            if success:
                embedding_warning = "Not generated - check Ollama server and embedding model"
        
        embedding_display = html.Div(
            [
                html.Strong("Embedding: "),
                html.Span(
                    embedding_warning,
                    className="text-warning",
                ),
            ],
            className="mb-1",
        )

    return html.Div(
        [
            img,
            html.Hr(),
            meta,
            html.Div(
                [
                    dbc.Button(
                        "Find Similar",
                        id="btn-find-similar",
                        color="primary",
                        size="sm",
                        className="me-2 mt-2",
                    ),
                    dbc.Button(
                        "Fullscreen",
                        id="btn-open-fullscreen",
                        color="info",
                        size="sm",
                        className="me-2 mt-2",
                    ),
                    dbc.Button(
                        "Copy Path",
                        id="btn-reveal-detail",
                        color="secondary",
                        size="sm",
                        className="mt-2",
                    ),
                ]
            ),
            html.Div(id="similar-photos-container", className="mt-3"),
            embedding_display,
        ]
    )


def build_similar_photos_carousel(similar_data, folder):
    """Build a carousel of similar photos with similarity scores.
    
    Args:
        similar_data: Dict with 'images' and 'scores' keys, or None.
        folder: Current folder path for preview URLs.
        
    Returns:
        A ``dash.html.Div`` containing the similar photos carousel, or empty if no data.
    """
    if not similar_data or not similar_data.get("images"):
        return html.Div()
    
    images = similar_data.get("images", [])
    scores = similar_data.get("scores", [])
    
    items = []
    for i, (image_path, score) in enumerate(zip(images, scores)):
        preview_url = _preview_url(image_path, folder, size="thumb")
        score_pct = score * 100
        filename = image_path.split("/")[-1] if "/" in image_path else image_path
        
        items.append(
            dbc.Col(
                html.Div(
                    [
                        html.Img(
                            src=preview_url,
                            style={"maxWidth": "120px", "maxHeight": "120px", "objectFit": "cover", "cursor": "pointer"},
                            className="img-thumbnail mb-1",
                            id={"type": "similar-thumbnail", "index": image_path},
                            n_clicks=0,
                        ),
                        html.Small(
                            [
                                html.Strong(f"{score_pct:.1f}% "),
                                html.Span(filename, className="text-muted"),
                            ],
                            className="d-block text-center",
                        ),
                    ],
                    className="text-center mb-2",
                    style={"cursor": "pointer"},
                ),
                width="auto",
            )
        )
    
    return html.Div(
        [
            html.H6("Similar Photos", className="mt-3 mb-2"),
            dbc.Row(items, className="g-2 flex-wrap"),
        ]
    )


def build_fullscreen_viewer(image_path, folder, metadata, embedding=None, embedding_error=None):
    """Build the content for the fullscreen photo viewer.

    Args:
        image_path: Absolute path to the image.
        folder: Current folder scope.
        metadata: Dict from ``FeaturesDatabase.get_feature_summary`` or None.
        embedding: Optional list of floats representing the embedding vector.
        embedding_error: Optional error message if embedding couldn't be loaded.

    Returns:
        A ``dash.html.Div`` with a full-viewport image, navigation arrows,
        a close button, and a toggleable metadata overlay.
    """
    preview_url = _preview_url(image_path, folder, size="full") if folder else ""

    if not metadata:
        meta_items = [html.P("Not yet processed", className="text-white mb-0")]
    else:
        meta_items = []
        for key in ("description", "subjects", "objects", "colors", "setting", "mood"):
            val = metadata.get(key)
            if val:
                meta_items.append(
                    html.P(
                        [html.Strong(f"{key.capitalize()}: "), str(val)],
                        className="mb-1 text-white",
                    )
                )
        tags = metadata.get("tags")
        if tags:
            meta_items.append(
                html.P(
                    [html.Strong("Tags: "), ", ".join(str(t) for t in tags)],
                    className="mb-1 text-white",
                )
            )
        
        # Add image metadata if available
        image_metadata = metadata.get("metadata", {})
        if image_metadata and isinstance(image_metadata, dict) and len(image_metadata) > 0:
            # Add a separator between AI features and image metadata
            meta_items.append(html.Hr(className="my-2 border-light"))
            meta_items.append(html.P("Image Metadata", className="text-muted mb-2 text-white"))
            
            # Try to use the database's formatted metadata display if available
            try:
                from src.sidecar.database.db import FeaturesDatabase
                # Create a temporary database instance for this folder to use get_metadata_for_display
                db_path = FeaturesDatabase.default_db_path(folder) if folder else None
                if db_path and db_path.exists():
                    db = FeaturesDatabase(db_path)
                    try:
                        display_metadata = db.get_metadata_for_display(image_path)
                        if display_metadata:
                            # Sort metadata keys for consistent display
                            for key in sorted(display_metadata.keys()):
                                value = display_metadata[key]
                                if value:  # Only display non-empty values
                                    meta_items.append(
                                        html.P(
                                            [html.Strong(f"{key}: "), str(value)],
                                            className="mb-1 text-white",
                                        )
                                    )
                    finally:
                        db.close()
                else:
                    # Fallback: manual formatting if we can't use database
                    try:
                        from src.metadata import format_metadata_for_display, ImageMetadata
                        
                        # Convert raw metadata to ImageMetadata object for formatting
                        metadata_obj = ImageMetadata()
                        for key, value in image_metadata.items():
                            if hasattr(metadata_obj, key):
                                setattr(metadata_obj, key, value)
                        
                        display_metadata = format_metadata_for_display(metadata_obj)
                        
                        # Sort metadata keys for consistent display
                        sorted_keys = sorted(display_metadata.keys())
                        for key in sorted_keys:
                            value = display_metadata[key]
                            if value:  # Only display non-empty values
                                meta_items.append(
                                    html.P(
                                        [html.Strong(f"{key}: "), str(value)],
                                        className="mb-1 text-white",
                                    )
                                )
                    except ImportError:
                        # Fallback to simple display if metadata module imports fail
                        for key, value in sorted(image_metadata.items()):
                            if value is not None and str(value).strip():
                                meta_items.append(
                                    html.P(
                                        [html.Strong(f"{key.replace('_', ' ').title()}: "), str(value)],
                                        className="mb-1 text-white",
                                    )
                                )
            except Exception as e:
                # If anything fails, fall back to simple display
                logger.debug("Failed to display formatted metadata for %s: %s", image_path, e)
                for key, value in sorted(image_metadata.items()):
                    if value is not None and str(value).strip():
                        meta_items.append(
                            html.P(
                                [html.Strong(f"{key.replace('_', ' ').title()}: "), str(value)],
                                className="mb-1 text-white",
                            )
                        )
        
        # Add embedding vector if available
        if embedding_error:
            # Show error message
            meta_items.append(
                html.P(
                    [
                        html.Strong("Embedding: "),
                        html.Span(
                            f"Error: {embedding_error}",
                            className="text-danger",
                        ),
                    ],
                    className="mb-1 text-white",
                )
            )
        elif embedding is not None and len(embedding) > 0:
            # Format embedding preview (show first 10 values)
            embedding_preview = ", ".join(f"{v:.4f}" for v in embedding[:10])
            if len(embedding) > 10:
                embedding_preview += f", ... ({len(embedding)} total)"
            meta_items.append(
                html.P(
                    [
                        html.Strong("Embedding: "),
                        html.Span(
                            embedding_preview,
                            className="selectable-text",
                            style={"userSelect": "text", "cursor": "text"},
                        ),
                    ],
                    className="mb-1 text-white d-flex align-items-center",
                )
            )
        else:
            # Show warning if embeddings are not available
            embedding_warning = "Not available"
            if metadata and isinstance(metadata, dict):
                model_output = metadata.get("model_output")
                if isinstance(model_output, dict) and model_output.get("embedding_error"):
                    embedding_warning = f"Generation failed: {model_output['embedding_error'][:100]}"
                elif isinstance(model_output, str):
                    # model_output might be a JSON string
                    import json
                    try:
                        parsed = json.loads(model_output)
                        if isinstance(parsed, dict) and parsed.get("embedding_error"):
                            embedding_warning = f"Generation failed: {parsed['embedding_error'][:100]}"
                    except (json.JSONDecodeError, TypeError):
                        pass
            
            # If no specific error but embedding is expected, provide guidance
            if embedding_warning == "Not available" and metadata and isinstance(metadata, dict):
                success = metadata.get("success", False)
                if success:
                    # Image was processed successfully but no embedding
                    embedding_warning = "Not generated - check Ollama server and embedding model"
            
            meta_items.append(
                html.P(
                    [
                        html.Strong("Embedding: "),
                        html.Span(
                            embedding_warning,
                            className="text-warning",
                        ),
                    ],
                    className="mb-1 text-white",
                )
            )

    return html.Div(
        [
            html.Img(
                src=preview_url,
                style={
                    "position": "absolute",
                    "top": "50%",
                    "left": "50%",
                    "transform": "translate(-50%, -50%)",
                    "maxHeight": "100vh",
                    "maxWidth": "100vw",
                    "objectFit": "contain",
                    "userSelect": "none",
                },
                draggable="false",
            ),
            html.Div(
                html.Div(meta_items),
                id="fullscreen-metadata-overlay",
                style={
                    "position": "absolute",
                    "bottom": "20px",
                    "left": "20px",
                    "right": "20px",
                    "background": "rgba(0,0,0,0.75)",
                    "color": "white",
                    "padding": "15px 20px",
                    "borderRadius": "8px",
                    "zIndex": "900",
                    "display": "none",
                    "maxHeight": "30vh",
                    "overflowY": "auto",
                },
            ),
        ],
        style={
            "position": "relative",
            "width": "100%",
            "height": "100%",
            "display": "flex",
            "justifyContent": "center",
            "alignItems": "center",
        },
    )


def build_errors_display(errors: List[dict], folder: str) -> html.Div:
    """Build a display of failed images with their error messages.
    
    Args:
        errors: List of error dicts with keys: image_path, error_code, error_msg, ts
        folder: Current folder path
        
    Returns:
        A dash.html.Div containing the error list or an empty-state message.
    """
    if not errors:
        return html.Div(
            dbc.Alert(
                [
                    html.Span("✓ ", className="me-2"),
                    "No errors found. All images processed successfully.",
                ],
                color="success",
                className="mb-0",
            )
        )
    
    # Sort by timestamp (newest first)
    sorted_errors = sorted(errors, key=lambda x: x.get("ts", ""), reverse=True)
    
    items = []
    for error in sorted_errors:
        image_path = error.get("image_path", "unknown")
        error_code = error.get("error_code", "unknown")
        error_msg = error.get("error_msg", "No error message")
        ts = error.get("ts", "")
        
        # Extract just the filename for display
        filename = os.path.basename(image_path)
        
        # Format timestamp
        try:
            dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            ts_display = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            ts_display = ts[:19] if ts else "unknown"
        
        # Build error card
        items.append(
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.Div(
                                [
                                    html.Strong(filename, className="me-2"),
                                    dbc.Badge(
                                        error_code or "error",
                                        color="danger",
                                        className="me-2",
                                    ),
                                    html.Small(
                                        ts_display,
                                        className="text-muted",
                                    ),
                                ],
                                className="d-flex align-items-center mb-2",
                            ),
                            html.Div(
                                [
                                    html.Strong("Error: ", className="text-danger"),
                                    html.Span(
                                        error_msg,
                                        id={"type": "error-msg", "index": len(items)},
                                        className="selectable-text",
                                    ),
                                    dbc.Button(
                                        "📋",
                                        id={"type": "btn-copy-error", "index": len(items)},
                                        color="light",
                                        size="sm",
                                        className="ms-2 p-0",
                                        title="Copy error message",
                                        style={"width": "24px", "height": "24px"},
                                    ),
                                ],
                                className="mb-2 d-flex align-items-center",
                            ),
                            html.Div(
                                [
                                    html.Strong("Path: "),
                                    html.Code(image_path, className="text-muted small"),
                                ],
                                className="mb-1",
                            ),
                        ]
                    ),
                ],
                className="mb-2 shadow-sm",
            )
        )
    
    return html.Div(
        [
            dbc.Alert(
                [
                    html.Span(f"⚠ {len(errors)} error(s) found", className="me-2"),
                    dbc.Button(
                        "Clear all",
                        id="btn-clear-errors",
                        color="link",
                        size="sm",
                        className="p-0 ms-2",
                    ),
                ],
                color="warning",
                className="mb-3",
            ),
            html.Div(items),
        ]
    )


def build_closest_photos_input() -> html.Div:
    """Build an input field and button for finding similar photos by text description.

    Returns:
        A ``dash.html.Div`` containing the search card with an input, a find button,
        and a clear button.
    """
    return html.Div(
        [
            dbc.Card(
                [
                    dbc.CardBody(
                        [
                            html.Label("Closest Photos", className="form-label"),
                            dbc.Input(
                                id="closest-photos-input",
                                placeholder="e.g., 'A dog running on the beach'",
                                type="text",
                                className="mb-2 form-control",
                                style={"backgroundColor": "#212529", "color": "#f8f9fa"},
                            ),
                            html.Div(
                                [
                                    dbc.Button(
                                        "Find Similar",
                                        id="btn-find-closest-photos",
                                        color="primary",
                                        size="sm",
                                    ),
                                    dbc.Button(
                                        "Clear",
                                        id="btn-clear-closest-photos",
                                        color="secondary",
                                        size="sm",
                                        outline=True,
                                        className="ms-2",
                                    ),
                                ],
                                className="d-flex gap-2",
                            ),
                            html.Div(id="closest-photos-status", className="mt-2"),
                            html.Div(id="closest-photos-results", className="mt-3"),
                        ]
                    )
                ],
                className="mb-3",
            )
        ],
        className="mb-4"
    )


def build_chat_interface():
    """Build the simple chat interface component.
    
    Returns:
        A dbc.Card containing input, send button, and response textbox.
    """
    return dbc.Card(
        [
            dbc.CardHeader(
                html.H5("Chat with your photos", className="mb-0 d-flex align-items-center"),
            ),
            dbc.CardBody(
                [
                    # Response display (textbox above input) - fills available space
                    html.Div(
                        id="chat-response-container",
                        style={
                            "flex": "1 1 auto",
                            "minHeight": "100px",
                            "padding": "10px",
                            "backgroundColor": "#212529",
                            "borderRadius": "5px",
                            "marginBottom": "15px",
                            "overflowY": "auto",
                            "color": "#f8f9fa",
                            "position": "relative",
                        },
                        children=[
                            # Actual chat response content
                            html.Div(
                                id="chat-response",
                                style={
                                    "whiteSpace": "pre-wrap",
                                },
                                className="chat-response-content",
                            ),
                        ],
                    ),
                    # Input and buttons container
                    html.Div(
                        [
                            # Input area with Send and Clear Chat buttons inline
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dcc.Input(
                                            id="chat-input",
                                            type="text",
                                            placeholder="Type a message or use /about, /tools...",
                                            className="bg-dark text-light",
                                            style={"width": "100%", "padding": "0.5rem", "border": "1px solid #495057", "borderRadius": "0.25rem", "height": "38px"},
                                            debounce=True,
                                        ),
                                        width=8,
                                        className="pe-1",
                                    ),
                                    dbc.Col(
                                        dbc.Button(
                                            "Clear Chat",
                                            id="btn-clear-chat",
                                            color="secondary",
                                            className="w-100",
                                            style={"height": "38px"},
                                        ),
                                        width=2,
                                        className="px-1",
                                    ),
                                    dbc.Col(
                                        dbc.Button(
                                            "Send",
                                            id="chat-send",
                                            color="primary",
                                            className="w-100",
                                            style={"height": "38px"},
                                        ),
                                        width=2,
                                        className="ps-1",
                                    ),
                                ],
                                className="g-0 mb-2 align-items-center",
                            ),
                        ],
                        style={"flex": "0 0 auto"},
                    ),
                ],
                style={"display": "flex", "flexDirection": "column", "height": "100%", "overflow": "hidden"},
            ),
        ],
        className="mb-4 d-flex flex-column",
        style={"width": "100%", "marginLeft": "auto", "marginRight": "auto", "height": "100%", "maxWidth": "1400px"},
    )


def build_chat_message(sender: str, content: str, error: Optional[str] = None) -> html.Div:
    """Build a single chat message component.
    
    Args:
        sender: "user" or "assistant"
        content: Message text content
        error: Optional error message
        
    Returns:
        HTML Div component for the chat message
    """
    is_user = sender == "user"
    
    # Message bubble styling
    bubble_style = {
        "padding": "10px 15px",
        "borderRadius": "15px",
        "marginBottom": "10px",
        "maxWidth": "80%",
        "wordWrap": "break-word",
    }
    
    if is_user:
        bubble_style.update({
            "marginLeft": "auto",
            "marginRight": "0",
            "backgroundColor": "#007bff",
            "color": "white",
        })
    else:
        bubble_style.update({
            "marginLeft": "0",
            "marginRight": "auto",
            "backgroundColor": "#f8f9fa",
            "color": "#212529",
            "border": "1px solid #dee2e6",
        })
    
    # Build message content
    message_content = [
        html.Div(content, style={"whiteSpace": "pre-wrap"}),
    ]
    
    if error:
        message_content.append(
            dbc.Alert(error, color="danger", className="mb-0 mt-2")
        )
    
    return html.Div(
        html.Div(
            message_content,
            style=bubble_style,
        ),
        className="d-flex",
        style={"justifyContent": "flex-end" if is_user else "flex-start"},
    )
