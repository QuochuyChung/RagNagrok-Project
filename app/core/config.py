"""
Core configuration module.

Reads all environment variables using pydantic-settings and exposes them
through a cached singleton.  Every service URL (Qdrant, Ollama, Open WebUI,
PostgreSQL) is built as a computed property so the rest of the codebase never
has to construct connection strings manually.

Usage:
    from app.core.config import get_settings
    settings = get_settings()
"""

from __future__ import annotations

from functools import lru_cache
from typing import ClassVar
from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings populated from environment variables / .env file."""

    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "ap-southeast-1"
    s3_bucket_name: str = "ragnarok-documents-dev"

    # ── Pydantic-settings configuration ──────────────────────────────────
    model_config = {
        # Automatically load a .env file sitting next to the project root
        "env_file": ".env",
        # .env values do NOT override real environment variables
        "env_file_encoding": "utf-8",
        # Allow computed (read-only) fields alongside regular fields
        "frozen": False,
        # Ignore extra fields from .env (such as UI / Vite configuration)
        "extra": "ignore",
    }

    # ── Gateway settings ─────────────────────────────────────────────────
    gateway_host: str = Field(
        default="0.0.0.0",
        description="Host address the gateway binds to.",
    )
    gateway_port: int = Field(
        default=8000,
        gt=0,
        description="Port the gateway listens on (must be > 0).",
    )
    debug_mode: bool = Field(
        default=False,
        description="Enable debug mode for verbose health checks and logging.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )
    enable_latency_profiling: bool = Field(
        default=True,
        validation_alias="ENABLE_LATENCY_PROFILING",
        description="Bật đo latency từng chặng của pipeline (LatencyTracker).",
    )
    latency_profiling_dir: str = Field(
        default="profiling_results",
        validation_alias="LATENCY_PROFILING_DIR",
        description="Thư mục chứa file JSONL kết quả đo latency.",
    )
    app_version: str = Field(
        default="0.2.0",
        description="Semantic version of this application.",
    )

    app_name: str = Field(
        default="Multi-Tenant-RAG-API-Gateway",
        description="Application name"
    )

    # ── PostgreSQL settings (Sprint 2) ────────────────────────────────────ư
    ## DEFAULT POSTGRES HOST - CHẠY LOCAL
    postgres_host: str = Field(
        default="postgres",
        description="PostgreSQL server hostname.",
    )
    postgres_port: int = Field(
        default=5432,
        gt=0,
        description="PostgreSQL server port.",
    )
    postgres_user: str = Field(
        default="ragnarok",
        description="PostgreSQL username.",
    )
    postgres_password: str = Field(
        default="ragnarok_secret",
        description="PostgreSQL password.",
    )
    postgres_db: str = Field(
        default="rag_db",
        description="PostgreSQL database name.",
    )
    postgres_pool_size: int = Field(
        default=10,
        gt=0,
        description="SQLAlchemy connection pool size.",
    )
    postgres_max_overflow: int = Field(
        default=20,
        ge=0,
        description="Maximum extra connections above pool_size.",
    )

    # ── Qdrant settings ──────────────────────────────────────────────────

    qdrant_api_key: str
    qdrant_url_override: str | None = Field(
        default=None,
        validation_alias="QDRANT_URL",
        description="Optional full Qdrant URL override.",
    )
    qdrant_host: str = Field(
        default="qdrant",
        description="Qdrant vector-DB hostname.",
    )
    qdrant_port: int = Field(
        default=6333,
        gt=0,
        description="Qdrant REST API port (must be > 0).",
    )

    """
    QDRANT_HTTP_PORT=6333
    QDRANT_GRPC_PORT=6334
    """

    qdrant_http_port: int = Field(
        default=6333,
        gt=0,
        description="Qdrant HTTP port must be 6333",
    )

    qdrant_grpc_port: int = Field(
        default=6334,
        gt=0,
        description="Qdrant GRPC port must be 6334",
    )

    # ── Ollama settings ──────────────────────────────────────────────────
    ollama_url_override: str | None = Field(
        default=None,
        validation_alias="OLLAMA_URL",
        description="Optional full Ollama URL override.",
    )
    ollama_host: str = Field(
        default="ollama",
        description="Ollama server hostname.",
    )
    ollama_port: int = Field(
        default=11434,
        gt=0,
        description="Ollama server port (must be > 0).",
    )
    llm_model: str = Field(
        default="llama3.2",
        description="LLM model name used for chat completions.",
    )
    embedding_model: str = Field(
        default="nomic-embed-text",
        description="Embedding model name used for vector encoding.",
    )
    embedding_provider: str = Field(
        default="ollama",
        description="Provider for embedding generation (e.g. 'ollama').",
    )
    rag_collection_name: str = Field(
        default="ragnarok_structure_aware",
        description="Qdrant collection used for document embeddings.",
    )
    rag_vector_size: int = Field(
        default=768,
        gt=0,
        description="Embedding vector size for the configured model.",
    )

    # === Classify Provider
    classify_provider: str = Field(
        default="ollama",
        description=""
    )

    local_model_reranker: str = Field(
        default="jinaai/jina-reranker-v2-base-multilingual",
        description="Đây là model để rerank"
    )

    rerank_provider: str = Field(
        default="cohere",
        description="Provider cho rerank: 'cohere'"
    )

    cohere_trial_key: str = Field(
        default="",
        description="API Key cho Cohere Rerank"
    )

    cohere_rerank_model: str = Field(
        default="rerank-v3.5",
        description="Model Cohere dùng cho Rerank"
    )

    # ── Document service settings ────────────────────────────────────────
    document_allowed_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".txt", ".md", ".docx"],
        validation_alias="DOCUMENT_ALLOWED_EXTENSIONS",
        description="Allowed file extensions for document ingestion.",
    )
    document_storage_root: str = Field(
        default="storage/documents",
        validation_alias="DOCUMENT_STORAGE_ROOT",
        description="Root folder for persisted document files.",
    )

    # ── Ingestion settings ───────────────────────────────────────────────
    chunk_size: int = Field(
        default=1024,
        gt=0,
        description="Number of tokens per document chunk.",
    )
    chunk_overlap: int = Field(
        default=128,
        ge=0,
        description="Token overlap between consecutive chunks.",
    )
    max_chunk_chars: int = Field(
        default=2048,
        gt=0,
        description="Maximum number of characters for a text chunk before recursive splitting.",
    )
    chunk_overlap_chars: int = Field(
        default=256,
        ge=0,
        description="Character overlap between recursive text chunks.",
    )
    txt_chunk_words: int = Field(
        default=500,
        gt=0,
        description="Word count target for plain-text chunking.",
    )
    txt_overlap_ratio: float = Field(
        default=0.15,
        ge=0.0,
        lt=1.0,
        description="Overlap ratio for plain-text chunking.",
    )
    max_upload_size_mb: int = Field(
        default=10,
        gt=0,
        description="Maximum upload file size in megabytes.",
    )
    max_chunks_per_doc: int = Field(
        default=500,
        gt=0,
        description="Maximum number of chunks a single document may produce.",
    )

    # ── Chat / conversation settings ─────────────────────────────────────
    max_conversation_turns: int = Field(
        default=20,
        gt=0,
        description="Max turns stored per conversation.",
    )
    conversation_ttl_seconds: int = Field(
        default=3600,
        gt=0,
        description="Conversation time-to-live (seconds).",
    )

    # ── Rate limiting ────────────────────────────────────────────────────
    rate_limit_requests_per_minute: int = Field(
        default=60,
        gt=0,
        description="Per-tenant requests allowed per minute.",
    )

    # ── Encryption settings (Sprint 3) ───────────────────────────────────────
    system_kek: str = Field(
        default="0000000000000000000000000000000000000000000000000000000000000000",
        description="Key Encryption Key (AES-256 in hex format) for wrapping tenant DEKs.",
    )

    # ── Timeout settings (seconds) ───────────────────────────────────────
    qdrant_timeout: int = Field(
        default=10,
        gt=0,
        description="Timeout for Qdrant operations (seconds).",
    )
    ollama_timeout: int = Field(
        default=120,
        gt=0,
        description="Timeout for Ollama LLM calls (seconds).",
    )
    db_connect_timeout: int = Field(
        default=10,
        gt=0,
        description="Timeout for PostgreSQL connection attempts (seconds).",
    )

    gemini_timeout: int = Field(
        default=60,
        gt=0,
        description="Timeout cho request tới Gemini API (seconds).",
    )

    s3_connect_timeout: int = Field(
        default=5,
        gt=0,
        description="Timeout kết nối TCP tới S3 (seconds).",
    )
    s3_read_timeout: int = Field(
        default=30,
        gt=0,
        description="Timeout chờ data từ S3 sau khi đã kết nối (seconds).",
    )
    s3_max_retries: int = Field(
        default=1,
        ge=1,
        description="Số lần thử của botocore cho 1 call S3 (1 = không tự retry ở tầng botocore).",
    )
    kms_connect_timeout: int = Field(
        default=5,
        gt=0,
        description="Timeout kết nối TCP tới KMS (seconds).",
    )
    kms_read_timeout: int = Field(
        default=10,
        gt=0,
        description="Timeout chờ data từ KMS (seconds).",
    )
    kms_max_retries: int = Field(
        default=1,
        ge=1,
        description="Số lần thử của botocore cho 1 call KMS (1 = không tự retry ở tầng botocore).",
    )
    embedding_timeout: int = Field(
        default=120,
        gt=0,
        description="Timeout cho request embedding tới Ollama (seconds).",
    )

    # ==== GEMINI SETTINGS
    gemini_api_key: str = Field(
        default="",
        description="API Key lấy trong .env"
    )

    gemini_api_model: str = Field(
        default="gemini-3.5-flash",
        description="API Model chọn bên trong .env"
    )

    # JWT Settings
    jwt_secret_key: str = Field(
        default="change-secret-key-in-production-secret-32bytes",
        description="Secret key for verify JWT (HS256). Change it in production"
    )

    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm for verifying JWT (HS256).",
    )

    jwt_expired_minutes: int = Field(
        default=60,
        gt=0,
        description="Timeout for JWT expiration (seconds).",
    )

    # ── SMTP / Email settings ────────────────────────────────────────────
    smtp_host: str = Field(
        default="localhost",
        description="SMTP server hostname.",
    )
    smtp_port: int = Field(
        default=587,
        gt=0,
        description="SMTP server port (587 for STARTTLS, 465 for SSL, 25 for plain).",
    )
    smtp_username: str | None = Field(
        default=None,
        description="SMTP authentication username (optional).",
    )
    smtp_password: str | None = Field(
        default=None,
        description="SMTP authentication password (optional).",
    )
    smtp_use_tls: bool = Field(
        default=True,
        description="Use STARTTLS for SMTP connection.",
    )
    smtp_from_email: str = Field(
        default="noreply@ragnarok.local",
        description="Sender email address for system emails.",
    )
    smtp_from_name: str = Field(
        default="Ragnarok Platform",
        description="Sender display name for system emails.",
    )

    # ── Invitation & Token settings ──────────────────────────────────────
    invite_token_expire_hours: int = Field(
        default=120,
        gt=0,
        description="Default invite token lifetime in hours (2 hours).",
    )
    password_reset_token_expire_minutes: int = Field(
        default=30,
        gt=0,
        description="Password reset token lifetime in minutes (30 minutes).",
    )
    frontend_base_url: str = Field(
        default="http://localhost:5173",
        description="Frontend base URL used to build invitation links in emails.",
    )
    cors_allowed_origins: str = Field(
        default="http://localhost:5173",
        validation_alias="CORS_ALLOWED_ORIGINS",
        description=(
            "Comma-separated list of origins allowed by CORS. "
            "Wildcard '*' is REJECTED when allow_credentials=True."
        ),
    )

    # ── Validators ───────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        """Ensure log_level is one of the standard Python logging levels."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"log_level must be one of {allowed}, got '{v}'"
            )
        return upper

    @field_validator(
        "qdrant_host",
        "ollama_host",
        "postgres_host",
        mode="before",
    )
    @classmethod
    def _must_not_be_empty(cls, v: str) -> str:
        """Critical host fields must not be empty strings."""
        if not v or not v.strip():
            raise ValueError("Host value must not be empty.")
        return v.strip()

    # ── Hardening: reject default secret values in production ────────────
    # Pydantic chạy @field_validator SAU khi đã load giá trị. Vì vậy ta check
    # bằng chính giá trị đó — nếu user để default ở .env mà bật DEBUG_MODE=false
    # thì app fail-fast ngay lúc start, không âm thầm chạy với KEK = 0.
    # ClassVar để Pydantic không coi đây là model field.
    DEFAULT_SYSTEM_KEK: ClassVar[str] = "0" * 64
    DEFAULT_JWT_SECRET: ClassVar[str] = "change-secret-key-in-production"
    DEFAULT_POSTGRES_PASSWORD: ClassVar[str] = "ragnarok_secret"

    # @field_validator("system_kek", mode="before")
    # @classmethod
    # def _validate_system_kek(cls, v: str) -> str:
    #     """KHÔNG bao giờ cho phép KEK = 64 byte 0 ở bất kỳ môi trường nào.
    #     1 byte đã biết (0x00) → kẻ tấn công brute-force / unwrap mọi tenant DEK
    #     dễ dàng. Nếu thấy default, raise RuntimeError ngay lúc start."""
    #     if v is None or v == cls.DEFAULT_SYSTEM_KEK:
    #         raise RuntimeError(
    #             "CRITICAL: system_kek is set to the default value (64 zero hex chars). "
    #             "Generate a real 32-byte KEK (e.g. `openssl rand -hex 32`) and set "
    #             "SYSTEM_KEK in .env. Default KEK = 0 means every tenant DEK is "
    #             "wrapped with a known key — DEK leak = plaintext leak."
    #         )
    #     if not isinstance(v, str) or len(v) != 64:
    #         raise RuntimeError(
    #             "CRITICAL: system_kek must be exactly 64 hex characters (32 bytes). "
    #             f"Got length={len(v) if isinstance(v, str) else 'n/a'}."
    #         )
    #     try:
    #         int(v, 16)
    #     except ValueError:
    #         raise RuntimeError("CRITICAL: system_kek must be a valid hex string.")
    #     return v

    # @field_validator("jwt_secret_key", mode="before")
    # @classmethod
    # def _validate_jwt_secret(cls, v: str) -> str:
    #     if v == cls.DEFAULT_JWT_SECRET:
    #         raise RuntimeError(
    #             "CRITICAL: jwt_secret_key is the literal default placeholder "
    #             "'change-secret-key-in-production'. Anyone reading this repo can "
    #             "forge JWTs. Set a random secret in .env "
    #             "(e.g. `openssl rand -base64 48`)."
    #         )
    #     if not v or len(v) < 32:
    #         raise RuntimeError(
    #             "CRITICAL: jwt_secret_key must be at least 32 chars. "
    #             "OWASP recommends 256 bits of entropy for HS256."
    #         )
    #     return v

    # @field_validator("postgres_password", mode="before")
    # @classmethod
    # def _validate_postgres_password(cls, v: str) -> str:
    #     if v == cls.DEFAULT_POSTGRES_PASSWORD:
    #         raise RuntimeError(
    #             "CRITICAL: postgres_password is the default literal "
    #             "'ragnarok_secret'. This is the DB superuser password — leak it "
    #             "and attacker owns every tenant schema. Set a real password in .env."
    #         )
    #     if not v or len(v) < 8:
    #         raise RuntimeError(
    #             "CRITICAL: postgres_password must be at least 8 chars."
    #         )
    #     return v

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def _validate_gemini_api_key(cls, v: str) -> str:
        # gemini_api_key cho phép rỗng khi dùng local LLM (Ollama), nhưng
        # nếu LLM provider được config là gemini mà key rỗng -> fail-fast.
        if v == "" or v is None:
            return v
        if not isinstance(v, str) or len(v) < 20:
            raise RuntimeError(
                "CRITICAL: gemini_api_key looks malformed (too short). "
                "Google API keys are typically 39 chars."
            )
        return v

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _validate_cors_origins(cls, v):
        """Parse env CORS_ALLOWED_ORIGINS=url1,url2,... thành comma-separated string.
        Wildcard '*' bị reject vì không tương thích với allow_credentials=True
        (CORS spec: response với Access-Control-Allow-Origin: * + Credentials
        bị browser từ chối, nhưng một số proxy/tool cũ vẫn pass qua -> CSRF risk).
        Trả về string để tránh pydantic-settings auto-decode JSON list phức tạp;
        main.py sẽ split thành list khi add middleware.
        """
        if v is None or v == "":
            return "http://localhost:5173"
        s = str(v).strip()
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if not parts:
            return "http://localhost:5173"
        if "*" in parts:
            raise RuntimeError(
                "CRITICAL: cors_allowed_origins must NOT contain '*' because "
                "FastAPI's CORSMiddleware rejects allow_credentials=True with "
                "wildcard origins (CORS spec). List explicit origins instead."
            )
        for origin in parts:
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise RuntimeError(
                    f"CRITICAL: cors_allowed_origins entry '{origin}' is not a "
                    "valid URL. Must start with http:// or https://."
                )
        return ",".join(parts)

    # ── Computed connection URLs ─────────────────────────────────────────

    @computed_field  # type: ignore[misc]
    @property
    def database_url(self) -> str:
        """Async PostgreSQL connection string for SQLAlchemy (Sprint 2)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def database_url_sync(self) -> str:
        """Sync PostgreSQL connection string (for Alembic migrations)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def qdrant_url(self) -> str:
        """Qdrant REST endpoint URL."""
        if self.qdrant_url_override:
            return self.qdrant_url_override
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @computed_field  # type: ignore[misc]
    @property
    def ollama_url(self) -> str:
        """Ollama API base URL."""
        if self.ollama_url_override:
            return self.ollama_url_override
        return f"http://{self.ollama_host}:{self.ollama_port}"

    


# ── Singleton accessor ───────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Using ``@lru_cache`` ensures the .env file is read only once and the
    same ``Settings`` object is reused across the application lifetime.
    Call ``get_settings.cache_clear()`` in tests to force a reload.
    """
    return Settings()
