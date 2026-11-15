"""Builder for the fullscreen photo viewer content."""

import logging
from typing import Any

from dash import html

from .preview import _preview_url

logger = logging.getLogger(__name__)


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
        meta_items: list[Any] = [html.P("Not yet processed", className="text-white mb-0")]
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
                        from src.metadata import ImageMetadata, format_metadata_for_display

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
