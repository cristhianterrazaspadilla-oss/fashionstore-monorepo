from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import declarative_base
from backend.app.core.config import settings

db_url = settings.async_database_url
if "?" in db_url and ("ssl" in db_url.lower() or "neon.tech" in db_url.lower()):
    base_part = db_url.split("?")[0]
    db_url = f"{base_part}?ssl=require"

engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
    poolclass=NullPool,
    # Evita depender de la zona del servidor (local, Render o Neon). PostgreSQL
    # sigue almacenando timestamptz como instante absoluto, pero now() y las
    # consultas SQL de fechas se interpretan/presentan en la zona del negocio.
    connect_args={"server_settings": {"timezone": settings.BUSINESS_TIMEZONE}},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
