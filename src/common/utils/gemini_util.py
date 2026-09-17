"""
Gemini (Google AI Studio API) structured-output client. Primary LLM provider.

Prefer ``src.common.utils.llm_util.LLMUtil`` over using this class directly;
it adds the Vertex and Claude fallbacks.

    util = get_gemini_util(GEMINI_API_KEY)
    result = await util.get_llm_response(prompt, MySchema, system_prompt, model="gemini-3-flash-preview", thinking="low")
    result, raw = await util.get_llm_response_with_grounding(prompt, MySchema, system_prompt)
    urls = await util.extract_citations(raw)
"""

import asyncio
import json
import logging
import threading
from typing import Any

import httpx
from google import genai
from google.api_core import exceptions as google_exceptions
from google.genai import types
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)
GEMINI_TIMEOUT_SECONDS = 90
GEMINI_CONCURRENCY_LIMIT = 30

# Singleton state - one client per worker process
_gemini_instance: "GeminiUtil | None" = None
_gemini_lock = threading.Lock()


def get_gemini_util(api_key: str) -> "GeminiUtil":
    """
    Return the process-wide GeminiUtil singleton.
    """
    global _gemini_instance
    if _gemini_instance is None:
        with _gemini_lock:
            if _gemini_instance is None:
                _gemini_instance = GeminiUtil(api_key=api_key)
    return _gemini_instance


class ModelRefusalError(Exception):
    pass


class GeminiError(Exception):
    pass


class GeminiRateLimitError(GeminiError):
    """Raised when Gemini returns HTTP 429 (ResourceExhausted).
    Caught by FallbackLLMUtil to trigger the Claude fallback."""

    pass


