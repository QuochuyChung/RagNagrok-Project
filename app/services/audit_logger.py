import asyncio
import logging

from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text

logger = logging.getLogger(__name__)

class AuditLoggerService:
    def __init__(self, batch_size: int = 1, flush_interval: float = 0.5):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._worker_task: asyncio.Task | None = None
        # Biến giữ reference tới sessionmaker của app
        self.session_maker: async_sessionmaker[AsyncSession] | None = None

    def init_app(self, session_maker: async_sessionmaker[AsyncSession]):
        """Truyền session_maker từ app.state.db_sessionmaker vào worker"""
        self.session_maker = session_maker

    async def log_event(self, log_data: Dict[str, Any]):
        """Đẩy log vào Queue (Non-blocking)"""
        await self.queue.put(log_data)

    async def start_worker(self):
        """Khởi chạy background worker"""
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Logger BG Worker đã khởi động.")

    async def stop_worker(self):
        """Dừng worker và flush nốt log dư thừa"""
        if self._worker_task:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)
        await self._flush_remaining()
        logger.info("Logger Worker dừng thành công.")

    async def _worker_loop(self):
        batch: List[Dict[str, Any]] = []
        while True:
            try:
                try:
                    log_item = await asyncio.wait_for(self.queue.get(), timeout=self.flush_interval)
                    batch.append(log_item)
                    self.queue.task_done()
                except asyncio.TimeoutError:
                    pass

                if len(batch) >= self.batch_size or (batch and self.queue.empty()):
                    await self._insert_batch(batch)
                    batch.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Lỗi ở audit log worker loop: {str(e)}")

    async def _insert_batch(self, batch: List[Dict[str, Any]]):
        if not batch or not self.session_maker:
            return

        # Lưu ý: Vì audit_logs nằm ở public schema nên ta ghi trực tiếp qua session_maker thông thường,
        # không cần dùng schema_translate_map (scope tenant)!
        query = text("""
            INSERT INTO public.audit_logs 
            (tenant_id, user_id, request_id, endpoint, method, status_code, latency_ms)
            VALUES (:tenant_id, :user_id, :request_id, :endpoint, :method, :status_code, :latency_ms)
        """)
        
        try:
            async with self.session_maker() as session:
                async with session.begin():
                    await session.execute(query, batch)
            logger.debug(f"Đã thêm thành công {len(batch)} audit logs vào public.audit_logs.")
        except Exception as e:
            logger.error(f"Thêm audit log batch thất bại: {str(e)}")

    async def _flush_remaining(self):
        batch = []
        while not self.queue.empty():
            batch.append(self.queue.get_nowait())
            self.queue.task_done()
        if batch:
            await self._insert_batch(batch)

audit_logger = AuditLoggerService()