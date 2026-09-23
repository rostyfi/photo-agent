"""Tests for src/api/debug.py — diagnostic vector self-test endpoints."""

import json
from unittest.mock import patch

import pytest
from flask import Flask

from src.config import AppConfig
from src.api.debug import register_debug_blueprint


@pytest.fixture()
def client(tmp_path):
    """Create a Flask app with the debug blueprint registered."""
    app = Flask(__name__)
    config = AppConfig(
        llm_host="localhost",
        llm_port=11434,
        llm_model="test",
        embedding_model="test-model",
    )
    register_debug_blueprint(app, config)
    app.config["TESTING"] = True
    return app.test_client()


class TestStoreVector:
    def test_store_and_retrieve(self, client):
        """The store_vector endpoint stores and retrieves a 768-dim vector."""
        resp = client.get("/_api/test_store_vector")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["dimension"] == 768
        assert "vec_initialized" in data

    def test_store_vector_handles_error(self, client):
        """The endpoint returns an error if the DB layer raises."""
        with patch("src.api.debug.FeaturesDatabase") as mock_fdb:
            mock_fdb.default_db_path.return_value = "/tmp/test.db"
            instance = mock_fdb.return_value
            instance.init_db.side_effect = Exception("DB error")
            resp = client.get("/_api/test_store_vector")
        data = resp.get_json()
        assert resp.status_code == 500
        assert data["status"] == "error"


class TestVectorRoundtrip:
    def test_roundtrip_success(self, client):
        """Full write/read/verify roundtrip succeeds."""
        resp = client.get("/_api/test_vector_roundtrip")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["original_dimension"] == 768
        assert data["retrieved_dimension"] == 768
        assert data["values_match"] is True

    def test_roundtrip_handles_error(self, client):
        """The endpoint returns an error if the DB layer raises."""
        with patch("src.api.debug.FeaturesDatabase") as mock_fdb:
            mock_fdb.default_db_path.return_value = "/tmp/test.db"
            instance = mock_fdb.return_value
            instance.init_db.side_effect = Exception("DB error")
            resp = client.get("/_api/test_vector_roundtrip")
        data = resp.get_json()
        assert resp.status_code == 500
        assert data["status"] == "error"


class TestRestVectorSearch:
    def test_rest_search_success(self, client):
        """REST vector search endpoint returns a valid response structure."""
        resp = client.get("/_api/test_rest_vector_search")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["rest_vector_search_available"] is True
        assert "test_results" in data
        assert "found_results" in data["test_results"]
        assert "test_passed" in data["test_results"]
        assert "top_results" in data["test_results"]

    def test_rest_search_handles_error(self, client):
        """The endpoint returns an error if the DB layer raises."""
        with patch("src.api.debug.FeaturesDatabase") as mock_fdb:
            mock_fdb.default_db_path.return_value = "/tmp/test.db"
            instance = mock_fdb.return_value
            instance.init_db.side_effect = Exception("DB error")
            resp = client.get("/_api/test_rest_vector_search")
        data = resp.get_json()
        assert resp.status_code == 500
        assert data["status"] == "error"
        assert data["rest_vector_search_available"] is False
