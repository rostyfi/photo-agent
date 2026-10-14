"""Tests for vector search functionality.

sqlite-vec is a HARD REQUIREMENT for vector search functionality.
These tests verify that vector operations work correctly with sqlite-vec.
"""

import os
import struct
import tempfile
from pathlib import Path

import pytest

from src.sidecar.database import FeaturesDatabase


class TestVectorDatabase:
    """Tests for vector embedding database operations."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_features.db"
            db = FeaturesDatabase(db_path)
            yield db
            db.close()

    def test_database_creation(self, temp_db):
        """Test that database is created successfully."""
        conn = temp_db.init_db()
        assert conn is not None
        conn.close()

    def test_image_embeddings_table_created(self, temp_db):
        """Test that image_embeddings table is created."""
        conn = temp_db.init_db()
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_embeddings'")
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "image_embeddings"
        finally:
            conn.close()

    def test_vec_extension_check(self, temp_db):
        """Test that sqlite-vec requirement is enforced."""
        # This test will pass if sqlite-vec is available
        # If sqlite-vec is not available, it will raise RuntimeError
        try:
            temp_db.init_vector_search()
            # If we get here, sqlite-vec is available
            assert True
        except RuntimeError as e:
            # sqlite-vec is not available - this is expected on some systems
            assert "sqlite-vec" in str(e) or "vec" in str(e).lower()
            assert "HARD REQUIREMENT" in str(e)

    def test_vector_to_blob_conversion(self, temp_db):
        """Test vector to BLOB conversion."""
        vector = [1.0, 2.0, 3.0]
        blob = FeaturesDatabase.vector_to_blob(vector)

        # Each float is 4 bytes
        assert len(blob) == len(vector) * 4

        # Convert back and verify
        converted = FeaturesDatabase.blob_to_vector(blob, len(vector))
        assert len(converted) == len(vector)
        for i, val in enumerate(vector):
            assert abs(converted[i] - val) < 1e-6

    def test_save_and_retrieve_embedding(self, temp_db):
        """Test saving and retrieving an embedding."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        image_path = "/test/image.jpg"
        model_name = "test-model"
        vector = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Save embedding
        temp_db.save_embedding(image_path, model_name, vector)

        # Retrieve embedding
        retrieved = temp_db.get_embedding(image_path, model_name)
        assert retrieved is not None
        assert len(retrieved) == len(vector)
        for i in range(len(vector)):
            assert abs(retrieved[i] - vector[i]) < 1e-6

    def test_has_embedding(self, temp_db):
        """Test checking if an embedding exists."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        image_path = "/test/image.jpg"
        model_name = "test-model"
        vector = [0.1, 0.2, 0.3]

        # Initially should not have embedding
        assert temp_db.has_embedding(image_path, model_name) is False

        # Save embedding
        temp_db.save_embedding(image_path, model_name, vector)

        # Now should have embedding
        assert temp_db.has_embedding(image_path, model_name) is True

    def test_find_similar_basic(self, temp_db):
        """Test basic similarity search."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        # Create some test vectors
        # Vector A
        vector_a = [1.0, 0.0, 0.0, 0.0]
        # Vector B - similar to A
        vector_b = [0.9, 0.1, 0.0, 0.0]
        # Vector C - different from A
        vector_c = [0.0, 0.0, 1.0, 0.0]

        temp_db.save_embedding("/test/a.jpg", "test-model", vector_a)
        temp_db.save_embedding("/test/b.jpg", "test-model", vector_b)
        temp_db.save_embedding("/test/c.jpg", "test-model", vector_c)

        # Search for similar to A
        results = temp_db.find_similar(vector_a, limit=3)

        # Should return at least 2 results (A itself and B)
        assert len(results) >= 2

        # First result should be A itself (100% similarity)
        assert results[0][1] >= 0.99  # Should be very close to 1.0

        # A and B should be more similar than A and C
        # Find positions of B and C in results
        b_score = None
        c_score = None
        for path, score in results:
            if path == "/test/b.jpg":
                b_score = score
            if path == "/test/c.jpg":
                c_score = score

        # B should have higher similarity to A than C
        if b_score is not None and c_score is not None:
            assert b_score > c_score

    def test_find_similar_empty_database(self, temp_db):
        """Test similarity search on empty database."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        vector = [0.1, 0.2, 0.3]
        results = temp_db.find_similar(vector, limit=10)
        assert results == []

    def test_find_similar_invalid_vector(self, temp_db):
        """Test similarity search with invalid vector."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        with pytest.raises(ValueError):
            temp_db.find_similar([], limit=10)

    def test_get_all_embeddings(self, temp_db):
        """Test getting all embeddings for a model."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        model_name = "test-model"
        vectors = [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ]

        for i, vector in enumerate(vectors):
            temp_db.save_embedding(f"/test/image{i}.jpg", model_name, vector)

        all_embeddings = temp_db.get_all_embeddings(model_name)
        assert len(all_embeddings) == 3

        for i, (image_path, vector) in enumerate(all_embeddings):
            assert image_path == f"/test/image{i}.jpg"
            assert len(vector) == 3

    def test_unique_constraint(self, temp_db):
        """Test that UNIQUE constraint on (image_path, model_name) works."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        image_path = "/test/image.jpg"
        model_name = "test-model"
        vector1 = [0.1, 0.2, 0.3]
        vector2 = [0.4, 0.5, 0.6]

        # Save first embedding
        temp_db.save_embedding(image_path, model_name, vector1)

        # Save second embedding with same image_path and model_name
        # This should update the existing record
        temp_db.save_embedding(image_path, model_name, vector2)

        # Should still have only one embedding for this image/model
        retrieved = temp_db.get_embedding(image_path, model_name)
        assert retrieved is not None
        assert len(retrieved) == len(vector2)

    def test_different_models_same_image(self, temp_db):
        """Test storing embeddings from different models for the same image."""
        try:
            temp_db.init_vector_search()
        except RuntimeError:
            pytest.skip("sqlite-vec not available")

        image_path = "/test/image.jpg"
        model1 = "model-1"
        model2 = "model-2"
        vector1 = [0.1, 0.2, 0.3]
        vector2 = [0.4, 0.5, 0.6, 0.7]  # Different dimension

        # Save embeddings from different models
        temp_db.save_embedding(image_path, model1, vector1)
        temp_db.save_embedding(image_path, model2, vector2)

        # Both should exist
        assert temp_db.has_embedding(image_path, model1) is True
        assert temp_db.has_embedding(image_path, model2) is True

        # Should be able to retrieve both
        emb1 = temp_db.get_embedding(image_path, model1)
        emb2 = temp_db.get_embedding(image_path, model2)
        assert emb1 is not None
        assert emb2 is not None
        assert len(emb1) == 3
        assert len(emb2) == 4


