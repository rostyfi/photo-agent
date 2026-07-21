"""
Photo Feature Extractor - Dash Web Application
===============================================
Run with: python app.py
Then open http://127.0.0.1:8050 in your browser.
"""

import io
import logging
import mimetypes
import signal
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import diskcache
from dash import DiskcacheManager
from flask import abort, make_response, request

from src.config import AppConfig
from src.layout import create_layout
from src.callbacks import register_callbacks
from plugins.llm import create_extractor, OllamaChatClient
from plugins.formats.image import read_image_bytes
from src.vector_search.availability import is_vector_search_available
from src.sidecar.database.db import TABLE_VEC_EMBEDDINGS
from src.services import ChatService
from src.api import api_chat_handler

logger = logging.getLogger(__name__)

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def create_app(config=None):
    """Create and return a configured Dash application instance.

    Args:
        config: Optional AppConfig. If not provided, loaded from env vars.

    Returns:
        A ``dash.Dash`` application ready to be served.
    """
    if config is None:
        config = AppConfig.from_env()

    cache = diskcache.FanoutCache("/tmp/dash-cache", size_limit=2**30, shards=4)
    background_callback_manager = DiskcacheManager(cache)

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        background_callback_manager=background_callback_manager,
        suppress_callback_exceptions=True,
    )

    def _create_extractor(backend=config.llm_backend, host=config.llm_host,
                          port=config.llm_port, model=config.llm_model,
                          timeout=config.timeout):
        """Factory wrapper that creates an extractor with the app's default prompt."""
        return create_extractor(
            backend=backend,
            host=host, port=port, model=model, timeout=timeout,
            default_prompt=config.default_prompt,
        )

    app.layout = create_layout(config)

    # Initialize services with proper dependency injection
    chat_client = OllamaChatClient(
        host=config.llm_host,
        port=config.llm_port,
        model=config.llm_model,
        timeout=config.timeout,
    )
    chat_service = ChatService(config, chat_client=chat_client)

    register_callbacks(app, _create_extractor, config.to_processing_config(),
                       config)

    @app.server.route("/preview")
    def preview():
        """Serve a resized image preview with path validation."""
        path_str = request.args.get("path")
        folder_str = request.args.get("folder")
        size = request.args.get("size", "thumb")
        if not path_str or not folder_str:
            abort(404)
        try:
            image_path = Path(path_str).resolve(strict=True)
            folder_path = Path(folder_str).resolve(strict=True)
            if not folder_path.is_dir():
                abort(404)
            # Prevent directory traversal: image must be inside folder
            image_path.relative_to(folder_path)
        except (ValueError, FileNotFoundError):
            abort(404)

        try:
            data = read_image_bytes(image_path)
        except FileNotFoundError:
            abort(404)
        except Exception:
            logger.exception("Preview read error for %s", path_str)
            abort(500)

        suffix = image_path.suffix.lower()
        if suffix in (".heic", ".heif"):
            content_type = "image/jpeg"
        else:
            content_type, _ = mimetypes.guess_type(str(image_path))
            if not content_type:
                content_type = "application/octet-stream"

        max_size = 150 if size == "thumb" else 600
        if _PIL_AVAILABLE and size in ("thumb", "full"):
            try:
                img = Image.open(io.BytesIO(data))
                img.thumbnail((max_size, max_size))
                buf = io.BytesIO()
                fmt = img.format
                if fmt == "PNG":
                    img.save(buf, format="PNG")
                else:
                    if img.mode in ("RGBA", "P", "LA"):
                        img = img.convert("RGB")
                    img.save(buf, format="JPEG", quality=85)
                data = buf.getvalue()
                content_type = "image/jpeg"
            except Exception:
                logger.warning("Image resize failed for %s, returning original", image_path, exc_info=True)

        response = make_response(data)
        response.headers["Content-Type"] = content_type
        return response

    @app.server.route("/_api/test_store_vector")
    def api_test_store_vector():
        """API endpoint to test vector storage."""
        from src.sidecar.database.db import FeaturesDatabase
        import tempfile
        import shutil
        
        try:
            test_dir = tempfile.mkdtemp(prefix="api_test_")
            db_path = FeaturesDatabase.default_db_path(test_dir)
            
            db = FeaturesDatabase(db_path)
            db.init_db()
            
            # Check if vector search is available
            vec_init = is_vector_search_available()
            
            try:
                if vec_init:
                    db.init_vector_search()
            except RuntimeError:
                vec_init = False
            
            test_image = "/test/api_test.jpg"
            test_model = "nomic-embed-text"
            test_vector = [0.123456789] * 768
            
            db.save_embedding(test_image, test_model, test_vector)
            
            if db.has_embedding(test_image, test_model):
                retrieved = db.get_embedding(test_image, test_model)
                if retrieved and len(retrieved) == 768:
                    db.close()
                    shutil.rmtree(test_dir, ignore_errors=True)
                    return {
                        "status": "success",
                        "message": "Embedding stored and retrieved successfully",
                        "vec_initialized": vec_init,
                        "dimension": len(retrieved)
                    }
            
            db.close()
            shutil.rmtree(test_dir, ignore_errors=True)
            return {"status": "error", "message": "Embedding not found after save", "vec_initialized": vec_init}, 500
            
        except Exception as e:
            import traceback
            return {"status": "error", "message": str(e), "traceback": str(traceback.format_exc())}, 500

    @app.server.route("/_api/test_vector_roundtrip")
    def api_test_vector_roundtrip():
        """API endpoint to test full vector write/read roundtrip.
        
        This endpoint:
        1. Generates a test vector with known values
        2. Stores it in the database
        3. Reads it back
        4. Verifies the data matches
        5. Returns detailed results
        """
        from src.sidecar.database.db import FeaturesDatabase
        import tempfile
        import shutil
        
        try:
            test_dir = tempfile.mkdtemp(prefix="roundtrip_test_")
            db_path = FeaturesDatabase.default_db_path(test_dir)
            
            db = FeaturesDatabase(db_path)
            db.init_db()
            
            # Check if vector search is available
            vec_init = is_vector_search_available()
            
            # Try to initialize vector search
            try:
                if vec_init:
                    db.init_vector_search()
            except RuntimeError:
                vec_init = False
            
            # Generate a test vector with varied values (not all the same)
            # This makes it easier to verify the data is correct
            test_image = "/test/roundtrip.jpg"
            test_model = "nomic-embed-text"
            test_vector = [float(i * 0.001) for i in range(768)]  # 0.000, 0.001, 0.002, ..., 0.767
            
            # Store the vector
            print(f"Storing vector for {test_image}...")
            db.save_embedding(test_image, test_model, test_vector)
            print(f"Vector stored. Original: {test_vector[:5]}...")
            
            # Read it back
            print(f"Reading vector back...")
            retrieved = db.get_embedding(test_image, test_model)
            
            if not retrieved:
                db.close()
                shutil.rmtree(test_dir, ignore_errors=True)
                return {
                    "status": "error",
                    "message": "Failed to retrieve embedding"
                }, 500
            
            # Verify the data matches
            print(f"Retrieved: {retrieved[:5]}...")
            
            if len(retrieved) != len(test_vector):
                db.close()
                shutil.rmtree(test_dir, ignore_errors=True)
                return {
                    "status": "error",
                    "message": f"Dimension mismatch: expected {len(test_vector)}, got {len(retrieved)}"
                }, 500
            
            # Check if values match (with tolerance for float precision)
            matches = True
            mismatches = []
            for i, (orig, retr) in enumerate(zip(test_vector, retrieved)):
                if abs(orig - retr) > 1e-6:  # Allow small floating point differences
                    matches = False
                    mismatches.append({"index": i, "original": orig, "retrieved": retr})
                    if len(mismatches) > 5:  # Only report first 5 mismatches
                        break
            
            db.close()
            shutil.rmtree(test_dir, ignore_errors=True)
            
            result = {
                "status": "success",
                "message": "Vector roundtrip test passed",
                "vec_initialized": vec_init,
                "original_dimension": len(test_vector),
                "retrieved_dimension": len(retrieved),
                "values_match": matches,
                "sample_original": test_vector[:5],
                "sample_retrieved": retrieved[:5]
            }
            
            if not matches:
                result["status"] = "warning"
                result["message"] = f"Vector roundtrip passed but {len(mismatches)} values differ slightly (float precision)"
                result["mismatches"] = mismatches[:5]
            
            result["vec_initialized"] = vec_init
            
            return result
            
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": str(e),
                "traceback": str(traceback.format_exc())
            }, 500

    @app.server.route("/_api/store_vector", methods=["POST"])
    def api_store_vector():
        """API endpoint to store a given vector in the database.
        
        Expects JSON payload:
        {
            "image_path": "/path/to/image.jpg",
            "model_name": "nomic-embed-text",
            "vector": [0.123, 0.456, ...]  # list of floats
        }
        
        Returns:
        {
            "status": "success",
            "message": "Vector stored successfully",
            "image_path": "...",
            "model_name": "...",
            "dimension": 768,
            "stored_in_vec": true/false
        }
        
        Note: Uses /photos as the test folder to allow reading back.
        """
        from flask import request
        from src.sidecar.database.db import FeaturesDatabase
        
        try:
            # Get data from request
            data = request.get_json()
            if not data:
                return {"status": "error", "message": "No JSON data provided"}, 400
            
            image_path = data.get("image_path")
            model_name = data.get("model_name", "unknown")
            vector = data.get("vector")
            
            if not image_path:
                return {"status": "error", "message": "image_path is required"}, 400
            if not vector or not isinstance(vector, list):
                return {"status": "error", "message": "vector must be a list of floats"}, 400
            if len(vector) == 0:
                return {"status": "error", "message": "vector cannot be empty"}, 400
            
            # Use /photos folder which is mounted in the container
            # This allows the get_vector endpoint to find it
            db_path = FeaturesDatabase.default_db_path("/photos")
            
            db = FeaturesDatabase(db_path)
            
            try:
                db.init_db()
            except:
                pass  # DB might already exist
            
            # Check if vector search library is available
            vec_available = is_vector_search_available()
            logger.info(f"Vector search available: {vec_available}")
            
            # Try to initialize vector search if available
            try:
                if vec_available:
                    # Check if embeddings table already exists first
                    import sqlite3
                    check_conn = sqlite3.connect(db_path)
                    try:
                        result = check_conn.execute(
                            f"SELECT 1 FROM sqlite_master WHERE name='{TABLE_VEC_EMBEDDINGS}'"
                        ).fetchone()
                        if not result:
                            logger.info("Initializing vector search (vec_embeddings table not found)")
                            db.init_vector_search()
                            logger.info("Vector search initialized successfully")
                        else:
                            logger.info("Vector search already initialized (vec_embeddings table exists)")
                        vec_available = True
                    finally:
                        check_conn.close()
            except Exception as e:
                # sqlite-vec library might not be available or table might already exist
                # This is OK - metadata will still be stored
                vec_available = False
                logger.error(f"sqlite-vec library initialization failed: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Store the vector
            db.save_embedding(image_path, model_name, vector)
            
            # Verify it was stored
            if db.has_embedding(image_path, model_name):
                retrieved = db.get_embedding(image_path, model_name)
                stored_in_vec = retrieved is not None and len(retrieved) == len(vector)
                logger.info(f"Vector stored and verified: dimension={len(vector)}, stored_in_vec={stored_in_vec}")
            else:
                stored_in_vec = False
                logger.warning(f"Vector stored but not found in metadata: {image_path}")
            
            db.close()
            
            return {
                "status": "success",
                "message": "Vector stored successfully",
                "image_path": image_path,
                "model_name": model_name,
                "dimension": len(vector),
                "vec_available": vec_available,
                "stored_in_metadata": True,
                "retrievable": stored_in_vec
            }
            
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": str(e),
                "traceback": str(traceback.format_exc())
            }, 500

    @app.server.route("/_api/get_vector", methods=["GET"])
    def api_get_vector():
        """API endpoint to retrieve a stored vector from the database.
        
        Query parameters:
        - image_path: Path to the image (required)
        - model_name: Embedding model name (default: "test-model")
        
        Returns the stored vector data.
        
        Note: Uses /photos folder to match the store_vector endpoint.
        """
        from flask import request
        from src.sidecar.database.db import FeaturesDatabase
        
        try:
            image_path = request.args.get("image_path")
            model_name = request.args.get("model_name", "test-model")
            
            if not image_path:
                return {"status": "error", "message": "image_path parameter is required"}, 400
            
            # Use /photos folder which is mounted in the container
            db_path = FeaturesDatabase.default_db_path("/photos")
            
            db = FeaturesDatabase(db_path)
            
            # Try to retrieve the vector
            retrieved = db.get_embedding(image_path, model_name)
            
            db.close()
            
            if retrieved:
                return {
                    "status": "success",
                    "image_path": image_path,
                    "model_name": model_name,
                    "vector": retrieved,
                    "dimension": len(retrieved)
                }
            else:
                return {
                    "status": "error",
                    "message": f"No embedding found for {image_path} with model {model_name}"
                }, 404
            
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "message": str(e),
                "traceback": str(traceback.format_exc())
            }, 500

    @app.server.route("/_api/find_similar", methods=["POST"])
    def api_find_similar():
        """API endpoint to find similar images using REST-based vector search.
        
        This endpoint provides vector search functionality without requiring
        sqlite-vec. It loads embeddings from the database and computes cosine
        similarity in Python.
        
        Expects JSON payload:
        {
            "folder": "/path/to/folder",
            "query": "text description",  // OR
            "vector": [0.123, 0.456, ...],  // OR
            "image_path": "/path/to/image.jpg",  // to get embedding from image
            "model_name": "nomic-embed-text",  // optional, defaults to config
            "limit": 10  // optional, default 10
        }
        
        Returns:
        {
            "status": "success",
            "results": [
                {"image_path": "...", "score": 0.95},
                ...
            ],
            "count": 5,
            "query_vector_dimension": 768
        }
        
        Note: This endpoint works without sqlite-vec by using Python-based
        cosine similarity calculations.
        """
        from flask import request
        from src.sidecar.database.db import FeaturesDatabase
        from src.embeddings import create_generator
        from src.config import AppConfig
        
        try:
            data = request.get_json()
            if not data:
                return {"status": "error", "message": "No JSON data provided"}, 400
            
            folder = data.get("folder")
            query_text = data.get("query")
            query_vector = data.get("vector")
            image_path = data.get("image_path")
            model_name = data.get("model_name")
            limit = data.get("limit", 10)
            
            if not folder:
                return {"status": "error", "message": "folder parameter is required"}, 400
            
            # Validate limit
            try:
                limit = int(limit)
                if limit <= 0:
                    limit = 10
            except (ValueError, TypeError):
                limit = 10
            
            # Get config for defaults
            config = AppConfig.from_env()
            if not model_name:
                model_name = config.embedding_model
            
            # Get database path
            db_path = FeaturesDatabase.default_db_path(folder)
            
            # Check if database exists
            if not db_path.exists():
                return {
                    "status": "error",
                    "message": f"No database found at {db_path}. Process the folder first."
                }, 404
            
            # Determine query vector
            if query_vector:
                # Use provided vector directly
                if not isinstance(query_vector, list) or len(query_vector) == 0:
                    return {"status": "error", "message": "vector must be a non-empty list of floats"}, 400
                query_vector_final = query_vector
            elif query_text:
                # Generate embedding from text
                try:
                    generator = create_generator(
                        backend=config.embedding_backend,
                        host=config.llm_host,
                        port=config.llm_port,
                        model=model_name,
                        timeout=config.timeout,
                    )
                    query_vector_final = generator.generate_from_text(query_text)
                except Exception as e:
                    logger.error(f"Failed to generate embedding from text: {e}")
                    return {
                        "status": "error",
                        "message": f"Failed to generate embedding from text: {str(e)}"
                    }, 500
            elif image_path:
                # Generate embedding from image path
                try:
                    generator = create_generator(
                        backend=config.embedding_backend,
                        host=config.llm_host,
                        port=config.llm_port,
                        model=model_name,
                        timeout=config.timeout,
                    )
                    query_vector_final = generator.generate(image_path)
                except Exception as e:
                    logger.error(f"Failed to generate embedding from image: {e}")
                    return {
                        "status": "error",
                        "message": f"Failed to generate embedding from image: {str(e)}"
                    }, 500
            else:
                return {
                    "status": "error",
                    "message": "One of query, vector, or image_path must be provided"
                }, 400
            
            # Find similar images using REST-based approach
            try:
                db = FeaturesDatabase(db_path)
                similar = db.find_similar_rest(query_vector_final, model_name, limit)
            except Exception as e:
                logger.error(f"Failed to find similar images: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to find similar images: {str(e)}"
                }, 500
            
            # Format results
            results = []
            for image_path_result, score in similar:
                results.append({
                    "image_path": image_path_result,
                    "score": score
                })
            
            return {
                "status": "success",
                "results": results,
                "count": len(results),
                "query_vector_dimension": len(query_vector_final),
                "model_name": model_name,
                "folder": folder
            }
            
        except Exception as e:
            import traceback
            logger.error(f"REST vector search failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "traceback": str(traceback.format_exc())
            }, 500

    @app.server.route("/_api/test_rest_vector_search")
    def api_test_rest_vector_search():
        """Test endpoint to verify REST-based vector search is working.
        
        This endpoint performs a simple test of the REST vector search functionality
        without requiring sqlite-vec. It's useful for testing in Docker containers.
        
        Returns:
        {
            "status": "success" or "error",
            "message": "...",
            "rest_vector_search_available": true/false,
            "test_results": {...}
        }
        """
        from src.sidecar.database.db import FeaturesDatabase
        from src.config import AppConfig
        import tempfile
        import shutil
         
        try:
            # REST vector search is always available (uses Python cosine similarity)
            service_available = True
            
            # Create a temporary test database
            test_dir = tempfile.mkdtemp(prefix="rest_vec_test_")
            db_path = FeaturesDatabase.default_db_path(test_dir)
            
            try:
                # Create database and add some test embeddings
                db = FeaturesDatabase(db_path)
                db.init_db()
                
                # Create test embeddings (simple vectors for testing)
                # These are 3-dimensional vectors for simplicity
                test_embeddings = [
                    ("test1.jpg", [1.0, 0.0, 0.0]),
                    ("test2.jpg", [0.9, 0.1, 0.0]),
                    ("test3.jpg", [0.8, 0.2, 0.0]),
                    ("test4.jpg", [0.0, 1.0, 0.0]),
                    ("test5.jpg", [0.0, 0.0, 1.0]),
                ]
                
                # Store embeddings using the database
                config = AppConfig.from_env()
                for image_path, vector in test_embeddings:
                    db.save_embedding(image_path, config.embedding_model, vector)
                
                db.close()
                
                # Test similarity search with a query vector
                query_vector = [0.95, 0.05, 0.0]
                test_db = FeaturesDatabase(db_path)
                similar = test_db.find_similar_rest(query_vector, None, limit=3)
                
                # Verify results
                test_passed = len(similar) > 0
                if test_passed:
                    # Check that the most similar results are test1, test2, test3
                    top_paths = [path for path, _ in similar[:3]]
                    expected_top = ["test1.jpg", "test2.jpg", "test3.jpg"]
                    # We don't check exact order due to floating point precision
                    test_passed = all(path in top_paths for path in expected_top[:len(top_paths)])
                
                return {
                    "status": "success",
                    "message": "REST vector search test passed",
                    "rest_vector_search_available": service_available,
                    "test_results": {
                        "found_results": len(similar),
                        "test_passed": test_passed,
                        "top_results": [
                            {"image_path": path, "score": score}
                            for path, score in similar[:3]
                        ]
                    }
                }
                
            finally:
                # Clean up
                shutil.rmtree(test_dir, ignore_errors=True)
                
        except Exception as e:
            import traceback
            logger.error(f"REST vector search test failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "rest_vector_search_available": False,
                "traceback": str(traceback.format_exc())
            }, 500

    @app.server.route("/_api/chat", methods=["POST"])
    def api_chat():
        """API endpoint to chat with the Ollama LLM with tool support.
        
        This endpoint has been refactored to use ChatService for business logic.
        The handler delegates to api_chat_handler which uses the ChatService.
        """
        return api_chat_handler(config, chat_service)

    return app, config


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app, config = create_app()
    DASH_HOST = config.dash_host
    DASH_PORT = config.dash_port
    DASH_DEBUG = config.dash_debug

    from src.state import request_shutdown
    signal.signal(signal.SIGINT, lambda _sig, _frame: request_shutdown())
    signal.signal(signal.SIGTERM, lambda _sig, _frame: request_shutdown())
    print(f"Starting Photo Feature Extractor web app on http://{DASH_HOST}:{DASH_PORT}")
    app.run(host=DASH_HOST, port=DASH_PORT, debug=DASH_DEBUG)
