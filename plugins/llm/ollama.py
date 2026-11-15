"""
Ollama LLM client for photo feature extraction.
"""

import json
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.constants import DEFAULT_LLM_HOST, DEFAULT_LLM_MODEL
from src.interfaces import DEFAULT_PROMPT, BasePhotoExtractor, ErrorCode, ProcessingResult

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
        json_retries: int = 1,
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
            json_retries: Number of retries with a stricter JSON-only prompt and
                Ollama JSON mode (``format="json"``) when the model response is
                not usable (invalid JSON, or JSON without a non-empty
                ``description``/``caption``).
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
        self.json_retries = max(0, json_retries)
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
        format: str | dict | None = None,
    ) -> dict:
        """Construct the JSON payload for the Ollama /api/generate endpoint.

        ``format`` maps to Ollama's top-level ``format`` field: ``"json"``
        enables JSON mode (the model must return valid JSON), or a JSON
        schema dict for structured outputs on newer Ollama versions.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": stream,
        }
        if options:
            payload["options"] = options
        if format is not None:
            payload["format"] = format
        return payload

    @staticmethod
    def _is_valid_extraction(parsed) -> bool:
        """Return True when *parsed* is a usable extraction result.

        Some models return syntactically valid JSON that is not a usable
        extraction — an empty object, a JSON array, or an object with an
        empty/missing ``description``. Downstream storage and embedding
        generation need at least a non-empty ``description`` (or ``caption``)
        string, so anything else counts as invalid and triggers a retry.
        """
        if not isinstance(parsed, dict):
            return False
        for key in ("description", "caption"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return True
        return False

    # Stricter prompt used when the first attempt returns non-JSON text.
    _JSON_RETRY_PROMPT = (
        "You MUST respond with ONLY a valid JSON object. Do NOT include any explanation, "
        "markdown formatting, or text before or after the JSON. "
        'Format: {"description": "...", "subjects": [...], "objects": [...], '
        '"colors": [...], "setting": "...", "mood": "...", "tags": [...]}.'
    )

    def extract_b64(
        self,
        image_b64: str,
        prompt: str | None = None,
        options: dict | None = None,
    ) -> ProcessingResult:
        """Extract features from a base64-encoded image via the Ollama API.

        Makes a first attempt with the given prompt. If the model response is
        not a usable extraction — invalid JSON, JSON that is not an object,
        or an object without a non-empty ``description``/``caption`` — retries
        up to ``json_retries`` times with a stricter JSON-only prompt and
        Ollama JSON mode (``format="json"``), which constrains the model to
        emit syntactically valid JSON. If every attempt fails to produce a
        usable extraction and the first response was non-JSON text, that raw
        text is stored as the description so the database always has a usable
        description.

        Returns a ProcessingResult with success/error details and the parsed
        JSON response (if the model returned valid JSON).
        """
        used_prompt = prompt or self.default_prompt or DEFAULT_PROMPT
        result = self._extract_once(image_b64, used_prompt, options)

        # Retry with a stricter JSON-only prompt + JSON mode when the first
        # attempt did not yield a usable extraction.
        if (
            result.success
            and not self._is_valid_extraction(result.parsed)
            and result.response
            and result.response.strip()
        ):
            for attempt in range(1, self.json_retries + 1):
                logger.info(
                    "Retrying with stricter JSON-only prompt + JSON mode (attempt %d/%d; response was not a usable extraction)",
                    attempt,
                    self.json_retries,
                )
                retry_result = self._extract_once(image_b64, self._JSON_RETRY_PROMPT, options, format="json")
                if retry_result.success and self._is_valid_extraction(retry_result.parsed):
                    # Retry produced a usable extraction — prefer it.
                    retry_result.prompt = used_prompt  # report the original prompt
                    return retry_result
            # All retries failed — fall through and apply the raw-text
            # fallback to the first result below.

        # Raw-text fallback: if the model returned non-JSON text, store it
        # as the description so the database has a usable value and embeddings
        # can be generated from it.
        if result.success and result.parsed is None and result.response and result.response.strip():
            raw_text = result.response.strip()
            result.parsed = {"description": raw_text}
            logger.warning(
                "Model response was not valid JSON; stored raw text as description (%d chars)",
                len(raw_text),
            )

        return result

    def _extract_once(
        self,
        image_b64: str,
        prompt: str,
        options: dict | None = None,
        format: str | dict | None = None,
    ) -> ProcessingResult:
        """Single extraction attempt against the Ollama /api/generate endpoint.

        Tries non-streaming first, falls back to streaming. Parses JSON and
        applies the raw-text fallback when JSON parsing fails. ``format`` is
        forwarded to the payload (e.g. ``"json"`` for Ollama JSON mode).
        """
        # Try non-streaming first, fall back to streaming if needed
        payload = self._build_payload(image_b64, prompt, stream=False, options=options, format=format)
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
                    prompt=prompt,
                    response=cleaned_response,
                    done=data.get("done", False),
                    total_duration_ms=data.get("total_duration", 0) / 1_000_000,
                    eval_count=data.get("eval_count", 0),
                )
            else:
                # Non-streaming returned empty/incomplete, try streaming
                logger.info("Non-streaming returned incomplete response, trying streaming mode")
                payload_stream = self._build_payload(image_b64, prompt, stream=True, options=options, format=format)
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
                        prompt=prompt,
                        error="Model returned empty response in both streaming and non-streaming modes",
                        error_code=ErrorCode.INVALID_RESPONSE.value,
                    )

                result = ProcessingResult(
                    success=True,
                    model=self.model,
                    prompt=prompt,
                    response=cleaned_response,
                    done=done,
                    total_duration_ms=total_duration / 1_000_000 if total_duration > 0 else 0,
                    eval_count=eval_count,
                )

            try:
                parsed = json.loads(result.response) if result.response else None
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
