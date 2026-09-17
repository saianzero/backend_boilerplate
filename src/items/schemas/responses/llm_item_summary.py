"""
Structured output schema for the LLM summarisation task.

Passed as ``structure=`` to ``LLMUtil.get_llm_response``; the provider is
forced to return JSON matching this model and the result is validated.
"""

from pydantic import BaseModel


class LLMItemSummary(BaseModel):
    title: str
    summary: str
    keywords: list[str] = []
    language: str = "en"
