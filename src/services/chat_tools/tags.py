"""Tags tool - Lists, filters, and explores photo tags with related tag suggestions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.services.chat_response import ChatResponse
from src.services.chat_tools.base import BaseTool, ToolMetadata

if TYPE_CHECKING:
    from src.sidecar.database.db import FeaturesDatabase


class TagsTool(BaseTool):
    """Tool for working with photo tags in chat.

    Supports:
    - /tags - List all tags with frequencies
    - /tags <topic> - Find tags related to a topic/keyword

    For showing photos with a specific tag, use the separate /tag command (TagTool).
    """

    metadata = ToolMetadata(
        command="/tags",
        name="Tags",
        description="List and filter photo tags by topic",
        help_text="/tags - List all tags. /tags <topic> - Find tags related to topic",
        usage="/tags [topic]",
        requires_folder=True,
        arg_pattern=r"^/tags\s+",
    )

    def execute(self, folder_path: str | None = None, args: str | None = None) -> ChatResponse:
        """Execute the tags tool.

        This tool handles the /tags command:
        - /tags - List all tags with frequencies
        - /tags <topic> - Find tags related to a topic/keyword

        For showing photos with a specific tag, use the /tag command (handled by TagTool).

        Args:
            folder_path: The folder path to search in
            args: Optional arguments - a topic/keyword to filter tags by

        Returns:
            ChatResponse with tags information
        """
        try:
            from src.sidecar.database.db import FeaturesDatabase

            db_path = FeaturesDatabase.default_db_path(folder_path)
            db = FeaturesDatabase(db_path)

            # If no arguments, list all tags with frequencies
            if not args or not args.strip():
                return self._list_all_tags(db)

            args = args.strip()

            # Always filter tags by the provided topic/keyword
            return self._filter_tags_by_topic(db, args)

        except Exception as e:
            import logging
            import traceback

            logger = logging.getLogger(__name__)
            logger.error("Error in tags tool: %s", e)
            logger.error(traceback.format_exc())
            return ChatResponse(
                status="error", response=f"Failed to work with tags: {e!s}", sender="assistant", model="N/A"
            )
        finally:
            if "db" in locals():
                db.close()

    def _list_all_tags(self, db: FeaturesDatabase) -> ChatResponse:
        """List all tags with their frequencies."""
        tag_frequencies = db.list_tag_frequencies(limit=100)

        if not tag_frequencies:
            return ChatResponse(
                status="success",
                response={"text": "No tags found in the database.", "tags": []},
                response_type="tags",
                sender="assistant",
                model="N/A",
            )

        # Format tags with frequencies for display
        tag_lines = []
        for tag, count in tag_frequencies:
            tag_lines.append(f"  • **{tag}** ({count} photos)")

        text_response = "**All Tags (Top 100):**\n\n" + "\n".join(tag_lines)

        # Return structured data with both text and tag list
        return ChatResponse(
            status="success",
            response={"text": text_response, "tags": [{"name": tag, "count": count} for tag, count in tag_frequencies]},
            response_type="tags",
            sender="assistant",
            model="N/A",
        )

    def _filter_tags_by_topic(self, db: FeaturesDatabase, topic: str) -> ChatResponse:
        """Filter tags that are related to a topic/keyword."""
        all_tags = db.list_all_tags()

        if not all_tags:
            return ChatResponse(
                status="success",
                response={"text": f"No tags found in the database to filter by '{topic}'.", "tags": []},
                response_type="tags",
                sender="assistant",
                model="N/A",
            )

        # Filter tags that contain the topic (case-insensitive)
        topic_lower = topic.lower()
        related_tags = [tag for tag in all_tags if topic_lower in tag.lower()]

        if not related_tags:
            # Try to find tags that might be semantically related
            # by looking for partial matches or similar words
            related_tags = self._find_semantically_related_tags(all_tags, topic)

        if not related_tags:
            return ChatResponse(
                status="success",
                response={"text": f"No tags found related to '{topic}'. Try a different keyword.", "tags": []},
                response_type="tags",
                sender="assistant",
                model="N/A",
            )

        # Get frequencies for the related tags
        tag_frequencies = db.list_tag_frequencies(limit=1000)
        freq_map = dict(tag_frequencies)

        # Sort related tags by frequency (descending)
        related_tags_sorted = sorted(related_tags, key=lambda t: freq_map.get(t, 0), reverse=True)

        # Format the response
        tag_lines = []
        tag_data = []
        for tag in related_tags_sorted[:50]:  # Limit to top 50
            count = freq_map.get(tag, 0)
            tag_lines.append(f"  • **{tag}** ({count} photos)")
            tag_data.append({"name": tag, "count": count})

        text_response = f"**Tags related to '{topic}':**\n\n" + "\n".join(tag_lines)

        if len(related_tags) > 50:
            text_response += f"\n\n*... and {len(related_tags) - 50} more tags*"

        text_response += "\n\n**Tip:** Click on a tag to see photos with that tag and discover related tags."

        return ChatResponse(
            status="success",
            response={"text": text_response, "tags": tag_data, "topic": topic},
            response_type="tags",
            sender="assistant",
            model="N/A",
        )

    def _find_semantically_related_tags(self, all_tags: list, topic: str) -> list:
        """Find tags that might be semantically related to the topic.

        This is a fallback when direct substring matching fails.
        """
        topic_words = set(re.findall(r"\b\w+\b", topic.lower()))
        related = []

        for tag in all_tags:
            tag_words = set(re.findall(r"\b\w+\b", tag.lower()))
            # If any word in the tag matches any word in the topic
            if topic_words & tag_words:
                related.append(tag)

        return related

    def _show_tag_photos_and_related(self, db: FeaturesDatabase, tag: str) -> ChatResponse:
        """Show photos with a specific tag and related tags."""
        # Get photos with this tag
        photos = db.get_features_by_tag(tag)

        if not photos:
            return ChatResponse(
                status="success",
                response={"text": f"No photos found with tag '**{tag}**'.", "photos": [], "related_tags": []},
                response_type="photos_and_tags",
                sender="assistant",
                model="N/A",
            )

        # Get related tags (tags that co-occur with this tag)
        related_tags = db.list_tag_frequencies_restricted([tag], limit=20)

        # Format photo results
        photo_lines = []
        photo_data = []
        for photo in photos[:20]:  # Limit to 20 photos
            path = photo.get("image_path", "")
            description = photo.get("description", "No description")
            photo_lines.append(f"  • **{path}** - {description[:100]}...")
            photo_data.append({"path": path, "description": description})

        photos_section = f"**Photos with tag '{tag}' ({len(photos)} total):**\n\n"
        photos_section += "\n".join(photo_lines)

        if len(photos) > 20:
            photos_section += f"\n\n*... and {len(photos) - 20} more photos*"

        # Format related tags
        related_lines = []
        related_tag_data = []
        if related_tags:
            for related_tag, count in related_tags:
                related_lines.append(f"  • **{related_tag}** ({count} photos)")
                related_tag_data.append({"name": related_tag, "count": count})

            related_section = f"\n\n**Tags that often appear with '{tag}':**\n\n"
            related_section += "\n".join(related_lines)
        else:
            related_section = f"\n\n**No other tags co-occur with '{tag}'.**"

        text_response = photos_section + related_section
        text_response += "\n\n**Tip:** Click on a related tag to explore photos with both tags."

        return ChatResponse(
            status="success",
            response={
                "text": text_response,
                "photos": photo_data,
                "related_tags": related_tag_data,
                "tag": tag,
                "total_photos": len(photos),
            },
            response_type="photos_and_tags",
            sender="assistant",
            model="N/A",
        )


class TagTool(BaseTool):
    """Tool for showing photos with a specific tag.

    This is a separate tool from TagsTool to handle the /tag command
    which shows photos with a specific tag name.
    """

    metadata = ToolMetadata(
        command="/tag",
        name="Tag",
        description="Show photos with a specific tag and related tags",
        help_text="/tag <tagname> - Show photos with a specific tag and related tags",
        usage="/tag <tagname>",
        requires_folder=True,
        arg_pattern=r"^/tag\s+",
    )

    def execute(self, folder_path: str | None = None, args: str | None = None) -> ChatResponse:
        """Execute the tag tool to show photos with a specific tag.

        Args:
            folder_path: The folder path to search in
            args: The tag name to look up

        Returns:
            ChatResponse with photos and related tags information
        """
        try:
            from src.sidecar.database.db import FeaturesDatabase

            if not args or not args.strip():
                return ChatResponse(
                    status="error", response="Please provide a tag name.", sender="assistant", model="N/A"
                )

            # Parse comma-separated tags (preserves case), drop empties/dupes
            raw_tags = [t.strip() for t in args.split(",")]
            seen = set()
            tags = []
            for t in raw_tags:
                if t and t.lower() not in seen:
                    seen.add(t.lower())
                    tags.append(t)

            if not tags:
                return ChatResponse(
                    status="error", response="Please provide a tag name.", sender="assistant", model="N/A"
                )

            db_path = FeaturesDatabase.default_db_path(folder_path)
            db = FeaturesDatabase(db_path)

            # Get photos matching ALL selected tags (AND semantics)
            photos = db.get_features_by_tags(tags)

            if not photos:
                label = ", ".join(tags)
                return ChatResponse(
                    status="success",
                    response={
                        "text": f"No photos found with tag(s): **{label}**.",
                        "photos": [],
                        "related_tags": [],
                        "selected_tags": tags,
                        "tag": label,
                        "total_photos": 0,
                    },
                    response_type="photos_and_tags",
                    sender="assistant",
                    model="N/A",
                )

            # Get co-occurring tags (excludes the already-selected ones)
            related_tags = db.list_tag_frequencies_restricted(tags, limit=20)

            # Format photo results
            photo_lines = []
            photo_data = []
            for photo in photos[:20]:  # Limit to 20 photos
                path = photo.get("image_path", "")
                description = photo.get("description", "No description")
                photo_lines.append(f"  • **{path}** - {description[:100]}...")
                photo_data.append({"path": path, "description": description})

            label = ", ".join(tags)
            photos_section = f"**Photos with tag(s) '{label}' ({len(photos)} total):**\n\n"
            photos_section += "\n".join(photo_lines)

            if len(photos) > 20:
                photos_section += f"\n\n*... and {len(photos) - 20} more photos*"

            # Format related tags
            related_lines = []
            related_tag_data = []
            if related_tags:
                for related_tag, count in related_tags:
                    related_lines.append(f"  • **{related_tag}** ({count} photos)")
                    related_tag_data.append({"name": related_tag, "count": count})

                related_section = f"\n\n**Tags that often appear with '{label}':**\n\n"
                related_section += "\n".join(related_lines)
            else:
                related_section = f"\n\n**No other tags co-occur with '{label}'.**"

            text_response = photos_section + related_section
            text_response += "\n\n**Tip:** Click a related tag to narrow the results (AND). Click a selected tag chip to remove it from the filter, or Clear to reset."

            return ChatResponse(
                status="success",
                response={
                    "text": text_response,
                    "photos": photo_data,
                    "related_tags": related_tag_data,
                    "selected_tags": tags,
                    "tag": label,
                    "total_photos": len(photos),
                },
                response_type="photos_and_tags",
                sender="assistant",
                model="N/A",
            )

        except Exception as e:
            import logging
            import traceback

            logger = logging.getLogger(__name__)
            logger.error("Error in tag tool: %s", e)
            logger.error(traceback.format_exc())
            return ChatResponse(
                status="error", response=f"Failed to show photos with tag: {e!s}", sender="assistant", model="N/A"
            )
        finally:
            if "db" in locals():
                db.close()
