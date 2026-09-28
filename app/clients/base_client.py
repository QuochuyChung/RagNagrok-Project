from abc import ABC, abstractmethod
from typing import AsyncIterator, Any

from app.schemas.chat import LLMResult


class BaseClient(ABC):
    @abstractmethod
    async def generate(self, *, prompt: str, system: str | None = None, model: str | None = None) -> LLMResult: ...

    @abstractmethod
    async def generate_stream(self, *, prompt: str, system: str | None = None, model: str | None = None) -> AsyncIterator[dict[str, Any]]:
        yield {}

    @abstractmethod
    async def classify(self, *, prompt: str ,system: str | None = None, schema: dict ,model: str | None = None) -> str: ...




