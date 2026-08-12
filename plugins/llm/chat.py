"""Ollama LLM chat client for text-based chat interactions.

This module provides OllamaChatClient which implements LLMChatClient
for text-based chat with Ollama models.
"""

import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.interfaces import LLMChatClient, DEFAULT_LLM_MODEL, DEFAULT_LLM_HOST

logger = logging.getLogger(__name__)


class OllamaChatClient(LLMChatClient):
    """Ollama-based chat client for text chat interactions.
    
    This client handles text-based chat with Ollama models via the /api/generate
    endpoint, providing retry logic and connection management.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        model: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ):
        """Initialise the Ollama chat client with connection and retry settings.

        Args:
            host: Ollama server hostname (default: DEFAULT_LLM_HOST).
            port: Ollama API port (default: 11434).
            model: Model tag to use for chat (default: DEFAULT_LLM_MODEL).
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum number of automatic retries on transient errors.
            backoff_factor: Backoff multiplier for retry delays.
        """
        super().__init__(
            host=host or DEFAULT_LLM_HOST,
            port=port or 11434,
            model=model or DEFAULT_LLM_MODEL,
            timeout=timeout,
        )
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._session = self._create_session()
        logger.info("Initialized Ollama chat client for %s using model '%s'", self.base_url, self.model)

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

    def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list] = None,
    ) -> str:
        """Send a chat message to Ollama and return the response.
        
        Args:
            message: The user message/prompt.
            system_prompt: Optional system prompt to guide the LLM.
            history: Optional chat history for conversation context.
            
        Returns:
            The LLM's response text.
            
        Raises:
            requests.exceptions.RequestException: If the request fails.
        """
        url = f"{self.base_url}/api/generate"
        
        # Build the full prompt with history context
        if history and len(history) > 0:
            # Format history as conversation context in the prompt
            context_messages = []
            for entry in history:
                sender = entry.get("sender", "")
                content = entry.get("content", "")
                entry_type = entry.get("type", "text")
                
                if entry_type == "photos":
                    photo_paths = entry.get("photo_paths", [])
                    count = entry.get("count", len(photo_paths))
                    context_messages.append(f"{sender}: Found {count} matching photos")
                elif entry_type == "error":
                    context_messages.append(f"{sender}: Error - {content}")
                else:
                    context_messages.append(f"{sender}: {content}")
            
            # Add context to the prompt - include user: prefix for current message
            full_prompt = "\n".join(context_messages) + "\nuser: " + message
        else:
            full_prompt = message
        
        # Build the payload
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
        }
        
        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt
        
        logger.debug("Sending chat request to %s with model '%s'", url, self.model)
        
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as e:
            logger.error("Ollama chat returned non-JSON response (status %d): %s", response.status_code, response.text[:200])
            raise RuntimeError(
                f"Ollama chat response was not valid JSON (status {response.status_code}). "
                f"Model: {self.model}. Response: {response.text[:200]}"
            ) from e
        
        return result.get("response", "")

    def health_check(self) -> bool:
        """Check if the Ollama server is reachable."""
        try:
            url = f"{self.base_url}/api/tags"
            response = self._session.get(url, timeout=10)
            response.raise_for_status()
            logger.info("Ollama server is reachable")
            return True
        except requests.exceptions.RequestException as e:
            logger.error("Health check failed: %s", e)
            return False
