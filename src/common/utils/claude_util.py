"""
Claude (Anthropic SDK) structured-output client. Last provider in the chain.

JSON is requested via the system prompt and repaired with ``json_repair``
before validating against the pydantic schema. Grounding uses the built-in
web search tool.
"""

import asyncio
import logging
import re
import threading
from typing import Any

import anthropic
import json_repair
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

CLAUDE_TIMEOUT_SECONDS = 90
CLAUDE_CONCURRENCY_LIMIT = 30
CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 8192

_claude_instance: "ClaudeUtil | None" = None
_claude_lock = threading.Lock()


def get_claude_util(api_key: str) -> "ClaudeUtil":
    """Return the process-wide ClaudeUtil singleton."""
    global _claude_instance
    if _claude_instance is None:
        with _claude_lock:
            if _claude_instance is None:
                _claude_instance = ClaudeUtil(api_key=api_key)
    return _claude_instance


class ClaudeError(Exception):
    pass


class ClaudeModelRefusalError(Exception):
    pass


class ClaudeUtil:
    """
    ClaudeUtil - async Claude inference via the Anthropic SDK.
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self._semaphore = asyncio.Semaphore(CLAUDE_CONCURRENCY_LIMIT)
        logger.info(
            f"Initialized async Claude client (per process concurrency_limit={CLAUDE_CONCURRENCY_LIMIT})"
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((ClaudeError, ClaudeModelRefusalError)),
        reraise=True,
    )
    async def get_llm_response(
        self,
        prompt: str,
        structure: Any,
        system_prompt: str = "",
        model: str = CLAUDE_DEFAULT_MODEL,
        **kwargs,  # absorbs Gemini-specific params (thinking=, etc.)
    ) -> Any:
        """
        Generate a structured response from Claude without web search.
        Uses messages.parse() with output_format for native schema enforcement —
        equivalent to Gemini's response_schema. No JSON parsing needed.
        """
        logger.info(f"Sending prompt to Claude model '{model}'")
        try:
            async with self._semaphore:
                response = await asyncio.wait_for(
                    self.client.messages.parse(
                        model=model,
                        max_tokens=CLAUDE_MAX_TOKENS,
                        system=system_prompt,
                        messages=[{"role": "user", "content": prompt}],
                        output_format=structure,
                    ),
                    timeout=CLAUDE_TIMEOUT_SECONDS,
                )

            if response.stop_reason == "refusal":
                logger.error("Claude refused to answer")
                raise ClaudeModelRefusalError("Claude refused to answer")

            if response.parsed_output is None:
                logger.error("Claude returned empty structured output")
                raise ClaudeModelRefusalError("Claude returned empty structured output")

            logger.info("Successfully parsed Claude response")
            return response.parsed_output

        except TimeoutError:
            logger.error(f"Claude API call timed out after {CLAUDE_TIMEOUT_SECONDS}s")
            raise ClaudeError(f"Claude API timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        except anthropic.RateLimitError as e:
            logger.warning(f"Claude rate limit: {e}")
            raise ClaudeError(f"Claude rate limit: {e}")
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise ClaudeError(f"Claude API error: {e}")
        except (ClaudeModelRefusalError, ClaudeError):
            raise
        except Exception as e:
            logger.error(f"Claude error: {e}")
            raise ClaudeError(f"Claude error: {e}")

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((ClaudeError, ClaudeModelRefusalError)),
        reraise=True,
    )
    async def get_llm_response_with_grounding(
        self,
        prompt: str,
        structure: Any,
        system_prompt: str = "",
        model: str = CLAUDE_DEFAULT_MODEL,
        **kwargs,
    ) -> tuple[Any, Any]:
        """
        Generate a structured response from Claude with web search grounding.

        Returns (parsed_pydantic_model, raw_response).
        The raw_response is the full Anthropic Message object; pass it to
        extract_citations() to retrieve source URLs.
        """
        logger.info(f"Sending prompt to Claude model '{model}' with web search grounding")
        try:
            full_system = self._build_system_prompt(system_prompt)

            async with self._semaphore:
                response = await asyncio.wait_for(
                    self.client.messages.create(
                        model=model,
                        max_tokens=CLAUDE_MAX_TOKENS,
                        system=full_system,
                        messages=[{"role": "user", "content": prompt}],
                        tools=[
                            {
                                "type": "web_search_20250305",
                                "name": "web_search",
                                "max_uses": 5,
                            }
                        ],
                    ),
                    timeout=CLAUDE_TIMEOUT_SECONDS,
                )

            # The last text block is Claude's final answer after all searches
            text = self._extract_final_text(response)
            if not text:
                logger.error("Claude returned empty response with grounding")
                raise ClaudeModelRefusalError("Claude returned empty response")

            extracted = self._extract_json(text)
            parsed = structure.model_validate(json_repair.loads(extracted))
            logger.info("Successfully parsed Claude response with grounding")
            return parsed, response

        except TimeoutError:
            logger.error(
                f"Claude API call with grounding timed out after {CLAUDE_TIMEOUT_SECONDS}s"
            )
            raise ClaudeError(f"Claude API timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        except anthropic.RateLimitError as e:
            logger.warning(f"Claude rate limit: {e}")
            raise ClaudeError(f"Claude rate limit: {e}")
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise ClaudeError(f"Claude API error: {e}")
        except (ClaudeModelRefusalError, ClaudeError):
            raise
        except Exception as e:
            logger.error(f"Claude error with grounding: {e}")
            raise ClaudeError(f"Claude error: {e}")

    async def extract_citations(self, response: Any) -> list[str]:
        """
        Extract citation URLs from a web-search response.

        Claude embeds citations in two places:
          • block.citations on text blocks (inline citations)
          • block.content on web_search_tool_result blocks (raw search hits)
        """
        try:
            if not response or not hasattr(response, "content"):
                return []

            urls: list[str] = []
            seen: set[str] = set()

            for block in response.content:
                # Inline citations on text blocks
                if hasattr(block, "citations") and block.citations:
                    for citation in block.citations:
                        url = getattr(citation, "url", None)
                        if url and url not in seen:
                            urls.append(url)
                            seen.add(url)

                # Raw search result URLs inside web_search_tool_result blocks
                if (
                    getattr(block, "type", None) == "web_search_tool_result"
                    and hasattr(block, "content")
                    and block.content
                ):
                    for result in block.content:
                        url = getattr(result, "url", None)
                        if url and url not in seen:
                            urls.append(url)
                            seen.add(url)

            logger.info(f"Extracted {len(urls)} unique citations from Claude response")
            return urls
        except Exception as e:
            logger.error(f"Error extracting Claude citations: {e}")
            return []

    @staticmethod
    def _build_system_prompt(system_prompt: str) -> str:
        json_rule = (
            "After performing all necessary web searches, your FINAL response "
            "MUST be a raw JSON object only — no markdown, no code fences, "
            "no explanation before or after the JSON. "
            "CRITICAL: every field value must match its declared type exactly — "
            "string fields must be plain text strings, never nested objects or arrays."
        )
        return f"{system_prompt}\n\n{json_rule}" if system_prompt else json_rule

    @staticmethod
    def _extract_final_text(response: Any) -> str:
        """Return text from the last text block (Claude's post-search answer)."""
        last_text = ""
        for block in response.content:
            if hasattr(block, "text") and block.text:
                last_text = block.text
        return last_text

    @staticmethod
    def _extract_json(text: str) -> str:
        """
        Best-effort extraction of a JSON string from text.
        Handles: raw JSON, markdown ```json blocks, JSON embedded in prose.
        """
        text = text.strip()
        if text.startswith("{") or text.startswith("["):
            return text

        # Fenced code block (```json ... ``` or ``` ... ```)
        match = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n```", text)
        if match:
            return match.group(1).strip()

        # Any JSON object or array embedded in prose
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if match:
            return match.group(1)

        return text
