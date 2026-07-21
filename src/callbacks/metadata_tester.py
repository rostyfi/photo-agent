"""Callbacks for the metadata tester feature in settings.

This module provides callbacks for:
- Handling file upload for metadata testing
- Extracting and displaying metadata from uploaded images
"""

import base64
import io
import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html

from src.metadata import extract_metadata, format_metadata_for_display

logger = logging.getLogger(__name__)


def build_metadata_result(contents, filename, metadata_dict):
    """Build the metadata display component."""
    # Build formatted metadata display
    metadata_items = []
    
    # Add image preview
    metadata_items.append(
        html.Div([
            html.H6("Image Preview:", className="mt-2 mb-2"),
            html.Img(
                src=contents,
                style={
                    "maxWidth": "100%",
                    "maxHeight": "300px",
                    "objectFit": "contain",
                    "border": "1px solid #dee2e6",
                    "borderRadius": "4px",
                    "backgroundColor": "#f8f9fa",
                },
            ),
            html.Small(f"Filename: {filename}", className="text-muted"),
        ])
    )
    
    # Add basic file info
    if metadata_dict:
        file_info = []
        if metadata_dict.get("file_size_bytes"):
            size_bytes = metadata_dict["file_size_bytes"]
            size_kb = size_bytes / 1024
            size_mb = size_kb / 1024
            if size_mb >= 1:
                file_info.append(f"File Size: {size_mb:.2f} MB")
            else:
                file_info.append(f"File Size: {size_kb:.1f} KB")
        if metadata_dict.get("file_extension"):
            file_info.append(f"Extension: {metadata_dict['file_extension']}")
        
        if file_info:
            metadata_items.append(
                html.Div([
                    html.H6("File Information:", className="mt-3 mb-2"),
                    html.Div(file_info, className="text-muted small"),
                ])
            )
        
        # Add dimensions
        dims = []
        if metadata_dict.get("width"):
            dims.append(f"Width: {metadata_dict['width']}px")
        if metadata_dict.get("height"):
            dims.append(f"Height: {metadata_dict['height']}px")
        if metadata_dict.get("aspect_ratio"):
            dims.append(f"Aspect Ratio: {metadata_dict['aspect_ratio']:.2f}")
        
        if dims:
            metadata_items.append(
                html.Div([
                    html.H6("Dimensions:", className="mt-3 mb-2"),
                    html.Div(dims, className="text-muted small"),
                ])
            )
        
        # Add camera info
        camera_info = []
        if metadata_dict.get("make"):
            camera_info.append(f"Make: {metadata_dict['make']}")
        if metadata_dict.get("model"):
            camera_info.append(f"Model: {metadata_dict['model']}")
        if metadata_dict.get("lens_model"):
            camera_info.append(f"Lens: {metadata_dict['lens_model']}")
        
        if camera_info:
            metadata_items.append(
                html.Div([
                    html.H6("Camera:", className="mt-3 mb-2"),
                    html.Div(camera_info, className="text-muted small"),
                ])
            )
        
        # Add exposure settings
        exposure_info = []
        if metadata_dict.get("exposure_time"):
            exposure_info.append(f"Exposure: {metadata_dict['exposure_time']}")
        if metadata_dict.get("f_number"):
            exposure_info.append(f"Aperture: f/{metadata_dict['f_number']}")
        if metadata_dict.get("iso_speed"):
            exposure_info.append(f"ISO: {metadata_dict['iso_speed']}")
        if metadata_dict.get("focal_length"):
            exposure_info.append(f"Focal Length: {metadata_dict['focal_length']}")
        
        if exposure_info:
            metadata_items.append(
                html.Div([
                    html.H6("Exposure:", className="mt-3 mb-2"),
                    html.Div(exposure_info, className="text-muted small"),
                ])
            )
        
        # Add date info
        date_info = []
        if metadata_dict.get("date_taken"):
            date_info.append(f"Date Taken: {metadata_dict['date_taken']}")
        if metadata_dict.get("date_created"):
            date_info.append(f"Date Created: {metadata_dict['date_created']}")
        if metadata_dict.get("date_modified"):
            date_info.append(f"Date Modified: {metadata_dict['date_modified']}")
        
        if date_info:
            metadata_items.append(
                html.Div([
                    html.H6("Dates:", className="mt-3 mb-2"),
                    html.Div(date_info, className="text-muted small"),
                ])
            )
        
        # Add GPS info
        gps_info = []
        if metadata_dict.get("latitude") is not None:
            gps_info.append(f"Latitude: {metadata_dict['latitude']:.6f}")
        if metadata_dict.get("longitude") is not None:
            gps_info.append(f"Longitude: {metadata_dict['longitude']:.6f}")
        if metadata_dict.get("altitude") is not None:
            gps_info.append(f"Altitude: {metadata_dict['altitude']:.1f}m")
        if metadata_dict.get("location_name"):
            gps_info.append(f"Location: {metadata_dict['location_name']}")
        
        if gps_info:
            metadata_items.append(
                html.Div([
                    html.H6("GPS/Location:", className="mt-3 mb-2"),
                    html.Div(gps_info, className="text-muted small"),
                ])
            )
        
        # Add other metadata
        other_info = []
        if metadata_dict.get("color_space"):
            other_info.append(f"Color Space: {metadata_dict['color_space']}")
        if metadata_dict.get("orientation"):
            other_info.append(f"Orientation: {metadata_dict['orientation']}")
        if metadata_dict.get("software"):
            other_info.append(f"Software: {metadata_dict['software']}")
        if metadata_dict.get("copyright"):
            other_info.append(f"Copyright: {metadata_dict['copyright']}")
        if metadata_dict.get("artist"):
            other_info.append(f"Artist: {metadata_dict['artist']}")
        if metadata_dict.get("title"):
            other_info.append(f"Title: {metadata_dict['title']}")
        if metadata_dict.get("image_description"):
            other_info.append(f"Description: {metadata_dict['image_description']}")
        
        if other_info:
            metadata_items.append(
                html.Div([
                    html.H6("Other Metadata:", className="mt-3 mb-2"),
                    html.Div(other_info, className="text-muted small"),
                ])
            )
    
    # If no metadata was extracted, show a message
    if not metadata_dict or len(metadata_items) <= 1:  # Only has image preview
        metadata_items.append(
            dbc.Alert(
                "No metadata found in this image.",
                color="info",
                className="mt-3",
            )
        )
    
    return dbc.Card([
        dbc.CardHeader(html.H5("Extracted Metadata")),
        dbc.CardBody(metadata_items),
    ], className="mt-3")


