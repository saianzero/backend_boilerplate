"""
Gemini via Vertex AI. Second provider in the fallback chain.

Needs ``GOOGLE_CLOUD_PROJECT`` and Application Default Credentials (or
``GOOGLE_APPLICATION_CREDENTIALS``). Enforces a daily call cap in Redis
(``VERTEX_DAILY_LIMIT``) and raises ``VertexDailyLimitError`` when exceeded.
"""

import asyncio
import json
import logging
import threading
from datetime import date
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

from src.common.utils.gemini_util import GeminiError, GeminiRateLimitError, ModelRefusalError
from src.core.redis_client import redis_client

logger = logging.getLogger(__name__)
VERTEX_GEMINI_TIMEOUT_SECONDS = 90
VERTEX_GEMINI_CONCURRENCY_LIMIT = 30
VERTEX_DAILY_LIMIT_REDIS_KEY = "vertex_gemini:daily_calls:{date}"
VERTEX_DAILY_LIMIT_TTL = 90000  # 25 hours

_vertex_instance: "VertexGeminiUtil | None" = None
_vertex_lock = threading.Lock()


class VertexDailyLimitError(Exception):
    """Raised when the self-imposed daily Vertex AI call limit is reached.
    Extends Exception directly (not GeminiError) so tenacity does not retry it.
    Caught explicitly by FallbackLLMUtil to trigger the Claude fallback."""

    pass


def get_vertex_gemini_util(
    project: str,
    location: str = "global",
    daily_limit: int = 10,
) -> "VertexGeminiUtil":
    """Return the process-wide VertexGeminiUtil singleton."""
    global _vertex_instance
    if _vertex_instance is None:
        with _vertex_lock:
            if _vertex_instance is None:
                _vertex_instance = VertexGeminiUtil(
                    project=project,
                    location=location,
                    daily_limit=daily_limit,
                )
    return _vertex_instance


