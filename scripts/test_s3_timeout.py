"""
Test verify timeout: set S3_READ_TIMEOUT cực thấp để giả lập mạng chậm,
đọc 1 file thật trong S3, verify raise đúng RuntimeError chứa "timeout"
thay vì rơi vào silent fallback (đúng hành vi mới đã sửa).
"""
import os
# PHẢI set trước khi import bất kỳ module nào gọi get_settings() — vì
# get_settings() dùng @lru_cache, chỉ đọc env 1 lần đầu tiên.
os.environ["S3_READ_TIMEOUT"] = "1"

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


async def main():
    settings = get_settings()
    print(f"S3 read_timeout đang dùng: {settings.s3_read_timeout}s (đã override để test)")

    engine = create_async_engine(settings.database_url)

    async with engine.connect() as conn:
        tenants = (await conn.execute(
            text("SELECT tenant_name FROM public.tenants WHERE is_deleted = FALSE LIMIT 5")
        )).scalars().all()

    if not tenants:
        print("❌ Không tìm thấy tenant nào — chưa có dữ liệu để test.")
        await engine.dispose()
        return

    storage_key = None
    used_tenant = None
    for tname in tenants:
        schema = f'SCHEMA_{tname.upper()}'
        async with engine.connect() as conn:
            await conn.execute(text(f'SET search_path TO "{schema}"'))
            row = (await conn.execute(
                text("SELECT storage_key FROM documents "
                     "WHERE storage_key IS NOT NULL AND storage_key != '' LIMIT 1")
            )).first()
        if row:
            storage_key = row[0]
            used_tenant = tname
            break

    await engine.dispose()

    if not storage_key:
        print("❌ Không có document nào có storage_key — upload thử 1 file trước rồi chạy lại.")
        return

    print(f"Dùng storage_key: {storage_key} (tenant: {used_tenant})")

    from app.utils.s3_storage import read_file_from_s3_by_key

    try:
        await read_file_from_s3_by_key(storage_key)
        print("⚠️  Không timeout — file có thể quá nhỏ hoặc mạng quá nhanh cho 1s. "
              "Thử hạ S3_READ_TIMEOUT xuống thấp hơn nữa hoặc bỏ qua nếu chỉ cần xác nhận luồng thường vẫn chạy.")
    except RuntimeError as e:
        if "timeout" in str(e).lower():
            print(f"✅ Timeout raised đúng: {e}")
        else:
            print(f"❌ RuntimeError nhưng KHÔNG phải timeout: {e}")
    except Exception as e:
        print(f"❌ Raised nhầm loại lỗi ({type(e).__name__}): {e}")


asyncio.run(main())