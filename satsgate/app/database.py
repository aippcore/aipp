import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://aipp:Herm3sAIPP2026!@localhost:5432/aipp")

# Fallback for old SQLite path just in case
if DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(DATABASE_URL, echo=False)
else:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=10
    )

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with async_session_maker() as session:
        yield session
