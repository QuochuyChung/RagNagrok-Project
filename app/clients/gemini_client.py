from app.clients.base_client import BaseClient
from app.core.config import get_settings
from google import genai
from google.genai import types
from app.schemas.chat import LLMResult

from app.core.logging import get_logger

logger = get_logger(__name__)


class GeminiClient(BaseClient):
    async def classify(self, *, prompt: str, system: str | None = None, schema: dict, model: str | None = None) -> str:
        model = model or self._settings.gemini_api_model
        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json", response_schema=schema)
            )

            if not response:
                raise RuntimeError("[gemini_client - gemini] Gemini Response Error")

            return response.text

        except Exception as exc:
            logger.error("[gemini_client - gemini] Content trả về rỗng: %s", exc)
            logger.error("gemini_response_error", model=model, error=str(exc))
            raise RuntimeError("Gemini Classify Error") from exc



    def __init__(self, client: genai.Client):
        self._settings = get_settings()
        self._client = client

    async def generate(self, *, prompt: str, system: str | None = None, model: str | None = None) -> LLMResult:
        model_name = model or get_settings().gemini_api_model

        """
            Gói system prompt vào bên trong object config để gửi qua bên gemini
        """
        config = types.GenerateContentConfig(system_instruction=system)

        """
            Gửi qua Gemini
        """
        try:
            resp = await self._client.aio.models.generate_content(
                model=model_name,
                config=config,
                contents=prompt
            )

            # Lấy câu trả lời ra
            content = resp.text

            if not content:
                logger.error("[gemini_client - gemini] Content Gemini trả về rỗng")
                logger.error("gemini_response_empty", model=model_name)
                raise RuntimeError("Gemini trả response rỗng")

            # object usage dùng để tính toán chi phí sau 1 prompt
            usage = resp.usage_metadata

            # số token đầu vào của câu prompt
            prompt_tokens = usage.prompt_token_count or 0

            # số token model sinh ra
            output_tokens = usage.candidates_token_count or 0

            logger.info("gemini_response_usage", prompt_tokens=prompt_tokens, output_tokens=output_tokens)

            logger.info("[gemini_client - gemini] Gemini đã sinh câu trả lời thành công")

            return LLMResult(
                content=content,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
            )

        except Exception as exc:
            logger.error("[gemini_client - gemini] Gemini sinh câu trả lời bị lỗi: %s", exc)
            logger.error("gemini_response_error", model=model_name, error=str(exc))
            raise RuntimeError(f"Gemini Response Error: {exc}") from exc

    async def generate_stream(self, *, prompt: str, system: str | None = None, model: str | None = None):
        model = model or self._settings.gemini_api_model

        """
            Gói system prompt lại vào bên trong object config
        """

        config = types.GenerateContentConfig(system_instruction=system)

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=model,
                config=config,
                contents=prompt
            )

            output_tokens: int = 0
            async for chunk in stream:
                content = chunk.text
                if content:
                    yield {"content": content, "token_count": None}
                if chunk.usage_metadata and chunk.usage_metadata.prompt_token_count and chunk.usage_metadata.candidates_token_count:
                    output_tokens = chunk.usage_metadata.candidates_token_count
            yield {"content": None, "token_count": output_tokens}


        except Exception as exc:
            logger.error("[gemini_client - gemini] Gemini generate câu trả lời lỗi: %s", exc)
            logger.error("gemini_response_error", model=model, error=str(exc))
            raise RuntimeError(f"Gemini Response Error: {exc}") from exc
