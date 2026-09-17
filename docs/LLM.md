# LLM usage

## Providers and fallback

`src/common/utils/llm_util.py`

| Order | Provider | Class | Needs |
|---|---|---|---|
| 1 | Gemini (AI Studio API) | `GeminiUtil` | `GEMINI_API_KEY` |
| 2 | Gemini via Vertex AI | `VertexGeminiUtil` | `GOOGLE_CLOUD_PROJECT` + ADC / `GOOGLE_APPLICATION_CREDENTIALS`, Redis (daily cap `VERTEX_DAILY_LIMIT`) |
| 3 | Claude | `ClaudeUtil` | `ANTHROPIC_API_KEY` |

Fallback triggers: timeouts, 429/5xx, empty/refused responses, Vertex daily cap.
Each provider retries twice with exponential backoff (tenacity) before handing over.
All clients are process-wide singletons with a concurrency semaphore (30).

## Structured call

```python
from pydantic import BaseModel
from src.common.utils.llm_util import get_default_llm_util
from src.common.prompts import SUMMARIZE_DOCUMENT_SYSTEM_PROMPT, SUMMARIZE_DOCUMENT_USER_PROMPT

class Summary(BaseModel):
    title: str
    summary: str
    keywords: list[str] = []

llm = get_default_llm_util()
result: Summary = await llm.get_llm_response(
    prompt=SUMMARIZE_DOCUMENT_USER_PROMPT.format(document_text=text),
    structure=Summary,
    system_prompt=SUMMARIZE_DOCUMENT_SYSTEM_PROMPT,
    model="gemini-3-flash-preview",   # DEFAULT_LLM_MODEL
    thinking="low",                   # Gemini 3 thinking level; ignored by Claude
)
```

## Grounded call (web search) with citations

```python
result, raw = await llm.get_llm_response_with_grounding(prompt, Summary, system_prompt)
urls: list[str] = await llm.extract_citations(raw)   # resolved source URLs
```

## Conventions

- Prompts live in `src/common/prompts.py` as `<ACTION>_SYSTEM_PROMPT` / `<ACTION>_USER_PROMPT`.
- Response schemas live in `src/<module>/schemas/responses/llm_<action>.py`.
- Truncate inputs (`text[:100_000]`) before sending; log token-heavy calls at INFO.
- Call LLMs from tasks, not request handlers, unless latency is acceptable.
- Reference implementation: `src/items/tasks.py::_process_item`.
