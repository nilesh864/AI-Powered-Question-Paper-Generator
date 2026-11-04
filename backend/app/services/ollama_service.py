import json
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import settings

OLLAMA_ATTEMPT_TIMEOUT_SECONDS = 30


class OllamaUnavailable(RuntimeError):
    """Raised when local Ollama cannot produce a structured response."""


async def generate_structured_output(prompt: str, output_schema: type[BaseModel], temperature: float = 0.45) -> BaseModel:
    """Request and validate a JSON-schema-constrained response from Ollama."""
    base_url = settings.ollama_base_url.rstrip("/")
    request_body: dict[str, Any] = {
        "model": settings.ollama_model,
        "stream": False,
        "format": output_schema.model_json_schema(),
        "messages": [
            {"role": "system", "content": "Create the requested questions. Return one JSON object only, matching the provided schema exactly. Do not use Markdown or add text outside the JSON."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": temperature},
    }
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_ATTEMPT_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{base_url}/api/chat", json=request_body)
            response.raise_for_status()
        payload = response.json()
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaUnavailable("Ollama returned an empty response.")
        parsed = json.loads(content)
        return output_schema.model_validate(parsed)
    except OllamaUnavailable:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
        raise OllamaUnavailable(f"Ollama at {base_url} could not return a valid response: {error}") from error
