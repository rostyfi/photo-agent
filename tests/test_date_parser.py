"""Tests for the hybrid LLM-classifier DateParserService."""

from datetime import date

from src.config import AppConfig
from src.services.date_parser import DateParserService

TODAY = date(2026, 8, 18)  # mid-summer, Tuesday


class _StubChatClient:
    """Minimal LLMChatClient stub returning a canned response."""

    def __init__(self, response: str):
        self._response = response
        self.calls: list[tuple[str, str | None]] = []

    def chat(self, message, system_prompt=None, history=None):
        self.calls.append((message, system_prompt))
        return self._response

    def health_check(self):
        return True


class _RaisingChatClient:
    """Chat client that raises to simulate LLM unavailability."""

    def chat(self, message, system_prompt=None, history=None):
        raise RuntimeError("LLM unavailable")

    def health_check(self):
        return False


def _config():
    return AppConfig(
        llm_host="localhost", llm_port=11434, llm_model="test",
        embedding_backend="dry_run", embedding_model="test",
    )


class TestDateParserService:
    def test_deterministic_strategy_uses_deterministic_parser(self):
        # LLM classifies as deterministic; the regex parser must win.
        client = _StubChatClient(
            '{"strategy": "deterministic", "start": "2020-01-01", "end": "2020-12-31"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        start, end = svc.parse("summer 2024")
        # Deterministic result, NOT the LLM's 2020 range.
        assert start == "2024-06-01" and end == "2024-08-31"
        assert len(client.calls) == 1

    def test_llm_strategy_uses_llm_range(self):
        client = _StubChatClient(
            '{"strategy": "llm", "start": "2023-12-20", "end": "2024-01-05"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        start, end = svc.parse("around Christmas a few years ago")
        assert start == "2023-12-20" and end == "2024-01-05"

    def test_none_strategy_returns_none(self):
        client = _StubChatClient(
            '{"strategy": "none", "start": null, "end": null}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        assert svc.parse("banana") == (None, None)

    def test_llm_strategy_without_range_falls_back_to_deterministic(self):
        # LLM says "llm" but gives no valid dates; the deterministic parser is
        # tried as a fallback. "last summer" is deterministic-parseable.
        client = _StubChatClient('{"strategy": "llm", "start": null, "end": null}')
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        start, end = svc.parse("last summer")
        assert start == "2025-06-01" and end == "2025-08-31"

    def test_deterministic_misclassified_uses_llm_range_as_fallback(self):
        # LLM says "deterministic" but the expression can't be regex-parsed;
        # the LLM's best-effort range is used.
        client = _StubChatClient(
            '{"strategy": "deterministic", "start": "2023-12-20", "end": "2024-01-05"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        start, end = svc.parse("around Christmas a few years ago")
        assert start == "2023-12-20" and end == "2024-01-05"

    def test_llm_failure_degrades_to_deterministic(self):
        svc = DateParserService(_config(), chat_client=_RaisingChatClient(), today=TODAY)
        # "last summer" is deterministic-parseable, so we still get a range.
        start, end = svc.parse("last summer")
        assert start == "2025-06-01" and end == "2025-08-31"

    def test_malformed_llm_response_falls_back_to_deterministic(self):
        client = _StubChatClient("I think it's summer 2024, roughly.")
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        start, end = svc.parse("summer 2024")
        assert start == "2024-06-01" and end == "2024-08-31"

    def test_markdown_fenced_json_is_parsed(self):
        client = _StubChatClient(
            "```json\n{\"strategy\": \"llm\", \"start\": \"2023-12-20\", \"end\": \"2024-01-05\"}\n```"
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        start, end = svc.parse("around Christmas a few years ago")
        assert start == "2023-12-20" and end == "2024-01-05"

    def test_invalid_llm_dates_are_rejected(self):
        client = _StubChatClient(
            '{"strategy": "llm", "start": "not-a-date", "end": "also-bad"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        # LLM range rejected; deterministic fallback attempted (also fails for
        # this open-ended expression) -> no filter.
        assert svc.parse("around Christmas a few years ago") == (None, None)

    def test_empty_expression_returns_none_without_llm_call(self):
        client = _StubChatClient('{"strategy": "none"}')
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        assert svc.parse("") == (None, None)
        assert svc.parse("   ") == (None, None)
        assert client.calls == []

    def test_unknown_strategy_defaults_to_deterministic(self):
        client = _StubChatClient(
            '{"strategy": "banana", "start": "2020-01-01", "end": "2020-12-31"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        # Unknown strategy -> treated as deterministic -> regex parser used.
        start, end = svc.parse("summer 2024")
        assert start == "2024-06-01" and end == "2024-08-31"

    def test_today_date_injected_into_prompt(self):
        client = _StubChatClient('{"strategy": "none"}')
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        svc.parse("last summer")
        assert len(client.calls) == 1
        message, _system = client.calls[0]
        assert TODAY.isoformat() in message
        assert "last summer" in message


class TestSplitAndParse:
    def test_at_separator_uses_fast_path_no_llm_call(self):
        # When '@' is present, the isolated-expression parser is used; no split
        # LLM call is made.
        client = _StubChatClient('{"strategy": "deterministic"}')
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        desc, ds, de = svc.split_and_parse("baby @last winter")
        assert desc == "baby"
        # last winter in Aug 2026 -> Dec 2025 - Feb 2026
        assert ds == "2025-12-01" and de == "2026-02-28"
        # The split call should NOT have hit the LLM (fast path). The .parse()
        # path does hit the LLM once.
        assert len(client.calls) == 1

    def test_no_date_reference_skips_llm_call(self):
        # "cats" has no date words -> no LLM round-trip at all.
        client = _StubChatClient('{"strategy": "none"}')
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        desc, ds, de = svc.split_and_parse("cats")
        assert desc == "cats"
        assert ds is None and de is None
        assert client.calls == []

    def test_llm_split_extracts_description_and_deterministic_date(self):
        # LLM splits "baby last winter" -> description "baby", date "last winter"
        # classified as deterministic; the regex parser resolves it.
        client = _StubChatClient(
            '{"description": "baby", "date_phrase": "last winter", '
            '"strategy": "deterministic", "start": "2020-01-01", "end": "2020-12-31"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        desc, ds, de = svc.split_and_parse("baby last winter")
        assert desc == "baby"
        # Deterministic result wins over the LLM's decoy 2020 range.
        assert ds == "2025-12-01" and de == "2026-02-28"

    def test_llm_split_with_llm_strategy_uses_llm_range(self):
        client = _StubChatClient(
            '{"description": "baby", "date_phrase": "around Christmas a few years ago", '
            '"strategy": "llm", "start": "2023-12-20", "end": "2024-01-05"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        desc, ds, de = svc.split_and_parse("baby around Christmas a few years ago")
        assert desc == "baby"
        assert ds == "2023-12-20" and de == "2024-01-05"

    def test_llm_split_none_strategy_drops_date(self):
        client = _StubChatClient(
            '{"description": "red car", "date_phrase": null, "strategy": "none"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        desc, ds, de = svc.split_and_parse("red car")
        assert desc == "red car"
        assert ds is None and de is None

    def test_llm_split_empty_description_falls_back_to_args(self):
        client = _StubChatClient(
            '{"description": "", "date_phrase": "last winter", "strategy": "deterministic"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        desc, ds, de = svc.split_and_parse("last winter")
        # Refuse to drop the whole query — keep args as description, no date.
        assert desc == "last winter"
        assert ds is None and de is None

    def test_llm_split_failure_degrades_to_description_only(self):
        svc = DateParserService(_config(), chat_client=_RaisingChatClient(), today=TODAY)
        desc, ds, de = svc.split_and_parse("baby last winter")
        # LLM unavailable -> whole query kept as description, no date filter.
        assert desc == "baby last winter"
        assert ds is None and de is None

    def test_gate_triggers_on_year(self):
        # A bare year is a date reference -> the gate lets the LLM split run.
        client = _StubChatClient(
            '{"description": "beach", "date_phrase": "2023", "strategy": "deterministic"}'
        )
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        desc, ds, de = svc.split_and_parse("beach 2023")
        assert desc == "beach"
        assert ds == "2023-01-01" and de == "2023-12-31"
        assert len(client.calls) == 1

    def test_empty_args(self):
        client = _StubChatClient('{"strategy": "none"}')
        svc = DateParserService(_config(), chat_client=client, today=TODAY)
        assert svc.split_and_parse("") == ("", None, None)
        assert svc.split_and_parse("   ") == ("", None, None)
        assert client.calls == []

