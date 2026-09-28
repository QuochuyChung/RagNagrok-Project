from app.clients.base_client import BaseClient
from app.clients.gemini_client import GeminiClient
from app.clients.ollama_client import OllamaClient
from app.core.config import get_settings
from app.schemas.chat import ChatRequest


class ClientFactory:
    def __init__(self, ollama_client: OllamaClient, gemini_client: GeminiClient):
            self._client: dict[str, BaseClient] = {
                "ollama": ollama_client,
                "gemini": gemini_client,
            }
            self._settings = get_settings()

    def build_llm_client(self, request: ChatRequest) -> BaseClient:
        llm_client = self._client.get(request.llm_provider, self._client["ollama"])
        return llm_client

    def build_classify_client(self) -> BaseClient:
        provider = self._settings.classify_provider
        llm_client = self._client.get(provider, self._client["ollama"])
        return llm_client
