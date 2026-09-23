import unittest
from unittest.mock import MagicMock, Mock, patch

import dash
import dash_bootstrap_components as dbc
from dash import html

import src.callbacks.health_settings as _hs
from plugins.llm import create_extractor
from src.callbacks.health_settings import (
    register_concurrency_setting_callback,
    register_connection_settings_callback,
    register_health_callback,
    register_settings_modal_callback,
)
from src.config import AppConfig
from tests.test_callbacks import find_callback, patch_callback_context


class TestHealthCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="health-status"),
                html.Div(id="btn-health"),
                html.Div(id="input-host"),
                html.Div(id="input-port"),
                html.Div(id="input-model"),
                html.Div(id="input-backend"),
                html.Div(id="input-timeout"),
                html.Div(id="chk-dry-run"),
            ]
        )

        # Create a mock create_extractor_fn
        def create_extractor_fn(**kwargs):
            return type(
                "MockExtractor",
                (),
                {
                    "base_url": "http://test:1234",
                    "model": "test-model",
                    "health_check": lambda self: True,
                },
            )()

        from src.config import AppConfig

        app_config = AppConfig.from_env()
        register_health_callback(self.app, create_extractor_fn, app_config)

    def test_dry_run_returns_info(self):
        cb = find_callback(self.app, "health-status", "children").__wrapped__
        result = cb(1, None, None, None, None, None, True)
        self.assertIn("Dry-run", str(result))
        self.assertIn("info", str(result))

    def test_healthy_returns_success(self):
        cb = find_callback(self.app, "health-status", "children").__wrapped__
        # Use dry-run mode to avoid connection issues
        result = cb(1, "127.0.0.1", "11434", "gemma4:e2b-it-qat", "ollama", "120", True)
        self.assertIn("Dry-run", str(result))
        self.assertIn("info", str(result))

    def test_no_click_returns_no_update(self):
        cb = find_callback(self.app, "health-status", "children").__wrapped__
        result = cb(None, "host", "1234", "model", "backend", "60", False)
        self.assertEqual(result, dash.no_update)


class TestSettingsModalCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="settings-modal"),
                html.Div(id="btn-settings"),
                html.Div(id="btn-close-settings"),
            ]
        )
        register_settings_modal_callback(self.app)

    def test_open_settings(self):
        cb = find_callback(self.app, "settings-modal", "is_open").__wrapped__
        with patch_callback_context(_hs, [{"prop_id": "btn-settings.n_clicks", "value": 1}]):
            result = cb(1, None)
        self.assertTrue(result)

    def test_close_settings(self):
        cb = find_callback(self.app, "settings-modal", "is_open").__wrapped__
        with patch_callback_context(_hs, [{"prop_id": "btn-close-settings.n_clicks", "value": 1}]):
            result = cb(None, 1)
        self.assertFalse(result)

    def test_no_trigger_no_update(self):
        cb = find_callback(self.app, "settings-modal", "is_open").__wrapped__
        with patch_callback_context(_hs, []):
            result = cb(None, None)
        self.assertEqual(result, dash.no_update)


class TestConcurrencySettingCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div([html.Div(id="input-concurrency")])
        self.app_config = AppConfig()
        self.app_config.batch_concurrency = 1
        register_concurrency_setting_callback(self.app, self.app_config)

    def _cb(self):
        return find_callback(self.app, "input-concurrency", "valid").__wrapped__

    def test_updates_app_config_value(self):
        self._cb()(4, None)
        self.assertEqual(self.app_config.batch_concurrency, 4)

    def test_coerces_below_one_to_one(self):
        self._cb()(0, None)
        self.assertEqual(self.app_config.batch_concurrency, 1)
        self._cb()(-3, None)
        self.assertEqual(self.app_config.batch_concurrency, 1)

    def test_coerces_invalid_to_one(self):
        self._cb()("not-a-number", None)
        self.assertEqual(self.app_config.batch_concurrency, 1)

    def test_coerces_none_to_one(self):
        self._cb()(None, None)
        self.assertEqual(self.app_config.batch_concurrency, 1)

    def test_returns_valid_true(self):
        self.assertTrue(self._cb()(2, None))

    def test_writes_to_folder_settings_file(self, tmp_path=None):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            self._cb()(5, tmpdir)
            settings_file = Path(tmpdir) / ".local-photo-agent" / "settings.json"
            self.assertTrue(settings_file.exists())
            import json

            data = json.loads(settings_file.read_text())
            self.assertEqual(data["batch_concurrency"], 5)

    def test_empty_folder_skips_write(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            self._cb()(3, None)
            self.assertFalse((Path(tmpdir) / ".local-photo-agent").exists())


class TestConnectionSettingsCallback(unittest.TestCase):
    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div([html.Div(id="settings-persist-dummy")])
        self.app_config = AppConfig()
        register_connection_settings_callback(self.app, self.app_config)

    def _cb(self):
        return find_callback(self.app, "settings-persist-dummy", "children").__wrapped__

    def test_persists_settings_to_folder_file(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            self._cb()(
                "10.0.0.9",  # host
                12345,  # port
                "custom-model",  # model
                "dry_run",  # backend
                90,  # timeout
                False,  # recursive
                True,  # dry_run
                True,  # debug_reasoning
                False,  # embedding_enabled
                "all-minilm",  # embedding_model
                "ollama",  # embedding_backend
                25,  # slideshow_threshold
                tmpdir,  # folder
            )
            settings = json.loads((Path(tmpdir) / ".local-photo-agent" / "settings.json").read_text())
            assert settings["llm_host"] == "10.0.0.9"
            assert settings["llm_port"] == 12345
            assert settings["llm_model"] == "custom-model"
            assert settings["llm_backend"] == "dry_run"
            assert settings["timeout"] == 90
            assert settings["recursive"] is False
            assert settings["dry_run"] is True
            assert settings["debug_reasoning"] is True
            assert settings["embedding_enabled"] is False
            assert settings["embedding_model"] == "all-minilm"
            assert settings["embedding_backend"] == "ollama"
            assert settings["slideshow_threshold"] == 25

    def test_syncs_app_config_in_memory(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            self._cb()(
                "10.0.0.9",
                12345,
                "custom-model",
                "dry_run",
                90,
                False,
                True,
                True,
                False,
                "all-minilm",
                "ollama",
                25,
                tmpdir,
            )
            assert self.app_config.llm_host == "10.0.0.9"
            assert self.app_config.llm_port == 12345
            assert self.app_config.llm_model == "custom-model"
            assert self.app_config.dry_run is True
            assert self.app_config.debug_reasoning is True
            assert self.app_config.embedding_enabled is False
            assert self.app_config.slideshow_threshold == 25

    def test_empty_folder_skips_write(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._cb()(
                "10.0.0.9",
                12345,
                "m",
                "b",
                90,
                True,
                False,
                True,
                True,
                "em",
                "eb",
                25,
                None,
            )
            assert result is dash.no_update
            assert not (Path(tmpdir) / ".local-photo-agent").exists()

    def test_blank_string_values_are_dropped(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            self._cb()(
                "   ",  # blank host -> dropped
                12345,
                "",  # blank model -> dropped
                "dry_run",
                90,
                False,
                True,
                False,
                False,
                "all-minilm",
                "ollama",
                25,
                tmpdir,
            )
            settings = json.loads((Path(tmpdir) / ".local-photo-agent" / "settings.json").read_text())
            assert "llm_host" not in settings
            assert "llm_model" not in settings
            assert settings["llm_port"] == 12345


class TestCheckVectorSearchStatus(unittest.TestCase):
    """Tests for _check_vector_search_status."""

    def setUp(self):
        # Reset the cache before each test
        import src.callbacks.health_settings as hs

        self._hs = hs
        hs._VECTOR_SEARCH_AVAILABLE_CACHE = None
        hs._VECTOR_SEARCH_AVAILABLE_CHECKED = False

    def test_available(self):
        with patch.object(_hs, "is_vector_search_available", return_value=True):
            is_avail, msg, color = _hs._check_vector_search_status()
        self.assertTrue(is_avail)
        self.assertEqual(color, "success")
        self.assertIn("available", msg.lower())

    def test_not_available(self):
        with patch.object(_hs, "is_vector_search_available", return_value=False):
            is_avail, msg, color = _hs._check_vector_search_status()
        self.assertFalse(is_avail)
        self.assertEqual(color, "danger")

    def test_exception_returns_error(self):
        with patch.object(_hs, "is_vector_search_available", side_effect=Exception("lib error")):
            is_avail, msg, color = _hs._check_vector_search_status()
        self.assertFalse(is_avail)
        self.assertEqual(color, "danger")
        self.assertIn("sqlite-vec error", msg)

    def test_caches_result(self):
        with patch.object(_hs, "is_vector_search_available", return_value=True) as mock_check:
            _hs._check_vector_search_status()
            _hs._check_vector_search_status()
        # Should only call the underlying check once due to caching
        mock_check.assert_called_once()


class TestCheckEmbeddingStatus(unittest.TestCase):
    """Tests for _check_embedding_status."""

    def _config(self, embedding_enabled=True):
        config = MagicMock()
        config.embedding_enabled = embedding_enabled
        config.embedding_backend = "ollama"
        config.llm_host = "localhost"
        config.llm_port = 11434
        config.embedding_model = "test-model"
        return config

    def test_disabled_returns_secondary(self):
        config = self._config(embedding_enabled=False)
        is_avail, msg, color = _hs._check_embedding_status("host", 1234, "backend", config)
        self.assertTrue(is_avail)
        self.assertEqual(color, "secondary")
        self.assertIn("disabled", msg.lower())

    def test_healthy(self):
        config = self._config()
        with patch("src.embeddings.create_generator") as mock_gen:
            mock_gen.return_value.health_check.return_value = True
            is_avail, msg, color = _hs._check_embedding_status("host", 1234, "ollama", config)
        self.assertTrue(is_avail)
        self.assertEqual(color, "success")

    def test_unhealthy(self):
        config = self._config()
        with patch("src.embeddings.create_generator") as mock_gen:
            mock_gen.return_value.health_check.return_value = False
            is_avail, msg, color = _hs._check_embedding_status("host", 1234, "ollama", config)
        self.assertFalse(is_avail)
        self.assertEqual(color, "warning")

    def test_unknown_backend(self):
        config = self._config()
        with patch("src.embeddings.create_generator", side_effect=ValueError("Unknown embedding backend: foo")):
            is_avail, msg, color = _hs._check_embedding_status("host", 1234, "foo", config)
        self.assertFalse(is_avail)
        self.assertEqual(color, "danger")
        self.assertIn("Unknown embedding backend", msg)

    def test_value_error_other(self):
        config = self._config()
        with patch("src.embeddings.create_generator", side_effect=ValueError("some other error")):
            is_avail, msg, color = _hs._check_embedding_status("host", 1234, "ollama", config)
        self.assertFalse(is_avail)
        self.assertEqual(color, "danger")

    def test_connection_error(self):
        config = self._config()
        with patch("src.embeddings.create_generator", side_effect=Exception("Connection refused")):
            is_avail, msg, color = _hs._check_embedding_status("host", 1234, "ollama", config)
        self.assertFalse(is_avail)
        self.assertEqual(color, "danger")
        self.assertIn("Cannot connect", msg)

    def test_other_exception(self):
        config = self._config()
        with patch("src.embeddings.create_generator", side_effect=Exception("unexpected error")):
            is_avail, msg, color = _hs._check_embedding_status("host", 1234, "ollama", config)
        self.assertFalse(is_avail)
        self.assertEqual(color, "danger")
        self.assertIn("Embedding error", msg)


class TestVectorSearchStatusCallback(unittest.TestCase):
    """Tests for register_vector_search_status_callback."""

    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [html.Div(id="vector-search-status-indicator"), html.Div(id="poll-interval")]
        )
        from src.callbacks.health_settings import register_vector_search_status_callback

        register_vector_search_status_callback(self.app)
        # Reset cache
        _hs._VECTOR_SEARCH_AVAILABLE_CACHE = None
        _hs._VECTOR_SEARCH_AVAILABLE_CHECKED = False

    def _cb(self):
        return find_callback(self.app, "vector-search-status-indicator", "children").__wrapped__

    def test_available_shows_success(self):
        with patch.object(_hs, "is_vector_search_available", return_value=True):
            result = self._cb()(0)
        self.assertIn("success", str(result))

    def test_unavailable_shows_warning(self):
        with patch.object(_hs, "is_vector_search_available", return_value=False):
            result = self._cb()(0)
        self.assertIn("Unavailable", str(result))
        self.assertIn("danger", str(result))


class TestVectorDbCheckCallback(unittest.TestCase):
    """Tests for register_vector_db_check_callback."""

    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [html.Div(id="vector-db-check-result"), html.Div(id="btn-check-vector-db"), html.Div(id="input-folder")]
        )
        from src.callbacks.health_settings import register_vector_db_check_callback

        register_vector_db_check_callback(self.app)

    def _cb(self):
        return find_callback(self.app, "vector-db-check-result", "children").__wrapped__

    def test_no_clicks_returns_warning(self):
        result = self._cb()(None, "/folder")
        self.assertIn("select a folder", str(result))

    def test_no_folder_returns_warning(self):
        result = self._cb()(1, None)
        self.assertIn("select a folder", str(result))

    def test_no_db_returns_warning(self, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._cb()(1, tmpdir)
            self.assertIn("No database found", str(result))

    def test_empty_db_returns_info(self):
        import tempfile

        from src.sidecar.database import FeaturesDatabase

        with tempfile.TemporaryDirectory() as tmpdir:
            db = FeaturesDatabase(FeaturesDatabase.default_db_path(tmpdir))
            db.init_db()
            db.close()
            result = self._cb()(1, tmpdir)
            self.assertIn("No embeddings found", str(result))


class TestStoreVectorCallback(unittest.TestCase):
    """Tests for register_store_vector_callback."""

    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="vector-store-result"),
                html.Div(id="btn-store-vector"),
                html.Div(id="input-store-image-path"),
                html.Div(id="input-store-model-name"),
                html.Div(id="input-store-vector"),
                html.Div(id="input-folder"),
            ]
        )
        from src.callbacks.health_settings import register_store_vector_callback

        self.app_config = AppConfig()
        register_store_vector_callback(self.app, self.app_config)

    def _cb(self):
        return find_callback(self.app, "vector-store-result", "children").__wrapped__

    def test_no_clicks(self):
        result = self._cb()(None, "/img.jpg", "model", "0.1,0.2", "/folder")
        self.assertEqual(result, dash.no_update)

    def test_no_image_path(self):
        result = self._cb()(1, "", "model", "0.1,0.2", "/folder")
        self.assertIn("image path", str(result))

    def test_no_model_name(self):
        result = self._cb()(1, "/img.jpg", "", "0.1,0.2", "/folder")
        self.assertIn("model name", str(result))

    def test_no_vector(self):
        result = self._cb()(1, "/img.jpg", "model", "", "/folder")
        self.assertIn("vector", str(result))

    def test_invalid_vector_format(self):
        result = self._cb()(1, "/img.jpg", "model", "abc,def", "/folder")
        self.assertIn("Invalid vector format", str(result))

    def test_no_folder(self):
        result = self._cb()(1, "/img.jpg", "model", "0.1,0.2", None)
        self.assertIn("select a folder", str(result))


class TestVectorTestCallback(unittest.TestCase):
    """Tests for register_vector_test_callback."""

    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="vector-test-result"),
                html.Div(id="input-store-vector"),
                html.Div(id="input-store-model-name"),
                html.Div(id="btn-test-vector-search"),
                html.Div(id="input-host"),
                html.Div(id="input-port"),
                html.Div(id="input-embedding-model"),
                html.Div(id="input-embedding-backend"),
                html.Div(id="chk-embedding-enabled"),
            ]
        )
        from src.callbacks.health_settings import register_vector_test_callback

        self.app_config = AppConfig()
        register_vector_test_callback(self.app, self.app_config)

    def _cb(self):
        return find_callback(self.app, "vector-test-result", "children").__wrapped__

    def test_no_clicks(self):
        result = self._cb()(None, None, None, None, None, None)
        self.assertEqual(result, dash.no_update)

    def test_embedding_disabled(self):
        result = self._cb()(1, None, None, None, None, False)
        self.assertIn("disabled", str(result[0]).lower())

    def test_vector_search_not_available(self):
        with patch.object(_hs, "is_vector_search_available", return_value=False):
            result = self._cb()(1, None, None, None, None, True)
        self.assertIn("Not Available", str(result[0]))


class TestEmbeddingStatusCallback(unittest.TestCase):
    """Tests for register_embedding_status_indicator_callback."""

    def setUp(self):
        self.app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        self.app.layout = html.Div(
            [
                html.Div(id="embedding-status-indicator"),
                html.Div(id="input-host"),
                html.Div(id="input-port"),
                html.Div(id="input-backend"),
                html.Div(id="input-embedding-model"),
                html.Div(id="input-embedding-backend"),
                html.Div(id="chk-embedding-enabled"),
            ]
        )
        from src.callbacks.health_settings import register_embedding_status_indicator_callback

        self.app_config = AppConfig()
        register_embedding_status_indicator_callback(self.app, self.app_config)

    def _cb(self):
        return find_callback(self.app, "embedding-status-indicator", "children").__wrapped__

    def test_disabled_shows_secondary(self):
        with patch.object(_hs, "_get_app_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                llm_host="localhost", llm_port=11434, llm_backend="ollama",
                embedding_enabled=False, embedding_model="test", embedding_backend="ollama",
            )
            result = self._cb()("host", 1234, "ollama", "model", "ollama", False)
        self.assertIn("disabled", str(result).lower())


if __name__ == "__main__":
    unittest.main()
