"""
Ollama LLM client for photo feature extraction.
"""

import json
import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.constants import DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL
from src.interfaces import DEFAULT_PROMPT, BasePhotoExtractor, ErrorCode, ProcessingResult
from src.utils import encode_image_file

logger = logging.getLogger(__name__)


class OllamaPhotoExtractor(BasePhotoExtractor):
    """
    Extract features from photos using an Ollama vision model.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        model: str | None = None,
        timeout: int = 120,
        default_prompt: str | None = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ):
        """Initialise the Ollama extractor with connection and retry settings.

        Args:
            host: Ollama server hostname (default: see DEFAULT_LLM_HOST in constants).
            port: Ollama API port (default ``11434``).
            model: Vision model tag (default: see DEFAULT_LLM_MODEL in constants).
            timeout: HTTP request timeout in seconds.
            default_prompt: Fallback prompt used when none is provided per call.
            max_retries: Maximum number of automatic retries on transient errors.
            backoff_factor: Backoff multiplier for retry delays.
        """
        super().__init__(
            host=host or DEFAULT_LLM_HOST,
            port=port or 11434,
            model=model or DEFAULT_LLM_MODEL,
            timeout=timeout,
            default_prompt=default_prompt,
        )
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._session = self._create_session()
        logger.info("Initialized Ollama extractor for %s using model '%s'", self.base_url, self.model)

    def _create_session(self) -> requests.Session:
        """Build a requests Session with automatic retries on transient failures."""
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods={"GET", "POST"},
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _encode_image(self, image_path: str | Path) -> str:
        """Read and base64-encode an image file via the format plugin system."""
        return encode_image_file(str(image_path))

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove surrounding ```json / ``` markdown code fences from LLM output."""
        if not text:
            return text
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped[3:]
            if stripped.startswith("json"):
                stripped = stripped[4:]
            stripped = stripped.lstrip("\n")
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip("\n")
        return stripped

    def _build_payload(
        self,
        image_b64: str,
        prompt: str,
        stream: bool = False,
        options: dict | None = None,
    ) -> dict:
        """Construct the JSON payload for the Ollama /api/generate endpoint."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": stream,
        }
        if options:
            payload["options"] = options
        return payload

    def extract_b64(
        self,
        image_b64: str,
        prompt: str | None = None,
        options: dict | None = None,
    ) -> ProcessingResult:
        """Extract features from a base64-encoded image via the Ollama API.

        Returns a ProcessingResult with success/error details and the parsed
        JSON response (if the model returned valid JSON).
        """
        used_prompt = prompt or self.default_prompt or DEFAULT_PROMPT

        # Try non-streaming first, fall back to streaming if needed
        payload = self._build_payload(image_b64, used_prompt, stream=False, options=options)
        url = f"{self.base_url}/api/generate"

        try:
            logger.info("Sending image to Ollama at %s (model: %s)", url, self.model)
            response = self._session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            raw_response = data.get("response", "")
            cleaned_response = self._strip_markdown_fences(raw_response)

            # Check if non-streaming worked properly
            if data.get("done", False) and raw_response:
                # Non-streaming mode worked
                result = ProcessingResult(
                    success=True,
                    model=self.model,
                    prompt=used_prompt,
                    response=cleaned_response,
                    done=data.get("done", False),
                    total_duration_ms=data.get("total_duration", 0) / 1_000_000,
                    eval_count=data.get("eval_count", 0),
                )
            else:
                # Non-streaming returned empty/incomplete, try streaming
                logger.info("Non-streaming returned incomplete response, trying streaming mode")
                payload_stream = self._build_payload(image_b64, used_prompt, stream=True, options=options)
                response_stream = self._session.post(url, json=payload_stream, timeout=self.timeout, stream=True)
                response_stream.raise_for_status()

                # Collect all streaming chunks
                full_response = ""
                total_duration = 0
                eval_count = 0
                done = False

                for line in response_stream.iter_lines():
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        chunk_response = chunk.get("response", "")

                        # Smart concatenation: add space if the previous chunk ends with
                        # a letter/digit and the new chunk starts with a letter/digit
                        if (
                            full_response
                            and chunk_response
                            and full_response[-1].isalnum()
                            and chunk_response[0].isalnum()
                        ):
                            full_response += " " + chunk_response
                        else:
                            full_response += chunk_response

                        total_duration = chunk.get("total_duration", 0)
                        eval_count = chunk.get("eval_count", 0)
                        if chunk.get("done", False):
                            done = True
                            break

                cleaned_response = self._strip_markdown_fences(full_response)

                # Check if streaming also returned empty
                if not cleaned_response:
                    logger.error("Both streaming and non-streaming modes returned empty responses")
                    return ProcessingResult(
                        success=False,
                        model=self.model,
                        prompt=used_prompt,
                        error="Model returned empty response in both streaming and non-streaming modes",
                        error_code=ErrorCode.INVALID_RESPONSE.value,
                    )

                result = ProcessingResult(
                    success=True,
                    model=self.model,
                    prompt=used_prompt,
                    response=cleaned_response,
                    done=done,
                    total_duration_ms=total_duration / 1_000_000 if total_duration > 0 else 0,
                    eval_count=eval_count,
                )

            try:
                parsed = json.loads(result.response)
                result.parsed = parsed
            except json.JSONDecodeError:
                result.parsed = None
                logger.warning("Model response was not valid JSON")

            logger.info("Extraction complete")
            return result

        except requests.exceptions.Timeout as e:
            logger.error("Request timed out: %s", e)
            return ProcessingResult(
                success=False,
                error_code=ErrorCode.TIMEOUT.value,
                error=str(e),
            )
        except requests.exceptions.RequestException as e:
            logger.error("Request failed: %s", e)
            return ProcessingResult(
                success=False,
                error_code=ErrorCode.NETWORK_ERROR.value,
                error=str(e),
            )

    def extract(
        self,
        image_path: str | Path,
        prompt: str | None = None,
        options: dict | None = None,
    ) -> ProcessingResult:
        """Read an image file, encode to base64, then call extract_b64.

        The resulting ProcessingResult will have ``image_path`` set.
        """
        image_b64 = self._encode_image(image_path)
        result = self.extract_b64(image_b64, prompt=prompt, options=options)
        result.image_path = str(image_path)
        return result

    def health_check(self) -> bool:
        """Ping the Ollama /api/tags endpoint to verify server reachability."""
        try:
            url = f"{self.base_url}/api/tags"
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            logger.info("Ollama server is reachable")
            return True
        except requests.exceptions.RequestException as e:
            logger.error("Health check failed: %s", e)
            return False