def register_metadata_tester_callbacks(app):
    """Register all callbacks for the metadata tester feature.
    
    Args:
        app: Dash application instance
    """
    
    @app.callback(
        [
            Output("metadata-tester-store", "data"),
            Output("metadata-tester-filename", "children"),
        ],
        Input("metadata-tester-upload", "contents"),
        State("metadata-tester-upload", "filename"),
        prevent_initial_call=True,
    )
    def store_upload(contents, filename):
        """Store the uploaded image content in a Store component and display filename."""
        if contents is None:
            return dash.no_update, dash.no_update
        
        # Display filename
        filename_display = f"Selected: {filename}" if filename else "Image uploaded"
        
        # Return the contents to store it and the filename display
        return contents, filename_display
    
    
    @app.callback(
        [
            Output("metadata-tester-progress", "children"),
            Output("metadata-tester-result", "children"),
            Output("metadata-tester-running", "data"),
        ],
        Input("btn-metadata-tester-extract", "n_clicks"),
        State("metadata-tester-store", "data"),
        State("metadata-tester-upload", "filename"),
        prevent_initial_call=True,
    )
    def extract_metadata_from_upload(
        n_clicks,
        contents,
        filename,
    ):
        """Extract metadata from the uploaded image."""
        if n_clicks is None:
            return dash.no_update, dash.no_update, dash.no_update
        
        if contents is None:
            error_alert = dbc.Alert(
                [
                    html.Strong("No image uploaded "),
                    html.Br(),
                    "Please select an image using the 'Select Image' button before extracting metadata.",
                ],
                color="warning",
                dismissable=True,
            )
            return dash.no_update, error_alert, False
        
        # Progress indicator
        progress = dbc.Alert(
            [
                html.Span("Extracting metadata... ", className="me-2"),
                dbc.Spinner(size="sm", color="primary"),
            ],
            color="info",
            dismissable=False,
        )
        
        try:
            # Extract the base64 data from the upload content
            # The upload content format is: "data:image/png;base64,<base64_data>"
            if contents.startswith("data:"):
                # Extract the base64 part after the comma
                header, encoded = contents.split(",", 1)
                image_b64 = encoded
            else:
                image_b64 = contents
            
            # Decode base64 to bytes
            image_bytes = base64.b64decode(image_b64)
            
            # Save to a temporary file for processing
            # We need to write to a temp file because extract_metadata expects a file path
            import tempfile
            import os
            
            # Determine file extension from the data URI header or filename
            file_ext = ".jpg"  # default
            if filename and "." in filename:
                file_ext = filename[filename.rfind("."):].lower()
            elif contents.startswith("data:image/"):
                # Extract from data URI
                content_type = header.split(";")[0].split("/")[-1]
                file_ext = f".{content_type}"
            
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp_file:
                tmp_file.write(image_bytes)
                tmp_path = tmp_file.name
            
            try:
                # Extract metadata using the extract_metadata function
                metadata = extract_metadata(tmp_path)
                metadata_dict = metadata.to_dict()
                
                # Build the result display
                result_component = build_metadata_result(contents, filename, metadata_dict)
                
                return progress, result_component, False
                
            finally:
                # Clean up the temporary file
                try:
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file {tmp_path}: {e}")
            
        except Exception as e:
            logger.error(f"Error in metadata extraction: {e}", exc_info=True)
            error_msg = f"Error extracting metadata: {str(e)}"
            error_component = dbc.Alert(
                [
                    html.Strong("Metadata Extraction Failed: "),
                    html.Span(error_msg),
                ],
                color="danger",
                dismissable=True,
            )
            return progress, error_component, False
