import os
import unittest
from unittest.mock import patch

from src.config import (
    AppConfig,
    ProcessingConfig,
    _safe_int,
    _safe_int_or,
    _validate_host,
    _validate_port_range,
    _validate_positive,
)
from src.interfaces import DEFAULT_PROMPT


class TestSafeInt(unittest.TestCase):
    def test_returns_fallback_when_env_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            result = _safe_int("NONEXISTENT_VAR", 100)
            self.assertEqual(result, 100)

    def test_parses_valid_integer(self):
        with patch.dict(os.environ, {"TEST_PORT": "8080"}, clear=True):
            result = _safe_int("TEST_PORT", 11434)
            self.assertEqual(result, 8080)

    def test_returns_fallback_on_invalid_input(self):
        with patch.dict(os.environ, {"TEST_PORT": "not-an-int"}, clear=True):
            result = _safe_int("TEST_PORT", 42)
            self.assertEqual(result, 42)


class TestSafeIntOr(unittest.TestCase):
    def test_prefers_first_var(self):
        env = {"FIRST": "100", "SECOND": "200"}
        with patch.dict(os.environ, env, clear=True):
            result = _safe_int_or("FIRST", "SECOND", 0)
            self.assertEqual(result, 100)

    def test_falls_back_to_second_var(self):
        env = {"SECOND": "200"}
        with patch.dict(os.environ, env, clear=True):
            result = _safe_int_or("FIRST", "SECOND", 0)
            self.assertEqual(result, 200)

    def test_returns_fallback_when_neither_set(self):
        with patch.dict(os.environ, {}, clear=True):
            result = _safe_int_or("FIRST", "SECOND", 999)
            self.assertEqual(result, 999)

    def test_first_invalid_falls_back_to_second(self):
        env = {"FIRST": "abc", "SECOND": "300"}
        with patch.dict(os.environ, env, clear=True):
            result = _safe_int_or("FIRST", "SECOND", 0)
            self.assertEqual(result, 300)

    def test_both_invalid_returns_fallback(self):
        env = {"FIRST": "abc", "SECOND": "def"}
        with patch.dict(os.environ, env, clear=True):
            result = _safe_int_or("FIRST", "SECOND", 42)
            self.assertEqual(result, 42)


class TestValidatePortRange(unittest.TestCase):
    def test_valid_port(self):
        _validate_port_range("TEST_VAR", 8080, "test port")

    def test_port_too_low(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_port_range("TEST_VAR", 0, "test port")
        self.assertIn("test port", str(ctx.exception))
        self.assertIn("0", str(ctx.exception))

    def test_port_too_high(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_port_range("TEST_VAR", 99999, "test port")
        self.assertIn("test port", str(ctx.exception))
        self.assertIn("99999", str(ctx.exception))


class TestValidateHost(unittest.TestCase):
    def test_valid_host(self):
        _validate_host("TEST_VAR", "192.168.0.1", "test host")

    def test_empty_host(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_host("TEST_VAR", "", "test host")
        self.assertIn("test host", str(ctx.exception))

    def test_whitespace_only_host(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_host("TEST_VAR", "   ", "test host")
        self.assertIn("test host", str(ctx.exception))


class TestValidatePositive(unittest.TestCase):
    def test_positive_value(self):
        _validate_positive("TEST_VAR", 120, "timeout")

    def test_zero_value(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_positive("TEST_VAR", 0, "timeout")
        self.assertIn("timeout", str(ctx.exception))

    def test_negative_value(self):
        with self.assertRaises(ValueError) as ctx:
            _validate_positive("TEST_VAR", -5, "timeout")
        self.assertIn("timeout", str(ctx.exception))


class TestProcessingConfig(unittest.TestCase):
    def test_default_values(self):
        cfg = ProcessingConfig()
        self.assertEqual(cfg.backend, "ollama")
        self.assertEqual(cfg.host, "127.0.0.1")
        self.assertEqual(cfg.port, 11434)
        self.assertEqual(cfg.model, "gemma4:e2b-it-qat")
        self.assertEqual(cfg.timeout, 600)
        self.assertEqual(cfg.default_prompt, DEFAULT_PROMPT)

    def test_validate_passes_on_defaults(self):
        cfg = ProcessingConfig()
        cfg.validate()

    def test_validate_raises_on_invalid_port(self):
        cfg = ProcessingConfig(port=0)
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_validate_raises_on_empty_host(self):
        cfg = ProcessingConfig(host="")
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_validate_raises_on_non_positive_timeout(self):
        cfg = ProcessingConfig(timeout=0)
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_from_env_llm_vars_take_precedence(self):
        env = {
            "LOCAL_PHOTO_AGENT_LLM_PORT": "1234",
            "LOCAL_PHOTO_AGENT_OLLAMA_PORT": "5678",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = ProcessingConfig.from_env()
            self.assertEqual(cfg.port, 1234)

    def test_from_env_invalid_port_falls_back(self):
        env = {"LOCAL_PHOTO_AGENT_LLM_PORT": "INVALID"}
        with patch.dict(os.environ, env, clear=True):
            cfg = ProcessingConfig.from_env()
            self.assertEqual(cfg.port, 11434)


class TestAppConfig(unittest.TestCase):
    def test_default_values(self):
        cfg = AppConfig()
        self.assertEqual(cfg.llm_host, "127.0.0.1")
        self.assertEqual(cfg.llm_port, 11434)
        self.assertEqual(cfg.dash_host, "127.0.0.1")
        self.assertEqual(cfg.dash_port, 8050)
        self.assertEqual(cfg.timeout, 600)

    def test_validate_passes_on_defaults(self):
        cfg = AppConfig()
        cfg.validate()

    def test_validate_raises_on_invalid_llm_port(self):
        cfg = AppConfig(llm_port=0)
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_validate_raises_on_empty_llm_host(self):
        cfg = AppConfig(llm_host="")
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_validate_raises_on_non_positive_timeout(self):
        cfg = AppConfig(timeout=0)
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_validate_raises_on_invalid_dash_port(self):
        cfg = AppConfig(dash_port=0)
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_validate_raises_on_empty_dash_host(self):
        cfg = AppConfig(dash_host="")
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_dash_debug_false_values(self):
        for val in ("0", "false", "no", ""):
            with self.subTest(value=val):
                env = {"LOCAL_PHOTO_AGENT_DASH_DEBUG": val}
                with patch.dict(os.environ, env, clear=True):
                    cfg = AppConfig.from_env()
                    self.assertFalse(cfg.dash_debug)

    def test_to_processing_config(self):
        cfg = AppConfig(
            llm_backend="ollama",
            llm_host="example.com",
            llm_port=9999,
            llm_model="custom-model",
            timeout=300,
            default_prompt="Test prompt",
        )
        pc = cfg.to_processing_config()
        self.assertEqual(pc.backend, "ollama")
        self.assertEqual(pc.host, "example.com")
        self.assertEqual(pc.port, 9999)
        self.assertEqual(pc.model, "custom-model")
        self.assertEqual(pc.timeout, 300)
        self.assertEqual(pc.default_prompt, "Test prompt")


if __name__ == "__main__":
    unittest.main()
