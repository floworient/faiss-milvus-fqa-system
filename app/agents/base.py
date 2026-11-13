from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.chat import AgentEvent, AgentRequest, AgentResponse


class AgentStrategy(Protocol):
    name: str

    def run(self, request: AgentRequest) -> AgentResponse: ...

    def stream(self, request: AgentRequest) -> AsyncIterator[AgentEvent]: ...

