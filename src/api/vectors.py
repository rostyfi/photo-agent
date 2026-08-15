"""Flask blueprint for the vector storage/search REST API.

Endpoints:
    POST /_api/store_vector  - store a raw embedding vector
    GET  /_api/get_vector    - retrieve a stored embedding
    POST /_api/find_similar  - find similar images via cosine similarity
"""

import logging
import sqlite3

from flask import Blueprint, request

from src.config import AppConfig
from src.sidecar.database.db import FeaturesDatabase, TABLE_VEC_EMBEDDINGS
from src.sqlite_utils import open_connection
from src.vector_search.availability import is_vector_search_available

logger = logging.getLogger(__name__)


def _error(message, status=500, **extra):
    payload = {"status": "error", "message": message}
    payload.update(extra)
    return payload, status


def register_vectors_blueprint(server, config: AppConfig) -> Blueprint:
    """Register the vector API routes on the Flask server.

    Args:
        server: The Flask server (``app.server`` of a Dash app).
        config: Application config used for default folder, embedding model, and host/port.

    Returns:
        The registered :class:`flask.Blueprint`.
    """
    bp = Blueprint("vectors_api", __name__)

    @bp.route("/_api/store_vector", methods=["POST"])
    def store_vector():
        """Store a given vector in the database.

        JSON payload: ``{"image_path": str, "model_name": str, "vector": [float, ...]}``
        """
        data = request.get_json(silent=True)
        if not data:
            return _error("No JSON data provided", 400)

        image_path = data.get("image_path")
        model_name = data.get("model_name", "unknown")
        vector = data.get("vector")

        if not image_path:
            return _error("image_path is required", 400)
        if not vector or not isinstance(vector, list):
            return _error("vector must be a list of floats", 400)
        if len(vector) == 0:
            return _error("vector cannot be empty", 400)

        db_path = FeaturesDatabase.default_db_path(config.folder_path)
        db = FeaturesDatabase(db_path)

        try:
            try:
                db.init_db()
            except sqlite3.OperationalError:
                # DB schema already exists; safe to continue.
                pass

            vec_available = is_vector_search_available()
            logger.info("Vector search available: %s", vec_available)

            if vec_available:
                try:
                    check_conn = open_connection(db_path)
                    try:
                        exists = check_conn.execute(
                            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            (TABLE_VEC_EMBEDDINGS,),
                        ).fetchone()
                    finally:
                        check_conn.close()
                    if not exists:
                        logger.info("Initializing vector search (vec_embeddings table not found)")
                        db.init_vector_search()
                        logger.info("Vector search initialized successfully")
                    else:
                        logger.info("Vector search already initialized (vec_embeddings table exists)")
                except Exception:
                    vec_available = False
                    logger.error("sqlite-vec initialization failed", exc_info=True)

            db.save_embedding(image_path, model_name, vector)

            if db.has_embedding(image_path, model_name):
                retrieved = db.get_embedding(image_path, model_name)
                retrievable = retrieved is not None and len(retrieved) == len(vector)
                logger.info(
                    "Vector stored and verified: dimension=%d, stored_in_vec=%s",
                    len(vector), retrievable,
                )
            else:
                retrievable = False
                logger.warning("Vector stored but not found in metadata: %s", image_path)
        except Exception as e:
            logger.error("store_vector failed: %s", e, exc_info=True)
            return _error(str(e), 500)
        finally:
            db.close()

        return {
            "status": "success",
            "message": "Vector stored successfully",
            "image_path": image_path,
            "model_name": model_name,
            "dimension": len(vector),
            "vec_available": vec_available,
            "stored_in_metadata": True,
            "retrievable": retrievable,
        }

    @bp.route("/_api/get_vector", methods=["GET"])
    def get_vector():
        """Retrieve a stored vector.

        Query params: ``image_path`` (required), ``model_name`` (default "test-model").
        """
        image_path = request.args.get("image_path")
        model_name = request.args.get("model_name", "test-model")

        if not image_path:
            return _error("image_path parameter is required", 400)

        db_path = FeaturesDatabase.default_db_path(config.folder_path)
        db = FeaturesDatabase(db_path)
        try:
            retrieved = db.get_embedding(image_path, model_name)
        except Exception as e:
            logger.error("get_vector failed: %s", e, exc_info=True)
            return _error(str(e), 500)
        finally:
            db.close()

        if retrieved:
            return {
                "status": "success",
                "image_path": image_path,
                "model_name": model_name,
                "vector": retrieved,
                "dimension": len(retrieved),
            }
        return _error(
            "No embedding found for %s with model %s" % (image_path, model_name), 404
        )

    @bp.route("/_api/find_similar", methods=["POST"])
    def find_similar():
        """Find similar images using REST-based (Python cosine) vector search.

        JSON payload: ``{"folder": str, "query": str | "vector": [...] | "image_path": str,
        "model_name": str?, "limit": int?}``
        """
        data = request.get_json(silent=True)
        if not data:
            return _error("No JSON data provided", 400)

        folder = data.get("folder")
        query_text = data.get("query")
        query_vector = data.get("vector")
        image_path = data.get("image_path")
        model_name = data.get("model_name") or config.embedding_model
        limit = data.get("limit", 10)

        if not folder:
            return _error("folder parameter is required", 400)

        try:
            limit = int(limit)
            if limit <= 0:
                limit = 10
        except (ValueError, TypeError):
            limit = 10

        db_path = FeaturesDatabase.default_db_path(folder)
        if not db_path.exists():
            return _error(
                "No database found at %s. Process the folder first." % db_path, 404
            )

        if query_vector:
            if not isinstance(query_vector, list) or len(query_vector) == 0:
                return _error("vector must be a non-empty list of floats", 400)
            query_vector_final = query_vector
        elif query_text:
            try:
                from src.embeddings import create_generator
                generator = create_generator(
                    backend=config.embedding_backend,
                    host=config.llm_host,
                    port=config.llm_port,
                    model=model_name,
                    timeout=config.timeout,
                )
                query_vector_final = generator.generate_from_text(query_text)
            except Exception as e:
                logger.error("Failed to generate embedding from text: %s", e, exc_info=True)
                return _error("Failed to generate embedding from text: %s" % e, 500)
        elif image_path:
            try:
                from src.embeddings import create_generator
                generator = create_generator(
                    backend=config.embedding_backend,
                    host=config.llm_host,
                    port=config.llm_port,
                    model=model_name,
                    timeout=config.timeout,
                )
                query_vector_final = generator.generate(image_path)
            except Exception as e:
                logger.error("Failed to generate embedding from image: %s", e, exc_info=True)
                return _error("Failed to generate embedding from image: %s" % e, 500)
        else:
            return _error("One of query, vector, or image_path must be provided", 400)

        try:
            db = FeaturesDatabase(db_path)
            try:
                similar = db.find_similar_rest(query_vector_final, model_name, limit)
            finally:
                db.close()
        except Exception as e:
            logger.error("Failed to find similar images: %s", e, exc_info=True)
            return _error("Failed to find similar images: %s" % e, 500)

        results = [{"image_path": p, "score": s} for p, s in similar]
        return {
            "status": "success",
            "results": results,
            "count": len(results),
            "query_vector_dimension": len(query_vector_final),
            "model_name": model_name,
            "folder": folder,
        }

    server.register_blueprint(bp)
    return bp