class GeminiUtil:
    """
    GeminiUtil class for generating responses using Google's Gemini API.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._sync_client = genai.Client(api_key=api_key)
        self.client = self._sync_client.aio
        self._semaphore = asyncio.Semaphore(GEMINI_CONCURRENCY_LIMIT)
        logger.info(
            f"Initialized async Gemini client (concurrency_limit={GEMINI_CONCURRENCY_LIMIT})"
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((GeminiError, ModelRefusalError)),
        reraise=True,
    )
    async def get_llm_response(
        self,
        prompt: str,
        structure: Any,
        system_prompt: str = "",
        model: str = "gemini-3-flash-preview",
        thinking: str = "low",
    ) -> dict:
        """
        Generate a response from Gemini (Gemini 3 flash +thinking_level + grounding tool) based on the provided prompt (async).
        Default gemini 3 thinking is ste to 'high' if nothing is mentioned.
        Note: gemini 2.5 series do not work with thinking_level, but thinking budget.
        """

        logger.info(f"Sending prompt to Gemini model '{model}'")
        try:
            config = types.GenerateContentConfig(
                temperature=1.0,
                thinking_config=types.ThinkingConfig(thinking_level=thinking),
                response_mime_type="application/json",
            )

            if system_prompt:
                config.system_instruction = system_prompt
                logger.debug(f"Using system prompt: {system_prompt}")

            if structure is not None:
                config.response_schema = structure
                logger.debug(f"Using response schema: {structure}")

            async with self._semaphore:
                response = await asyncio.wait_for(
                    self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=GEMINI_TIMEOUT_SECONDS,
                )

            logger.debug("Received raw response text")

            if not response.text:
                logger.error("Model refused to answer the question (empty response).")
                raise ModelRefusalError("The model refused to answer the question.")

            parsed_response = structure.model_validate(json.loads(response.text))
            logger.info("Successfully parsed Gemini response")
            return parsed_response

        except TimeoutError:
            logger.error(f"Gemini API call timed out after {GEMINI_TIMEOUT_SECONDS}s")
            raise GeminiError(f"Gemini API call timed out after {GEMINI_TIMEOUT_SECONDS} seconds")

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Gemini rate limit (429): {e}")
            raise GeminiRateLimitError(f"Gemini rate limit error: {e}")

        except google_exceptions.ServiceUnavailable as e:
            logger.warning(f"Retryable error: {e}")
            raise GeminiError(f"Gemini API error: {e}")

        except (GeminiRateLimitError, ModelRefusalError):
            raise

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise GeminiError(f"Gemini API error: {e}")

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((GeminiError, ModelRefusalError)),
        reraise=True,
    )
    async def get_llm_response_with_grounding(
        self,
        prompt: str,
        structure: Any,
        system_prompt: str = "",
        model: str = "gemini-3-flash-preview",
        thinking: str = "low",
    ) -> tuple[dict, Any]:
        logger.info(f"Sending prompt to Gemini model '{model}' with grounding")
        try:
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            config = types.GenerateContentConfig(
                temperature=1.0,
                tools=[grounding_tool],
                thinking_config=types.ThinkingConfig(thinking_level=thinking),
                response_mime_type="application/json",
            )

            if system_prompt:
                config.system_instruction = system_prompt
                logger.debug(f"Using system prompt: {system_prompt}")

            if structure is not None:
                config.response_schema = structure
                logger.debug(f"Using response schema: {structure}")

            async with self._semaphore:
                response = await asyncio.wait_for(
                    self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config,
                    ),
                    timeout=GEMINI_TIMEOUT_SECONDS,
                )

            logger.debug("Received raw response text with grounding metadata")

            if not response.text:
                logger.error("Model refused to answer the question (empty response).")
                raise ModelRefusalError("The model refused to answer the question.")

            parsed_response = structure.model_validate(json.loads(response.text))
            logger.info("Successfully parsed Gemini response with grounding")
            return parsed_response, response

        except TimeoutError:
            logger.error(f"Gemini API call timed out after {GEMINI_TIMEOUT_SECONDS}s")
            raise GeminiError(f"Gemini API call timed out after {GEMINI_TIMEOUT_SECONDS} seconds")

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Gemini rate limit (429) with grounding: {e}")
            raise GeminiRateLimitError(f"Gemini rate limit error: {e}")

        except google_exceptions.ServiceUnavailable as e:
            logger.warning(f"Retryable error with grounding: {e}")
            raise GeminiError(f"Gemini API error: {e}")

        except (GeminiRateLimitError, ModelRefusalError):
            raise

        except Exception as e:
            logger.error(f"Gemini API error with grounding: {e}")
            raise GeminiError(f"Gemini API error: {e}")

    async def _resolve_redirect_url(self, redirect_url: str) -> str:
        """Resolve Vertex AI redirect URL to actual destination URL."""
        try:
            # Check if it's a Vertex AI redirect URL
            if "vertexaisearch.cloud.google.com" not in redirect_url:
                return redirect_url

            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                try:
                    response = await client.head(redirect_url)
                    # Return the final URL after following redirects
                    return str(response.url)
                except httpx.TimeoutException:
                    logger.warning(f"Timeout resolving redirect URL: {redirect_url}")
                    return redirect_url
                except Exception as e:
                    logger.warning(f"Error resolving redirect URL {redirect_url}: {e}")
                    return redirect_url
        except Exception as e:
            logger.error(f"Failed to resolve redirect URL {redirect_url}: {e}")
            return redirect_url

    async def extract_citations(self, response: Any) -> list[str]:
        """Extract citations from grounding metadata as a list of actual URLs."""
        try:
            if not response or not hasattr(response, "candidates") or not response.candidates:
                logger.warning("No candidates in response, returning empty citations")
                return []

            candidate = response.candidates[0]

            if not hasattr(candidate, "grounding_metadata") or not candidate.grounding_metadata:
                logger.warning("No grounding metadata in response, returning empty citations")
                return []

            grounding_metadata = candidate.grounding_metadata

            chunks = (
                grounding_metadata.grounding_chunks
                if hasattr(grounding_metadata, "grounding_chunks")
                else []
            )

            if not chunks:
                logger.warning("No grounding chunks found, returning empty citations")
                return []

            # Collect all redirect URLs first
            redirect_urls = []
            for chunk in chunks:
                uri = None
                if hasattr(chunk, "web") and chunk.web:
                    uri = chunk.web.uri if hasattr(chunk.web, "uri") else None
                if uri:
                    redirect_urls.append(uri)

            logger.info(
                f"Found {len(redirect_urls)} URLs in grounding metadata, resolving redirects..."
            )

            # Resolve all redirect URLs concurrently
            resolved_urls = await asyncio.gather(
                *[self._resolve_redirect_url(url) for url in redirect_urls],
                return_exceptions=True,
            )

            # Deduplicate resolved URLs and filter out exceptions
            citations = []
            seen_urls = set()
            for url in resolved_urls:
                if isinstance(url, str) and url and url not in seen_urls:
                    citations.append(url)
                    seen_urls.add(url)

            logger.info(f"Extracted {len(citations)} unique citations after resolving redirects")
            return citations

        except Exception as e:
            logger.error(f"Error extracting citations: {e}")
            return []
