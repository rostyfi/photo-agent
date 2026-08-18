"""Hybrid date-expression parser using an LLM as a routing classifier.

The :class:`DateParserService` resolves a natural-language date expression
(such as "last summer", "around Christmas a few years ago", or "summer 2024")
into an inclusive ``(start, end)`` ISO date range.

It uses a two-stage strategy:

1. **Classify** — a single LLM call inspects the expression alongside today's
   date and decides which parser is appropriate:
   - ``deterministic`` — a standard form (seasons, months, years, relative
     keywords) that the dependency-free :func:`src.date_filter.parse_date_expression`
     handles with exact calendar arithmetic.
   - ``llm`` — an open-ended or contextual expression the regex parser cannot
     handle (e.g. "when we visited Spain", "around Christmas a few years ago").
     The LLM supplies the range directly.
   - ``none`` — the expression is not a date at all; no filter is applied.

2. **Route** — apply the chosen parser. The LLM always returns a best-effort
   ``start``/``end`` pair alongside its classification, used as a fallback when
   the deterministic parser unexpectedly returns nothing.

If the LLM is unavailable or returns malformed output, the service degrades
gracefully to the deterministic parser alone, so the find tool still works
without an LLM round-trip.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import TYPE_CHECKING

from src.date_filter import parse_date_expression

if TYPE_CHECKING:
    from src.config import AppConfig
    from src.interfaces import LLMChatClient

logger = logging.getLogger(__name__)

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Cheap gate: only invoke the LLM split when the query plausibly contains a
# date/time reference. Keeps simple descriptions like "cats" or "a red car"
# from costing an LLM round-trip. False positives only cost an extra LLM call
# (the LLM then reports no date); false negatives are the real risk, so the
# keyword set is kept broad.
_DATE_REF_RE = re.compile(
    r"\b(?:"
    r"today|yesterday|tomorrow|tonight|last\s+night|recently|"
    r"(?:this|last|next)\s+(?:week|month|year|weekend|night|quarter)|"
    r"(?:this|last|next)\s+(?:winter|spring|summer|fall|autumn)|"
    r"(?:this|last)\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)|"
    r"last\s+(?:few\s+)?(?:days|weeks|months|years)|"
    r"winter|spring|summer|fall|autumn|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"\d{4}-\d{1,2}(?:-\d{1,2})?|"
    r"(?:19|20)\d{2}|"
    r"\d+\s+(?:day|week|month|year)s?\s+ago|ago"
    r")\b",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = (
    "You classify date expressions for a photo search filter and may resolve them.\n"
    "You are given today's date and a user-supplied date expression.\n"
    "Decide which parser should handle it:\n"
    "- \"deterministic\": standard forms the regex parser handles exactly: "
    "seasons (summer/winter/spring/fall/autumn) optionally with a year "
    "(\"summer 2024\", \"last summer\", \"this winter\"), month names optionally "
    "with a year (\"January 2024\", \"last march\", \"august\"), bare years "
    "(\"2023\"), ISO dates (\"2024-01-15\", \"2024-01\"), and relative keywords "
    "(\"today\", \"yesterday\", \"this week\", \"last week\", \"this month\", "
    "\"last month\", \"this year\", \"last year\").\n"
    "- \"llm\": open-ended, contextual, or fuzzy expressions the regex parser "
    "cannot handle (e.g. \"around Christmas a few years ago\", \"when we were in "
    "Spain\", \"last few months\"). Resolve these to an inclusive date range using "
    "today's date.\n"
    "- \"none\": not a date expression at all.\n"
    "ALSO return your best-effort start/end as YYYY-MM-DD regardless of strategy "
    "(used as a fallback). Use null when not applicable.\n"
    "Respond with ONLY a JSON object, no markdown, no explanation:\n"
    '{"strategy": "deterministic|llm|none", "start": "YYYY-MM-DD|null", "end": "YYYY-MM-DD|null"}'
)

_SPLIT_SYSTEM_PROMPT = (
    "You split a photo search query into a DESCRIPTION and an optional DATE part, "
    "and classify the date part.\n"
    "You are given today's date and a free-text search query that mixes a visual "
    "description of photos with an optional time reference (which may or may not "
    "be separated by an '@').\n"
    "Extract:\n"
    "- \"description\": the visual/subject description with all time words removed "
    "(e.g. from \"photos from last winter with a baby on them\" extract \"baby\"). "
    "Keep it concise — subjects and scenes only, no date words, no filler like "
    "\"photos of\" / \"pictures of\". Never empty.\n"
    "- \"date_phrase\": the time words exactly as the user wrote them, or null if "
    "there is no time reference (e.g. \"last winter\", \"summer 2024\", "
    "\"January 2024\", \"2023\").\n"
    "- \"strategy\": how to resolve the date phrase — \"deterministic\" for "
    "standard forms the regex parser handles (seasons/months/years/relative "
    "keywords), \"llm\" for open-ended or fuzzy time references, \"none\" when "
    "date_phrase is null.\n"
    "- \"start\"/\"end\": your best-effort inclusive range as YYYY-MM-DD (used "
    "when strategy is \"llm\", or as a fallback). Use null when not applicable.\n"
    "Respond with ONLY a JSON object, no markdown, no explanation:\n"
    '{"description": "...", "date_phrase": "...|null", '
    '"strategy": "deterministic|llm|none", "start": "YYYY-MM-DD|null", '
    '"end": "YYYY-MM-DD|null"}'
)


class DateParserService:
    """Resolve date expressions using an LLM classifier + deterministic parser.

    The LLM decides which parser to use; the deterministic parser handles
    standard forms with reliable calendar arithmetic, while the LLM handles
    open-ended expressions. Falls back to deterministic-only if the LLM is
    unavailable.
    """

    def __init__(
        self,
        config: AppConfig,
        chat_client: LLMChatClient | None = None,
        today: date | None = None,
    ):
        self.config = config
        self._chat_client = chat_client
        self._today = today or date.today()

    def _ensure_chat_client(self) -> LLMChatClient:
        """Lazily build a default Ollama chat client from config if none injected."""
        if self._chat_client is None:
            from plugins.llm import OllamaChatClient

            self._chat_client = OllamaChatClient(
                host=getattr(self.config, "llm_host", None),
                port=getattr(self.config, "llm_port", None),
                model=getattr(self.config, "llm_model", None),
                timeout=getattr(self.config, "timeout", 120),
            )
        return self._chat_client

    def parse(self, expression: str) -> tuple[str | None, str | None]:
        """Parse a date expression into an inclusive ISO date range.

        Uses the LLM to classify the expression, then routes to the
        deterministic parser or the LLM's own resolution. Degrades to
        deterministic-only when the LLM is unavailable.

        Args:
            expression: Natural-language date expression.

        Returns:
            ``(start_iso, end_iso)`` as ``YYYY-MM-DD`` strings, or
            ``(None, None)`` if the expression is not a date.
        """
        if not expression or not expression.strip():
            return None, None

        try:
            classification = self._classify(expression.strip())
        except Exception as e:
            # Network failure, LLM down, etc. — fall back to deterministic only.
            logger.warning("LLM date classification failed (%s); using deterministic fallback", e)
            return parse_date_expression(expression, self._today)

        strategy = classification.get("strategy", "deterministic")
        llm_start = self._normalise_date(classification.get("start"))
        llm_end = self._normalise_date(classification.get("end"))

        if strategy == "none":
            logger.debug("LLM classified %r as non-date", expression)
            return None, None

        if strategy == "llm":
            if llm_start and llm_end:
                logger.debug("LLM parsed %r -> %s..%s", expression, llm_start, llm_end)
                return llm_start, llm_end
            # LLM said it could handle it but gave no valid range — try deterministic.
            det = parse_date_expression(expression, self._today)
            if det[0] and det[1]:
                return det
            logger.warning("LLM strategy 'llm' for %r yielded no range; ignoring", expression)
            return None, None

        # strategy == "deterministic"
        det_start, det_end = parse_date_expression(expression, self._today)
        if det_start and det_end:
            return det_start, det_end
        # Deterministic parser unexpectedly failed — use the LLM's range if valid.
        if llm_start and llm_end:
            logger.info(
                "Deterministic parser failed for %r; using LLM range %s..%s",
                expression, llm_start, llm_end,
            )
            return llm_start, llm_end
        logger.warning("Could not resolve date expression %r", expression)
        return None, None

    def split_and_parse(self, args: str) -> tuple[str, str | None, str | None]:
        """Split a find query into a description and an optional date range.

        Used when the caller has NOT already separated the date with an ``@``
        marker — e.g. the routing LLM emitted ``/find baby last winter`` instead
        of ``/find baby @last winter``. The LLM extracts the visual description
        and resolves the date part in one call.

        Args:
            args: The raw find arguments (description possibly mixed with a date).

        Returns:
            ``(description, date_start, date_end)`` where the date pair is
            ``None`` when no time reference was found or the LLM is unavailable.
        """
        if not args or not args.strip():
            return "", None, None

        # Fast path: explicit '@' separator — no LLM split needed.
        if "@" in args:
            head, _, tail = args.partition("@")
            description = head.strip()
            date_start, date_end = self.parse(tail.strip())
            return description, date_start, date_end

        # Cheap gate: skip the LLM round-trip when there's no sign of a date
        # reference in the query. The whole string is treated as the description.
        if not _DATE_REF_RE.search(args):
            return args.strip(), None, None

        try:
            split = self._split(args.strip())
        except Exception as e:
            logger.warning("LLM date split failed (%s); using args as description only", e)
            return args.strip(), None, None

        description = str(split.get("description") or "").strip()
        if not description:
            # Refuse to drop the whole query — keep the original args as the
            # description and apply no date filter.
            logger.warning("LLM split returned empty description for %r; using args as-is", args)
            return args.strip(), None, None

        date_phrase = split.get("date_phrase")
        date_phrase = str(date_phrase).strip() if date_phrase else None
        strategy = str(split.get("strategy", "none")).strip().lower()
        if strategy not in ("deterministic", "llm", "none"):
            strategy = "deterministic"

        llm_start = self._normalise_date(split.get("start"))
        llm_end = self._normalise_date(split.get("end"))

        if strategy == "none" or not date_phrase:
            return description, None, None

        if strategy == "llm":
            if llm_start and llm_end:
                return description, llm_start, llm_end
            # Fall through to deterministic attempt on the extracted phrase.
            det = parse_date_expression(date_phrase, self._today)
            if det[0] and det[1]:
                return description, det[0], det[1]
            logger.warning("LLM split 'llm' strategy for %r yielded no range; ignoring", date_phrase)
            return description, None, None

        # strategy == "deterministic"
        det_start, det_end = parse_date_expression(date_phrase, self._today)
        if det_start and det_end:
            return description, det_start, det_end
        if llm_start and llm_end:
            logger.info(
                "Deterministic parser failed for %r; using LLM range %s..%s",
                date_phrase, llm_start, llm_end,
            )
            return description, llm_start, llm_end
        return description, None, None

    def _split(self, args: str) -> dict:
        """Ask the LLM to split the query into description + date parts."""
        client = self._ensure_chat_client()
        message = f"Today's date is {self._today.isoformat()}.\nSearch query: {args}"
        raw = client.chat(message, system_prompt=_SPLIT_SYSTEM_PROMPT)
        return self._parse_split(raw)

    @staticmethod
    def _parse_split(raw: str) -> dict:
        """Extract the JSON split result from the LLM's raw response."""
        if not raw:
            return {"description": "", "strategy": "none"}
        text = raw.strip()
        if text.startswith("```"):
            text = text[3:].lstrip()
            if text.endswith("```"):
                text = text[:-3].rstrip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            logger.warning("LLM split response had no JSON object: %r", raw)
            return {"description": "", "strategy": "none"}
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            logger.warning("LLM split JSON parse failed (%s): %r", e, raw)
            return {"description": "", "strategy": "none"}
        if not isinstance(data, dict):
            return {"description": "", "strategy": "none"}
        return {
            "description": data.get("description"),
            "date_phrase": data.get("date_phrase"),
            "strategy": data.get("strategy", "none"),
            "start": data.get("start"),
            "end": data.get("end"),
        }

    def _classify(self, expression: str) -> dict:
        """Ask the LLM to classify the expression and provide a fallback range."""
        client = self._ensure_chat_client()
        message = f"Today's date is {self._today.isoformat()}.\nDate expression: {expression}"
        raw = client.chat(message, system_prompt=_SYSTEM_PROMPT)
        return self._parse_classification(raw)

    @staticmethod
    def _parse_classification(raw: str) -> dict:
        """Extract the JSON classification from the LLM's raw response."""
        if not raw:
            return {"strategy": "deterministic"}
        text = raw.strip()
        # Strip markdown code fences if present.
        if text.startswith("```"):
            text = text[3:].lstrip()
            if text.endswith("```"):
                text = text[:-3].rstrip()
        # Find the first JSON object in the response.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            logger.warning("LLM classification response had no JSON object: %r", raw)
            return {"strategy": "deterministic"}
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            logger.warning("LLM classification JSON parse failed (%s): %r", e, raw)
            return {"strategy": "deterministic"}
        if not isinstance(data, dict):
            return {"strategy": "deterministic"}
        strategy = str(data.get("strategy", "deterministic")).strip().lower()
        if strategy not in ("deterministic", "llm", "none"):
            strategy = "deterministic"
        return {
            "strategy": strategy,
            "start": data.get("start"),
            "end": data.get("end"),
        }

    @staticmethod
    def _normalise_date(value) -> str | None:
        """Coerce an LLM-provided date value to a validated ``YYYY-MM-DD`` string."""
        if value is None:
            return None
        s = str(value).strip()
        if s.lower() in ("null", "none", ""):
            return None
        if _ISO_RE.match(s):
            return s
        logger.debug("Rejected non-ISO date value %r", value)
        return None
