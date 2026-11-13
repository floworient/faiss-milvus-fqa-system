from collections.abc import Sequence

from app.agents.base import AgentStrategy
from app.core.errors import AppError


class AgentRegistry:
    def __init__(self, strategies: Sequence[AgentStrategy]) -> None:
        self._strategies: dict[str, AgentStrategy] = {}
        for strategy in strategies:
            if strategy.name in self._strategies:
                raise ValueError(f"duplicate agent strategy: {strategy.name}")
            self._strategies[strategy.name] = strategy

    def get(self, name: str) -> AgentStrategy:
        strategy = self._strategies.get(name)
        if strategy is None:
            raise AppError(
                "agent_strategy_not_found", "Agent strategy was not found.", 404
            )
        return strategy

    @property
    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

