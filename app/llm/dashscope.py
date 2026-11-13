from collections.abc import AsyncIterator
from http import HTTPStatus

import dashscope

from app.llm.ports import (
    LLMInvalidRequest,
    LLMRateLimited,
    LLMTimeout,
    LLMUnavailable,
)


class DashScopeLLMAdapter:
    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def complete(self, prompt: str) -> str:
        try:
            response = dashscope.Generation.call(
                api_key=self.api_key,
                model=self.model,
                prompt=prompt,
                result_format="message",
                timeout=self.timeout_seconds,
            )
        except TimeoutError as error:
            raise LLMTimeout("DashScope request timed out") from error
        except Exception as error:
            raise LLMUnavailable("DashScope request failed") from error
        self._raise_for_response(response)
        return str(response.output.choices[0].message.content)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        try:
            responses = dashscope.Generation.call(
                api_key=self.api_key,
                model=self.model,
                prompt=prompt,
                result_format="message",
                stream=True,
                incremental_output=True,
                timeout=self.timeout_seconds,
            )
            for response in responses:
                self._raise_for_response(response)
                content = response.output.choices[0].message.content
                if content:
                    yield str(content)
        except TimeoutError as error:
            raise LLMTimeout("DashScope stream timed out") from error
        except (LLMInvalidRequest, LLMRateLimited, LLMUnavailable):
            raise
        except Exception as error:
            raise LLMUnavailable("DashScope stream failed") from error

    @staticmethod
    def _raise_for_response(response: object) -> None:
        status_code = getattr(response, "status_code", None)
        if status_code == HTTPStatus.OK:
            return
        if status_code == HTTPStatus.TOO_MANY_REQUESTS:
            raise LLMRateLimited("DashScope rate limit reached")
        if status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.UNPROCESSABLE_ENTITY):
            raise LLMInvalidRequest("DashScope rejected the request")
        raise LLMUnavailable("DashScope service unavailable")
