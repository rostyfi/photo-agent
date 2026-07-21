"""Callbacks for vector similarity search functionality.

Uses REST-based vector search that doesn't require sqlite-vec.
Ollama v0.1.0+ is required for embedding generation.

All vector search operations are performed via REST API endpoint.
"""

import logging
import os

from dash import Input, Output, State, html, no_update
import dash_bootstrap_components as dbc

from src.components import build_similar_photos_carousel, _preview_url
from src.sidecar.database import FeaturesDatabase
from src.config import AppConfig

logger = logging.getLogger(__name__)


def _get_db(folder: str):
    """Get a FeaturesDatabase instance for a folder."""
    if not folder:
        return None
    db_path = FeaturesDatabase.default_db_path(folder)
    if not db_path.exists():
        return None
    return FeaturesDatabase(db_path)


def register_find_similar_callback(app):
    """Register callback to find similar photos for a given image.
    
    This callback is triggered when the user clicks "Find Similar" button
    in the detail modal or fullscreen viewer.
    """
    @app.callback(
        Output("similar-photos-store", "data", allow_duplicate=True),
        Input("btn-find-similar", "n_clicks"),
        State("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def find_similar(n_clicks, store_data, folder):
        if not n_clicks or not folder:
            return None
        
        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None
        
        if current_index is None or current_index >= len(paths):
            return None
        
        current_image_path = paths[current_index]
        
        try:
            # Get config
            config = AppConfig.from_env()
            
            # Check if database exists
            db_path = FeaturesDatabase.default_db_path(folder)
            if not db_path.exists():
                logger.warning("No database found for folder: %s", folder)
                return None
            
            # Call REST API endpoint to find similar photos by image
            import requests
            
            # Build the API URL (same server, different endpoint)
            # Use localhost for internal requests (works in Docker container)
            api_url = f"http://127.0.0.1:{config.dash_port}/_api/find_similar"
            
            payload = {
                "folder": folder,
                "image_path": current_image_path,
                "model_name": config.embedding_model,
                "limit": config.similarity_limit
            }
            
            try:
                response = requests.post(
                    api_url,
                    json=payload,
                    timeout=300
                )
                
                if response.status_code != 200:
                    error_msg = f"API request failed with status {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                    except:
                        error_msg = f"{error_msg}: {response.text[:200]}"
                    
                    logger.error("REST vector search API error: %s", error_msg)
                    return None
                
                result = response.json()
                
                if result.get("status") != "success":
                    logger.error("REST vector search failed: %s", result.get("message", "Unknown error"))
                    return None
                
                similar_results = result.get("results", [])
                
                # Return similar images data in the expected format
                return {
                    "images": [item.get("image_path") for item in similar_results],
                    "scores": [item.get("score", 0.0) for item in similar_results],
                }
                
            except requests.exceptions.RequestException as e:
                logger.error("REST vector search request failed: %s", e)
                return None
                
        except Exception as e:
            logger.error("Failed to find similar images: %s", e)
            return None


def register_similarity_search_callback(app):
    """Register callback for image-based similarity search.
    
    This allows users to upload an image and find similar photos.
    Uses REST-based vector search that doesn't require sqlite-vec.
    """
    @app.callback(
        Output("similarity-search-results", "children", allow_duplicate=True),
        Input("btn-similarity-search", "n_clicks"),
        State("upload-similarity-image", "contents"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def similarity_search(n_clicks, image_contents, folder):
        if not n_clicks or not image_contents or not folder:
            return html.Div("Upload an image to find similar photos.", className="text-muted")
        
        try:
            import base64
            import tempfile
            import os
            
            # Decode the uploaded image
            content_type, content_string = image_contents.split(",")
            image_data = base64.b64decode(content_string)
            
            # Save the uploaded image to a temporary file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                tmp_file.write(image_data)
                tmp_image_path = tmp_file.name
            
            try:
                # Get config
                config = AppConfig.from_env()
                
                # Check if database exists
                db_path = FeaturesDatabase.default_db_path(folder)
                if not db_path.exists():
                    return html.Div("No database found for the selected folder.", className="text-danger")
                
                # Call REST API endpoint to find similar photos by image
                import requests
                
                # Build the API URL (same server, different endpoint)
                # Use localhost for internal requests (works in Docker container)
                api_url = f"http://127.0.0.1:{config.dash_port}/_api/find_similar"
                
                payload = {
                    "folder": folder,
                    "image_path": tmp_image_path,
                    "model_name": config.embedding_model,
                    "limit": config.similarity_limit
                }
                
                response = requests.post(
                    api_url,
                    json=payload,
                    timeout=300
                )
                
                if response.status_code != 200:
                    error_msg = f"API request failed with status {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                    except:
                        error_msg = f"{error_msg}: {response.text[:200]}"
                    
                    logger.error("REST vector search API error: %s", error_msg)
                    return html.Div(f"Error: {error_msg}", className="text-danger")
                
                result = response.json()
                
                if result.get("status") != "success":
                    error_msg = result.get("message", "Unknown error")
                    logger.error("REST vector search failed: %s", error_msg)
                    return html.Div(f"Error: {error_msg}", className="text-danger")
                
                similar_results = result.get("results", [])
                
                if not similar_results:
                    return html.Div("No similar images found.", className="text-muted")
                
                # Build results display
                from src.components import _preview_url
                items = []
                for item in similar_results:
                    image_path = item.get("image_path")
                    score = item.get("score", 0.0)
                    preview_url = _preview_url(image_path, folder, size="thumb")
                    score_pct = score * 100
                    items.append(
                        dbc.Col(
                            html.Div(
                                [
                                    html.Img(
                                        src=preview_url,
                                        style={"maxWidth": "140px", "maxHeight": "140px", "objectFit": "cover"},
                                        className="img-thumbnail mb-1",
                                    ),
                                    html.Small(f"{score_pct:.1f}% similar", className="text-muted"),
                                ],
                                className="text-center mb-2",
                            ),
                            width="auto",
                        )
                    )
                
                return dbc.Row(items, className="g-2 flex-wrap")
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(tmp_image_path)
                except:
                    pass
                
        except Exception as e:
            logger.error("Similarity search failed: %s", e)
            return html.Div(f"Error: {str(e)}", className="text-danger")


def register_embedding_status_callback(app):
    """Register callback to check embedding generation status.
    
    Returns whether embeddings are available for a given image.
    """
    @app.callback(
        Output("embedding-status", "children", allow_duplicate=True),
        Input("photo-list-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def check_embedding_status(store_data, folder):
        if not folder or not store_data:
            return ""
        
        paths = store_data.get("paths", []) if isinstance(store_data, dict) else []
        current_index = store_data.get("index") if isinstance(store_data, dict) else None
        
        if current_index is None or current_index >= len(paths):
            return ""
        
        current_image_path = paths[current_index]
        
        try:
            db = _get_db(folder)
            if db is None:
                return dbc.Badge("No database", color="warning")
            
            from src.config import AppConfig
            config = AppConfig.from_env()
            
            has_emb = db.has_embedding(current_image_path, config.embedding_model)
            db.close()
            
            if has_emb:
                return dbc.Badge("Embedding available", color="success")
            else:
                return dbc.Badge("No embedding", color="warning")
                
        except Exception as e:
            logger.error("Failed to check embedding status: %s", e)
            return dbc.Badge("Error", color="danger")


def register_display_similar_photos_callback(app):
    """Register callback to display similar photos in the detail modal."""
    @app.callback(
        Output("similar-photos-container", "children", allow_duplicate=True),
        Input("similar-photos-store", "data"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def display_similar_photos(similar_data, folder):
        if not similar_data or not folder:
            return html.Div()
        
        return build_similar_photos_carousel(similar_data, folder)


def register_closest_photos_callback(app):
    """Register callback for finding closest photos by text description.
    
    This callback:
    1. Takes a text query from the user
    2. Calls the REST API endpoint to perform vector search
    3. Returns top 10 matching photos
    
    Uses REST-based vector search that doesn't require sqlite-vec.
    """
    @app.callback(
        Output("closest-photos-results", "children"),
        Output("closest-photos-status", "children"),
        Input("btn-find-closest-photos", "n_clicks"),
        State("closest-photos-input", "value"),
        State("input-folder", "value"),
        prevent_initial_call=True,
    )
    def find_closest_photos(n_clicks, query, folder):
        if not n_clicks or not query or not folder:
            return no_update, no_update
        
        try:
            # Get config
            config = AppConfig.from_env()
            
            # Get database path to check if it exists
            from src.sidecar.database.db import FeaturesDatabase
            db_path = FeaturesDatabase.default_db_path(folder)
            
            if not db_path.exists():
                return (
                    html.Div(),
                    dbc.Alert(
                        "No features.db found for this folder. Process the folder first.",
                        color="warning",
                        dismissable=True,
                    ),
                )
            
            # Call REST API endpoint to find similar photos
            import requests
            
            # Build the API URL (same server, different endpoint)
            # Use localhost for internal requests (works in Docker container)
            api_url = f"http://127.0.0.1:{config.dash_port}/_api/find_similar"
            
            payload = {
                "folder": folder,
                "query": query,
                "model_name": config.embedding_model,
                "limit": 10
            }
            
            try:
                response = requests.post(
                    api_url,
                    json=payload,
                    timeout=300  # Longer timeout for embedding generation
                )
                
                if response.status_code != 200:
                    error_msg = f"API request failed with status {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                    except:
                        error_msg = f"{error_msg}: {response.text[:200]}"
                    
                    logger.error("REST vector search API error: %s", error_msg)
                    return (
                        html.Div(),
                        dbc.Alert(
                            f"Error: {error_msg}",
                            color="danger",
                            dismissable=True,
                        ),
                    )
                
                result = response.json()
                
                if result.get("status") != "success":
                    error_msg = result.get("message", "Unknown error")
                    logger.error("REST vector search failed: %s", error_msg)
                    return (
                        html.Div(),
                        dbc.Alert(
                            f"Error: {error_msg}",
                            color="danger",
                            dismissable=True,
                        ),
                    )
                
                similar_results = result.get("results", [])
                
                if not similar_results:
                    return (
                        html.Div("No similar photos found.", className="text-muted"),
                        dbc.Alert("No similar photos found.", color="info", dismissable=True),
                    )
                
                # Build results display
                items = []
                for item in similar_results:
                    image_path = item.get("image_path")
                    score = item.get("score", 0.0)
                    filename = os.path.basename(image_path)
                    preview_url = _preview_url(image_path, folder, size="thumb")
                    score_pct = score * 100
                    
                    items.append(
                        dbc.Col(
                            html.Div(
                                [
                                    html.Img(
                                        src=preview_url,
                                        style={"maxWidth": "140px", "maxHeight": "140px", "objectFit": "cover", "pointerEvents": "none", "userSelect": "none"},
                                        className="img-thumbnail",
                                        title=filename,
                                        draggable="false",
                                    ),
                                    html.Small(
                                        [
                                            html.Strong(f"{score_pct:.1f}% "),
                                            html.Span(filename, className="text-muted"),
                                        ],
                                        className="d-block text-center mt-1",
                                    ),
                                ],
                                id={"type": "thumbnail", "source": "closest", "index": image_path},
                                n_clicks=0,
                                style={"cursor": "pointer", "userSelect": "none"},
                                className="text-center mb-3",
                            ),
                            width="auto",
                        )
                    )
                
                return (
                    dbc.Row(items, className="g-2 flex-wrap"),
                    dbc.Alert(
                        f"Found {len(similar_results)} similar photo(s) for: '{query}'",
                        color="success",
                        dismissable=True,
                    ),
                )
                
            except requests.exceptions.RequestException as e:
                logger.error("REST vector search request failed: %s", e)
                return (
                    html.Div(),
                    dbc.Alert(
                        f"Failed to connect to vector search API: {str(e)}",
                        color="danger",
                        dismissable=True,
                    ),
                )
                
        except Exception as e:
            logger.error("Failed to find closest photos: %s", e)
            return (
                html.Div(),
                dbc.Alert(
                    f"Error finding closest photos: {str(e)}",
                    color="danger",
                    dismissable=True,
                ),
            )


def register_clear_closest_photos_callback(app):
    """Register callback to clear closest photos results."""
    @app.callback(
        Output("closest-photos-results", "children"),
        Output("closest-photos-status", "children"),
        Output("closest-photos-input", "value"),
        Input("btn-clear-closest-photos", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_closest_photos(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update
        
        return html.Div(), html.Div(), ""
