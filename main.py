"""
Photo Feature Extractor using Vision Models
======================================================
A simplified application for extracting features from photos
using LLM vision models connected via local network.

Simplified approach:
- Simple sequential processing of images
- Database tracking of processed files
- On consecutive runs: automatically skip already-processed images

Vector embedding support:
- Generate vector embeddings for images using Ollama
- Find similar images using cosine similarity
- Requires vector search library for vector search functionality
- Requires Ollama v0.1.0+ for embedding generation
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

from plugins.llm import create_extractor
from src.config import AppConfig
from src.constants import VEC_REQUIRED
from src.discovery import PhotoList
from src.sequential_processor import process_paths
from src.sidecar.database import FeaturesDatabase
from src.utils import compute_duration_stats
from src.version import __version__

config = AppConfig.from_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parent_dir(p: str) -> str:
    """Return the parent directory of a path, or the path itself if it's already a directory."""
    pp = Path(p).resolve()
    if pp.is_dir():
        return str(pp)
    return str(pp.parent)


def main():
    """CLI entry point for single-image, multi-image, and recursive folder processing."""
    config.validate()
    parser = argparse.ArgumentParser(description="Extract features from photos using a vision model")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("path", nargs="+", help="Path(s) to image file(s) or folder(s)")
    parser.add_argument("--host", default=config.llm_host, help="LLM server host")
    parser.add_argument("--port", type=int, default=config.llm_port, help="LLM server port")
    parser.add_argument("--model", default=config.llm_model, help="LLM vision model")
    parser.add_argument("--backend", default=config.llm_backend, help="LLM backend name")
    parser.add_argument("--timeout", type=int, default=config.timeout, help="LLM request timeout in seconds")
    parser.add_argument("--prompt", default=None, help="Custom prompt")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM calls and write placeholder sidecars")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--format", choices=["json", "pretty"], default="pretty", help="Output format")
    parser.add_argument("--recursive", action="store_true", default=True, help="Scan directories recursively")
    parser.add_argument(
        "--no-recursive", dest="recursive", action="store_false", help="Do not scan directories recursively"
    )
    parser.add_argument("--resume", action="store_true", default=True, help="Skip already-processed images (default)")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Force reprocess all images")

    # Embedding options
    parser.add_argument("--no-embeddings", action="store_true", help="Disable embedding generation")
    parser.add_argument("--embedding-model", default=None, help="Embedding model to use (default: nomic-embed-text)")
    parser.add_argument("--embedding-backend", default=None, help="Embedding backend to use (default: ollama)")
    parser.add_argument("--embeddings-only", action="store_true", help="Only generate embeddings, skip LLM extraction")
    parser.add_argument("--find-similar", action="store_true", help="Find similar images to the first input image")
    parser.add_argument(
        "--similar-limit", type=int, default=None, help="Number of similar images to return (default: 10)"
    )
    parser.add_argument(
        "--list-embedding-models", action="store_true", help="List available embedding models from Ollama"
    )

    args = parser.parse_args()

    # Handle --list-embedding-models
    if args.list_embedding_models:
        try:
            from src.embeddings import create_generator

            generator = create_generator(
                backend=args.embedding_backend or config.embedding_backend,
                host=args.host,
                port=args.port,
                model="nomic-embed-text",  # Dummy model for listing
            )
            models = generator.list_models()
            print("Available embedding models:")
            for model in models:
                print(f"  - {model}")
            print("\nDefault: nomic-embed-text")
            print(f"Note: Requires Ollama v0.1.0+ and {VEC_REQUIRED}")
        except Exception as e:
            logger.error("Failed to list embedding models: %s", e)
            sys.exit(1)
        sys.exit(0)

    # Handle --find-similar
    if args.find_similar:
        if len(args.path) == 0:
            logger.error("Please provide an image path to find similar images for")
            sys.exit(1)

        query_image_path = Path(args.path[0]).resolve()
        if not query_image_path.exists():
            logger.error(f"Image not found: {query_image_path}")
            sys.exit(1)

        # Get the folder for the query image
        folder = str(query_image_path.parent)
        db_path = FeaturesDatabase.default_db_path(folder)

        if not db_path.exists():
            logger.error(f"No features database found for folder: {folder}")
            logger.error("Please process the folder first with embeddings enabled")
            sys.exit(1)

        try:
            from src.embeddings import create_generator

            # Create a generator to get the query embedding
            generator = create_generator(
                backend=args.embedding_backend or config.embedding_backend,
                host=args.host,
                port=args.port,
                model=args.embedding_model or config.embedding_model,
                timeout=args.timeout,
            )

            # Generate embedding for the query image
            query_embedding = generator.generate(str(query_image_path))
            if query_embedding is None:
                logger.error("Failed to generate embedding for query image")
                sys.exit(1)

            # Find similar images
            db = FeaturesDatabase(db_path)
            db.init_vector_search()
            limit = args.similar_limit or config.similarity_limit
            similar = db.find_similar(query_embedding, limit=limit)
            db.close()

            print(f"Found {len(similar)} similar images to {query_image_path.name}:")
            for i, (image_path, similarity) in enumerate(similar, 1):
                score_pct = similarity * 100
                print(f"  {i}. {image_path} (similarity: {score_pct:.1f}%)")

        except Exception as e:
            logger.error("Failed to find similar images: %s", e)
            sys.exit(1)

        sys.exit(0)

    # Create extractor
    extractor = create_extractor(
        backend="dry_run" if args.dry_run else args.backend,
        host=args.host,
        port=args.port,
        model=args.model,
        timeout=args.timeout,
        default_prompt=config.default_prompt,
    )

    if not args.dry_run and not extractor.health_check():
        sys.exit(2)

    # Get all image paths
    image_paths = PhotoList(recursive=args.recursive).list_photos(args.path)
    if not image_paths:
        logger.error("No images found in the provided path(s).")
        sys.exit(3)

    # If resume is enabled, exclude already processed images
    if args.resume:
        groups = defaultdict(list)
        for p in image_paths:
            groups[_parent_dir(p)].append(p)

        filtered = []
        skipped = 0
        for folder, paths in groups.items():
            try:
                from src.simple_processing_tracker import SimpleProcessingTracker

                tracker = SimpleProcessingTracker(folder)
                processed = tracker.get_processed_files()
            except Exception:
                processed = set()

            for p in paths:
                if p in processed:
                    skipped += 1
                else:
                    filtered.append(p)

        if skipped:
            logger.info("Skipping %d already-processed image(s) (via simple tracker)", skipped)
        image_paths = filtered

    if not image_paths:
        logger.info("All images already processed. Nothing to do.")
        sys.exit(0)

    logger.info("Found %d image(s) to process", len(image_paths))

    prompt = args.prompt or config.default_prompt

    # Group by folder for processing (needed for embedding generation)
    folder_groups = defaultdict(list)
    for p in image_paths:
        folder_groups[_parent_dir(p)].append(p)

    # Handle embeddings-only mode
    if args.embeddings_only:
        logger.info("Embeddings-only mode: generating embeddings without LLM extraction")

        embedding_backend = args.embedding_backend or config.embedding_backend
        embedding_model = args.embedding_model or config.embedding_model

        # Group by folder for tracking
        folder_groups = defaultdict(list)
        for p in image_paths:
            folder_groups[_parent_dir(p)].append(p)

        for folder, paths in folder_groups.items():
            try:
                from src.embeddings import create_generator

                generator = create_generator(
                    backend=embedding_backend,
                    host=args.host,
                    port=args.port,
                    model=embedding_model,
                    timeout=args.timeout,
                )

                db_path = FeaturesDatabase.default_db_path(folder)
                db = FeaturesDatabase(db_path)
                try:
                    db.init_vector_search()
                except RuntimeError as e:
                    logger.warning(
                        "Vector search library not available: %s. Embeddings will be saved to metadata only.", e
                    )

                tracker = SimpleProcessingTracker(folder)

                for i, path in enumerate(paths, 1):
                    logger.info("Generating embedding %d/%d: %s", i, len(paths), path)
                    try:
                        embedding = generator.generate(path)
                        if embedding is not None:
                            db.save_embedding(path, embedding_model, embedding)
                            tracker.mark_completed(path)  # Mark as processed
                            logger.info("Saved embedding for %s (dimension: %d)", path, len(embedding))
                        else:
                            tracker.mark_failed(path, "embedding_none", "Embedding generation returned None")
                            raise RuntimeError(f"Embedding generation returned None for {path}. {VEC_REQUIRED}")
                    except RuntimeError as e:
                        tracker.mark_failed(path, "embedding_error", str(e))
                        logger.error("CRITICAL: Failed to generate embedding for %s: %s", path, e)
                        raise

                db.close()
                logger.info("Embeddings-only processing complete for %s", folder)

            except Exception as e:
                logger.error("Failed to process embeddings for %s: %s", folder, e)
                sys.exit(1)

        sys.exit(0)

    # Process images using simple sequential processor
    # Process each folder separately to enable embedding generation
    all_results = []
    len(image_paths)
    processed = 0
    skipped = 0
    successes = 0
    failures = 0

    for folder, folder_paths in folder_groups.items():
        result = process_paths(
            folder_paths,
            extractor,
            prompt=prompt,
            resume=False,  # We already filtered by resume above
            folder=folder,  # Pass folder for embedding generation
        )
        all_results.extend(result["results"])
        processed += result["processed"]
        skipped += result["skipped"]
        successes += result["successes"]
        failures += result["failures"]

    # Extract durations for statistics
    all_durations = []
    for result_dict in all_results:
        if result_dict.get("success") and result_dict.get("total_duration_ms") is not None:
            all_durations.append(result_dict["total_duration_ms"])

    if args.format == "pretty":
        for result_dict in all_results:
            print("-" * 60)
            print(f"Image : {result_dict.get('image_path')}")
            print(f"Model : {result_dict.get('model')}")
            print(f"Duration : {result_dict.get('total_duration_ms', 0):.1f} ms")
            print(f"Response:\n{result_dict.get('response', '')}")
            if result_dict.get("parsed"):
                print(f"Parsed:\n{json.dumps(result_dict['parsed'], indent=2, ensure_ascii=False)}")
            if result_dict.get("error"):
                print(f"Error : {result_dict['error']}")

    if all_durations and args.format == "pretty":
        stats = compute_duration_stats(all_durations)
        print("-" * 60)
        print(f"Processing complete: {len(all_results)} photo(s)")
        print(
            f"Per-image — min: {stats['min_ms']:.0f} ms  max: {stats['max_ms']:.0f} ms  avg: {stats['avg_ms']:.0f} ms"
        )
        print(f"Total model time: {stats['total_s']:.1f} s")

    output_data = {"results": all_results}
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        logger.info("Results saved to %s", args.output)
    elif args.format == "json":
        print(json.dumps(output_data, indent=2, ensure_ascii=False))

    for result_dict in all_results:
        if not result_dict.get("success"):
            sys.exit(1)


if __name__ == "__main__":
    main()
