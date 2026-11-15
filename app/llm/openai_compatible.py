from __future__ import annotations

import json
from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any

import httpx

from app.llm.ports import (
    LLMError,
    LLMInvalidRequest,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)


class OpenAICompatibleLLMAdapter:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str) -> str:
        try:
            with httpx.Client(
                base_url=f"{self.base_url}/",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ) as client:
                response = client.post("chat/completions", json=self._payload(prompt))
            self._raise_for_response(response)
            return self._completion_content(response.json())
        except LLMError:
            raise
        except httpx.TimeoutException as error:
            raise LLMTimeout("OpenAI-compatible request timed out") from error
        except httpx.RequestError as error:
            raise LLMUnavailable("OpenAI-compatible request failed") from error
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise LLMUnavailable("OpenAI-compatible response was malformed") from error

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(
                base_url=f"{self.base_url}/",
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ) as client:
                async with client.stream(
                    "POST",
                    "chat/completions",
                    json=self._payload(prompt, stream=True),
                ) as response:
                    self._raise_for_response(response)
                    finished = False
                    async for line in response.aiter_lines():
                        if finished or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            finished = True
                            continue
                        if not payload:
                            continue
                        content = self._stream_content(json.loads(payload))
                        if content:
                            yield content
        except LLMError:
            raise
        except httpx.TimeoutException as error:
            raise LLMTimeout("OpenAI-compatible stream timed out") from error
        except httpx.RequestError as error:
            raise LLMUnavailable("OpenAI-compatible stream failed") from error
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise LLMUnavailable("OpenAI-compatible stream was malformed") from error

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, *, stream: bool = False) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }

    @staticmethod
    def _completion_content(payload: object) -> str:
        if not isinstance(payload, dict):
            raise TypeError("completion payload must be an object")
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content:
            raise ValueError("completion content is missing")
        return content

    @staticmethod
    def _stream_content(payload: object) -> str:
        if not isinstance(payload, dict):
            raise TypeError("stream payload must be an object")
        content = payload["choices"][0].get("delta", {}).get("content", "")
        if content is None:
            return ""
        if not isinstance(content, str):
            raise TypeError("stream content must be text")
        return content

    @staticmethod
    def _raise_for_response(response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code == HTTPStatus.OK:
            return
        if status_code == HTTPStatus.TOO_MANY_REQUESTS:
            raise LLMRateLimited("OpenAI-compatible rate limit reached")
        if status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNPROCESSABLE_ENTITY):
            raise LLMInvalidRequest("OpenAI-compatible request was rejected")
        raise LLMUnavailable("OpenAI-compatible service unavailable")
