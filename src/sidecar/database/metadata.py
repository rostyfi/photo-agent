"""Image metadata (EXIF/IPTC/XMP) storage mixin for FeaturesDatabase."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)


class MetadataMixin:
    """EXIF/IPTC/XMP metadata persistence for FeaturesDatabase.

    Requires the owning class to provide ``db_path`` and
    ``get_connection()`` (from :class:`DatabaseConnectionMixin`).
    """

    db_path: Path

    if TYPE_CHECKING:

        def get_connection(self): ...

    def save_metadata(self, image_path: str, metadata: dict) -> None:
        """Save image metadata to the database.

        Args:
            image_path: Path to the image.
            metadata: Dictionary containing metadata (from src.metadata.extract_metadata_dict).
        """
        if not metadata:
            logger.debug("Not saving metadata: metadata dict is empty")
            return

        try:
            with self.get_connection() as conn:
                updated_at = datetime.now(timezone.utc).isoformat()

                # Prepare all metadata fields
                fields = [
                    "image_path",
                    "file_name",
                    "file_size_bytes",
                    "file_extension",
                    "width",
                    "height",
                    "aspect_ratio",
                    "make",
                    "model",
                    "camera_serial",
                    "lens_make",
                    "lens_model",
                    "exposure_time",
                    "f_number",
                    "iso_speed",
                    "focal_length",
                    "focal_length_35mm",
                    "aperture_value",
                    "date_taken",
                    "date_created",
                    "date_modified",
                    "latitude",
                    "longitude",
                    "altitude",
                    "gps_precision",
                    "location_name",
                    "color_space",
                    "bits_per_sample",
                    "orientation",
                    "software",
                    "copyright",
                    "artist",
                    "image_description",
                    "title",
                    "updated_at",
                ]

                # Build placeholders
                placeholders = ", ".join(["?"] * len(fields))

                # Convert all values to SQLite-compatible types (handle IFDRational, etc.)
                def _convert_value(val: Any) -> Any:
                    """Convert special types to SQLite-compatible types."""
                    if val is None:
                        return None
                    # Handle IFDRational from Pillow EXIF
                    if hasattr(val, "numerator") and hasattr(val, "denominator"):
                        try:
                            return float(val.numerator) / float(val.denominator)
                        except (ValueError, ZeroDivisionError, TypeError):
                            return str(val)
                    # Handle tuples (already handled by metadata module, but just in case)
                    if isinstance(val, tuple) and len(val) == 2:
                        try:
                            return float(val[0]) / float(val[1])
                        except (ValueError, ZeroDivisionError, TypeError):
                            return str(val)
                    # Handle bytes
                    if isinstance(val, bytes):
                        try:
                            return val.decode("utf-8", errors="ignore")
                        except (UnicodeDecodeError, AttributeError):
                            return str(val)
                    # For lists, convert to comma-separated string
                    if isinstance(val, list):
                        return ", ".join(str(v) for v in val if v is not None)
                    return val

                values = [_convert_value(metadata.get(field)) for field in fields]
                values[-1] = updated_at  # Set updated_at
                values[0] = image_path  # Ensure image_path is set

                # Build SET clause for ON CONFLICT
                set_clause = ", ".join([f"{field} = excluded.{field}" for field in fields if field != "image_path"])

                conn.execute(
                    f"""
                    INSERT INTO image_metadata ({", ".join(fields)})
                    VALUES ({placeholders})
                    ON CONFLICT(image_path) DO UPDATE SET {set_clause}
                    """,
                    values,
                )
                conn.commit()
                logger.debug("Saved metadata for %s (keys: %s)", image_path, list(metadata.keys()))
        except Exception as e:
            logger.error("Failed to save metadata for %s: %s", image_path, e, exc_info=True)
            raise

    def get_metadata(self, image_path: str) -> dict | None:
        """Retrieve metadata for a specific image.

        Args:
            image_path: Path to the image.

        Returns:
            Dictionary containing all metadata fields, or None if not found.
        """
        if not self.db_path.exists():
            logger.debug("Database does not exist at %s", self.db_path)
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM image_metadata WHERE image_path = ?",
                    (image_path,),
                )
                row = cursor.fetchone()

                if not row:
                    logger.debug("No metadata row found for %s in %s", image_path, self.db_path)
                    return None

                # Get column names
                columns = [desc[0] for desc in cursor.description]
                result = dict(zip(columns, row, strict=False))
                logger.debug("Retrieved metadata for %s (keys: %s)", image_path, list(result.keys()))
                return result
        except Exception as e:
            logger.error("Failed to get metadata for %s: %s", image_path, e, exc_info=True)
            return None

    def get_metadata_for_display(self, image_path: str) -> dict[str, str]:
        """Get metadata formatted for display.

        Args:
            image_path: Path to the image.

        Returns:
            Dictionary with formatted metadata suitable for UI display.
        """
        from src.metadata import ImageMetadata, format_metadata_for_display

        raw_metadata = self.get_metadata(image_path)
        if not raw_metadata:
            return {}

        # Convert to ImageMetadata object
        metadata_obj = ImageMetadata()
        for key, value in raw_metadata.items():
            if hasattr(metadata_obj, key):
                setattr(metadata_obj, key, value)

        return format_metadata_for_display(metadata_obj)

    def get_sort_metadata_batch(self, image_paths: list[str]) -> dict[str, dict]:
        """Retrieve the sort-relevant metadata for a batch of images.

        Args:
            image_paths: Paths to look up. Duplicates are deduplicated by the
                returned dict's keys.

        Returns:
            Mapping of ``image_path`` to ``{"date_taken", "date_modified",
            "file_name"}``. Paths without a metadata row are omitted. EXIF
            ``date_taken`` is commonly stored as ``"YYYY:MM:DD HH:MM:SS"``;
            callers normalise colons to dashes before comparing.
        """
        if not image_paths or not self.db_path.exists():
            return {}

        paths_json = json.dumps([str(p) for p in image_paths])
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """
                    WITH input(image_path) AS (SELECT value FROM json_each(?))
                    SELECT im.image_path, im.date_taken, im.date_modified, im.file_name
                    FROM image_metadata im
                    JOIN input ON im.image_path = input.image_path
                    """,
                    (paths_json,),
                ).fetchall()
        except Exception as e:
            logger.error("Failed to batch-fetch sort metadata: %s", e, exc_info=True)
            return {}

        return {
            row[0]: {
                "date_taken": row[1],
                "date_modified": row[2],
                "file_name": row[3],
            }
            for row in rows
        }
