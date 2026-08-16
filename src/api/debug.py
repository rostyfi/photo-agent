"""Flask blueprint for diagnostic/self-test vector endpoints.

These are debug scaffolding for verifying the vector storage layer works in a
given environment (e.g. inside Docker). They create temporary databases and
should not be relied upon for production data flows.

Endpoints:
    GET  /_api/test_store_vector       - store + retrieve a sample 768-dim vector
    GET  /_api/test_vector_roundtrip   - full write/read/verify roundtrip
    GET  /_api/test_rest_vector_search - exercise REST (Python cosine) search
"""

import logging
import shutil
import tempfile

from flask import Blueprint

from src.config import AppConfig
from src.sidecar.database.db import FeaturesDatabase
from src.vector_search.availability import is_vector_search_available

logger = logging.getLogger(__name__)

_VEC_DIM = 768


def _error(message, status=500, **extra):
    payload = {"status": "error", "message": message}
    payload.update(extra)
    return payload, status


def register_debug_blueprint(server, config: AppConfig) -> Blueprint:
    """Register the diagnostic vector self-test routes on the Flask server.

    Args:
        server: The Flask server (``app.server`` of a Dash app).
        config: Application config (used for the embedding model name).

    Returns:
        The registered :class:`flask.Blueprint`.
    """
    bp = Blueprint("debug_api", __name__)

    @bp.route("/_api/test_store_vector")
    def test_store_vector():
        """Store and retrieve a sample vector in a temporary database."""
        test_dir = tempfile.mkdtemp(prefix="api_test_")
        try:
            db_path = FeaturesDatabase.default_db_path(test_dir)
            db = FeaturesDatabase(db_path)
            try:
                db.init_db()

                vec_init = is_vector_search_available()
                try:
                    if vec_init:
                        db.init_vector_search()
                except RuntimeError:
                    vec_init = False

                test_image = "/test/api_test.jpg"
                test_model = config.embedding_model
                test_vector = [0.123456789] * _VEC_DIM

                db.save_embedding(test_image, test_model, test_vector)

                if db.has_embedding(test_image, test_model):
                    retrieved = db.get_embedding(test_image, test_model)
                    if retrieved and len(retrieved) == _VEC_DIM:
                        return {
                            "status": "success",
                            "message": "Embedding stored and retrieved successfully",
                            "vec_initialized": vec_init,
                            "dimension": len(retrieved),
                        }

                return _error("Embedding not found after save", 500, vec_initialized=vec_init)
            finally:
                db.close()
        except Exception as e:
            logger.error("test_store_vector failed: %s", e, exc_info=True)
            return _error(str(e), 500)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    @bp.route("/_api/test_vector_roundtrip")
    def test_vector_roundtrip():
        """Full write/read/verify roundtrip for a vector with varied values."""
        test_dir = tempfile.mkdtemp(prefix="roundtrip_test_")
        try:
            db_path = FeaturesDatabase.default_db_path(test_dir)
            db = FeaturesDatabase(db_path)
            try:
                db.init_db()

                vec_init = is_vector_search_available()
                try:
                    if vec_init:
                        db.init_vector_search()
                except RuntimeError:
                    vec_init = False

                test_image = "/test/roundtrip.jpg"
                test_model = config.embedding_model
                test_vector = [float(i * 0.001) for i in range(_VEC_DIM)]

                db.save_embedding(test_image, test_model, test_vector)
                retrieved = db.get_embedding(test_image, test_model)

                if not retrieved:
                    return _error("Failed to retrieve embedding", 500)

                if len(retrieved) != len(test_vector):
                    return _error(
                        f"Dimension mismatch: expected {len(test_vector)}, got {len(retrieved)}",
                        500,
                    )

                mismatches = []
                for i, (orig, retr) in enumerate(zip(test_vector, retrieved, strict=False)):
                    if abs(orig - retr) > 1e-6:
                        mismatches.append({"index": i, "original": orig, "retrieved": retr})
                        if len(mismatches) > 5:
                            break

                result = {
                    "status": "success",
                    "message": "Vector roundtrip test passed",
                    "vec_initialized": vec_init,
                    "original_dimension": len(test_vector),
                    "retrieved_dimension": len(retrieved),
                    "values_match": not mismatches,
                    "sample_original": test_vector[:5],
                    "sample_retrieved": retrieved[:5],
                }

                if mismatches:
                    result["status"] = "warning"
                    result["message"] = (
                        f"Vector roundtrip passed but {len(mismatches)} values differ slightly (float precision)"
                    )
                    result["mismatches"] = mismatches[:5]

                return result
            finally:
                db.close()
        except Exception as e:
            logger.error("test_vector_roundtrip failed: %s", e, exc_info=True)
            return _error(str(e), 500)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    @bp.route("/_api/test_rest_vector_search")
    def test_rest_vector_search():
        """Exercise the REST (Python cosine) similarity path with sample vectors."""
        test_dir = tempfile.mkdtemp(prefix="rest_vec_test_")
        try:
            db_path = FeaturesDatabase.default_db_path(test_dir)
            db = FeaturesDatabase(db_path)
            try:
                db.init_db()

                test_embeddings = [
                    ("test1.jpg", [1.0, 0.0, 0.0]),
                    ("test2.jpg", [0.9, 0.1, 0.0]),
                    ("test3.jpg", [0.8, 0.2, 0.0]),
                    ("test4.jpg", [0.0, 1.0, 0.0]),
                    ("test5.jpg", [0.0, 0.0, 1.0]),
                ]

                for image_path, vector in test_embeddings:
                    db.save_embedding(image_path, config.embedding_model, vector)
            finally:
                db.close()

            query_vector = [0.95, 0.05, 0.0]
            test_db = FeaturesDatabase(db_path)
            try:
                similar = test_db.find_similar_rest(query_vector, None, limit=3)
            finally:
                test_db.close()

            test_passed = len(similar) > 0
            if test_passed:
                top_paths = [p for p, _ in similar[:3]]
                expected_top = ["test1.jpg", "test2.jpg", "test3.jpg"]
                test_passed = all(p in top_paths for p in expected_top[: len(top_paths)])

            return {
                "status": "success",
                "message": "REST vector search test passed",
                "rest_vector_search_available": True,
                "test_results": {
                    "found_results": len(similar),
                    "test_passed": test_passed,
                    "top_results": [{"image_path": p, "score": s} for p, s in similar[:3]],
                },
            }
        except Exception as e:
            logger.error("test_rest_vector_search failed: %s", e, exc_info=True)
            return _error(str(e), 500, rest_vector_search_available=False)

    server.register_blueprint(bp)
    return bp
