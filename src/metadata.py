"""
Image Metadata Extraction for Local Photo Agent.

Extracts EXIF and other metadata from image files using Pillow.
Handles various image formats including JPEG, PNG, HEIC, etc.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class ImageMetadata:
    """Structured container for image metadata."""

    # Basic file information
    file_path: str = ""
    file_name: str = ""
    file_size_bytes: int = 0
    file_extension: str = ""

    # Image dimensions
    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None

    # Camera information
    make: str | None = None
    model: str | None = None
    camera_serial: str | None = None
    lens_make: str | None = None
    lens_model: str | None = None

    # Exposure settings
    exposure_time: str | None = None
    f_number: str | None = None
    iso_speed: int | None = None
    focal_length: str | None = None
    focal_length_35mm: str | None = None
    aperture_value: str | None = None

    # Date/time information
    date_taken: str | None = None
    date_created: str | None = None
    date_modified: str | None = None

    # GPS/Location information
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    gps_precision: str | None = None
    location_name: str | None = None

    # Color information
    color_space: str | None = None
    bits_per_sample: int | None = None

    # Orientation
    orientation: str | None = None

    # Software
    software: str | None = None

    # Copyright
    copyright: str | None = None
    artist: str | None = None

    # Additional metadata
    image_description: str | None = None
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def get_camera_info(self) -> str:
        """Get formatted camera information."""
        parts = []
        if self.make:
            parts.append(self.make)
        if self.model:
            parts.append(self.model)
        if self.lens_model:
            parts.append(f"({self.lens_model})")
        return " ".join(parts) if parts else "Unknown"

    def get_exposure_info(self) -> str:
        """Get formatted exposure information."""
        parts = []
        if self.f_number:
            parts.append(f"f/{self.f_number}")
        if self.exposure_time:
            parts.append(f"{self.exposure_time}s")
        if self.iso_speed:
            parts.append(f"ISO {self.iso_speed}")
        if self.focal_length:
            parts.append(f"{self.focal_length}mm")
        return ", ".join(parts) if parts else "Not available"

    def get_location_info(self) -> str:
        """Get formatted location information."""
        if self.location_name:
            return self.location_name
        if self.latitude is not None and self.longitude is not None:
            return f"{self.latitude:.6f}, {self.longitude:.6f}"
        return "Not available"

    def get_dimensions_info(self) -> str:
        """Get formatted dimensions information."""
        if self.width and self.height:
            return (
                f"{self.width} × {self.height} ({self.aspect_ratio:.2f} aspect ratio)"
                if self.aspect_ratio
                else f"{self.width} × {self.height}"
            )
        return "Not available"


def _convert_to_degrees(value: Any) -> float | None:
    """Convert GPS coordinates from EXIF format to decimal degrees."""
    try:
        if not value:
            return None

        # GPS coordinates in EXIF are stored as rational numbers
        # Format: ((degrees_num, degrees_denom), (minutes_num, minutes_denom), (seconds_num, seconds_denom))
        d, m, s = value

        # Convert each component
        degrees = float(d[0]) / float(d[1]) if isinstance(d, tuple) else float(d)
        minutes = float(m[0]) / float(m[1]) if isinstance(m, tuple) else float(m)
        seconds = float(s[0]) / float(s[1]) if isinstance(s, tuple) else float(s)

        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    except (ValueError, TypeError, ZeroDivisionError, AttributeError) as e:
        logger.debug("Error converting GPS coordinates: %s", e)
        return None


def _get_exif_tag(exif_data: dict, tag_id: int, tag_name: str | None = None) -> Any | None:
    """Get a specific EXIF tag value with proper type conversion."""
    try:
        if tag_id in exif_data:
            value = exif_data[tag_id]

            # Handle different tag types
            if isinstance(value, bytes):
                try:
                    return value.decode("utf-8", errors="ignore")
                except (UnicodeDecodeError, AttributeError):
                    return str(value)
            elif isinstance(value, tuple):
                # Try to convert rational numbers to float
                if len(value) == 2:
                    try:
                        return float(value[0]) / float(value[1])
                    except (ValueError, ZeroDivisionError, TypeError):
                        return str(value)
                return str(value)

            return value
        return None
    except Exception as e:
        logger.debug("Error getting EXIF tag %s (%s): %s", tag_id, tag_name, e)
        return None


def _format_exposure_time(exposure: Any) -> str | None:
    """Format exposure time for display."""
    try:
        if exposure is None:
            return None

        if isinstance(exposure, float):
            if exposure >= 1:
                return f"{exposure:.1f}s"
            elif exposure > 0:
                return f"1/{int(1 / exposure)}s"
        elif isinstance(exposure, str):
            return exposure

        return str(exposure)
    except (ValueError, ZeroDivisionError, TypeError):
        return str(exposure) if exposure else None


def _format_focal_length(focal: Any) -> str | None:
    """Format focal length for display."""
    try:
        if focal is None:
            return None

        if isinstance(focal, float):
            return f"{focal:.1f}mm"
        elif isinstance(focal, str):
            return focal

        return str(focal)
    except (ValueError, TypeError):
        return str(focal) if focal else None


def _format_f_number(f_number: Any) -> str | None:
    """Format f-number for display."""
    try:
        if f_number is None:
            return None

        if isinstance(f_number, float):
            return f"{f_number:.1f}"
        elif isinstance(f_number, str):
            return f_number

        return str(f_number)
    except (ValueError, TypeError):
        return str(f_number) if f_number else None


def extract_metadata(image_path: str) -> ImageMetadata:
    """Extract metadata from an image file.

    Args:
        image_path: Path to the image file.

    Returns:
        ImageMetadata object containing all extracted metadata.
    """
    metadata = ImageMetadata()
    metadata.file_path = str(image_path)

    try:
        path_obj = Path(image_path)
        metadata.file_name = path_obj.name
        metadata.file_extension = path_obj.suffix.lower()
        metadata.file_size_bytes = path_obj.stat().st_size

        # Get file modification time
        mod_time = path_obj.stat().st_mtime
        metadata.date_modified = datetime.fromtimestamp(mod_time).isoformat()

    except Exception as e:
        logger.warning("Error getting file info for %s: %s", image_path, e)

    try:
        # Open image with Pillow to get dimensions and EXIF
        with Image.open(image_path) as img:
            # Get dimensions
            metadata.width = img.size[0] if img.size else None
            metadata.height = img.size[1] if img.size and len(img.size) > 1 else None

            # Calculate aspect ratio
            if metadata.width and metadata.height and metadata.height > 0:
                metadata.aspect_ratio = metadata.width / metadata.height

            # Get color space
            metadata.color_space = img.mode if hasattr(img, "mode") else None

            # Get bits per sample
            if hasattr(img, "bits"):
                metadata.bits_per_sample = img.bits

            # Try to get EXIF data
            try:
                exif_data = img._getexif() or {}

                # Common EXIF tags with their IDs
                exif_tags = {
                    270: ("image_description", _get_exif_tag),
                    274: ("orientation", _get_exif_tag),
                    271: ("make", _get_exif_tag),
                    272: ("model", _get_exif_tag),
                    305: ("software", _get_exif_tag),
                    306: ("date_taken", _get_exif_tag),
                    315: ("artist", _get_exif_tag),
                    33432: ("copyright", _get_exif_tag),
                    33434: ("exposure_time", _get_exif_tag),
                    33437: ("f_number", _get_exif_tag),
                    34855: ("iso_speed", _get_exif_tag),
                    36867: ("date_taken", _get_exif_tag),
                    37378: ("aperture_value", _get_exif_tag),
                    37386: ("focal_length", _get_exif_tag),
                    41989: ("focal_length_35mm", _get_exif_tag),
                    42034: ("lens_make", _get_exif_tag),
                    42035: ("lens_model", _get_exif_tag),
                    40091: ("camera_serial", _get_exif_tag),
                    36864: ("exif_version", _get_exif_tag),
                    41728: ("file_source", _get_exif_tag),
                    41729: ("scene_type", _get_exif_tag),
                }

                # Extract known tags
                for tag_id, (attr_name, getter) in exif_tags.items():
                    value = getter(exif_data, tag_id)
                    if value is not None:
                        setattr(metadata, attr_name, value)

                # Handle date taken - try multiple formats
                if metadata.date_taken is None and 306 in exif_data:
                    raw_date = exif_data[306]
                    if isinstance(raw_date, bytes):
                        try:
                            metadata.date_taken = raw_date.decode("utf-8", errors="ignore")
                        except (UnicodeDecodeError, AttributeError):
                            metadata.date_taken = str(raw_date)
                    elif isinstance(raw_date, str):
                        metadata.date_taken = raw_date

                # Format numeric values
                if metadata.exposure_time is not None:
                    metadata.exposure_time = _format_exposure_time(metadata.exposure_time)
                if metadata.f_number is not None:
                    metadata.f_number = _format_f_number(metadata.f_number)
                if metadata.focal_length is not None:
                    metadata.focal_length = _format_focal_length(metadata.focal_length)
                if metadata.focal_length_35mm is not None:
                    metadata.focal_length_35mm = _format_focal_length(metadata.focal_length_35mm)

                # Handle orientation
                if metadata.orientation:
                    orientation_map = {
                        1: "Normal",
                        2: "Mirrored",
                        3: "Rotated 180°",
                        4: "Mirrored and Rotated 180°",
                        5: "Mirrored and Rotated 270°",
                        6: "Rotated 270°",
                        7: "Mirrored and Rotated 90°",
                        8: "Rotated 90°",
                    }
                    metadata.orientation = orientation_map.get(
                        metadata.orientation, f"Unknown ({metadata.orientation})"
                    )

                # Try to extract GPS data
                try:
                    if hasattr(img, "_getexif") and exif_data:
                        # GPS info is stored in a separate IFD
                        gps_info = exif_data.get(34853)  # GPSInfo tag
                        if gps_info:
                            # GPS data is a dict with specific tags
                            gps_latitude = gps_info.get(2)  # GPSLatitude
                            gps_longitude = gps_info.get(4)  # GPSLongitude
                            gps_altitude = gps_info.get(6)  # GPSAltitude
                            gps_latitude_ref = gps_info.get(1)  # GPSLatitudeRef (N or S)
                            gps_longitude_ref = gps_info.get(3)  # GPSLongitudeRef (E or W)
                            gps_altitude_ref = gps_info.get(5)  # GPSAltitudeRef (above or below sea level)

                            if gps_latitude and gps_latitude_ref:
                                lat = _convert_to_degrees(gps_latitude)
                                if lat is not None and gps_latitude_ref == "S":
                                    lat = -lat
                                metadata.latitude = lat

                            if gps_longitude and gps_longitude_ref:
                                lon = _convert_to_degrees(gps_longitude)
                                if lon is not None and gps_longitude_ref == "W":
                                    lon = -lon
                                metadata.longitude = lon

                            if gps_altitude and gps_altitude_ref:
                                alt = _convert_to_degrees(gps_altitude)
                                if alt is not None and gps_altitude_ref == 1:  # Below sea level
                                    alt = -alt
                                metadata.altitude = alt
                except Exception as gps_error:
                    logger.debug("Error extracting GPS data from %s: %s", image_path, gps_error)

                # Try to get date created from file metadata
                if metadata.date_taken is None:
                    try:
                        # Try to get creation date from EXIF
                        if 36868 in exif_data:  # DateTimeOriginal
                            metadata.date_taken = exif_data[36868]
                        elif 306 in exif_data:  # DateTime
                            metadata.date_taken = exif_data[306]
                    except Exception as e:
                        logger.debug("Failed to read EXIF date: %s", e, exc_info=True)

                # Try to get title from various sources
                if metadata.title is None:
                    try:
                        # Try IPTC or other metadata
                        if hasattr(img, "info") and "title" in img.info:
                            metadata.title = img.info["title"]
                    except Exception as e:
                        logger.debug("Failed to read image title: %s", e, exc_info=True)

            except Exception as exif_error:
                logger.debug("Error extracting EXIF from %s: %s", image_path, exif_error)

    except Exception as e:
        logger.warning("Error opening image %s for metadata extraction: %s", image_path, e)

    return metadata


def extract_metadata_dict(image_path: str) -> dict[str, Any]:
    """Extract metadata and return as a dictionary.

    Args:
        image_path: Path to the image file.

    Returns:
        Dictionary containing all extracted metadata (None values excluded).
    """
    metadata = extract_metadata(image_path)
    return metadata.to_dict()


def format_metadata_for_display(metadata: ImageMetadata) -> dict[str, str]:
    """Format metadata for display in the UI.

    Args:
        metadata: ImageMetadata object.

    Returns:
        Dictionary with formatted metadata suitable for display.
    """
    display = {}

    # Basic info
    if metadata.file_size_bytes:
        size_kb = metadata.file_size_bytes / 1024
        size_mb = size_kb / 1024
        if size_mb >= 1:
            display["File Size"] = f"{size_mb:.2f} MB"
        else:
            display["File Size"] = f"{size_kb:.1f} KB"

    if metadata.date_modified:
        try:
            dt = datetime.fromisoformat(metadata.date_modified.replace("Z", "+00:00"))
            display["File Modified"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            display["File Modified"] = metadata.date_modified

    if metadata.date_taken:
        display["Date Taken"] = metadata.date_taken

    # Dimensions
    dimensions = metadata.get_dimensions_info()
    if dimensions != "Not available":
        display["Dimensions"] = dimensions

    # Camera info
    camera_info = metadata.get_camera_info()
    if camera_info != "Unknown":
        display["Camera"] = camera_info

    # Exposure
    exposure_info = metadata.get_exposure_info()
    if exposure_info != "Not available":
        display["Exposure"] = exposure_info

    # Location
    location_info = metadata.get_location_info()
    if location_info != "Not available":
        display["Location"] = location_info

    # Software
    if metadata.software:
        display["Software"] = metadata.software

    # Copyright
    if metadata.copyright:
        display["Copyright"] = metadata.copyright

    # Artist
    if metadata.artist:
        display["Artist"] = metadata.artist

    # Color space
    if metadata.color_space:
        display["Color Space"] = metadata.color_space

    # Orientation
    if metadata.orientation:
        display["Orientation"] = metadata.orientation

    # Title/Description
    if metadata.title:
        display["Title"] = metadata.title
    if metadata.image_description:
        display["Description"] = metadata.image_description

    return display
