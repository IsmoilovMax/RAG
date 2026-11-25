"""Ollama client for local, CPU-only LLM inference."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.exceptions import LLMUnavailableError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(slots=True)
class GenerationOptions:
    model: str
    temperature: float = 0.1
    num_ctx: int = 4096
    num_thread: int | None = None
    keep_alive: str = "30m"


class LLMClient(Protocol):
    async def stream_chat(
        self, messages: list[ChatMessage], options: GenerationOptions
    ) -> AsyncIterator[str]: ...

    async def list_models(self) -> list[dict[str, Any]]: ...

    async def health(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...


class OllamaClient:
    def __init__(self, base_url: str, *, timeout_s: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_s, connect=5.0),
        )

    @staticmethod
    def _payload(messages: list[ChatMessage], options: GenerationOptions) -> dict[str, Any]:
        model_options: dict[str, Any] = {
            "temperature": options.temperature,
            "num_ctx": options.num_ctx,
        }
        if options.num_thread:
            model_options["num_thread"] = options.num_thread
        return {
            "model": options.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "keep_alive": options.keep_alive,
            "options": model_options,
        }

    async def stream_chat(
        self, messages: list[ChatMessage], options: GenerationOptions
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, options)
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise LLMUnavailableError(_error_message(response.status_code, body, options.model))
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed Ollama chunk", extra={"line": line[:200]})
                        continue
                    if chunk.get("error"):
                        raise LLMUnavailableError(f"Ollama error: {chunk['error']}")
                    token = (chunk.get("message") or {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"Cannot reach Ollama at {self.base_url}. Is the Ollama server running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("The language model timed out while generating") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama request failed: {exc}") from exc

    async def list_models(self) -> list[dict[str, Any]]:
        try:
            response = await self._client.get("/api/tags", timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Cannot list Ollama models: {exc}") from exc
        models = response.json().get("models", [])
        return [
            {
                "name": m.get("name"),
                "size_bytes": m.get("size"),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "quantization": (m.get("details") or {}).get("quantization_level"),
                "family": (m.get("details") or {}).get("family"),
                "modified_at": m.get("modified_at"),
            }
            for m in models
        ]

    async def health(self) -> dict[str, Any]:
        response = await self._client.get("/api/version", timeout=5.0)
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()


def _error_message(status: int, body: str, model: str) -> str:
    try:
        detail = json.loads(body).get("error", body)
    except json.JSONDecodeError:
        detail = body
    if status == 404 or "not found" in str(detail).lower():
        return f"Model '{model}' is not installed in Ollama. Run: ollama pull {model}"
    return f"Ollama returned HTTP {status}: {detail}"