class TestRestSearchModelHandling:
    """Tests for find_similar_rest model filtering and dimension handling."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing (no sqlite-vec needed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = FeaturesDatabase(Path(tmpdir) / "test_features.db")
            yield db
            db.close()

    def test_find_similar_rest_no_model_returns_all_models(self, temp_db):
        """model_name=None means "no filter": embeddings from all models are searched."""
        temp_db.save_embedding("/a.jpg", "model-a", [1.0, 0.0, 0.0])
        temp_db.save_embedding("/b.jpg", "model-b", [0.0, 1.0, 0.0])

        results = temp_db.find_similar_rest([1.0, 0.0, 0.0], None, limit=10)
        assert {p for p, _ in results} == {"/a.jpg", "/b.jpg"}

    def test_find_similar_rest_skips_dimension_mismatch(self, temp_db):
        """Stored vectors whose dimension differs from the query are skipped,
        not silently truncated to a misaligned prefix."""
        temp_db.save_embedding("/same_dim.jpg", "m", [1.0, 0.0])
        temp_db.save_embedding("/other_dim.jpg", "m", [1.0, 0.0, 0.0, 0.0, 0.0])

        results = temp_db.find_similar_rest([1.0, 0.0], "m", limit=10)
        assert {p for p, _ in results} == {"/same_dim.jpg"}

    def test_get_all_embeddings_without_model_returns_all(self, temp_db):
        """get_all_embeddings(None) returns embeddings for every model."""
        temp_db.save_embedding("/a.jpg", "model-a", [0.1, 0.2])
        temp_db.save_embedding("/a.jpg", "model-b", [0.3, 0.4])

        assert len(temp_db.get_all_embeddings(None)) == 2
        assert len(temp_db.get_all_embeddings("model-a")) == 1


class TestVecTableModelColumn:
    """Tests for the model_name column in the vec_embeddings virtual table."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with vector search initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = FeaturesDatabase(Path(tmpdir) / "test_features.db")
            try:
                db.init_vector_search()
            except RuntimeError:
                pytest.skip("sqlite-vec not available")
            yield db
            db.close()

    def test_vec_search_can_filter_by_model(self, temp_db):
        """Rows are tagged with their model and vec search can filter by it."""
        temp_db.save_embedding("/test/a.jpg", "model-a", [1.0, 0.0, 0.0])
        temp_db.save_embedding("/test/b.jpg", "model-b", [0.0, 1.0, 0.0])

        with temp_db.get_connection() as conn:
            temp_db._ensure_extension_loaded(conn)
            assert temp_db._vec_table_has_model_column(conn)

            all_results = temp_db.vec_find_similar(conn, [1.0, 0.0, 0.0], limit=10)
            assert {p for p, _ in all_results} == {"/test/a.jpg", "/test/b.jpg"}

            filtered = temp_db.vec_find_similar(conn, [1.0, 0.0, 0.0], limit=10, model_name="model-a")
            assert [p for p, _ in filtered] == ["/test/a.jpg"]

        # find_similar passes the model filter through
        results = temp_db.find_similar([1.0, 0.0, 0.0], limit=10, model_name="model-b")
        assert [p for p, _ in results] == ["/test/b.jpg"]

    def test_vec_table_keeps_one_row_per_image_across_models(self, temp_db):
        """Saving a second model for the same image replaces the old row."""
        temp_db.save_embedding("/test/a.jpg", "model-a", [1.0, 0.0, 0.0])
        temp_db.save_embedding("/test/a.jpg", "model-b", [0.0, 1.0, 0.0])

        with temp_db.get_connection() as conn:
            temp_db._ensure_extension_loaded(conn)
            rows = conn.execute("SELECT image_path, model_name FROM vec_embeddings").fetchall()
            assert rows == [("/test/a.jpg", "model-b")]

    def test_save_to_vec_table_legacy_schema(self, temp_db):
        """Tables created before the model column existed still accept writes
        and ignore the model filter."""
        with temp_db.get_connection() as conn:
            temp_db._ensure_extension_loaded(conn)
            conn.execute("DROP TABLE vec_embeddings")
            conn.execute("CREATE VIRTUAL TABLE vec_embeddings USING vec0(image_path TEXT, embedding float[2048])")
            conn.commit()

            assert not temp_db._vec_table_has_model_column(conn)
            assert temp_db.save_to_vec_table(conn, "/test/legacy.jpg", [1.0, 0.0, 0.0], model_name="model-a")

            results = temp_db.vec_find_similar(conn, [1.0, 0.0, 0.0], limit=10, model_name="model-a")
            assert [p for p, _ in results] == ["/test/legacy.jpg"]
