"""
Provider-agnostic LLM facade with automatic fallback.

Order: Gemini API -> Vertex AI Gemini -> Claude. Each provider returns an
instance of the pydantic ``structure`` you pass in, so callers never parse JSON.

Get the singleton (safe to call from tasks and request handlers):

    from src.common.utils.llm_util import get_default_llm_util
    llm = get_default_llm_util()

Structured call:

    class Summary(BaseModel):
        title: str
        summary: str

    result: Summary = await llm.get_llm_response(
        prompt=USER_PROMPT.format(document_text=text),
        structure=Summary,
        system_prompt=SYSTEM_PROMPT,
        model="gemini-3-flash-preview",   # optional
        thinking="low",                   # Gemini 3 only
    )

Grounded call (web search) + citations:

    result, raw = await llm.get_llm_response_with_grounding(prompt, Summary, SYSTEM_PROMPT)
    urls = await llm.extract_citations(raw)
"""

import logging
import threading
from typing import Any

from src.common.utils.claude_util import ClaudeUtil, get_claude_util
from src.common.utils.gemini_util import (
    GeminiError,
    GeminiUtil,
    ModelRefusalError,
    get_gemini_util,
)
from src.common.utils.vertex_gemini_util import (
    VertexDailyLimitError,
    VertexGeminiUtil,
    get_vertex_gemini_util,
)

logger = logging.getLogger(__name__)

_llm_util_instance: "LLMUtil | None" = None
_llm_util_lock = threading.Lock()


class RawResponse:
    """
    Wraps a raw LLM response and tags which provider produced it so that
    extract_citations() can dispatch to the correct underlying util.
    """

    __slots__ = ("raw_response", "provider")

    def __init__(self, raw_response: Any, provider: str) -> None:
        self.raw_response = raw_response
        self.provider = provider  # "gemini" | "gemini_vertex" | "claude"


class LLMUtil:
    """
    Wraps GeminiUtil (primary), VertexGeminiUtil (secondary), and ClaudeUtil (tertiary).

    Fallback order
    --------------
    1. Gemini via Google API (GeminiUtil)
    2. Gemini via Vertex AI (VertexGeminiUtil) — triggered on any GeminiError or ModelRefusalError from step 1
    3. Claude (ClaudeUtil) — triggered on any GeminiError or VertexDailyLimitError from step 2
    """

    def __init__(
        self,
        gemini_util: GeminiUtil,
        vertex_gemini_util: VertexGeminiUtil,
        claude_util: ClaudeUtil,
    ) -> None:
        self._gemini = gemini_util
        self._vertex = vertex_gemini_util
        self._claude = claude_util

    async def get_llm_response(
        self,
        prompt: str,
        structure: Any,
        system_prompt: str = "",
        model: str = "gemini-3-flash-preview",
        **kwargs,
    ) -> Any:
        # Step 1: Google API Gemini
        try:
            # raise GeminiRateLimitError("forced for testing fallback")
            return await self._gemini.get_llm_response(
                prompt, structure, system_prompt, model, **kwargs
            )
        except (GeminiError, ModelRefusalError) as e:
            logger.warning(f"Gemini API failed — trying Vertex AI. Reason: {e}")

        # Step 2: Vertex AI Gemini
        try:
            return await self._vertex.get_llm_response(
                prompt, structure, system_prompt, model, **kwargs
            )
        except (GeminiError, ModelRefusalError, VertexDailyLimitError) as e:
            logger.warning(f"Vertex AI Gemini failed — falling back to Claude. Reason: {e}")

        # Step 3: Claude
        return await self._claude.get_llm_response(prompt, structure, system_prompt)

    async def get_llm_response_with_grounding(
        self,
        prompt: str,
        structure: Any,
        system_prompt: str = "",
        model: str = "gemini-3-flash-preview",
        **kwargs,
    ) -> tuple[Any, RawResponse]:
        """
        Returns (parsed_pydantic_model, RawResponse).
        Pass the RawResponse directly to extract_citations().
        """
        logger.info(
            f"[GROUNDING CALL] structure={structure.__name__ if hasattr(structure, '__name__') else structure}"
        )
        # Step 1: Google API Gemini
        try:
            # raise GeminiRateLimitError("forced for testing fallback")
            result, raw = await self._gemini.get_llm_response_with_grounding(
                prompt, structure, system_prompt, model, **kwargs
            )
            return result, RawResponse(raw, "gemini")
        except (GeminiError, ModelRefusalError) as e:
            logger.warning(f"Gemini API failed (grounding) — trying Vertex AI. Reason: {e}")

        # Step 2: Vertex AI Gemini
        try:
            result, raw = await self._vertex.get_llm_response_with_grounding(
                prompt, structure, system_prompt, model, **kwargs
            )
            return result, RawResponse(raw, "gemini_vertex")
        except (GeminiError, ModelRefusalError, VertexDailyLimitError) as e:
            logger.warning(
                f"Vertex AI Gemini failed (grounding) — falling back to Claude. Reason: {e}"
            )

        # Step 3: Claude
        result, raw = await self._claude.get_llm_response_with_grounding(
            prompt, structure, system_prompt
        )
        return result, RawResponse(raw, "claude")

    async def extract_citations(self, raw: RawResponse) -> list[str]:
        """
        Dispatch to the correct util's extract_citations based on which
        provider produced the raw response.
        """
        if raw.provider == "claude":
            return await self._claude.extract_citations(raw.raw_response)
        if raw.provider == "gemini_vertex":
            return await self._vertex.extract_citations(raw.raw_response)
        return await self._gemini.extract_citations(raw.raw_response)


def get_llm_util(
    gemini_api_key: str,
    anthropic_api_key: str,
    gcp_project: str = "",
    gcp_location: str = "global",
    vertex_daily_limit: int = 1000,
) -> LLMUtil:
    """Return the process-wide LLMUtil singleton."""
    global _llm_util_instance
    if _llm_util_instance is None:
        with _llm_util_lock:
            if _llm_util_instance is None:
                if not anthropic_api_key:
                    logger.warning(
                        "ANTHROPIC_API_KEY is not set — Claude fallback is unavailable. "
                        "Set it in .env to enable automatic recovery."
                    )
                if not gcp_project:
                    logger.warning(
                        "GOOGLE_CLOUD_PROJECT is not set — Vertex AI fallback is unavailable."
                    )
                gemini_util = get_gemini_util(api_key=gemini_api_key)
                vertex_util = get_vertex_gemini_util(
                    project=gcp_project,
                    location=gcp_location,
                    daily_limit=vertex_daily_limit,
                )
                claude_util = get_claude_util(api_key=anthropic_api_key)
                _llm_util_instance = LLMUtil(gemini_util, vertex_util, claude_util)
    return _llm_util_instance


def get_default_llm_util() -> LLMUtil:
    """``get_llm_util`` pre-filled from ``src.core.config``."""
    from src.core.config import (
        ANTHROPIC_API_KEY,
        GCP_LOCATION,
        GCP_PROJECT,
        GEMINI_API_KEY,
        VERTEX_DAILY_LIMIT,
    )

    return get_llm_util(
        gemini_api_key=GEMINI_API_KEY,
        anthropic_api_key=ANTHROPIC_API_KEY,
        gcp_project=GCP_PROJECT,
        gcp_location=GCP_LOCATION,
        vertex_daily_limit=VERTEX_DAILY_LIMIT,
    )
