"""
Ollama LLM client.

Bọc SDK `ollama` (AsyncClient) cho phần sinh text non-streaming.
Không biết gì về tenant / RAG domain — chỉ lo gọi model và trả text về.

TODO: phần embedding hiện vẫn nằm ở ChunkerService.embed_text (gọi HTTP thẳng
      bằng `requests`, blocking) — sẽ chuyển sang AsyncClient.embed() sau.
"""

from __future__ import annotations

from huggingface_hub.cli.models import models_ls
from ollama import AsyncClient, RequestError, ResponseError

from app.clients.base_client import BaseClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.chat import LLMResult

logger = get_logger(__name__)


class OllamaClient(BaseClient):
    """
    Thin wrapper quanh ollama.AsyncClient.

    AsyncClient được tạo 1 lần trong lifespan (main.py) rồi truyền vào đây
    -> tái dùng connection pool, không tạo client mới mỗi request.
    """
    def __init__(self, client: AsyncClient) -> None:
        self._settings = get_settings()
        self._client = client

    async def generate(
        self,
        *,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
    ) -> LLMResult:
        """
        Gọi LLM sinh câu trả lời (non-streaming).

        Dùng /api/chat (qua SDK) thay vì /api/generate vì nó nhận mảng messages
        có role — sau này thêm lịch sử hội thoại chỉ cần append vào mảng.

        Raises:
            RuntimeError: khi Ollama báo lỗi, không kết nối được, hoặc trả rỗng.
        """
        model_name = model or self._settings.llm_model

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = await self._client.chat(
                model=model_name,
                messages=messages,
                stream=False
            )
            """
                resp trả về cục object ChatResponse 
            """

            content = resp.message.content

            if not content:
                logger.error("ollama_empty_response", model=model_name)
                raise RuntimeError("Ollama trả response rỗng")

            result = LLMResult(
                content=content,
                prompt_tokens=resp.prompt_eval_count or 0,
                output_tokens=resp.eval_count or 0,
            )
            logger.info(
                "ollama_generate_done",
                model=model_name,
                prompt_tokens=result.prompt_tokens,
                output_tokens=result.output_tokens,
            )

            return result
        except ResponseError as exc:
            # Ollama trả lỗi có nội dung: model chưa pull, request sai format...
            logger.exception("ollama_response_error", model=model_name, status=exc.status_code)
            raise RuntimeError(f"Ollama báo lỗi: {exc.error}") from exc
        except RequestError as exc:
            # Không kết nối được / timeout
            logger.exception("ollama_request_failed", model=model_name)
            raise RuntimeError(
                f"Không gọi được Ollama tại {self._settings.ollama_url}. "
                "Kiểm tra service ollama đang chạy và model đã pull chưa."
            ) from exc


    async def generate_stream(self, *, prompt: str, system: str | None = None, model: str | None = None):
        model_name = model or self._settings.llm_model

        messages: list[dict[str, str]] = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        try:
            stream = await self._client.chat(
                model=model_name,
                messages=messages,
                stream=True
            )

            """
                stream trả về 1 băng chuyền AsyncIterator[ChatResponse]
                chunk là 1 object Chat Response
                vòng for sẽ đi hỏi Ollama liên tục rồi lấy dữ liệu thông qua stream
                Thay vì trả về câu trả lời , sẽ for từng cục ra
            """

            logger.info(f"Bắt đầu trả từng chunk Chat Response ra từ stream")

            async for chunk in stream:
                content = chunk.message.content
                if content:
                    yield {"content": content, "token_count": None}
                if chunk.done:
                    yield {"content": None, "token_count": chunk.eval_count or 0}

        except ResponseError as exc:
            logger.exception("ollama_response_error", model=model_name, status=exc.status_code)
            raise RuntimeError(f"Ollama báo lỗi: {exc.error}") from exc
        except RequestError as exc:
            logger.exception("ollama_request_failed", model=model_name)
            raise RuntimeError(f"Không gọi được Ollama tại: {self._settings.ollama_url}"
                               f". Kiểm tra lại service của Ollama đã pull chưa") from exc

    async def classify(self, *, prompt: str, system: str | None = None, schema: dict,
                           model: str | None = None) -> str:
        """
        schema: format llm trả về bắt buộc phải truyền schema vào
        """

        """
            Lấy model ra
        """
        model = model or self._settings.llm_model

        """
            Soạn message
        """
        messages = [
            {"role" : "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        response = await self._client.chat(
            model=model,
            messages=messages,
            format=schema,
            stream=False
        )

        content = response.message.content

        if not content:
            raise RuntimeError("ollama trả về rỗng")

        return content





