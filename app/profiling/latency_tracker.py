"""
Latency tracker.

Đo thời gian từng chặng (stage) của một pipeline dài rồi xuất ra:
    1. Structured log (1 dòng JSON tổng kết khi pipeline kết thúc)
    2. File JSONL append-only trong ``profiling_results/`` để phân tích offline

Thiết kế:
    - Mỗi request tạo 1 instance riêng -> an toàn khi chạy song song, không
      dùng biến global/module-level nào để giữ số đo.
    - Dùng ``perf_counter`` (monotonic) thay vì ``time()`` để không bị lệch
      khi đồng hồ hệ thống bị chỉnh.
    - Mọi lỗi bên trong tracker đều bị nuốt và chỉ log ở mức debug — đo đạc
      KHÔNG BAO GIỜ được phép làm hỏng luồng nghiệp vụ thật.
    - Bật/tắt qua ``settings.enable_latency_profiling`` để production có thể
      tắt hoàn toàn chi phí ghi file.

Cách dùng::

    tracker = LatencyTracker("chat", conversation_id=str(conv_id))

    async with tracker.astage("intent_classify"):
        ...

    with tracker.stage("rerank"):
        ...

    tracker.finish()          # log + ghi file

Stage lồng nhau được hỗ trợ: tên stage con sẽ có dạng ``cha.con``.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Ghi file từ nhiều coroutine/thread -> nối tiếp bằng lock để dòng JSONL
# không bị xen kẽ vào nhau.
_FILE_LOCK = threading.Lock()


@dataclass
class StageTiming:
    """Kết quả đo của 1 stage."""

    name: str
    duration_ms: float
    started_at_ms: float
    failed: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "stage": self.name,
            "duration_ms": round(self.duration_ms, 3),
            "offset_ms": round(self.started_at_ms, 3),
        }
        if self.failed:
            data["failed"] = True
            data["error"] = self.error
        if self.metadata:
            data["metadata"] = self.metadata
        return data


class LatencyTracker:
    """Thu thập thời gian từng chặng của 1 pipeline."""

    def __init__(self, flow: str, **context: Any) -> None:
        """
        Args:
            flow: Tên pipeline — "tenant_provisioning" | "document_ingest" | "chat".
            **context: Thông tin định danh kèm theo (tenant_id, doc_id...).
        """
        self.flow = flow
        self.context = {k: v for k, v in context.items() if v is not None}
        self.stages: list[StageTiming] = []
        self._t0 = perf_counter()
        self._stack: list[str] = []
        self._finished = False

        try:
            self._enabled = bool(getattr(get_settings(), "enable_latency_profiling", True))
        except Exception:  # pragma: no cover - settings luôn load được ở runtime
            self._enabled = False

    # ── Ghi nhận stage ──────────────────────────────────────────────────

    @contextmanager
    def stage(self, name: str, **metadata: Any):
        """Đo 1 đoạn code đồng bộ."""
        if not self._enabled:
            yield
            return

        full_name = self._push(name)
        start = perf_counter()
        offset = (start - self._t0) * 1000
        try:
            yield
        except BaseException as exc:
            self._record(full_name, start, offset, metadata, exc)
            self._pop()
            raise
        else:
            self._record(full_name, start, offset, metadata, None)
            self._pop()

    @asynccontextmanager
    async def astage(self, name: str, **metadata: Any):
        """Đo 1 đoạn code bất đồng bộ (dùng ``async with``)."""
        if not self._enabled:
            yield
            return

        full_name = self._push(name)
        start = perf_counter()
        offset = (start - self._t0) * 1000
        try:
            yield
        except BaseException as exc:
            self._record(full_name, start, offset, metadata, exc)
            self._pop()
            raise
        else:
            self._record(full_name, start, offset, metadata, None)
            self._pop()

    def mark(self, name: str, duration_ms: float, **metadata: Any) -> None:
        """Ghi thẳng 1 số đo đã có sẵn (vd latency do service khác trả về)."""
        if not self._enabled:
            return
        self.stages.append(
            StageTiming(
                name=name,
                duration_ms=duration_ms,
                started_at_ms=(perf_counter() - self._t0) * 1000 - duration_ms,
                metadata=metadata,
            )
        )

    def add_context(self, **context: Any) -> None:
        """Bổ sung context sau khi tracker đã được tạo (vd doc_id sinh ra giữa chừng)."""
        self.context.update({k: v for k, v in context.items() if v is not None})

    # ── Kết thúc ────────────────────────────────────────────────────────

    @property
    def total_ms(self) -> float:
        return (perf_counter() - self._t0) * 1000

    def snapshot(self) -> dict[str, Any]:
        """Bản tổng kết dạng dict (dùng được cho log/response/test)."""
        total = self.total_ms
        measured = sum(s.duration_ms for s in self.stages if "." not in s.name)
        return {
            "flow": self.flow,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_ms": round(total, 3),
            # Phần thời gian KHÔNG nằm trong stage nào — hở nhiều nghĩa là còn
            # chặng tốn thời gian chưa được đo.
            "unattributed_ms": round(max(total - measured, 0.0), 3),
            "slowest_stage": self._slowest_stage_name(),
            **self.context,
            "stages": [s.to_dict() for s in self.stages],
        }

    def finish(self, **extra_context: Any) -> dict[str, Any]:
        """Chốt số đo: log 1 dòng tổng kết + append vào file JSONL."""
        if self._finished or not self._enabled:
            return self.snapshot()

        self._finished = True
        self.add_context(**extra_context)
        data = self.snapshot()

        try:
            logger.info("latency_profile", **_flatten_for_log(data))
        except Exception:
            logger.debug("latency_profile_log_failed", exc_info=True)

        self._append_to_file(data)
        return data

    # ── Nội bộ ──────────────────────────────────────────────────────────

    def _push(self, name: str) -> str:
        full_name = f"{self._stack[-1]}.{name}" if self._stack else name
        self._stack.append(full_name)
        return full_name

    def _pop(self) -> None:
        if self._stack:
            self._stack.pop()

    def _record(
        self,
        name: str,
        start: float,
        offset: float,
        metadata: dict[str, Any],
        exc: BaseException | None,
    ) -> None:
        self.stages.append(
            StageTiming(
                name=name,
                duration_ms=(perf_counter() - start) * 1000,
                started_at_ms=offset,
                failed=exc is not None,
                error=f"{type(exc).__name__}: {exc}" if exc is not None else None,
                metadata=metadata,
            )
        )

    def _slowest_stage_name(self) -> str | None:
        top_level = [s for s in self.stages if "." not in s.name]
        if not top_level:
            return None
        return max(top_level, key=lambda s: s.duration_ms).name

    def _append_to_file(self, data: dict[str, Any]) -> None:
        try:
            settings = get_settings()
            out_dir = Path(getattr(settings, "latency_profiling_dir", "profiling_results"))
            out_dir.mkdir(parents=True, exist_ok=True)
            # 1 file / flow / ngày -> dễ so sánh giữa các ngày, không phình vô hạn.
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            path = out_dir / f"latency_{self.flow}_{day}.jsonl"
            line = json.dumps(data, ensure_ascii=False, default=str)
            with _FILE_LOCK:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(line + os.linesep)
        except Exception:
            # Không bao giờ để việc ghi file profiling làm hỏng request thật.
            logger.debug("latency_profile_write_failed", exc_info=True)


def _flatten_for_log(data: dict[str, Any]) -> dict[str, Any]:
    """Đổi snapshot thành kwargs phẳng cho structured logger."""
    flat = {k: v for k, v in data.items() if k != "stages"}
    for stage in data.get("stages", []):
        flat[f"ms_{stage['stage'].replace('.', '_')}"] = stage["duration_ms"]
    return flat
