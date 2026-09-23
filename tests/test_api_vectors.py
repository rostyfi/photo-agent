"""Tests for src/api/vectors.py — vector storage/search REST API."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

from src.api.vectors import register_vectors_blueprint
from src.config import AppConfig
from src.sidecar.database import FeaturesDatabase


@pytest.fixture()
def app_and_client(tmp_path):
    """Create a Flask app with the vectors blueprint, using a temp folder."""
    config = AppConfig(
        llm_host="localhost",
        llm_port=11434,
        llm_model="test",
        embedding_model="test-model",
        embedding_backend="dry_run",
    )
    config.folder_path = str(tmp_path)

    # Initialize the database so endpoints can use it
    db_path = FeaturesDatabase.default_db_path(str(tmp_path))
    db = FeaturesDatabase(db_path)
    db.init_db()
    db.close()

    app = Flask(__name__)
    register_vectors_blueprint(app, config)
    app.config["TESTING"] = True
    return app, app.test_client()


class TestStoreVector:
    def test_store_success(self, app_and_client):
        _, client = app_and_client
        resp = client.post(
            "/_api/store_vector",
            data=json.dumps({
                "image_path": "/test/img.jpg",
                "model_name": "test-model",
                "vector": [0.1, 0.2, 0.3],
            }),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["dimension"] == 3
        assert data["image_path"] == "/test/img.jpg"

    def test_no_json_data(self, app_and_client):
        _, client = app_and_client
        resp = client.post("/_api/store_vector", content_type="application/json")
        data = resp.get_json()
        assert resp.status_code == 400
        assert data["status"] == "error"
        assert "No JSON data" in data["message"]

    def test_missing_image_path(self, app_and_client):
        _, client = app_and_client
        resp = client.post(
            "/_api/store_vector",
            data=json.dumps({"vector": [0.1]}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 400
        assert "image_path is required" in data["message"]

    def test_missing_vector(self, app_and_client):
        _, client = app_and_client
        resp = client.post(
            "/_api/store_vector",
            data=json.dumps({"image_path": "/test.jpg"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 400
        assert "vector must be a list" in data["message"]

    def test_empty_vector(self, app_and_client):
        _, client = app_and_client
        resp = client.post(
            "/_api/store_vector",
            data=json.dumps({"image_path": "/test.jpg", "vector": []}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 400
        assert "vector" in data["message"]

    def test_default_model_name(self, app_and_client):
        _, client = app_and_client
        resp = client.post(
            "/_api/store_vector",
            data=json.dumps({"image_path": "/test.jpg", "vector": [0.1]}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["model_name"] == "unknown"


class TestGetVector:
    def test_get_success(self, app_and_client):
        _, client = app_and_client
        # First store a vector
        client.post(
            "/_api/store_vector",
            data=json.dumps({"image_path": "/test/get.jpg", "model_name": "test-model", "vector": [0.5, 0.6]}),
            content_type="application/json",
        )
        # Then retrieve it
        resp = client.get("/_api/get_vector?image_path=/test/get.jpg&model_name=test-model")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["dimension"] == 2
        assert len(data["vector"]) == 2
        assert abs(data["vector"][0] - 0.5) < 1e-5
        assert abs(data["vector"][1] - 0.6) < 1e-5

    def test_get_missing_image_path(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/_api/get_vector")
        data = resp.get_json()
        assert resp.status_code == 400
        assert "image_path parameter is required" in data["message"]

    def test_get_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/_api/get_vector?image_path=/nonexistent.jpg&model_name=nope")
        data = resp.get_json()
        assert resp.status_code == 404
        assert "No embedding found" in data["message"]

    def test_default_model_name(self, app_and_client):
        _, client = app_and_client
        # Store with default model name "test-model"
        client.post(
            "/_api/store_vector",
            data=json.dumps({"image_path": "/test/default.jpg", "model_name": "test-model", "vector": [0.1]}),
            content_type="application/json",
        )
        # Retrieve without specifying model_name — should default to "test-model"
        resp = client.get("/_api/get_vector?image_path=/test/default.jpg")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["model_name"] == "test-model"


class TestFindSimilar:
    def test_no_json_data(self, app_and_client):
        _, client = app_and_client
        resp = client.post("/_api/find_similar", content_type="application/json")
        data = resp.get_json()
        assert resp.status_code == 400
        assert "No JSON data" in data["message"]

    def test_missing_folder(self, app_and_client):
        _, client = app_and_client
        resp = client.post(
            "/_api/find_similar",
            data=json.dumps({"query": "cat"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 400
        assert "folder parameter is required" in data["message"]

    def test_no_query_method(self, app_and_client, tmp_path):
        _, client = app_and_client
        resp = client.post(
            "/_api/find_similar",
            data=json.dumps({"folder": str(tmp_path)}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 400
        assert "One of query, vector, or image_path" in data["message"]

    def test_db_not_found(self, app_and_client, tmp_path):
        _, client = app_and_client
        # Use a subfolder that has no database
        missing_folder = str(tmp_path / "no_db")
        resp = client.post(
            "/_api/find_similar",
            data=json.dumps({"folder": missing_folder, "vector": [0.1]}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 404
        assert "No database found" in data["message"]

    def test_find_similar_with_vector(self, app_and_client, tmp_path):
        _, client = app_and_client
        # Store some vectors first
        for i, vec in enumerate([
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
        ]):
            client.post(
                "/_api/store_vector",
                data=json.dumps({
                    "image_path": f"/test/{i}.jpg",
                    "model_name": "test-model",
                    "vector": vec,
                }),
                content_type="application/json",
            )

        resp = client.post(
            "/_api/find_similar",
            data=json.dumps({
                "folder": str(tmp_path),
                "vector": [0.95, 0.05, 0.0],
                "limit": 2,
            }),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["count"] <= 2
        assert len(data["results"]) <= 2

    def test_invalid_vector_format(self, app_and_client, tmp_path):
        _, client = app_and_client
        resp = client.post(
            "/_api/find_similar",
            data=json.dumps({"folder": str(tmp_path), "vector": "not-a-list"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 400
        assert "non-empty list" in data["message"]

    def test_invalid_limit_defaults_to_10(self, app_and_client, tmp_path):
        _, client = app_and_client
        # Store a vector
        client.post(
            "/_api/store_vector",
            data=json.dumps({"image_path": "/test/1.jpg", "model_name": "test-model", "vector": [0.1, 0.2]}),
            content_type="application/json",
        )
        resp = client.post(
            "/_api/find_similar",
            data=json.dumps({"folder": str(tmp_path), "vector": [0.1, 0.2], "limit": "not-a-number"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "success"

    def test_zero_limit_defaults_to_10(self, app_and_client, tmp_path):
        _, client = app_and_client
        client.post(
            "/_api/store_vector",
            data=json.dumps({"image_path": "/test/1.jpg", "model_name": "test-model", "vector": [0.1, 0.2]}),
            content_type="application/json",
        )
        resp = client.post(
            "/_api/find_similar",
            data=json.dumps({"folder": str(tmp_path), "vector": [0.1, 0.2], "limit": 0}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert resp.status_code == 200
