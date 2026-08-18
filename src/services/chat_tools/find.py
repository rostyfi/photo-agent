"""Find tool - Finds photos matching description using vector search."""

import logging
import re

from src.date_filter import parse_date_expression
from src.services.chat_response import ChatResponse
from src.services.chat_tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class FindTool(BaseTool):
    """Tool that finds photos matching a description using vector embeddings.

    An optional date filter may be appended with ``@`` to restrict results to
    photos taken within a date range, e.g. ``/find car @last summer`` or
    ``/find 5 car @summer 2024``. The date expression is resolved to an
    inclusive ``(start, end)`` range and applied *before* similarity ranking,
    so only photos matching both the date window and the description are
    returned.

    Date resolution uses :class:`src.services.date_parser.DateParserService`,
    which asks the LLM to classify the expression and routes standard forms
    (seasons, months, years, relative keywords) to a deterministic parser and
    open-ended expressions to the LLM itself. If the LLM is unavailable, the
    deterministic parser is used alone.
    """

    metadata = ToolMetadata(
        command="/find",
        name="Find",
        description="Finds photos matching the description",
        help_text=(
            "/find <number> <description> [@<date>] - Finds photos matching the "
            "description (default: 10). Optional @<date> filters by when the photo "
            "was taken, e.g. @last summer, @summer 2024, @January 2024, @2023."
        ),
        usage="/find <number> <description> [@<date>]",
        requires_folder=True,
        arg_pattern=r"^/find\s+",
    )

    def execute(self, folder_path: str | None = None, args: str | None = None) -> ChatResponse:
        """Execute the find tool.

        Uses vector embeddings to find photos matching the description. An
        optional ``@<date>`` suffix restricts results to a date window parsed
        from natural language (e.g. ``last summer``, ``summer 2024``,
        ``January 2024``, ``2023``).

        Args:
            folder_path: The folder path to search in
            args: The search description, optional limit, and optional date

        Returns:
            ChatResponse with matching photos or error
        """
        if not args:
            return ChatResponse(
                status="error", response="Please provide a description to search for.", sender="assistant", model="N/A"
            )

        # Extract an optional leading count (e.g. "5 cats") first; the rest is
        # the description possibly mixed with a date reference.
        query, limit = self._split_limit(args.strip())

        date_start: str | None = None
        date_end: str | None = None
        try:
            from src.services.date_parser import DateParserService

            parser = DateParserService(self.config)
            description, date_start, date_end = parser.split_and_parse(query)
        except Exception as e:
            logger.warning("Date parser failed for %r (%s); using deterministic fallback", query, e)
            description, _limit, date_start, date_end = FindTool._parse_args(query)

        if not description:
            return ChatResponse(
                status="error", response="Please provide a description to search for.", sender="assistant", model="N/A"
            )

        try:
            from src.embeddings import create_generator
            from src.sidecar.database.db import FeaturesDatabase

            db_path = FeaturesDatabase.default_db_path(folder_path)
            db = FeaturesDatabase(db_path)

            # Generate embedding from the description text
            generator = create_generator(
                backend=self.config.embedding_backend,
                host=self.config.llm_host,
                port=self.config.llm_port,
                model=self.config.embedding_model,
                timeout=self.config.timeout,
            )
            query_vector = generator.generate_from_text(description)

            # Find similar photos using REST-based search with the parsed limit
            # and optional date filter.
            results = db.find_similar_rest(
                query_vector,
                self.config.embedding_model,
                limit=limit,
                date_start=date_start,
                date_end=date_end,
            )
            db.close()

            if results:
                response_data = {
                    "type": "photos",
                    "count": len(results),
                    "limit": limit,
                    "photos": [{"path": p, "score": s} for p, s in results[:limit]],
                }
                if date_start and date_end:
                    response_data["date_range"] = {"start": date_start, "end": date_end}
                return ChatResponse(
                    status="success", response=response_data, response_type="photos", sender="assistant", model="N/A"
                )
            else:
                return ChatResponse(
                    status="success", response="No matching photos found.", sender="assistant", model="N/A"
                )
        except Exception as e:
            import traceback

            logger.error("Error finding photos: %s", e)
            logger.error(traceback.format_exc())
            return ChatResponse(
                status="error", response=f"Failed to find photos: {e!s}", sender="assistant", model="N/A"
            )

    @staticmethod
    def _split_limit(args: str) -> tuple[str, int]:
        """Strip an optional leading count from find arguments.

        Returns ``(remaining_query, limit)``. The remaining query still
        contains any ``@<date>`` marker or mixed date words, which are resolved
        by :class:`DateParserService.split_and_parse`.
        """
        limit = 10  # Default limit
        match = re.match(r"^(\d+)\s+(.+)$", args)
        if match:
            try:
                limit = int(match.group(1))
                args = match.group(2).strip()
            except ValueError:
                # If the first part isn't a valid number, ignore it
                pass
        return args.strip(), limit

    @staticmethod
    def _split_args(args: str) -> tuple[str, int, str | None]:
        """Split raw find arguments into (description, limit, date_expr).

        Pure string parsing — no date resolution. The ``date_expr`` is the raw
        text after the first ``@`` (or ``None`` when no date filter is present).

        Recognised forms::

            "car"                       -> ("car", 10, None)
            "5 car"                     -> ("car", 5, None)
            "car @last summer"          -> ("car", 10, "last summer")
            "5 car @summer 2024"        -> ("car", 5, "summer 2024")
        """
        date_expr: str | None = None
        if "@" in args:
            head, _, tail = args.partition("@")
            args = head.strip()
            date_expr = tail.strip() or None

        description = args.strip()
        limit = 10  # Default limit
        match = re.match(r"^(\d+)\s+(.+)$", description)
        if match:
            try:
                limit = int(match.group(1))
                description = match.group(2).strip()
            except ValueError:
                # If the first part isn't a valid number, ignore it
                pass

        return description, limit, date_expr

    @staticmethod
    def _parse_args(args: str) -> tuple[str, int, str | None, str | None]:
        """Deterministic-only split + date parse (no LLM call).

        Convenience wrapper around :meth:`_split_args` that resolves the date
        expression with the deterministic parser alone. Used by tests and as a
        fallback when the LLM is unavailable.
        """
        description, limit, date_expr = FindTool._split_args(args)
        date_start: str | None = None
        date_end: str | None = None
        if date_expr:
            ds, de = parse_date_expression(date_expr)
            if ds and de:
                date_start, date_end = ds, de
            else:
                logger.warning("Unrecognised date filter %r; ignoring", date_expr)
        return description, limit, date_start, date_end
