import json
import re
import time

from openai import OpenAI

from app.config import settings

_client = OpenAI(base_url=settings.nim_base_url, api_key=settings.nvidia_nim_api_key)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_JSON_BLOCK_RE = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


def _retry(fn, attempts: int = 3, base_delay: float = 2.0):
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # openai raises various subclasses of APIError
            last_exc = exc
            if i < attempts - 1:
                time.sleep(base_delay * (2**i))
    raise last_exc


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1024) -> str:
    def _call():
        response = _client.chat.completions.create(
            model=settings.nim_chat_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120,
        )
        return response.choices[0].message.content or ""

    return _retry(_call)


def chat_json(
    messages: list[dict], temperature: float = 0.2, max_tokens: int = 2048, max_attempts: int = 3
) -> dict | list:
    """Chat call where the model is instructed to return JSON only. Parses defensively
    (strips code fences, falls back to extracting the first {...}/[...] block). If the
    response is truncated mid-JSON (model ran out of its token budget on a large
    input), retries with a doubled token budget rather than failing outright."""
    last_exc: json.JSONDecodeError | None = None
    tokens = max_tokens
    for attempt in range(max_attempts):
        raw = chat(messages, temperature=temperature, max_tokens=tokens)
        cleaned = _JSON_FENCE_RE.sub("", raw.strip()).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            match = _JSON_BLOCK_RE.search(cleaned)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            last_exc = exc
            tokens = min(tokens * 2, 8192)
    raise last_exc


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    def _call():
        response = _client.embeddings.create(
            model=settings.nim_embed_model,
            input=texts,
            extra_body={"input_type": "query"},
            timeout=60,
        )
        return [item.embedding for item in response.data]

    return _retry(_call)
