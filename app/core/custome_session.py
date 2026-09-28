"""
 Decorator @asynccontextmanager đảm bảo là cú pháp async with tên_hàm sẽ được hợp lệ
 Nhưng sẽ không đảm bảo là kết nối sẽ được đóng
 => Phải đảm bảo đóng thủ công
 => Hàm này viết như vậy là để đóng gói session lại để tái sử dụng ở nhiều nơi mà ngoài
 scope của request mà vẫn muốn xài session theo schemas.
 VD: Background Job
"""
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession


@asynccontextmanager
async def get_db_with_tenant_scope_session(engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession], tenant_name: str):
    schema_name = f"SCHEMA_{tenant_name.upper()}"
    async with engine.connect() as connection:
        """
        + execution_options: dùng để gắn tùy chọn cho connection
        -> nó trả về connection mới và gán vào biến connection cũ
        -> None: schema_name: là 1 dict dùng để trong _table_args schema xài là gì
        VD: trong __table_args__ = {"schema": "shared"}, nếu trong schema_translate_map ghi là 
        "shared": "SCHEMA_ACME_shared" thì schema sẽ là SCHEMA_ACME_shared
        """
        connection = await connection.execution_options(schema_translate_map={None: schema_name})
        # bind connection vào trong session đó
        async with session_maker(bind=connection) as session: # as đã đảm bảo kết nối được đóng
            yield session