class VertexGeminiUtil:
    """
    Gemini inference via Vertex AI (google-genai SDK, vertexai=True).
    Used as the second fallback after the Google API Gemini client.

    Enforces a self-imposed daily call limit tracked in Redis.
    Raises VertexDailyLimitError when the limit is reached, which triggers
    the Claude fallback in FallbackLLMUtil.
    """

    def __init__(self, project: str, location: str = "global", daily_limit: int = 1000):
        self.project = project
        self.location = location
        self.daily_limit = daily_limit
        self._semaphore = asyncio.Semaphore(VERTEX_GEMINI_CONCURRENCY_LIMIT)

        self._sync_client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(timeout=VERTEX_GEMINI_TIMEOUT_SECONDS * 1000),
        )
        self.client = self._sync_client.aio

        logger.info(
            f"Initialized Gemini client via Vertex AI ADC "
            f"(project={project}, location={location}, daily_limit={daily_limit})"
        )

    async def _check_and_increment_daily_limit(self) -> None:
        """
        Atomically increments today's Vertex AI call counter in Redis.
        Raises VertexDailyLimitError if the daily limit has been reached.
        TTL is set on first write so the key auto-expires after 25 hours.
        """
        key = VERTEX_DAILY_LIMIT_REDIS_KEY.format(date=date.today().isoformat())

        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, VERTEX_DAILY_LIMIT_TTL)

        if count > self.daily_limit:
            logger.warning(
                f"Vertex AI daily limit reached ({count}/{self.daily_limit}) — "
                f"falling back to Claude."
            )
            raise VertexDailyLimitError(
                f"Vertex AI daily call limit of {self.daily_limit} reached (count={count})."
            )

        logger.debug(f"Vertex AI daily call count: {count}/{self.daily_limit}")

    def _build_config(
        self,
        structure: Any,
        system_prompt: str,
        thinking: str,
        with_grounding: bool,
    ) -> types.GenerateContentConfig:
        config = types.GenerateContentConfig(
            temperature=1.0,
            thinking_config=types.ThinkingConfig(thinking_level=thinking),
            response_mime_type="application/json",
        )
        if with_grounding:
            config.tools = [types.Tool(google_search=types.GoogleSearch())]
        if system_prompt:
            config.system_instruction = system_prompt
        if structure is not None:
            config.response_schema = structure
        return config

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
    ) -> Any:
        """Generate a structured response from Gemini via Vertex AI (no grounding)."""
        await self._check_and_increment_daily_limit()
        logger.info(f"Sending prompt to Vertex AI Gemini model '{model}'")
        try:
            config = self._build_config(
                structure=structure,
                system_prompt=system_prompt,
                thinking=thinking,
                with_grounding=False,
            )
            async with self._semaphore:
                response = await self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )

            if not response.text:
                logger.error("Vertex AI model refused to answer (empty response).")
                raise ModelRefusalError("The model refused to answer the question.")

            parsed_response = structure.model_validate(json.loads(response.text))
            logger.info("Successfully parsed Vertex AI Gemini response")
            return parsed_response

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Vertex AI rate limit (429): {e}")
            raise GeminiRateLimitError(f"Vertex AI rate limit error: {e}")

        except google_exceptions.ServiceUnavailable as e:
            logger.warning(f"Vertex AI service unavailable: {e}")
            raise GeminiError(f"Vertex AI error: {e}")

        except (GeminiRateLimitError, ModelRefusalError):
            raise

        except Exception as e:
            logger.error(f"Vertex AI Gemini error: {e}")
            raise GeminiError(f"Vertex AI error: {e}")

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
    ) -> tuple[Any, Any]:
        """Generate a structured response from Gemini via Vertex AI with grounding."""
        await self._check_and_increment_daily_limit()
        logger.info(f"Sending prompt to Vertex AI Gemini model '{model}' with grounding")
        try:
            config = self._build_config(
                structure=structure,
                system_prompt=system_prompt,
                thinking=thinking,
                with_grounding=True,
            )
            async with self._semaphore:
                response = await self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )

            if not response.text:
                logger.error("Vertex AI model refused to answer (empty response).")
                raise ModelRefusalError("The model refused to answer the question.")

            try:
                candidate = response.candidates[0] if response.candidates else None
                web_search_queries = (
                    candidate.grounding_metadata.web_search_queries
                    if candidate
                    and hasattr(candidate, "grounding_metadata")
                    and candidate.grounding_metadata
                    and hasattr(candidate.grounding_metadata, "web_search_queries")
                    else []
                )
                logger.info(
                    f"Vertex AI grounding used {len(web_search_queries)} billable "
                    f"search quer{'y' if len(web_search_queries) == 1 else 'ies'}: "
                    f"{web_search_queries}"
                )
            except Exception:
                pass

            parsed_response = structure.model_validate(json.loads(response.text))
            logger.info("Successfully parsed Vertex AI Gemini response with grounding")
            return parsed_response, response

        except google_exceptions.ResourceExhausted as e:
            logger.warning(f"Vertex AI rate limit (429) with grounding: {e}")
            raise GeminiRateLimitError(f"Vertex AI rate limit error: {e}")

        except google_exceptions.ServiceUnavailable as e:
            logger.warning(f"Vertex AI service unavailable with grounding: {e}")
            raise GeminiError(f"Vertex AI error: {e}")

        except (GeminiRateLimitError, ModelRefusalError):
            raise

        except Exception as e:
            logger.error(f"Vertex AI Gemini error with grounding: {e}")
            raise GeminiError(f"Vertex AI error: {e}")

    async def _resolve_redirect_url(self, redirect_url: str) -> str:
        """Resolve Vertex AI redirect URL to actual destination URL."""
        try:
            if "vertexaisearch.cloud.google.com" not in redirect_url:
                return redirect_url
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                try:
                    response = await client.head(redirect_url)
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
        """Extract and resolve grounding citations from a Vertex AI response."""
        try:
            if not response or not hasattr(response, "candidates") or not response.candidates:
                logger.warning("No candidates in response, returning empty citations")
                return []

            candidate = response.candidates[0]
            if not hasattr(candidate, "grounding_metadata") or not candidate.grounding_metadata:
                logger.warning("No grounding metadata in response")
                return []

            grounding_metadata = candidate.grounding_metadata
            chunks = (
                grounding_metadata.grounding_chunks
                if hasattr(grounding_metadata, "grounding_chunks")
                else []
            )
            if not chunks:
                logger.warning("No grounding chunks found")
                return []

            redirect_urls = []
            for chunk in chunks:
                uri = None
                if hasattr(chunk, "web") and chunk.web:
                    uri = chunk.web.uri if hasattr(chunk.web, "uri") else None
                if uri:
                    redirect_urls.append(uri)

            logger.info(f"Found {len(redirect_urls)} URLs in grounding metadata, resolving...")
            resolved_urls = await asyncio.gather(
                *[self._resolve_redirect_url(url) for url in redirect_urls],
                return_exceptions=True,
            )

            citations = []
            seen_urls = set()
            for url in resolved_urls:
                if isinstance(url, str) and url and url not in seen_urls:
                    citations.append(url)
                    seen_urls.add(url)

            logger.info(f"Extracted {len(citations)} unique citations")
            return citations

        except Exception as e:
            logger.error(f"Error extracting citations: {e}")
            return []
