"""
Prompt templates.

Keep prompts here (not inline in tasks/services) so they are easy to find,
diff and reuse. Pair each prompt with a pydantic response schema in
``src/<module>/schemas/responses/llm_*.py`` and pass both to ``LLMUtil``.

Convention: ``<ACTION>_SYSTEM_PROMPT`` + ``<ACTION>_USER_PROMPT`` with
``str.format`` placeholders.
"""

SUMMARIZE_DOCUMENT_SYSTEM_PROMPT = (
    "You are a precise analyst. Read the document and return ONLY a JSON object "
    "matching the requested schema. Use 'Not Found' for missing values. Be concise."
)

SUMMARIZE_DOCUMENT_USER_PROMPT = """Summarize the following document.

Return:
- title: a short descriptive title
- summary: at most 120 words
- keywords: 3-8 keywords
- language: ISO 639-1 code of the document language

Document:
\"\"\"
{document_text}
\"\"\"
"""
