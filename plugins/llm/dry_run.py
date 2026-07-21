"""Dry-run LLM backend that skips real model calls and returns placeholder results."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Union

from src.interfaces import BasePhotoExtractor, ProcessingResult

logger = logging.getLogger(__name__)


class DryRunPhotoExtractor(BasePhotoExtractor):
    """Extractor that simulates extraction without calling an LLM backend.

    Useful for testing the full pipeline (discovery, WAL, sidecars, progress
    reporting) without incurring GPU time or network latency.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        model: Optional[str] = None,
        timeout: int = 120,
        default_prompt: Optional[str] = None,
    ):
        """Initialise the dry-run extractor.

        Args are accepted for API compatibility with real backends but only
        ``model`` and ``default_prompt`` affect the synthetic result.
        """
        super().__init__(
            host=host or "dry-run",
            port=port or 0,
            model=model or "dry-run",
            timeout=timeout,
            default_prompt=default_prompt,
        )
        logger.info("Initialized DryRun extractor (model: %s)", self.model)

    def extract(
        self,
        image_path: Union[str, Path],
        prompt: Optional[str] = None,
        options: Optional[Dict] = None,
    ) -> ProcessingResult:
        """Return a synthetic ProcessingResult for the given image path."""
        used_prompt = prompt or self.default_prompt
        result = self._make_result(used_prompt, seed=str(image_path))
        result.image_path = str(image_path)
        logger.info("[DRY RUN] Pretended to process %s", image_path)
        return result

    def extract_b64(
        self,
        image_b64: str,
        prompt: Optional[str] = None,
        options: Optional[Dict] = None,
    ) -> ProcessingResult:
        """Return a synthetic ProcessingResult for the given base64 image."""
        used_prompt = prompt or self.default_prompt
        result = self._make_result(used_prompt, seed=image_b64)
        logger.info("[DRY RUN] Pretended to process base64 image (%d chars)", len(image_b64))
        return result

    def health_check(self) -> bool:
        """Dry-run is always "healthy" — no server required."""
        return True

    def _make_result(self, used_prompt: str, seed: Optional[str] = None) -> ProcessingResult:
        """Build a realistic synthetic ProcessingResult matching the prompt schema."""
        # deterministic but varied synthetic content based on seed
        suffix = ""
        if seed:
            import hashlib
            suffix = hashlib.md5(seed.encode()).hexdigest()[:6]

        synthetic_response = json.dumps(
            {
                "description": f"A detailed outdoor photograph captured in natural daylight. The scene is composed with soft foreground elements and a clear, textured background. (dry-run ID: {suffix})",
                "subjects": ["person", "landscape", "sky"],
                "objects": ["tree", "cloud", "pathway"],
                "colors": ["blue", "green", "white", "earth tones"],
                "setting": "daytime outdoor environment",
                "mood": "calm and serene",
                "tags": ["nature", "outdoor", "daylight", "scenic", "dry-run"],
            },
            indent=2,
            ensure_ascii=False,
        )

        return ProcessingResult(
            success=True,
            model=self.model,
            prompt=used_prompt,
            response=synthetic_response,
            parsed=json.loads(synthetic_response),
            total_duration_ms=0.0,
            eval_count=0,
            done=True,
        )
